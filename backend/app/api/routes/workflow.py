"""
工作流 API 端点

POST /api/v1/workflow/run          — 启动工作流（后台异步执行）
GET  /api/v1/workflow/status/{id}  — 查询运行状态
"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.workflow.graph import get_graph
from app.workflow.streaming import run_workflow_async

logger = logging.getLogger(__name__)

router = APIRouter()

# 存储正在运行的任务引用（防止 GC）
_running_tasks: dict[str, asyncio.Task] = {}


def _load_workflow_topics() -> tuple[list[str], list[dict]]:
    """加载工作流所需的主题信息：扁平关键词 + 结构化主题"""
    from app.api.routes.topics import get_enabled_topic_keywords, get_enabled_topics_detail

    keywords = get_enabled_topic_keywords()
    detail = get_enabled_topics_detail()
    return keywords, detail


@router.post("/workflow/run")
async def start_workflow(
    topics: list[str] = Query(default=[], description="监控主题关键词列表"),
):
    """
    启动 LangGraph 工作流（后台异步执行）

    工作流在后台执行，立即返回 run_id。
    可通过 GET /workflow/status/{run_id} 查询进度，
    或通过 WS /ws/v1/workflow/{run_id} 接收实时推送。

    如果未指定 topics 参数，自动从 configs/topics.json 加载用户配置的主题。
    """
    import uuid

    run_id = uuid.uuid4().hex[:12]

    # 自动加载结构化主题配置
    config_keywords, topics_detail = _load_workflow_topics()

    # 如果 API 调用未传 topics，从配置中提取
    if not topics and topics_detail:
        topics = config_keywords
    elif topics and topics_detail:
        # 防御：过滤掉可能混入的 topic name（前端可能误传）
        topic_names = {t["name"] for t in topics_detail}
        filtered = [t for t in topics if t not in topic_names]
        if len(filtered) != len(topics):
            logger.warning("[api] 已过滤掉 topic name: %s → %s", topics, filtered)
        topics = filtered

    # 启动后台任务
    task = asyncio.create_task(
        run_workflow_async(run_id=run_id, topics=topics, topics_detail=topics_detail),
        name=f"workflow-{run_id}",
    )
    _running_tasks[run_id] = task

    # 任务完成后自动清理
    task.add_done_callback(lambda _: _running_tasks.pop(run_id, None))

    logger.info("[api] 工作流已启动: run_id=%s, topics=%s", run_id, topics)

    return {
        "status": "ok",
        "message": "工作流已启动",
        "run_id": run_id,
        "topics": topics,
        "topics_detail": [t.get("name") for t in topics_detail],
    }


@router.post("/workflow/{run_id}/stop")
async def stop_workflow(run_id: str):
    """
    停止正在运行的工作流

    使用双重保障:
    1. 协作式取消 — asyncio.Event 标志位，节点间快速响应
    2. Task.cancel — 在 await 点注入 CancelledError 兜底
    """
    from app.workflow.streaming import cancel_workflow

    # 方式 1: 协作式取消（快速响应，节点完成后立即停止）
    found = cancel_workflow(run_id)

    # 方式 2: Task.cancel（兜底 — 在 await 点中断当前节点）
    task = _running_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
        logger.info("[api] 工作流 Task.cancel 已发送: run_id=%s", run_id)

    if not found and not task:
        raise HTTPException(status_code=404, detail="工作流未在运行或已结束")

    if task and task.done():
        raise HTTPException(status_code=409, detail="工作流已结束")

    logger.info("[api] 工作流停止信号已发送: run_id=%s", run_id)

    return {
        "status": "ok",
        "message": "停止信号已发送，工作流将在当前节点完成后终止",
        "run_id": run_id,
    }


@router.get("/workflow/status/{run_id}")
async def get_workflow_status(run_id: str):
    """
    查询工作流运行状态

    返回当前状态快照：进度、各阶段统计、错误信息。
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": run_id}}

    try:
        state = graph.get_state(config)

        if state is None or state.values is None:
            return {
                "run_id": run_id,
                "status": "not_found",
                "message": "未找到该运行记录（可能已过期或 run_id 错误）",
            }

        values = state.values

        # 推断当前进度
        nodes_completed = _infer_progress(values)
        is_running = run_id in _running_tasks

        # 确定工作流状态：优先信任 state 中的 workflow_status
        # （export_node 完成后 state 已标记 completed，但 task 可能尚未清理）
        state_status = values.get("workflow_status", "")

        if state_status == "cancelled":
            workflow_status = "cancelled"
        elif state_status == "completed":
            # state 明确标记完成 → 即使 task 引用未清理也视为完成
            workflow_status = "completed"
        elif state_status == "failed" or (values.get("errors") and not is_running):
            workflow_status = "failed"
        elif is_running:
            workflow_status = "running"
        else:
            workflow_status = "completed"

        return {
            "run_id": run_id,
            "status": workflow_status,
            "nodes_completed": nodes_completed,
            "stats": {
                "raw_articles": len(values.get("raw_articles") or []),
                "clean_articles": len(values.get("clean_articles") or []),
                "unique_articles": len(values.get("unique_articles") or []),
                "topic_clusters": len(values.get("topic_clusters") or []),
                "research_reports": len(values.get("research_reports") or []),
                "review_results": len(values.get("review_results") or []),
                "review_passed": values.get("review_passed", False),
                "retry_count": values.get("retry_count", 0),
                "export_paths": values.get("export_paths") or [],
            },
            "errors": values.get("errors", []),
            "dedup_stats": values.get("dedup_stats", {}),
            "collection_errors": values.get("collection_errors", []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询状态失败: {e}")


def _infer_progress(state_values: dict) -> list[str]:
    """根据状态字段推断已完成的节点列表（None 表示节点尚未执行）"""
    completed = []

    if state_values.get("raw_articles") or state_values.get("collection_errors"):
        completed.append("collect")
    else:
        return completed

    if state_values.get("clean_articles"):
        completed.append("preprocess")
    else:
        return completed

    if state_values.get("unique_articles") or state_values.get("dedup_stats", {}).get("total_in", 0) > 0:
        completed.append("dedup")
    else:
        return completed

    if state_values.get("topic_clusters") is not None:
        completed.append("cluster")
    else:
        return completed

    if state_values.get("research_reports") is not None:
        completed.append("research")
    else:
        return completed

    if state_values.get("review_results") is not None:
        completed.append("review")
    else:
        return completed

    if state_values.get("daily_brief") is not None:
        completed.append("compose")
    else:
        return completed

    if state_values.get("export_paths"):
        completed.append("export")

    return completed

"""
工作流事件总线 + 后台流式执行

- WorkflowEventBus: asyncio.Queue Pub/Sub
- run_workflow_async: 后台执行 graph.astream()，每个节点完成后推送事件
- 协作式取消: cancel_workflow() 设置 asyncio.Event，各节点检查后快速退出
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone

from app.workflow.state import PlatformState
from app.workflow.graph import get_graph
from app.workflow.event_bus import event_bus

logger = logging.getLogger(__name__)

# 协作式取消事件注册表 — run_id → asyncio.Event
_cancel_events: dict[str, asyncio.Event] = {}


def cancel_workflow(run_id: str) -> bool:
    """设置取消事件，返回是否成功找到对应工作流"""
    event = _cancel_events.get(run_id)
    if event is None:
        return False
    event.set()
    logger.info("[workflow] 取消事件已设置: %s", run_id)
    return True


def is_cancelled(run_id: str) -> bool:
    """检查工作流是否已被取消"""
    event = _cancel_events.get(run_id)
    return event is not None and event.is_set()


def _cleanup_cancel_event(run_id: str):
    """清理取消事件"""
    _cancel_events.pop(run_id, None)


async def run_workflow_async(
    run_id: str | None = None,
    topics: list[str] | None = None,
    topics_detail: list[dict] | None = None,
) -> str:
    """
    后台执行 LangGraph 工作流，通过 event_bus 实时推送进度

    Args:
        run_id: 运行 ID（不传则自动生成）
        topics: 监控主题关键词（扁平列表，用于采集检索）
        topics_detail: 结构化主题配置（含名称和关键词，用于日报对齐归类）

    Returns:
        run_id
    """
    if run_id is None:
        run_id = uuid.uuid4().hex[:12]

    if topics is None:
        topics = []
    if topics_detail is None:
        topics_detail = []

    # 注册取消事件
    cancel_event = asyncio.Event()
    _cancel_events[run_id] = cancel_event

    graph = get_graph()
    config = {"configurable": {"thread_id": run_id}}

    # 初始状态
    today = datetime.now(timezone.utc).date().isoformat()
    initial_state: PlatformState = {
        "raw_articles": [],
        "collection_errors": [],
        "clean_articles": [],
        "unique_articles": [],
        "dedup_stats": {},
        "topic_clusters": None,
        "research_reports": None,
        "review_results": None,
        "review_passed": False,
        "retry_count": 0,
        "daily_brief": None,
        "export_paths": [],
        "errors": [],
        "target_date": today,
        "topics": topics,
        "topics_detail": topics_detail,
        "workflow_status": "running",
        "run_id": run_id,
    }

    logger.info("[workflow] 启动工作流 %s, 主题=%s", run_id, topics)

    try:
        # 流式执行 — 每个节点完成后 yield {node_name: output}
        async for event in graph.astream(initial_state, config):
            node_name = list(event.keys())[0]

            # 跳过内部元数据节点
            if node_name in ("__start__", "__end__"):
                continue

            # 每个节点完成后检查取消标志
            if cancel_event.is_set():
                logger.info("[workflow] ⏹️ 节点 %s 完成后检测到取消信号: %s", node_name, run_id)
                break

            logger.info("[workflow] ✓ 节点完成: %s", node_name)

            await event_bus.publish(run_id, {
                "type": "node_complete",
                "node": node_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # 获取最终状态
        final_state = graph.get_state(config)
        final_values = final_state.values if final_state else {}

        if cancel_event.is_set():
            final_values["workflow_status"] = "cancelled"
            logger.info("[workflow] ⏹️ 工作流已取消: %s", run_id)
            await event_bus.publish(run_id, {
                "type": "workflow_cancelled",
                "run_id": run_id,
                "status": "cancelled",
                "state_summary": _summarize_state(final_values),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        else:
            final_values["workflow_status"] = "completed"
            logger.info("[workflow] ✅ 工作流完成: %s", run_id)
            await event_bus.publish(run_id, {
                "type": "workflow_complete",
                "run_id": run_id,
                "status": "completed",
                "state_summary": _summarize_state(final_values),
                "collection_errors": final_values.get("collection_errors", []),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # 保存状态快照供 API 路由读取
        _save_state_snapshot(final_values)

    except asyncio.CancelledError:
        logger.info("[workflow] ⏹️ 工作流 Task 被取消: %s", run_id)
        try:
            final_state = graph.get_state(config)
            final_values = final_state.values if final_state else {}
            final_values["workflow_status"] = "cancelled"
            _save_state_snapshot(final_values)
        except Exception:
            pass

        await event_bus.publish(run_id, {
            "type": "workflow_error",
            "run_id": run_id,
            "error": "用户手动停止",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    except Exception as e:
        logger.error("[workflow] ❌ 工作流异常: %s — %s", run_id, e)

        await event_bus.publish(run_id, {
            "type": "workflow_error",
            "run_id": run_id,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    finally:
        _cleanup_cancel_event(run_id)

    return run_id


def _summarize_state(state: dict) -> dict:
    """提取状态摘要（避免返回大量文章内容）

    注意：topic_clusters / research_reports / review_results 初始值为 None，
    使用 or [] 而非 .get(key, []) 正确处理 None 值。
    因为 dict.get(key, default) 在 key 存在但值为 None 时返回 None 而非 default。
    """
    return {
        "raw_articles": len(state.get("raw_articles", [])),
        "clean_articles": len(state.get("clean_articles", [])),
        "unique_articles": len(state.get("unique_articles", [])),
        "topic_clusters": len(state.get("topic_clusters") or []),
        "research_reports": len(state.get("research_reports") or []),
        "review_results": len(state.get("review_results") or []),
        "review_passed": state.get("review_passed", False),
        "retry_count": state.get("retry_count", 0),
        "export_paths": state.get("export_paths") or [],
        "errors": len(state.get("errors", [])),
        "dedup_stats": state.get("dedup_stats") or {},
        "workflow_status": state.get("workflow_status", ""),
    }


def _save_state_snapshot(state: dict) -> None:
    """保存工作流最终状态快照，同时保留按 run_id 独立存档"""
    exports_dir = Path(__file__).parent.parent.parent / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    run_id = state.get("run_id", "unknown")

    # 只保存关键字段，不保存大量全文内容
    snapshot = {
        "run_id": run_id,
        "target_date": state.get("target_date", ""),
        "topics": state.get("topics", []),
        "topics_detail": state.get("topics_detail", []),
        "workflow_status": state.get("workflow_status", ""),
        "topic_clusters": state.get("topic_clusters", []),
        "research_reports": state.get("research_reports", []),
        "review_results": state.get("review_results", []),
        "review_passed": state.get("review_passed", False),
        "retry_count": state.get("retry_count", 0),
        "daily_brief": state.get("daily_brief"),
        "export_paths": state.get("export_paths", []),
        "dedup_stats": state.get("dedup_stats", {}),
        "collection_errors": state.get("collection_errors", []),
        "unique_articles": [
            {
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source_name": a.get("source_name", ""),
                "published_at": a.get("published_at"),
                "cluster_id": _find_article_cluster(a.get("id", ""), state.get("topic_clusters", [])),
            }
            for a in state.get("unique_articles", [])
        ],
        "errors": state.get("errors", []),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # 1) 覆盖 latest_state.json（向后兼容，各 API 读最新数据）
        state_file = exports_dir / "latest_state.json"
        state_file.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[workflow] 状态快照已保存: %s", state_file)

        # 2) 按 run_id 独立存档（历史追溯）
        states_dir = exports_dir / "states"
        states_dir.mkdir(parents=True, exist_ok=True)
        run_state_file = states_dir / f"{run_id}.json"
        run_state_file.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[workflow] 运行存档已保存: %s", run_state_file)
    except Exception as e:
        logger.warning("[workflow] 保存状态快照失败: %s", e)


def _find_article_cluster(article_id: str, clusters: list[dict]) -> int | None:
    """查找文章所属的簇 ID"""
    for c in clusters:
        for a in c.get("articles", []):
            if a.get("id") == article_id:
                return c.get("cluster_id")
    return None

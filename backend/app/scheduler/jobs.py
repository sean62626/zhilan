"""
定时任务定义

所有定时任务函数在此定义，由 APScheduler 调度执行。
任务函数必须:
  - 是 async 函数
  - 捕获所有异常，不向调度器传播
  - 通过 history_tracker 记录执行结果
"""

import logging

from app.scheduler.history import get_history_tracker

logger = logging.getLogger(__name__)


def _load_enabled_topic_keywords() -> list[str]:
    """从 topics.json 加载所有启用主题的关键词（去重合并）"""
    from app.api.routes.topics import get_enabled_topic_keywords
    return get_enabled_topic_keywords()


def _load_enabled_topics_detail() -> list[dict]:
    """从 topics.json 加载所有启用主题的完整结构（含名称和关键词）"""
    from app.api.routes.topics import get_enabled_topics_detail
    return get_enabled_topics_detail()


async def collect_all_sources_job():
    """
    定时采集任务 — 从所有已配置数据源采集新闻

    1. 从 configs/topics.json 读取启用的主题关键词
    2. 调用 CollectorAgent.run_collection() 执行采集
    3. 单个源失败不影响其他源（CollectorAgent 内部已隔离）
    4. 结果由 CollectorAgent 自动写入 ES
    """
    tracker = get_history_tracker()
    run = tracker.start("collect_all_sources")

    try:
        from app.agents.collector import run_collection

        keywords = _load_enabled_topic_keywords()
        logger.info("[jobs] 开始定时采集，关键词数=%d", len(keywords))

        result = await run_collection(topics=keywords if keywords else None)

        # 构建摘要
        summary = {
            "total_sources": result.total_sources,
            "successful_sources": result.successful_sources,
            "total_articles": len(result.articles),
            "source_stats": result.source_stats,
        }

        tracker.finish(run, success=True, result=summary)
        logger.info(
            "[jobs] ✅ 定时采集完成: %d/%d 源成功, %d 篇文章",
            result.successful_sources, result.total_sources, len(result.articles),
        )

    except Exception as e:
        logger.error("[jobs] ❌ 定时采集失败: %s", e, exc_info=True)
        tracker.finish(run, success=False, error=str(e))


async def generate_daily_brief_job():
    """
    定时日报生成任务 — 触发完整 LangGraph 工作流

    1. 从 configs/topics.json 读取启用的主题关键词
    2. 调用 run_workflow_async() 执行 8 节点工作流
    3. 等待工作流完成（最长 30 分钟）
    """
    tracker = get_history_tracker()
    run = tracker.start("generate_daily_brief")

    try:
        from app.workflow.streaming import run_workflow_async

        keywords = _load_enabled_topic_keywords()
        topics_detail = _load_enabled_topics_detail()
        logger.info("[jobs] 开始日报生成，关键词数=%d, 结构化主题数=%d", len(keywords), len(topics_detail))

        # run_workflow_async 内部创建 asyncio.Task, 持续 astream 直到完成
        wf_run_id = await run_workflow_async(topics=keywords, topics_detail=topics_detail)

        tracker.finish(run, success=True, result={"workflow_run_id": wf_run_id})
        logger.info("[jobs] ✅ 日报生成完成: workflow_run_id=%s", wf_run_id)

    except Exception as e:
        logger.error("[jobs] ❌ 日报生成失败: %s", e, exc_info=True)
        tracker.finish(run, success=False, error=str(e))


async def health_check_job():
    """
    定时健康检查任务 — 验证核心依赖连通性

    每 5 分钟运行一次，检查 Redis/ES/MySQL 连通性。
    """
    tracker = get_history_tracker()
    run = tracker.start("health_check")

    try:
        from app.cache.cache_manager import get_redis
        from opensearchpy import OpenSearch

        checks = {}

        # Redis
        try:
            r = get_redis()
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = str(e)

        # OpenSearch
        try:
            from app.config import get_settings
            settings = get_settings()
            client = OpenSearch(settings.os.OS_HOST, request_timeout=3)
            if client.ping():
                checks["opensearch"] = "ok"
            else:
                checks["opensearch"] = "ping failed"
        except Exception as e:
            checks["opensearch"] = str(e)

        # MySQL
        try:
            from app.models.base import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["mysql"] = "ok"
        except Exception as e:
            checks["mysql"] = str(e)

        all_ok = all(v == "ok" for v in checks.values())
        tracker.finish(run, success=all_ok, result=checks)

        if not all_ok:
            failed = [k for k, v in checks.items() if v != "ok"]
            logger.warning("[jobs] 健康检查警告: %s 异常 — %s", failed, checks)

    except Exception as e:
        logger.error("[jobs] 健康检查异常: %s", e)
        tracker.finish(run, success=False, error=str(e))

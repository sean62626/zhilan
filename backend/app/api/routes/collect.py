"""
采集触发路由

POST /api/v1/collect        — 触发即时采集
GET  /api/v1/collect/status — 最近一次采集状态
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter

from app.agents.collector import run_collection
from app.rag.es_indexer import index_articles

logger = logging.getLogger(__name__)

router = APIRouter()

# 最近一次采集结果（内存中保存）
_last_result: Optional[dict] = None
_last_collection_time: Optional[datetime] = None


def _load_enabled_keywords() -> list[str]:
    """从 topics.json 加载所有启用主题的关键词"""
    from app.api.routes.topics import get_enabled_topic_keywords
    return get_enabled_topic_keywords()


@router.post("/collect")
async def trigger_collection():
    """
    触发即时采集

    并行运行所有启用的采集源，使用用户配置的监控主题关键词，
    将结果写入 Elasticsearch（如可用），返回各源采集统计与文章总数
    """
    global _last_result, _last_collection_time

    keywords = _load_enabled_keywords()
    result = await run_collection(topics=keywords if keywords else None)

    # 写入 ES
    indexed_count = 0
    if result.articles:
        indexed_count = index_articles(result.articles)

    elapsed = (result.finished_at - result.started_at).total_seconds() if result.finished_at else 0

    response = {
        "status": "completed",
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat() if result.finished_at else None,
        "elapsed_seconds": round(elapsed, 2),
        "total_sources": result.total_sources,
        "successful_sources": result.successful_sources,
        "total_articles": len(result.articles),
        "indexed_articles": indexed_count,
        "source_stats": result.source_stats,
    }

    # 缓存最近结果
    _last_result = response
    _last_collection_time = datetime.now(timezone.utc)

    return response


@router.get("/collect/status")
async def collection_status():
    """查询最近一次采集状态"""
    if _last_result is None:
        return {
            "status": "idle",
            "message": "尚未执行过采集",
        }
    return {
        "status": "ok",
        "last_collection_time": _last_collection_time.isoformat() if _last_collection_time else None,
        "last_result": _last_result,
    }

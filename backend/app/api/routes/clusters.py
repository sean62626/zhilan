"""
聚类分析路由

GET /api/v1/clusters — 获取最近的聚类结果

数据来源（按优先级）：
1. exports/latest_state.json — 工作流完成后自动保存的状态快照
2. 空结果 — 尚未执行过工作流
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

STATE_FILE = Path(__file__).parent.parent.parent.parent / "exports" / "latest_state.json"


@router.get("/clusters")
async def get_clusters():
    """获取最近一次工作流的聚类结果"""
    if not STATE_FILE.exists():
        return {
            "status": "ok",
            "message": "尚未执行过工作流，无聚类数据",
            "clusters": [],
            "total_articles": 0,
        }

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[clusters] 读取状态文件失败: %s", e)
        return {"status": "ok", "message": "数据读取失败", "clusters": [], "total_articles": 0}

    clusters = state.get("topic_clusters", [])
    unique_articles = state.get("unique_articles", [])

    # 构建簇详情（含文章预览）
    enriched = []
    for c in clusters:
        cluster_articles = [
            {
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "source_name": a.get("source_name", ""),
                "published_at": a.get("published_at"),
            }
            for a in unique_articles
            if a.get("id") in [ca.get("id") for ca in c.get("articles", [])]
        ]
        enriched.append({
            "cluster_id": c.get("cluster_id"),
            "label": c.get("label", ""),
            "importance": c.get("importance", 5),
            "article_count": c.get("article_count", 0),
            "keywords": c.get("keywords", []),
            "representative_title": c.get("representative_title", ""),
            "articles": cluster_articles[:10],  # 每簇最多 10 篇
        })

    # 文章时间分布
    dates = []
    for a in unique_articles:
        pub = a.get("published_at")
        if pub:
            dates.append(pub[:10])  # YYYY-MM-DD

    return {
        "status": "ok",
        "clusters": enriched,
        "total_clusters": len(clusters),
        "total_articles": len(unique_articles),
        "date_distribution": _count_distribution(dates),
    }


def _count_distribution(items: list[str]) -> list[dict]:
    """统计条目频率分布"""
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return sorted(
        [{"date": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["date"],
    )

"""
处理管道路由

POST /api/v1/pipeline/run        — 运行完整管道（采集 → 预处理 → 去重 → 聚类 → 研报）
POST /api/v1/pipeline/research   — 对已有聚类结果运行 RAG 研报生成
POST /api/v1/pipeline/preprocess — 仅运行预处理
POST /api/v1/pipeline/dedup      — 仅运行去重
POST /api/v1/pipeline/cluster    — 仅运行聚类
"""

import logging

from fastapi import APIRouter, Query

from app.agents.collector import run_collection
from app.agents.preprocessor import run_preprocess
from app.agents.dedup import run_dedup
from app.agents.cluster import run_clustering
from app.agents.researcher import run_research
from app.models.article import RawArticle, CleanArticle, TopicCluster

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/pipeline/run")
async def run_full_pipeline(
    skip_research: bool = Query(default=False, description="跳过 RAG 研报生成阶段"),
    topics: list[str] = Query(default=[], description="监控主题关键词"),
):
    """
    运行完整管道

    采集 → 预处理 → 去重 → 聚类 → 研报生成
    返回各阶段统计 + 聚类结果 + 研报列表

    - ?skip_research=true 可跳过研报生成阶段
    - ?topics=AI&topics=芯片 指定采集关键词（不传则从配置文件加载）
    """
    # 自动加载用户配置的主题关键词
    if not topics:
        from app.api.routes.topics import get_enabled_topic_keywords
        topics = get_enabled_topic_keywords()

    # 阶段 1: 采集
    collection_result = await run_collection(topics=topics if topics else None)
    articles = collection_result.articles

    if not articles:
        return {
            "status": "ok",
            "message": "无新文章可供处理",
            "collection": _collection_stats(collection_result),
            "preprocess": None,
            "dedup": None,
            "clusters": [],
            "reports": [],
        }

    # 阶段 2: 预处理
    clean_articles = await run_preprocess(articles)

    if not clean_articles:
        return {
            "status": "ok",
            "message": "预处理后无有效文章",
            "collection": _collection_stats(collection_result),
            "preprocess": {"input": len(articles), "output": 0},
            "dedup": None,
            "clusters": [],
            "reports": [],
        }

    # 阶段 3: 去重
    unique_articles = await run_dedup(clean_articles)

    # 阶段 4: 聚类
    clusters = await run_clustering(unique_articles)

    # 阶段 5: RAG 研报生成
    reports = []
    if not skip_research and clusters:
        research_results = await run_research(
            clusters=clusters,
            corpus=unique_articles,
        )
        reports = _format_reports(research_results)

    # 构建响应
    cluster_summary = _format_clusters(clusters)

    return {
        "status": "ok",
        "collection": _collection_stats(collection_result),
        "preprocess": {"input": len(articles), "output": len(clean_articles)},
        "dedup": {"input": len(clean_articles), "output": len(unique_articles)},
        "clusters": {
            "count": len(clusters),
            "total_articles_in_clusters": sum(c.article_count for c in clusters),
            "items": cluster_summary,
        },
        "reports": reports,
    }


@router.post("/pipeline/preprocess")
async def preprocess_only(articles: list[RawArticle]):
    """仅运行预处理"""
    clean = await run_preprocess(articles)
    return {
        "status": "ok",
        "input": len(articles),
        "output": len(clean),
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "language": a.language,
                "content_preview": a.cleaned_content[:200],
            }
            for a in clean[:10]  # 只返回前 10 篇预览
        ],
    }


@router.post("/pipeline/dedup")
async def dedup_only(articles: list[CleanArticle]):
    """仅运行去重"""
    unique = await run_dedup(articles)
    return {
        "status": "ok",
        "input": len(articles),
        "output": len(unique),
        "removed": len(articles) - len(unique),
    }


@router.post("/pipeline/cluster")
async def cluster_only(articles: list[CleanArticle]):
    """仅运行聚类"""
    clusters = await run_clustering(articles)
    return {
        "status": "ok",
        "cluster_count": len(clusters),
        "clusters": _format_clusters(clusters),
    }


@router.post("/pipeline/research")
async def research_only(
    body: dict,
    max_reports: int = Query(default=3, description="最多生成研报数"),
):
    """
    对已有聚类结果运行 RAG 研报生成

    Body (JSON):
      {
        "clusters": [...],   // TopicCluster 列表
        "articles": [...]    // CleanArticle 列表
      }
    """
    try:
        clusters_data = body.get("clusters", [])
        articles_data = body.get("articles", [])

        if not clusters_data:
            return {"status": "ok", "message": "无主题簇", "reports": []}

        if not articles_data:
            return {"status": "ok", "message": "语料库为空", "reports": []}

        # 解析为 Pydantic 模型
        clusters = [TopicCluster(**c) for c in clusters_data]
        articles = [CleanArticle(**a) for a in articles_data]
    except Exception as e:
        return {"status": "error", "message": f"数据解析失败: {e}", "reports": []}

    results = await run_research(
        clusters=clusters,
        corpus=articles,
        max_clusters=max_reports,
    )

    return {
        "status": "ok",
        "reports": _format_reports(results),
    }


def _format_clusters(clusters: list[TopicCluster]) -> list[dict]:
    """格式化聚类摘要"""
    return [
        {
            "cluster_id": c.cluster_id,
            "label": c.label,
            "importance": c.importance,
            "article_count": c.article_count,
            "keywords": c.keywords,
            "representative_title": c.representative_title,
        }
        for c in clusters
    ]


def _format_reports(results) -> list[dict]:
    """格式化研报结果列表"""
    formatted = []
    for r in results:
        if r.report:
            formatted.append({
                "report_id": r.report.report_id,
                "cluster_id": r.cluster_id,
                "title": r.report.title,
                "background": r.report.background[:500],
                "analysis": r.report.analysis[:500],
                "outlook": r.report.outlook[:500],
                "risk": r.report.risk[:500],
                "references_count": len(r.report.references),
                "model_used": r.report.model_used,
                "queries_used": r.queries_used,
                "docs_retrieved": r.docs_retrieved,
                "docs_reranked": r.docs_reranked,
                "elapsed_seconds": r.elapsed_seconds,
                "error": r.error,
                "generated_at": r.report.generated_at.isoformat() if r.report.generated_at else None,
            })
        else:
            formatted.append({
                "cluster_id": r.cluster_id,
                "error": r.error or "未知错误",
                "queries_used": r.queries_used,
            })
    return formatted


def _collection_stats(result) -> dict:
    """提取采集统计（含诊断信息）"""
    source_details = {}
    for k, v in result.source_stats.items():
        detail = {"count": v.get("count", 0), "status": v.get("status", "unknown")}
        if v.get("error"):
            detail["error"] = v["error"]
        if v.get("diagnostic"):
            detail["diagnostic"] = v["diagnostic"]
        source_details[k] = detail

    return {
        "total_sources": result.total_sources,
        "successful_sources": result.successful_sources,
        "total_articles": len(result.articles),
        "source_details": source_details,
        "elapsed_seconds": (
            round((result.finished_at - result.started_at).total_seconds(), 2)
            if result.finished_at
            else 0
        ),
    }

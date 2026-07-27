"""
ResearchAgent — RAG 检索增强 + 深度研报生成

职责：
  1. 对每个主题簇执行 Query 改写
  2. 多路混合检索（BM25 + kNN）
  3. Rerank 精排
  4. 上下文组装
  5. DeepSeek 结构化研报生成
  6. LLM 不可用时生成回退简报

输入: TopicCluster[] + 全量语料 CleanArticle[] → 输出: ResearchReport[]
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.article import TopicCluster, CleanArticle, ResearchReport
from app.generators.summarizer import rewrite_queries
from app.generators.report_writer import generate_report
from app.rag.retriever import hybrid_search
from app.rag.reranker import rerank
from app.rag.context import assemble_context, format_references
from app.workflow.event_bus import event_bus, publish_event_safe

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """单个研报的生成结果（含元信息）"""

    cluster_id: int
    report: ResearchReport | None = None
    queries_used: list[str] = field(default_factory=list)
    docs_retrieved: int = 0
    docs_reranked: int = 0
    elapsed_seconds: float = 0
    error: str | None = None


async def run_research(
    clusters: list[TopicCluster],
    corpus: list[CleanArticle],
    run_id: str = "",
    max_clusters: int = 3,
    top_k_retrieve: int = 20,
    top_k_rerank: int = 8,
    max_context_tokens: int = 8000,
    review_feedback: dict[int, dict] | None = None,
) -> list[ResearchResult]:
    """
    对主题簇执行 RAG 深度研报生成

    Args:
        clusters: 主题簇列表（按 importance 排序）
        corpus: 全量语料库（所有去重后的文章）
        run_id: 工作流运行 ID（用于 WebSocket 进度推送）
        max_clusters: 最多处理的簇数量
        top_k_retrieve: 混合检索召回数
        top_k_rerank: Rerank 精排保留数
        max_context_tokens: 上下文最大 token 数
        review_feedback: 审核反馈 {cluster_id: {fact_errors, hallucination_issues, suggestions}}
                         重试时传入，用于指导 LLM 修正上一版的问题

    Returns:
        ResearchResult 列表
    """
    if not clusters:
        logger.info("无主题簇，跳过研报生成")
        return []

    if not corpus:
        logger.warning("语料库为空，无法进行 RAG 检索")
        return []

    # 按重要性排序，只处理前 N 个
    sorted_clusters = sorted(clusters, key=lambda c: c.importance, reverse=True)
    target_clusters = sorted_clusters[:max_clusters]

    logger.info(
        "开始 RAG 研报生成: %d 个主题簇（共 %d 个）, 语料 %d 篇",
        len(target_clusters), len(clusters), len(corpus),
    )

    results: list[ResearchResult] = []

    for i, cluster in enumerate(target_clusters):
        t0 = time.monotonic()
        result = ResearchResult(cluster_id=cluster.cluster_id)
        cluster_tag = f"簇 {i + 1}/{len(target_clusters)}"

        try:
            # 进度: 开始处理簇
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"📝 开始处理 {cluster_tag}：「{cluster.label}」",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # 步骤 0: 提取簇内文章作为核心来源材料
            cluster_sources = _format_cluster_sources(cluster)

            # 步骤 1: Query 改写
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  🔍 {cluster_tag}：正在改写查询...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            queries = await rewrite_queries(
                topic_label=cluster.label,
                keywords=cluster.keywords,
                n=4,
            )
            result.queries_used = queries
            logger.info("  簇 %d [%s] → %d 个检索 Query", cluster.cluster_id, cluster.label, len(queries))

            # 步骤 2: 多路混合检索（对每个 query 检索，合并去重）
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  📚 {cluster_tag}：正在混合检索（{len(queries)} 个 Query）...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            all_docs: dict[str, tuple[CleanArticle, float]] = {}
            for query in queries:
                retrieved = await hybrid_search(
                    query=query,
                    corpus=corpus,
                    top_k_knn=top_k_retrieve,
                    top_k_bm25=top_k_retrieve,
                    final_top_k=top_k_retrieve,
                )
                for doc, score in retrieved:
                    if doc.id not in all_docs or score > all_docs[doc.id][1]:
                        all_docs[doc.id] = (doc, score)

            merged_docs = sorted(all_docs.values(), key=lambda x: x[1], reverse=True)
            result.docs_retrieved = len(merged_docs)
            logger.info("  簇 %d: 混合检索召回 %d 篇", cluster.cluster_id, len(merged_docs))

            if not merged_docs:
                result.error = "检索无结果"
                result.report = _make_empty_report(cluster)
                results.append(result)
                publish_event_safe(run_id, {
                    "type": "node_progress",
                    "node": "research",
                    "message": f"  ⚠️ {cluster_tag}：检索无结果，跳过",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # 步骤 3: Rerank 精排
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  🎯 {cluster_tag}：正在Rerank精排（{len(merged_docs)} 篇 → {top_k_rerank} 篇）...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            query_for_rerank = f"{cluster.label} {' '.join(cluster.keywords)}"
            reranked = await rerank(query_for_rerank, merged_docs, top_k=top_k_rerank)
            result.docs_reranked = len(reranked)
            logger.info("  簇 %d: Rerank 精排 → %d 篇", cluster.cluster_id, len(reranked))

            # 步骤 4: 上下文组装
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  📋 {cluster_tag}：正在组装上下文...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            context_text = assemble_context(reranked, max_tokens=max_context_tokens)
            references = format_references(reranked[:top_k_rerank])

            # 步骤 5: 研报生成（核心来源 = 簇内文章，RAG 上下文 = 补充材料）
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  🤖 {cluster_tag}：正在调用 DeepSeek 生成研报...",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            # 获取该簇的审核反馈（重试时用于指导 LLM 修正）
            cluster_feedback = (review_feedback or {}).get(cluster.cluster_id)
            report_dict = await generate_report(
                cluster_label=cluster.label,
                keywords=cluster.keywords,
                context_text=context_text,
                references=references,
                cluster_sources=cluster_sources,
                review_feedback=cluster_feedback,
            )

            report = ResearchReport(
                report_id=ResearchReport.make_id(cluster.cluster_id, report_dict["title"]),
                cluster_id=cluster.cluster_id,
                title=report_dict["title"],
                background=report_dict.get("background", ""),
                analysis=report_dict.get("analysis", ""),
                outlook=report_dict.get("outlook", ""),
                risk=report_dict.get("risk", ""),
                raw_text=report_dict.get("raw_text", ""),
                references=references,
                model_used=report_dict.get("model_used", ""),
                generated_at=datetime.now(timezone.utc),
            )
            result.report = report
            elapsed = round(time.monotonic() - t0, 1)
            logger.info("  簇 %d: 研报生成完成 — %s", cluster.cluster_id, report.title)

            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  ✅ {cluster_tag}：研报生成完成「{report.title}」（耗时 {elapsed} 秒）",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            logger.error("  簇 %d: 研报生成失败: %s", cluster.cluster_id, e)
            result.error = str(e)
            result.report = _make_empty_report(cluster)
            publish_event_safe(run_id, {
                "type": "node_progress",
                "node": "research",
                "message": f"  ❌ {cluster_tag}：生成失败 — {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        result.elapsed_seconds = round(time.monotonic() - t0, 2)
        results.append(result)

    # 统计
    success_count = sum(1 for r in results if r.report and r.report.model_used != "fallback")
    fallback_count = sum(1 for r in results if r.report and r.report.model_used == "fallback")
    error_count = sum(1 for r in results if r.error)
    logger.info(
        "RAG 研报生成完成: %d 成功 + %d 回退 + %d 失败",
        success_count, fallback_count, error_count,
    )

    return results


def _make_empty_report(cluster: TopicCluster) -> ResearchReport:
    """生成空研报（错误情况下的占位）"""
    return ResearchReport(
        report_id=ResearchReport.make_id(cluster.cluster_id, "empty"),
        cluster_id=cluster.cluster_id,
        title=f"「{cluster.label}」研报生成失败",
        background="处理过程中出现错误，请重试。",
        analysis="",
        outlook="",
        risk="",
        model_used="error",
        generated_at=datetime.now(timezone.utc),
    )


def _format_cluster_sources(cluster: TopicCluster) -> str:
    """
    将簇内文章格式化为 LLM 可用的核心来源材料

    优先使用 AI 摘要（summary），摘要为空时回退到清洗后正文（cleaned_content），
    每篇文章截取前 600 字，编号后按发布时间排序。
    """
    if not cluster.articles:
        return "（该主题簇内无文章数据）"

    # 按发布时间排序
    sorted_articles = sorted(
        cluster.articles,
        key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    parts = []
    for i, a in enumerate(sorted_articles):
        title = a.title or "无标题"
        source = a.source_name or a.source or "未知来源"
        published = ""
        if a.published_at:
            if hasattr(a.published_at, "strftime"):
                published = a.published_at.strftime("%Y-%m-%d")
            else:
                published = str(a.published_at)[:10]

        # 优先用 AI 摘要，回退到正文
        body = a.summary or a.cleaned_content or a.content or ""
        # 截断，避免单篇过长挤占 token
        body = body[:600]

        parts.append(
            f"[来源{i + 1}] **{title}**\n"
            f"    来源: {source} | {published}\n"
            f"    内容: {body}\n"
        )

    return "\n".join(parts)

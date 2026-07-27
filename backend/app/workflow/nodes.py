"""
LangGraph 工作流 Node 函数

每个 Node 函数遵循统一模式：
  1. 从 state 读取序列化的 dict 数据
  2. 反序列化为 Pydantic 模型
  3. 调用对应 Agent
  4. 序列化输出写回 state
  5. 异常 → 记录 errors（append-only），返回空数据让后续节点跳过

Phase 6 新增:
  - review_node     (审核闭环 — 事实核查 + 幻觉检测)
  - compose_node    (日报组装)
  - export_node     (Markdown/PDF 导出)
  - research_node 增强 — 重试时使用审核反馈
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.workflow.state import PlatformState
from app.workflow.event_bus import event_bus
from app.models.article import RawArticle, CleanArticle, TopicCluster

logger = logging.getLogger(__name__)


async def _publish_node_started(run_id: str, node_name: str):
    """向事件总线发布 node_started 事件（同步等待，确保在 node_complete 之前到达前端）"""
    if not run_id:
        return
    try:
        await event_bus.publish(run_id, {
            "type": "node_started",
            "node": node_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        # 发布失败不阻塞工作流
        pass


# ========== Node 1: 数据采集 ==========

async def collect_node(state: PlatformState) -> dict:
    """调用 CollectorAgent，采集多源新闻数据"""
    await _publish_node_started(state.get("run_id", ""), "collect")
    logger.info("[workflow] 开始采集阶段")
    run_id = state.get("run_id", "")

    try:
        from app.agents.collector import run_collection

        topics = state.get("topics", [])
        topics_detail = state.get("topics_detail", [])
        logger.info("[DEBUG-collect_node] state['topics']=%s", topics)
        logger.info("[DEBUG-collect_node] state['topics_detail']=%s",
                    [t.get("name", "?") + ":" + str(t.get("keywords", [])) for t in topics_detail])
        result = await run_collection(topics=topics if topics else None, run_id=run_id)

        articles_dicts = [a.model_dump(mode="json") for a in result.articles]

        # 将文章异步索引到 OpenSearch（失败不影响主流程，检索时降级为本地 TF-IDF）
        if result.articles:
            try:
                from app.rag.es_indexer import index_articles
                indexed = await asyncio.to_thread(index_articles, result.articles)
                logger.info("[workflow] OpenSearch 索引: %d/%d 篇文章写入", indexed, len(result.articles))
            except Exception as e_idx:
                logger.warning("[workflow] OpenSearch 索引写入失败（检索时将降级为本地 TF-IDF）: %s", e_idx)

        errors = [
            f"[{k}] {v.get('error')}"
            for k, v in result.source_stats.items()
            if v.get("error")
        ]
        # 额外收集"空返回"的信息（源成功执行但未返回文章），附带诊断原因
        empty_sources = [
            _format_empty_source_msg(k, v)
            for k, v in result.source_stats.items()
            if not v.get("error") and v.get("count", 0) == 0
        ]
        if empty_sources:
            errors.extend(empty_sources)

        logger.info("[workflow] 采集完成: %d 篇文章, %d 个源出错", len(articles_dicts), len(errors))

        return {
            "raw_articles": articles_dicts,
            "collection_errors": errors,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 采集阶段异常: %s", e)
        return {
            "raw_articles": [],
            "collection_errors": [str(e)],
            "errors": [f"采集阶段失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 2: 文本预处理 ==========

async def preprocess_node(state: PlatformState) -> dict:
    """调用 PreprocessAgent，清洗文本并检测语言"""
    await _publish_node_started(state.get("run_id", ""), "preprocess")
    raw_dicts = state.get("raw_articles", [])

    if not raw_dicts:
        logger.info("[workflow] 无原始文章，跳过预处理")
        return {"clean_articles": [], "workflow_status": "running"}

    logger.info("[workflow] 开始预处理: %d 篇文章", len(raw_dicts))

    try:
        from app.agents.preprocessor import run_preprocess

        raw_articles = [_deserialize(RawArticle, d) for d in raw_dicts]
        clean_articles = await run_preprocess(raw_articles)
        clean_dicts = [a.model_dump(mode="json") for a in clean_articles]

        logger.info("[workflow] 预处理完成: %d → %d 篇", len(raw_dicts), len(clean_dicts))

        return {
            "clean_articles": clean_dicts,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 预处理阶段异常: %s", e)
        return {
            "clean_articles": [],
            "errors": [f"预处理阶段失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 3: 三层去重 ==========

async def dedup_node(state: PlatformState) -> dict:
    """调用 DedupAgent，三层去重（URL → SimHash → Embedding）"""
    await _publish_node_started(state.get("run_id", ""), "dedup")
    clean_dicts = state.get("clean_articles", [])

    if not clean_dicts:
        logger.info("[workflow] 无清洗文章，跳过去重")
        return {
            "unique_articles": [],
            "dedup_stats": {"total_in": 0, "total_out": 0, "reason": "no_input"},
            "workflow_status": "running",
        }

    logger.info("[workflow] 开始去重: %d 篇文章", len(clean_dicts))

    try:
        from app.agents.dedup import run_dedup

        clean_articles = [_deserialize(CleanArticle, d) for d in clean_dicts]
        total_in = len(clean_articles)
        unique_articles = await run_dedup(clean_articles)
        total_out = len(unique_articles)
        unique_dicts = [a.model_dump(mode="json") for a in unique_articles]

        stats = {
            "total_in": total_in,
            "total_out": total_out,
            "removed": total_in - total_out,
        }

        logger.info("[workflow] 去重完成: %d → %d 篇 (%d 篇重复)", total_in, total_out, total_in - total_out)

        return {
            "unique_articles": unique_dicts,
            "dedup_stats": stats,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 去重阶段异常: %s", e)
        return {
            "unique_articles": [],
            "dedup_stats": {"total_in": len(clean_dicts), "total_out": 0, "error": str(e)},
            "errors": [f"去重阶段失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 4: 语义聚类 ==========

async def cluster_node(state: PlatformState) -> dict:
    """调用 ClusterAgent，语义聚类 + 标签生成"""
    await _publish_node_started(state.get("run_id", ""), "cluster")
    cluster_run_id = state.get("run_id", "")
    unique_dicts = state.get("unique_articles", [])

    if not unique_dicts:
        logger.info("[workflow] 无去重文章，跳过聚类")
        return {"topic_clusters": [], "workflow_status": "running"}

    logger.info("[workflow] 开始聚类: %d 篇文章", len(unique_dicts))

    try:
        from app.agents.cluster import run_clustering

        unique_articles = [_deserialize(CleanArticle, d) for d in unique_dicts]
        clusters = await run_clustering(unique_articles, run_id=cluster_run_id)

        # TopicCluster.articles 是嵌套的 CleanArticle 列表，序列化时需要处理
        cluster_dicts = [_serialize_cluster(c) for c in clusters]

        logger.info("[workflow] 聚类完成: %d 个主题簇", len(clusters))

        return {
            "topic_clusters": cluster_dicts,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 聚类阶段异常: %s", e)
        return {
            "topic_clusters": [],
            "errors": [f"聚类阶段失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 5: RAG 研报生成 ==========

async def research_node(state: PlatformState) -> dict:
    """调用 ResearchAgent，RAG 检索增强 + 深度研报生成

    重试模式 (retry_count > 0):
      - 读取审核反馈 (review_results)，识别未通过的 cluster_id
      - 仅重新生成未通过审核的簇（而非全部簇）
      - 将审核反馈注入 LLM 提示以改进生成质量
    """
    cluster_dicts = state.get("topic_clusters") or []
    unique_dicts = state.get("unique_articles") or []
    retry_count = state.get("retry_count", 0)

    if not cluster_dicts:
        logger.info("[workflow] 无主题簇，跳过研报生成")
        return {"research_reports": [], "workflow_status": "running"}

    if not unique_dicts:
        logger.info("[workflow] 无语料库，跳过研报生成")
        return {"research_reports": [], "workflow_status": "running"}

    run_id = state.get("run_id", "")
    await _publish_node_started(run_id, "research")

    # 从配置获取最大簇数
    from app.config import get_settings
    max_clusters = get_settings().app.RESEARCH_MAX_CLUSTERS

    # 收集审核反馈，识别未通过的 cluster_id（重试时有用）
    review_feedback = _get_review_feedback_for_retry(state)
    failed_cluster_ids = set(review_feedback.keys()) if review_feedback else set()

    # ========== 重试模式：仅重新生成失败的簇 ==========
    if retry_count > 0 and failed_cluster_ids:
        # 保留已通过审核的研报，仅重新生成失败的
        previous_reports = state.get("research_reports") or []
        passed_reports = [
            r for r in previous_reports
            if r.get("cluster_id") not in failed_cluster_ids
        ]
        logger.info(
            "[workflow] 重试模式（第 %d 次）: %d 个簇失败 → 仅重新生成失败簇 %s，保留已通过 %d 份",
            retry_count, len(failed_cluster_ids), failed_cluster_ids, len(passed_reports),
        )

        # 筛选出失败的簇
        all_clusters = [_deserialize(TopicCluster, d) for d in cluster_dicts]
        retry_clusters = [c for c in all_clusters if c.cluster_id in failed_cluster_ids]
        clusters_to_process = retry_clusters
    else:
        passed_reports = []
        all_clusters = [_deserialize(TopicCluster, d) for d in cluster_dicts]
        clusters_to_process = all_clusters

    retry_tag = f"（第 {retry_count + 1} 次生成）" if retry_count > 0 else ""
    logger.info(
        "[workflow] 开始研报生成%s: %d 个簇（共 %d 个）, %d 篇语料",
        retry_tag, len(clusters_to_process), len(cluster_dicts), len(unique_dicts),
    )

    try:
        from app.agents.researcher import run_research

        corpus = [_deserialize(CleanArticle, d) for d in unique_dicts]

        results = await run_research(
            clusters=clusters_to_process,
            corpus=corpus,
            run_id=run_id,
            max_clusters=max_clusters,
            review_feedback=review_feedback,  # 传递审核反馈给 LLM
        )

        # 序列化新生成的研报结果
        new_reports = []
        for r in results:
            entry = {
                "cluster_id": r.cluster_id,
                "queries_used": r.queries_used,
                "docs_retrieved": r.docs_retrieved,
                "docs_reranked": r.docs_reranked,
                "elapsed_seconds": r.elapsed_seconds,
                "error": r.error,
                "retry_count": retry_count,
                "retry_feedback": review_feedback,
            }
            if r.report:
                entry["report"] = r.report.model_dump(mode="json")
            new_reports.append(entry)

        # 合并：已通过的 + 新生成的
        reports = passed_reports + new_reports

        logger.info(
            "[workflow] 研报生成完成: %d 份（保留 %d + 新生成 %d）",
            len(reports), len(passed_reports), len(new_reports),
        )

        return {
            "research_reports": reports,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 研报生成阶段异常: %s", e)
        return {
            "research_reports": [],
            "errors": [f"研报生成阶段失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 6: 质量审核 (Phase 6) ==========

async def review_node(state: PlatformState) -> dict:
    """调用 ReviewAgent，四维度审核（事实、幻觉、平衡、完整）

    每次执行递增 retry_count。
    审核结果存入 review_results，review_passed = 全部通过。
    """
    reports = state.get("research_reports") or []
    unique_dicts = state.get("unique_articles") or []
    current_retry = state.get("retry_count", 0)
    new_retry_count = current_retry + 1

    if not reports:
        logger.info("[workflow] 无研报需要审核")
        return {
            "review_results": [],
            "review_passed": True,
            "retry_count": new_retry_count,
            "workflow_status": "running",
        }

    await _publish_node_started(state.get("run_id", ""), "review")
    logger.info("[workflow] 开始审核: %d 份研报 (第 %d 次)", len(reports), new_retry_count)

    try:
        from app.agents.reviewer import run_review

        results = await run_review(
            research_reports=reports,
            unique_articles=unique_dicts,
        )

        results_dicts = [r.model_dump(mode="json") for r in results]
        all_passed = all(r.passed for r in results)

        passed_count = sum(1 for r in results if r.passed)
        logger.info(
            "[workflow] 审核完成: %d/%d 通过 (重试 %d/3)%s",
            passed_count, len(results), new_retry_count,
            " ✅" if all_passed else " → 返回 ResearchAgent 重试",
        )

        return {
            "review_results": results_dicts,
            "review_passed": all_passed,
            "retry_count": new_retry_count,
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 审核阶段异常: %s", e)
        # 审核异常时强制通过（不阻塞管道）
        return {
            "review_results": [],
            "review_passed": True,
            "retry_count": new_retry_count,
            "errors": [f"审核阶段异常（已强制通过）: {e}"],
            "workflow_status": "running",
        }


# ========== Node 7: 日报组装 (Phase 6) ==========

async def compose_node(state: PlatformState) -> dict:
    """调用 ComposeAgent，组装每日简报"""
    reports = state.get("research_reports", [])
    review_results = state.get("review_results", [])
    clusters = state.get("topic_clusters", [])
    topics_detail = state.get("topics_detail", [])
    target_date = state.get("target_date", "")
    article_count = len(state.get("unique_articles", []))
    run_id = state.get("run_id", "")

    await _publish_node_started(state.get("run_id", ""), "compose")
    logger.info("[workflow] 开始日报组装: %d 份研报 (run_id=%s)", len(reports), run_id)

    try:
        from app.agents.composer import run_compose

        brief = await run_compose(
            research_reports=reports,
            review_results=review_results,
            topic_clusters=clusters,
            topics_detail=topics_detail,
            target_date=target_date,
            article_count=article_count,
            run_id=run_id,
        )

        logger.info("[workflow] 日报组装完成: %s", brief.brief_id)

        return {
            "daily_brief": brief.model_dump(mode="json"),
            "workflow_status": "running",
        }

    except Exception as e:
        logger.error("[workflow] 日报组装异常: %s", e)
        return {
            "daily_brief": None,
            "errors": [f"日报组装失败: {e}"],
            "workflow_status": "running",
        }


# ========== Node 8: 导出 (Phase 6) ==========

async def export_node(state: PlatformState) -> dict:
    """调用 ExportAgent，导出 Markdown / PDF"""
    brief = state.get("daily_brief")

    if brief is None:
        logger.info("[workflow] 无简报数据，跳过导出")
        return {"export_paths": [], "workflow_status": "completed"}

    run_id = state.get("run_id", "")

    await _publish_node_started(state.get("run_id", ""), "export")
    logger.info("[workflow] 开始导出 (run_id=%s)", run_id)

    try:
        from app.agents.exporter import run_export

        paths = await run_export(
            daily_brief=brief,
            formats=["md"],
            run_id=run_id,
        )

        logger.info("[workflow] 导出完成: %s", paths)

        return {
            "export_paths": paths,
            "workflow_status": "completed",
        }

    except Exception as e:
        logger.error("[workflow] 导出异常: %s", e)
        return {
            "export_paths": [],
            "errors": [f"导出失败: {e}"],
            "workflow_status": "completed",
        }


# ========== 辅助函数 ==========

def _deserialize(model_cls, data: dict):
    """将 dict 反序列化为 Pydantic 模型"""
    return model_cls(**data)


def _serialize_cluster(cluster: TopicCluster) -> dict:
    """序列化 TopicCluster，文章内嵌转为 dict"""
    d = cluster.model_dump(mode="json")
    d["article_count"] = cluster.article_count
    return d


def _get_review_feedback_for_retry(state: PlatformState) -> dict[int, dict]:
    """从上次审核结果中提取反馈，按 cluster_id 索引

    返回 {cluster_id: {fact_errors, hallucination_issues, suggestions}}
    仅包含未通过审核的研报。
    """
    review_results = state.get("review_results", [])

    if not review_results:
        return {}

    feedback: dict[int, dict] = {}
    for rv in review_results:
        if not rv.get("passed", False):
            cid = rv.get("cluster_id", 0)
            feedback[cid] = {
                "fact_errors": rv.get("fact_errors", []),
                "hallucination_issues": rv.get("hallucination_issues", []),
                "suggestions": rv.get("suggestions", []),
            }

    return feedback


def _format_empty_source_msg(source_key: str, stat: dict) -> str:
    """格式化采集源空返回消息，附带诊断原因"""
    diagnostic = stat.get("diagnostic", "")
    if diagnostic:
        return f"[{source_key}] {diagnostic}"
    return f"[{source_key}] 未返回文章（原因未知）"

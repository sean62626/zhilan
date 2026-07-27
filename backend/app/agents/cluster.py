"""
ClusterAgent — 语义聚类 + LLM 标签生成 + LLM 重要性评分

职责：
  1. BGE Embedding 向量化
  2. PCA 降维（可选）
  3. HDBSCAN 聚类
  4. TF-IDF 关键词提取
  5. LLM 标签生成 + LLM 重要性评分
  6. LLM 不可用时回退到公式 + 关键词

输入: CleanArticle[] → 输出: TopicCluster[]
"""

import logging
import re
from datetime import datetime, timezone

from app.models.article import CleanArticle, TopicCluster
from app.processors.clusterer import (
    encode_articles,
    reduce_dimensions,
    cluster_hdbscan,
    extract_keywords,
    compute_importance,
)
from app.generators.prompts import CLUSTER_IMPORTANCE_PROMPT, CLUSTER_LABEL_PROMPT
from app.generators.summarizer import call_deepseek
from app.workflow.event_bus import publish_event_safe

logger = logging.getLogger(__name__)


async def run_clustering(
    articles: list[CleanArticle],
    min_cluster_size: int = 3,
    pca_dimensions: int | None = 128,
    run_id: str = "",
) -> list[TopicCluster]:
    """
    对去重后的文章进行语义聚类

    Args:
        articles: 去重后的文章列表
        min_cluster_size: 最小簇大小
        pca_dimensions: PCA 降维维度（None 则不降维）

    Returns:
        TopicCluster 列表（按重要性降序排列）
    """
    if len(articles) < min_cluster_size:
        logger.info("文章数量 %d < 最小簇大小 %d，跳过聚类", len(articles), min_cluster_size)
        # 将所有文章作为一个簇
        if articles:
            cluster = TopicCluster(
                cluster_id=0,
                label="全部文章",
                importance=5,
                articles=articles,
                article_count=len(articles),
                representative_title=articles[0].title if articles else "",
                keywords=extract_keywords([a.text_for_embedding for a in articles]),
            )
            return [cluster]
        return []

    # 步骤 1: 向量化
    publish_event_safe(run_id, {
        "type": "node_progress",
        "node": "cluster",
        "message": f"🔗 正在向量化 {len(articles)} 篇文章...",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    texts = [a.text_for_embedding for a in articles]
    embeddings = encode_articles(texts)

    if embeddings is None:
        logger.warning("Embedding 模型不可用，使用 SimHash 特征降级聚类")
        embeddings = _fallback_features(articles)

    logger.info("向量化完成: shape=%s", embeddings.shape)

    # 步骤 2: PCA 降维
    if pca_dimensions and embeddings.shape[1] > pca_dimensions:
        embeddings = reduce_dimensions(embeddings, target_dim=pca_dimensions)
        logger.info("PCA 降维完成: shape=%s", embeddings.shape)

    # 步骤 3: HDBSCAN 聚类
    publish_event_safe(run_id, {
        "type": "node_progress",
        "node": "cluster",
        "message": f"🔗 正在执行 HDBSCAN 聚类（{len(articles)} 篇文章）...",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    labels = cluster_hdbscan(embeddings, min_cluster_size=min_cluster_size, min_samples=1)

    # 步骤 4: 构建 TopicCluster 列表
    unique_labels = set(labels)
    noise_count = int((labels == -1).sum())
    logger.info("聚类完成: %d 个簇 + %d 篇噪声", len(unique_labels - {-1}), noise_count)

    clusters: list[TopicCluster] = []
    total = len(articles)

    # 先构建基础簇对象（关键词 + 临时标签 + 公式评分兜底）
    for label in sorted(unique_labels):
        if label == -1:
            continue  # 跳过噪声点

        indices = [i for i, l in enumerate(labels) if l == label]
        cluster_articles = [articles[i] for i in indices]
        cluster_texts = [articles[i].text_for_embedding for i in indices]
        keywords = extract_keywords(cluster_texts)

        cluster = TopicCluster(
            cluster_id=int(label),
            label=" · ".join(keywords[:3]) if keywords else "未分类",
            importance=compute_importance(len(cluster_articles), total),
            articles=cluster_articles,
            article_count=len(cluster_articles),
            representative_title=cluster_articles[0].title,
            keywords=keywords,
        )
        clusters.append(cluster)

    # 如果 HDBSCAN 全标为噪声（0 个簇），回退为单簇模式
    if not clusters:
        logger.warning(
            "HDBSCAN 未发现任何簇（%d 篇噪声 / %d 篇总文章），回退为单簇模式",
            noise_count, total,
        )
        all_keywords = extract_keywords([a.text_for_embedding for a in articles])
        fallback_cluster = TopicCluster(
            cluster_id=0,
            label=" · ".join(all_keywords[:3]) if all_keywords else "今日综合要闻",
            importance=compute_importance(total, total),  # 100% → 应该是 10 但公式修正后会合理
            articles=articles,
            article_count=total,
            representative_title=articles[0].title,
            keywords=all_keywords,
        )
        clusters.append(fallback_cluster)

    # 调用 LLM 批量评分 + 生成标签
    if clusters:
        publish_event_safe(run_id, {
            "type": "node_progress",
            "node": "cluster",
            "message": f"🔗 正在用 LLM 为 {len(clusters)} 个簇生成标签与重要性评分...",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        try:
            llm_scores = await _llm_score_importance(clusters)
        except Exception as e:
            logger.warning("LLM 重要性评分失败，使用公式 fallback: %s", e)
            llm_scores = {}
        try:
            llm_labels = await _llm_generate_labels(clusters)
        except Exception as e:
            logger.warning("LLM 标签生成失败，使用关键词 fallback: %s", e)
            llm_labels = {}
        for c in clusters:
            if llm_scores and c.cluster_id in llm_scores:
                c.importance = llm_scores[c.cluster_id]
            if llm_labels and c.cluster_id in llm_labels:
                c.label = llm_labels[c.cluster_id]

    # 按重要性降序
    clusters.sort(key=lambda c: c.importance, reverse=True)

    logger.info("聚类结果: %d 个簇", len(clusters))
    for c in clusters:
        logger.info("  簇 %d [%s]: %d 篇, 重要性=%d", c.cluster_id, c.label, c.article_count, c.importance)

    publish_event_safe(run_id, {
        "type": "node_progress",
        "node": "cluster",
        "message": f"🔗 聚类完成: 发现 {len(clusters)} 个主题簇",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return clusters


def _fallback_features(articles: list[CleanArticle]) -> "np.ndarray":
    """
    降级方案：使用 SimHash 指纹作为聚类特征

    当 sentence-transformers 模型不可用时使用
    """
    import numpy as np
    from app.processors.simhash import compute_fingerprint

    fps = [compute_fingerprint(a.text_for_simhash) for a in articles]
    # 将 64-bit 指纹展开为 64 维二值向量
    features = np.zeros((len(fps), 64), dtype=np.float32)
    for i, fp in enumerate(fps):
        for bit in range(64):
            if fp & (1 << bit):
                features[i, bit] = 1.0
    return features


def _format_clusters_for_llm(clusters: list[TopicCluster]) -> str:
    """将簇信息格式化为 LLM 可读的文本"""
    parts = []
    for c in clusters:
        titles = [a.title[:80] for a in c.articles[:5]]
        kw = " · ".join(c.keywords)
        parts.append(
            f"cluster_id:{c.cluster_id}\n"
            f"  关键词: {kw}\n"
            f"  文章数: {c.article_count}\n"
            f"  代表文章:\n"
            + "\n".join(f"    - {t}" for t in titles)
        )
    return "\n".join(parts)


async def _llm_score_importance(clusters: list[TopicCluster]) -> dict[int, int]:
    """调用 LLM 批量评分重要性，返回 {cluster_id: score}"""
    clusters_text = _format_clusters_for_llm(clusters)
    prompt = CLUSTER_IMPORTANCE_PROMPT.format(clusters_text=clusters_text)

    response = await call_deepseek(
        messages=[
            {"role": "system", "content": "你是一名资深新闻编辑。请严格按照输出格式评分，不要输出多余内容。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=200,
    )

    if not response:
        logger.warning("LLM 不可用，重要性评分使用公式 fallback")
        return {}

    # 解析 "cluster_id:0 score:7" 格式
    scores: dict[int, int] = {}
    for line in response.strip().split("\n"):
        m = re.match(r"cluster_id:(\d+)\s+score:(\d+)", line.strip())
        if m:
            cid = int(m.group(1))
            score = int(m.group(2))
            scores[cid] = min(10, max(1, score))
    logger.info("LLM 重要性评分: %s", scores)
    return scores


async def _llm_generate_labels(clusters: list[TopicCluster]) -> dict[int, str]:
    """调用 LLM 批量生成主题标签，返回 {cluster_id: label}"""
    clusters_text = _format_clusters_for_llm(clusters)
    prompt = CLUSTER_LABEL_PROMPT.format(clusters_text=clusters_text)

    response = await call_deepseek(
        messages=[
            {"role": "system", "content": "你是一名资深新闻编辑。请严格按照输出格式生成标签，不要输出多余内容。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=300,
    )

    if not response:
        logger.warning("LLM 不可用，标签使用关键词组合 fallback")
        return {}

    # 解析 "cluster_id:0 标签文本" 格式
    labels: dict[int, str] = {}
    for line in response.strip().split("\n"):
        m = re.match(r"cluster_id:(\d+)\s+(.+)", line.strip())
        if m:
            cid = int(m.group(1))
            label = m.group(2).strip()
            if label:
                labels[cid] = label
    logger.info("LLM 标签生成: %s", labels)
    return labels

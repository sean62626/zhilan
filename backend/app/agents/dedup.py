"""
DedupAgent — 三层去重

L1: URL 精确去重 — 基于文章 ID（URL MD5）
L2: SimHash 近似去重 — 汉明距离 < 阈值
L3: Embedding 语义去重 — 余弦相似度 > 阈值（需要 Embedding 模型）

输入: CleanArticle[] → 输出: CleanArticle[]
"""

import logging

import numpy as np

from app.models.article import CleanArticle
from app.processors.simhash import compute_fingerprint, dedup_by_simhash, DEFAULT_THRESHOLD

logger = logging.getLogger(__name__)

# L2 SimHash 汉明距离阈值（< 3 → 相似度 > 0.9）
SIMHASH_THRESHOLD = DEFAULT_THRESHOLD
# L3 语义去重余弦相似度阈值
EMBEDDING_THRESHOLD = 0.92


async def run_dedup(articles: list[CleanArticle]) -> list[CleanArticle]:
    """
    三层去重管道

    L1: URL 精确去重
    L2: SimHash 近似去重
    L3: Embedding 语义去重（如模型可用）
    """
    total = len(articles)
    if total == 0:
        return []

    # ------- L1: URL 精确去重 -------
    seen_ids: set[str] = set()
    l1_result: list[CleanArticle] = []
    for a in articles:
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            l1_result.append(a)
    l1_removed = total - len(l1_result)
    logger.info("L1 精确去重: %d → %d (%d 篇重复)", total, len(l1_result), l1_removed)

    if len(l1_result) <= 1:
        return l1_result

    # ------- L2: SimHash 近似去重 -------
    # 计算每篇文章的 SimHash 指纹
    fingerprints = [
        compute_fingerprint(a.text_for_simhash) for a in l1_result
    ]
    keep_indices = dedup_by_simhash(fingerprints, SIMHASH_THRESHOLD)
    l2_result = [l1_result[i] for i in keep_indices]
    l2_removed = len(l1_result) - len(l2_result)
    logger.info("L2 SimHash 去重: %d → %d (%d 篇近似重复)", len(l1_result), len(l2_result), l2_removed)

    if len(l2_result) <= 1:
        return l2_result

    # ------- L3: Embedding 语义去重 -------
    l3_result = await _semantic_dedup(l2_result)
    l3_removed = len(l2_result) - len(l3_result)
    logger.info("L3 语义去重: %d → %d (%d 篇语义重复)", len(l2_result), len(l3_result), l3_removed)

    logger.info("去重完成: %d → %d 篇 (总计移除 %d 篇)", total, len(l3_result), total - len(l3_result))
    return l3_result


async def _semantic_dedup(articles: list[CleanArticle]) -> list[CleanArticle]:
    """
    L3: 基于 Embedding 余弦相似度的语义去重

    如果 Embedding 模型不可用，跳过此层
    """
    from app.processors.clusterer import get_embedding_model

    model = get_embedding_model()
    if model is None:
        logger.info("Embedding 模型不可用，跳过 L3 语义去重")
        return articles

    if len(articles) <= 1:
        return articles

    # 批量编码
    texts = [a.text_for_embedding for a in articles]
    try:
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
    except Exception as e:
        logger.warning("Embedding 编码失败，跳过 L3 语义去重: %s", e)
        return articles

    # 余弦相似度矩阵
    embeddings = np.array(embeddings)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = embeddings / norms
    sim_matrix = np.dot(normalized, normalized.T)

    # 贪心去重：顺序遍历，标记与已保留文章相似度过高的文章
    n = len(articles)
    keep_mask = np.ones(n, dtype=bool)

    for i in range(n):
        if not keep_mask[i]:
            continue
        # 找到与 i 相似度 > 阈值且索引 > i 的文章
        for j in range(i + 1, n):
            if keep_mask[j] and sim_matrix[i, j] > EMBEDDING_THRESHOLD:
                keep_mask[j] = False

    result = [articles[i] for i in range(n) if keep_mask[i]]
    return result

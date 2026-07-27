"""
混合检索器 — 多路召回 + RRF 合并

双路召回策略：
  - BM25 关键词: OpenSearch multi_match（优先）/ 本地 TF-IDF（降级）
  - kNN 向量语义: BGE Embedding + cosine similarity（优先）/ SimHash（降级）

合并策略：Reciprocal Rank Fusion (RRF)，k=60
"""

import logging
import asyncio

import numpy as np

from app.models.article import CleanArticle

logger = logging.getLogger(__name__)

RRF_K = 60


async def bm25_search(
    query: str,
    corpus: list[CleanArticle],
    top_k: int = 20,
) -> list[tuple[CleanArticle, float]]:
    """
    BM25 关键词检索

    优先使用 OpenSearch multi_match，不可用时降级为本地 TF-IDF
    """
    # 尝试 OpenSearch 检索
    from app.rag.es_indexer import get_os_client

    client = get_os_client()
    if client is not None:
        try:
            return await _os_bm25_search(client, query, top_k)
        except Exception as e:
            logger.warning("OpenSearch BM25 检索失败，降级为本地 TF-IDF: %s", e)

    # 降级：本地 TF-IDF
    return _local_tfidf_search(query, corpus, top_k)


async def _os_bm25_search(client, query: str, top_k: int) -> list[tuple[CleanArticle, float]]:
    """OpenSearch multi_match 检索"""
    from app.config import get_settings

    settings = get_settings()
    index_name = settings.os.OS_INDEX

    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "content"],
                "type": "best_fields",
            }
        },
        "size": top_k,
    }

    resp = client.search(index=index_name, body=body)
    hits = resp.get("hits", {}).get("hits", [])

    results = []
    for hit in hits:
        source = hit.get("_source", {})
        score = hit.get("_score", 0)
        try:
            article = CleanArticle(**source)
            results.append((article, score))
        except Exception:
            continue

    return results


def _local_tfidf_search(
    query: str,
    corpus: list[CleanArticle],
    top_k: int,
) -> list[tuple[CleanArticle, float]]:
    """本地 TF-IDF 检索（ES 不可用时的降级方案）"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if not corpus:
        return []

    # 构建文档文本
    docs = [f"{a.title} {a.cleaned_content[:500]}" for a in corpus]
    all_texts = [query] + docs

    try:
        vectorizer = TfidfVectorizer(
            max_features=5000,
            token_pattern=r"(?u)\b[a-zA-Z]{2,}\b|[一-鿿]{1,}",
        )
        tfidf = vectorizer.fit_transform(all_texts)
        query_vec = tfidf[0:1]
        doc_vecs = tfidf[1:]

        scores = cosine_similarity(query_vec, doc_vecs).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [(corpus[i], float(scores[i])) for i in top_indices if scores[i] > 0]
    except Exception as e:
        logger.warning("本地 TF-IDF 检索失败: %s", e)
        return []


async def knn_search(
    query: str,
    corpus: list[CleanArticle],
    top_k: int = 20,
) -> list[tuple[CleanArticle, float]]:
    """
    向量语义检索

    优先使用 BGE Embedding + cosine similarity，不可用时降级为 SimHash
    """
    if not corpus:
        return []

    from app.rag.embedding import encode_articles, encode_query

    # 尝试 BGE Embedding
    query_vec = encode_query(query)
    if query_vec is not None:
        texts = [a.text_for_embedding for a in corpus]
        doc_vecs = encode_articles(texts)
        if doc_vecs is not None:
            return _cosine_similarity_search(query_vec, doc_vecs, corpus, top_k)

    # 降级：SimHash 汉明距离
    logger.info("Embedding 模型不可用，降级为 SimHash 向量检索")
    return _simhash_search(query, corpus, top_k)


def _cosine_similarity_search(
    query_vec: np.ndarray,
    doc_vecs: np.ndarray,
    corpus: list[CleanArticle],
    top_k: int,
) -> list[tuple[CleanArticle, float]]:
    """余弦相似度检索"""
    # 归一化
    q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
    d_norm = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-8)
    scores = np.dot(d_norm, q_norm)

    top_indices = np.argsort(scores)[::-1][:top_k]
    return [(corpus[i], float(scores[i])) for i in top_indices if scores[i] > 0]


def _simhash_search(
    query: str,
    corpus: list[CleanArticle],
    top_k: int,
) -> list[tuple[CleanArticle, float]]:
    """SimHash 汉明距离检索（终极降级）"""
    from app.processors.simhash import compute_fingerprint, hamming_distance

    query_fp = compute_fingerprint(query)
    scored = []
    for a in corpus:
        fp = compute_fingerprint(a.text_for_simhash)
        dist = hamming_distance(query_fp, fp)
        # 汉明距离越小越相似，转换为相似度分数
        score = 1.0 - (dist / 64.0)
        scored.append((a, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


async def hybrid_search(
    query: str,
    corpus: list[CleanArticle],
    top_k_knn: int = 20,
    top_k_bm25: int = 20,
    final_top_k: int = 20,
) -> list[tuple[CleanArticle, float]]:
    """
    混合检索：BM25 + kNN 双路召回 → RRF 合并

    Args:
        query: 检索查询
        corpus: 文章语料库
        top_k_knn: kNN 路召回数
        top_k_bm25: BM25 路召回数
        final_top_k: 最终返回数

    Returns:
        [(article, rrf_score), ...] 按分数降序排列
    """
    if not corpus:
        return []

    # 并发执行双路召回
    bm25_task = bm25_search(query, corpus, top_k_bm25)
    knn_task = knn_search(query, corpus, top_k_knn)

    bm25_results, knn_results = await asyncio.gather(bm25_task, knn_task, return_exceptions=True)

    if isinstance(bm25_results, Exception):
        logger.warning("BM25 检索异常: %s", bm25_results)
        bm25_results = []
    if isinstance(knn_results, Exception):
        logger.warning("kNN 检索异常: %s", knn_results)
        knn_results = []

    # RRF 合并
    scores: dict[str, tuple[CleanArticle, float]] = {}

    for rank, (article, _) in enumerate(bm25_results):
        rrf = 1.0 / (RRF_K + rank + 1)
        scores[article.id] = (article, scores.get(article.id, (article, 0))[1] + rrf)

    for rank, (article, _) in enumerate(knn_results):
        rrf = 1.0 / (RRF_K + rank + 1)
        scores[article.id] = (article, scores.get(article.id, (article, 0))[1] + rrf)

    # 按 RRF 分数降序
    merged = sorted(scores.values(), key=lambda x: x[1], reverse=True)
    return merged[:final_top_k]

"""
HDBSCAN 语义聚类处理器

功能：
  - 文章向量化（委托给 rag.embedding）
  - PCA 降维（可选）
  - HDBSCAN 聚类
  - 关键词提取（TF-IDF）
"""

import logging
import math
from collections import Counter

import numpy as np
from hdbscan import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer

# 从 rag.embedding 导入 Embedding 服务（共享单例）
from app.rag.embedding import get_embedding_model, encode_articles  # noqa: F401 — 重新导出给旧调用方

logger = logging.getLogger(__name__)


def reduce_dimensions(embeddings: np.ndarray, target_dim: int = 128) -> np.ndarray:
    """
    PCA 降维

    Args:
        embeddings: (n, d) 矩阵
        target_dim: 目标维度

    Returns:
        (n, target_dim) 矩阵
    """
    n_samples = embeddings.shape[0]
    actual_dim = min(target_dim, n_samples - 1, embeddings.shape[1])

    if actual_dim >= embeddings.shape[1]:
        return embeddings

    pca = PCA(n_components=actual_dim, random_state=42)
    return pca.fit_transform(embeddings)


def cluster_hdbscan(
    vectors: np.ndarray,
    min_cluster_size: int = 3,
    min_samples: int = 1,
) -> np.ndarray:
    """
    HDBSCAN 聚类

    Args:
        vectors: (n, d) 特征矩阵
        min_cluster_size: 最小簇大小
        min_samples: 最小样本数

    Returns:
        (n,) 标签数组，-1 表示噪声点
    """
    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",  # Excess of Mass
    )
    return clusterer.fit_predict(vectors)


def extract_keywords(texts: list[str], top_n: int = 5) -> list[str]:
    """
    用 TF-IDF 提取关键词

    Args:
        texts: 文本列表（一个簇内的所有文章文本）
        top_n: 返回关键词数量

    Returns:
        关键词列表
    """
    if not texts or len(texts) < 2:
        # 回退：简单词频统计
        word_counter = Counter()
        for text in texts:
            # 提取中英文词
            import re

            words = re.findall(r"[一-鿿]{2,}|[a-zA-Z]{3,}", text.lower())
            word_counter.update(words)
        return [w for w, _ in word_counter.most_common(top_n)]

    try:
        vectorizer = TfidfVectorizer(
            max_features=50,
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z]{3,}\b|[一-鿿]{2,}",
        )
        tfidf = vectorizer.fit_transform(texts)
        scores = np.array(tfidf.sum(axis=0)).flatten()
        indices = np.argsort(scores)[::-1][:top_n]
        feature_names = vectorizer.get_feature_names_out()
        return [feature_names[i] for i in indices]
    except Exception as e:
        logger.warning("TF-IDF 关键词提取失败: %s", e)
        return []


def compute_importance(article_count: int, total_articles: int) -> int:
    """
    基于簇大小计算重要性评分（LLM 不可用时的 fallback）

    使用线性映射代替原来的对数缩放，避免全部挤在 10 分：
      - 占比 0-10%   → 1-3 分
      - 占比 10-25%  → 4-6 分
      - 占比 25-50%  → 7-8 分
      - 占比 50%+    → 9-10 分

    Args:
        article_count: 簇内文章数
        total_articles: 总文章数

    Returns:
        1-10 的评分
    """
    if total_articles == 0:
        return 5

    ratio = article_count / total_articles
    # 线性映射到 1-10，确保小簇和大簇之间有区分度
    score = int(1 + 9 * ratio)
    return min(10, max(1, score))

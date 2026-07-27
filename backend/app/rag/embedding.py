"""
BGE Embedding 服务

提供文本向量化的统一入口。
模型延迟加载 + 单例缓存，不可用时优雅降级为 None。

从 processors/clusterer.py 迁移而来，作为 RAG 模块的共用基础。
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# 全局模型缓存（单例）
_embedding_model = None


def get_embedding_model():
    """延迟加载 sentence-transformers 模型（单例）"""
    global _embedding_model
    if _embedding_model is None:
        from app.config import get_settings

        settings = get_settings()
        model_name = settings.embedding.EMBEDDING_MODEL
        device = settings.embedding.EMBEDDING_DEVICE

        logger.info("加载 Embedding 模型: %s (device=%s)", model_name, device)
        try:
            from sentence_transformers import SentenceTransformer

            _embedding_model = SentenceTransformer(model_name, device=device)
            dims = _embedding_model.get_sentence_embedding_dimension()
            logger.info("Embedding 模型加载完成，维度: %d", dims)
        except Exception as e:
            logger.warning("无法加载 Embedding 模型 (%s)，将降级为 SimHash 模式: %s", model_name, e)
            _embedding_model = None

    return _embedding_model


def encode_articles(texts: list[str]) -> np.ndarray | None:
    """
    将文章文本列表编码为向量

    Args:
        texts: 文本列表

    Returns:
        shape (n, dim) 的 numpy 数组，或 None（模型不可用时）
    """
    model = get_embedding_model()
    if model is None:
        return None

    try:
        embeddings = model.encode(texts, show_progress_bar=False, batch_size=32)
        return np.array(embeddings)
    except Exception as e:
        logger.warning("Embedding 编码失败: %s", e)
        return None


def encode_query(text: str) -> np.ndarray | None:
    """
    将单条查询文本编码为向量

    Args:
        text: 查询文本

    Returns:
        shape (dim,) 的 numpy 数组，或 None（模型不可用时）
    """
    result = encode_articles([text])
    if result is not None and len(result) > 0:
        return result[0]
    return None

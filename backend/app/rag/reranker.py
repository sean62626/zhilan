"""
精排器 — BGE Cross-Encoder Reranker

对检索召回结果进行精细排序。
优先使用 BAAI/bge-reranker-v2-m3，不可用时降级为余弦相似度。
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# 全局模型缓存
_reranker_model = None


def get_reranker_model():
    """延迟加载 Cross-Encoder 模型（单例）"""
    global _reranker_model
    if _reranker_model is None:
        from app.config import get_settings

        settings = get_settings()
        model_name = settings.reranker.RERANKER_MODEL

        logger.info("加载 Reranker 模型: %s", model_name)
        try:
            from sentence_transformers import CrossEncoder

            _reranker_model = CrossEncoder(model_name)
            logger.info("Reranker 模型加载完成")
        except Exception as e:
            logger.warning("无法加载 Reranker 模型 (%s)，将降级为余弦相似度: %s", model_name, e)
            _reranker_model = None

    return _reranker_model


async def rerank(
    query: str,
    documents: list[tuple[object, float]],
    top_k: int = 8,
) -> list[tuple[object, float]]:
    """
    对召回的文档进行精排

    Args:
        query: 原始查询
        documents: [(doc, initial_score), ...] 召回的文档列表
        top_k: 保留数量

    Returns:
        [(doc, rerank_score), ...] 按精排分数降序
    """
    if not documents:
        return []

    if len(documents) <= top_k:
        return documents

    model = get_reranker_model()
    if model is None:
        # 降级：保持原排序
        logger.info("Reranker 不可用，使用原始检索分数")
        return documents[:top_k]

    # 准备文档文本
    docs = []
    for doc, _ in documents:
        if hasattr(doc, "text_for_embedding"):
            docs.append(doc.text_for_embedding)
        elif hasattr(doc, "cleaned_content"):
            docs.append(f"{getattr(doc, 'title', '')} {doc.cleaned_content[:300]}")
        else:
            docs.append(str(doc)[:500])

    # Cross-Encoder 批量预测
    try:
        pairs = [[query, doc_text] for doc_text in docs]
        scores = model.predict(pairs, show_progress_bar=False)

        # 排序
        ranked = sorted(
            zip(documents, scores, strict=False),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(doc, float(score)) for (doc, _), score in ranked[:top_k]]
    except Exception as e:
        logger.warning("Rerank 预测失败: %s", e)
        return documents[:top_k]

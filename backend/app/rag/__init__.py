"""
RAG 模块 — 检索增强生成

embedding  — BGE 文本向量化服务
retriever — 混合检索（OpenSearch BM25 + 本地 kNN）
reranker  — BGE Cross-Encoder 精排
context   — 上下文组装 + Token 估算
es_indexer — OpenSearch 索引管理
"""

from app.rag import embedding, retriever, reranker, context, es_indexer

__all__ = ["embedding", "retriever", "reranker", "context", "es_indexer"]

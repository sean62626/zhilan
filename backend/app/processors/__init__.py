"""
文本处理模块

cleaner   — HTML 清洗 · 文本规范化 · 语言检测
segmenter — 智能分段 · RecursiveCharacterTextSplitter
simhash   — SimHash 指纹 · 汉明距离比较
clusterer — BGE 向量化 · HDBSCAN 聚类 · 关键词提取
"""

from app.processors import cleaner, segmenter, simhash, clusterer

__all__ = ["cleaner", "segmenter", "simhash", "clusterer"]

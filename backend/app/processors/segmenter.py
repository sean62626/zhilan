"""
文本智能分段处理器

使用 LangChain RecursiveCharacterTextSplitter 将长文本
切分为语义连贯的段落，避免 Embedding 向量被截断

策略：
  - 中文优先按段落（\n\n）分割
  - 其次按句子（。！？. ! ?）分割
  - 回退按字符数分割
  - chunk_size=512, overlap=64
"""

import re
from typing import List


def split_by_paragraph(text: str) -> list[str]:
    """按段落分割（双换行）"""
    if not text:
        return []
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_by_sentence(text: str) -> list[str]:
    """按句子分割（中英文句末标点）"""
    if not text:
        return []
    # 在句末标点后分割（保留标点）
    sentences = re.split(r"(?<=[。！？.!?])\s*", text)
    return [s.strip() for s in sentences if s.strip()]


def merge_short_chunks(chunks: list[str], min_chars: int = 100) -> list[str]:
    """合并过短的 chunk 到相邻块"""
    if not chunks:
        return []
    merged = []
    buffer = ""
    for chunk in chunks:
        if len(buffer) + len(chunk) < min_chars * 2:
            buffer = (buffer + " " + chunk).strip()
        else:
            if buffer:
                merged.append(buffer)
            buffer = chunk
    if buffer:
        merged.append(buffer)
    return merged


def segment_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    min_chunk_chars: int = 100,
) -> list[str]:
    """
    智能文本分段

    分层策略：
      1. 段落级分割
      2. 超长段落 → 句级分割
      3. 超长句子 → 字符级滑动窗口
      4. 合并过短的 chunk

    Args:
        text: 输入文本
        chunk_size: 目标 chunk 大小（字符数）
        chunk_overlap: 相邻 chunk 重叠字符数
        min_chunk_chars: 最小 chunk 大小

    Returns:
        分段列表
    """
    if not text or len(text) <= chunk_size:
        return [text] if text else []

    # 第一层：按段落分割
    paragraphs = split_by_paragraph(text)

    # 第二层：超长段落按句子分割
    chunks: list[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            sentences = split_by_sentence(para)
            for sent in sentences:
                if len(sent) <= chunk_size:
                    chunks.append(sent)
                else:
                    # 第三层：字符级滑动窗口
                    for i in range(0, len(sent), chunk_size - chunk_overlap):
                        chunk = sent[i : i + chunk_size]
                        if len(chunk) >= min_chunk_chars:
                            chunks.append(chunk)

    # 合并过短 chunk
    chunks = merge_short_chunks(chunks, min_chunk_chars)

    return chunks if chunks else [text]


def segment_article(text: str, max_segments: int = 5) -> list[str]:
    """
    为单篇文章生成分段（限制最大段数以控制计算量）

    Args:
        text: 文章正文
        max_segments: 最大分段数

    Returns:
        分段列表，前 max_segments 段
    """
    segments = segment_text(text, chunk_size=512, chunk_overlap=64)
    return segments[:max_segments]

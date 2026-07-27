"""
上下文组装 — Token 估算 + 截断 + 引用格式化

将 RAG 检索结果组装为 LLM 可消费的上下文文本。
"""

import re
from datetime import datetime


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数

    中文约 1.5 chars/token，英文约 4 chars/token
    混合文本取 2.5 chars/token 作为折中估计

    Args:
        text: 输入文本

    Returns:
        估算 token 数
    """
    if not text:
        return 0

    # 分别统计中文字符和英文字符
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    other_chars = len(text) - chinese_chars

    # 中文 ~1.5 chars/token, 英文/其他 ~4 chars/token
    chinese_tokens = chinese_chars / 1.5
    other_tokens = other_chars / 4.0

    return int(chinese_tokens + other_tokens)


def assemble_context(
    documents: list[tuple[object, float]],
    max_tokens: int = 8000,
) -> str:
    """
    将检索到的文档组装为上下文文本

    策略：逐文档追加，超过 max_tokens 时截断
    每个文档包含标题 + 内容摘要 + 来源信息

    Args:
        documents: [(doc, score), ...] 已排序的文档列表
        max_tokens: 上下文最大 token 数

    Returns:
        拼接后的上下文字符串
    """
    if not documents:
        return "（无额外上下文）"

    parts = []
    current_tokens = 0
    include_count = 0

    for i, (doc, score) in enumerate(documents):
        # 构建文档摘要文本
        title = getattr(doc, "title", "无标题")
        content = getattr(doc, "cleaned_content", "") or getattr(doc, "content", "")
        source = getattr(doc, "source_name", "") or getattr(doc, "source", "")
        url = getattr(doc, "url", "")
        published_at = getattr(doc, "published_at", None)

        # 内容截取（每篇最多 1000 字符）
        content_snippet = content[:1000] if content else ""

        # 格式化时间
        time_str = ""
        if published_at:
            if isinstance(published_at, datetime):
                time_str = published_at.strftime("%Y-%m-%d")
            elif isinstance(published_at, str):
                time_str = published_at[:10]

        doc_text = f"[{i + 1}] **{title}**\n"
        if source or time_str:
            doc_text += f"    来源: {source} | {time_str}\n"
        if url:
            doc_text += f"    URL: {url}\n"
        if content_snippet:
            doc_text += f"    {content_snippet}\n"

        doc_tokens = estimate_tokens(doc_text)

        if current_tokens + doc_tokens > max_tokens:
            # 剩余空间不足，尝试截取更短内容
            if include_count >= 3:
                break
            short_text = f"[{i + 1}] **{title}**\n    来源: {source}\n    {content_snippet[:300]}\n"
            short_tokens = estimate_tokens(short_text)
            if current_tokens + short_tokens <= max_tokens:
                parts.append(short_text)
                current_tokens += short_tokens
                include_count += 1
            break

        parts.append(doc_text)
        current_tokens += doc_tokens
        include_count += 1

    return "\n".join(parts) if parts else "（无额外上下文）"


def format_references(documents: list[tuple[object, float]]) -> list[dict]:
    """
    将文档列表格式化为引用信息

    Args:
        documents: [(doc, score), ...]

    Returns:
        [{title, url, source, published_at}, ...]
    """
    refs = []
    for doc, _ in documents:
        title = getattr(doc, "title", "无标题")
        url = getattr(doc, "url", "")
        source = getattr(doc, "source_name", "") or getattr(doc, "source", "")
        published_at = getattr(doc, "published_at", None)

        ref = {
            "title": title,
            "url": url,
            "source": source,
        }
        if published_at:
            if isinstance(published_at, datetime):
                ref["published_at"] = published_at.isoformat()
            else:
                ref["published_at"] = str(published_at)

        refs.append(ref)

    return refs

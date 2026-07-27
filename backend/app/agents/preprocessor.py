"""
PreprocessAgent — 文本预处理

职责：
  1. HTML 标签清洗
  2. 广告/导航文本剥离
  3. 空白规范化
  4. 语言检测
  5. 空文章过滤

输入: RawArticle[] → 输出: CleanArticle[]
"""

import logging

from app.models.article import RawArticle, CleanArticle
from app.processors.cleaner import clean_text, detect_language

logger = logging.getLogger(__name__)


async def run_preprocess(articles: list[RawArticle]) -> list[CleanArticle]:
    """
    对采集到的原始文章进行清洗

    处理每篇文章：清洗正文 + 检测语言 + 构造 CleanArticle
    """
    clean_articles: list[CleanArticle] = []
    skipped_empty = 0

    for raw in articles:
        # 清洗正文
        cleaned = clean_text(raw.content)
        # 如正文为空，尝试用 summary
        if not cleaned and raw.summary:
            cleaned = clean_text(raw.summary)

        if not cleaned or len(cleaned) < 50:
            skipped_empty += 1
            continue

        # 检测语言
        lang = detect_language(f"{raw.title} {cleaned[:200]}")

        clean = CleanArticle(
            id=raw.id,
            title=raw.title,
            url=raw.url,
            content=raw.content,
            cleaned_content=cleaned,
            summary=raw.summary,
            source=raw.source,
            source_name=raw.source_name,
            language=lang,
            published_at=raw.published_at,
            collected_at=raw.collected_at,
            metadata=raw.metadata,
        )
        clean_articles.append(clean)

    logger.info(
        "预处理完成: %d → %d 篇 (%d 篇因内容过短跳过)",
        len(articles), len(clean_articles), skipped_empty,
    )
    return clean_articles

"""
NewsAPI 采集器

调用 NewsAPI /v2/everything 接口获取新闻
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings
from app.models.article import RawArticle

logger = logging.getLogger(__name__)

# NewsAPI 免费版每日请求配额
FREE_TIER_DAILY_LIMIT = 100


async def collect(config: dict) -> list[RawArticle]:
    """
    从 NewsAPI 采集新闻

    config 格式（来自 sources.yaml）:
        {base_url, languages, page_size, query_topics}

    返回值附带诊断信息（通过 _collect_diagnostics 模块级变量传递，
    供 CollectorAgent 汇总报告使用）。
    """
    global _last_diagnostics
    _last_diagnostics = {"api_key_configured": False, "quota_exhausted": False,
                         "api_error": None, "total_calls": 0, "rate_limited_calls": 0}

    settings = get_settings()
    api_key = settings.collector.NEWSAPI_KEY

    if api_key == "xxx" or not api_key:
        logger.warning("NewsAPI key 未配置（NEWSAPI_KEY=%s），跳过采集", api_key[:8] if api_key else "空")
        _last_diagnostics["reason"] = "API key 未配置，请在 .env 中设置 NEWSAPI_KEY"
        return []

    _last_diagnostics["api_key_configured"] = True

    base_url = config.get("base_url", "https://newsapi.org/v2")
    languages = config.get("languages", ["zh"])
    page_size = config.get("page_size", 50)
    # 优先使用工作流传入的用户主题，其次 sources.yaml 配置
    if "_topics" in config:
        topics = config["_topics"]
        if not topics:
            logger.warning("NewsAPI: _topics 为空列表，跳过采集")
            _last_diagnostics["reason"] = "用户主题为空，无关键词可搜索"
            return []
    else:
        topics = config.get("query_topics", ["财经", "科技", "宏观经济"])
    logger.info("[newsapi] 最终搜索主题: %s (语言: %s)", topics, languages)

    articles: list[RawArticle] = []
    rate_limited = False
    total_calls = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for lang in languages:
            if rate_limited:
                break
            for topic in topics:
                if rate_limited:
                    break
                # 跳过语言明显不匹配的组合，节省 API 配额
                if not _topic_matches_language(topic, lang):
                    continue
                total_calls += 1
                try:
                    # 免费版有 24h 文章延迟，用 48h 前作为安全窗口
                    from_date = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
                    params = {
                        "q": topic,
                        "language": lang,
                        "pageSize": min(page_size, 100),
                        "sortBy": "publishedAt",
                        "apiKey": api_key,
                        "from": from_date,
                    }
                    resp = await client.get(f"{base_url}/everything", params=params)
                    resp.raise_for_status()
                    data = resp.json()

                    if data.get("status") != "ok":
                        error_msg = data.get("message", "未知错误")
                        logger.error("NewsAPI 返回错误 [%s/%s]: %s", lang, topic, error_msg)
                        if "rate" in error_msg.lower() or "quota" in error_msg.lower() or "limit" in error_msg.lower():
                            rate_limited = True
                            _last_diagnostics["quota_exhausted"] = True
                            _last_diagnostics["api_error"] = error_msg
                            break
                        continue

                    new_count = 0
                    for item in data.get("articles", []):
                        url = item.get("url", "")
                        if not url:
                            continue
                        article = RawArticle(
                            id=RawArticle.make_id(url),
                            title=item.get("title", "无标题"),
                            url=url,
                            content=item.get("content", "") or "",
                            summary=item.get("description"),
                            source="newsapi",
                            source_name=item.get("source", {}).get("name", "NewsAPI"),
                            language=lang,
                            published_at=_parse_date(item.get("publishedAt")),
                            metadata={"author": item.get("author")},
                        )
                        articles.append(article)
                        new_count += 1

                    logger.info("NewsAPI [%s/%s]: 获取到 %d 篇文章", lang, topic, new_count)

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logger.warning("NewsAPI 日配额已耗尽 (429 Too Many Requests)，停止后续请求")
                        rate_limited = True
                        _last_diagnostics["quota_exhausted"] = True
                        _last_diagnostics["api_error"] = "日配额耗尽 (429)"
                        _last_diagnostics["rate_limited_calls"] += 1
                        break
                    elif e.response.status_code == 401:
                        logger.error("NewsAPI key 无效 (401 Unauthorized)，请检查 NEWSAPI_KEY")
                        _last_diagnostics["api_error"] = "API key 无效 (401)"
                        rate_limited = True
                        break
                    else:
                        logger.error("NewsAPI HTTP %d [%s/%s]: %s", e.response.status_code, lang, topic, e)
                except httpx.RequestError as e:
                    logger.error("NewsAPI 网络错误 [%s/%s]: %s", lang, topic, e)
                except Exception as e:
                    logger.error("NewsAPI 解析异常 [%s/%s]: %s", lang, topic, e)

    _last_diagnostics["total_calls"] = total_calls

    if rate_limited and not articles:
        _last_diagnostics["reason"] = (
            f"NewsAPI 日配额耗尽（免费版 {FREE_TIER_DAILY_LIMIT} 次/天），"
            f"请等待明天 UTC+0 重置或升级付费计划"
        )
    elif not articles and total_calls > 0:
        _last_diagnostics["reason"] = (
            f"已调用 {total_calls} 次 API 但未获取到文章，"
            f"可能是搜索关键词在 48h 窗口内无匹配新闻"
        )

    return articles


# 模块级诊断信息（供 CollectorAgent 读取）
_last_diagnostics: dict = {
    "api_key_configured": False,
    "quota_exhausted": False,
    "api_error": None,
    "total_calls": 0,
    "rate_limited_calls": 0,
    "reason": None,
}


def get_diagnostics() -> dict:
    """返回最近一次采集的诊断信息"""
    return _last_diagnostics


def _parse_date(date_str: str | None) -> datetime | None:
    """解析 ISO 8601 日期字符串"""
    if not date_str:
        return None
    try:
        # Python 3.11+ 支持 Z 后缀
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _topic_matches_language(topic: str, lang: str) -> bool:
    """判断关键词是否可能在该语言新闻中出现

    宽松策略（避免过度过滤浪费配额）：
    - 短词（≤4 字符）对所有语言开放 — "AI"、"5G"、"ETF" 在中文媒体中也很常见
    - 长中文词 → 仅中文搜索
    - 长英文词 → 仅英文搜索
    """
    is_ascii = all(ord(c) < 128 for c in topic)
    # 短词（如 "AI", "5G", "ETF", "GDP"）对所有语言开放
    if len(topic) <= 4:
        return True
    # 长词按脚本过滤
    if lang == "zh" and is_ascii:
        return False
    if lang == "en" and not is_ascii:
        return False
    return True

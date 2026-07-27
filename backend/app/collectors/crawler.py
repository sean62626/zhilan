"""
自定义爬虫采集器

通过 httpx + BeautifulSoup 从财经新闻网站提取文章
Phase 2 策略：
  1. 拉取目标页面
  2. 提取文章链接列表（a[href] 含日期/文章路径特征）
  3. 逐个抓取文章页，提取标题 + 正文

支持 _deadline 配置（由 CollectorAgent 注入），超时前主动返回已抓取结果。
"""

import asyncio
import logging
import re
import time as _time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.models.article import RawArticle

logger = logging.getLogger(__name__)

# 每篇文章最大抓取字符数
MAX_CONTENT_CHARS = 5000
# 每源最多抓取文章数
MAX_ARTICLES_PER_SOURCE = 20
# 请求间隔（秒）
REQUEST_DELAY = 2.0
# 单个列表页拉取超时（秒）
LIST_PAGE_TIMEOUT = 20.0
# 单篇文章抓取超时（秒）
ARTICLE_FETCH_TIMEOUT = 15.0
# 硬 deadline 前的安全余量（秒）— 留时间返回结果
DEADLINE_MARGIN = 8.0


async def collect(config: dict) -> list[RawArticle]:
    """
    从配置的目标网站抓取新闻

    config 格式（来自 sources.yaml）:
        {targets: [{name, url}], _deadline?: float}

    支持 _deadline（Unix monotonic 时间戳），超时前主动返回已抓取结果。
    """
    targets = config.get("targets", [])
    if not targets:
        logger.warning("未配置爬虫目标")
        return []

    deadline = config.get("_deadline")  # None 表示无超时限制

    articles: list[RawArticle] = []

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        follow_redirects=True,
    ) as client:
        for target in targets:
            # 检查 deadline
            if deadline and _time.monotonic() > deadline - DEADLINE_MARGIN:
                logger.warning("爬虫: 接近超时，跳过剩余目标（已抓 %d 篇）", len(articles))
                break

            name = target.get("name", "未知")
            url = target.get("url", "")
            if not url:
                continue

            try:
                source_articles = await _scrape_target(client, name, url, deadline)
                articles.extend(source_articles)
                logger.info("爬虫 [%s]: 获取到 %d 篇文章", name, len(source_articles))

            except Exception as e:
                logger.error("爬虫 [%s] 采集失败: %s", name, e)

    return articles


def _make_soup(html: str) -> BeautifulSoup:
    """解析 HTML，依次尝试 lxml → html.parser"""
    for parser in ("lxml", "html.parser"):
        try:
            return BeautifulSoup(html, parser)
        except Exception:
            continue
    # 最后的兜底
    return BeautifulSoup(html, "html.parser")


async def _scrape_target(
    client: httpx.AsyncClient, name: str, base_url: str,
    deadline: float | None = None,
) -> list[RawArticle]:
    """抓取单个目标站点，deadline 超时前返回已抓取结果"""
    # 步骤 1：拉取列表页
    try:
        resp = await client.get(base_url, timeout=LIST_PAGE_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error("爬虫 [%s]: HTTP %d — %s", name, e.response.status_code,
                     "404 页面不存在" if e.response.status_code == 404 else "可能被反爬拦截")
        return []
    except httpx.RequestError as e:
        logger.error("爬虫 [%s]: 网络请求失败 — %s", name, e)
        return []

    # 自动检测编码
    try:
        resp.encoding = _detect_encoding(resp)
    except Exception:
        pass

    html_text = resp.text
    logger.debug("爬虫 [%s]: 列表页拉取成功, HTML 长度=%d", name, len(html_text))

    soup = _make_soup(html_text)

    # 步骤 2：提取文章链接
    article_links = _extract_article_links(soup, base_url)
    if not article_links:
        logger.warning("爬虫 [%s]: 未找到文章链接 (HTML=%d字节, 页面可能需 JS 渲染，或 URL 已失效)", name, len(html_text))
        return []

    logger.info("爬虫 [%s]: 找到 %d 个文章链接", name, len(article_links))

    # 限制数量
    article_links = article_links[:MAX_ARTICLES_PER_SOURCE]

    # 步骤 3：逐个抓取文章详情
    articles: list[RawArticle] = []
    for i, link in enumerate(article_links):
        # 检查 deadline — 超时前返回已抓取结果，不丢弃
        if deadline and _time.monotonic() > deadline - DEADLINE_MARGIN:
            logger.warning("爬虫 [%s]: 接近超时，已抓 %d/%d 篇，跳过剩余",
                           name, len(articles), len(article_links))
            break

        try:
            if i > 0:
                await asyncio.sleep(REQUEST_DELAY)
            article = await _fetch_article(client, link, source_name=name)
            if article:
                articles.append(article)
        except Exception as e:
            logger.debug("爬虫 [%s]: 抓取文章失败 %s — %s", name, link, e)
            continue

    return articles


def _extract_article_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """从列表页提取文章链接"""
    links: list[str] = []
    seen: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        # 过滤非文章链接
        if not href or href == "#" or href.startswith("javascript:"):
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # 只保留同一域名下的链接
        base_parsed = urlparse(base_url)
        if parsed.netloc != base_parsed.netloc:
            continue

        # 只保留路径看起来像文章的链接（含数字日期或 /a/ 路径段）
        path = parsed.path
        if not _looks_like_article(path):
            continue

        if full_url not in seen:
            seen.add(full_url)
            links.append(full_url)

    return links


def _looks_like_article(path: str) -> bool:
    """判断 URL 路径是否像文章详情页"""
    # 匹配中文财经站点的文章 URL 模式
    patterns = [
        r"/\d{6,}\.",            # 数字 ID + 扩展名: /1234567.shtml
        r"/a/\d",                # 东方财富: /a/202407261234567890
        r"/article/",
        r"/news/",
        r"/detail/",
        r"/doc-",                # 新浪: doc-xxxxx.shtml
        r"/\d{4}-\d{2}/\d{2}/",  # 日期路径 /2024/07/26/
        r"/\d{4}/\d{2}/\d{2}/",  # 日期路径 /2024/07/26/ (无前导斜杠变体)
        r"/gncj/",               # 新浪财经国内财经
        r"/cj/\d",               # 财经频道数字路径
        r"/roll/",               # 滚动新闻
        r"/cnews/",              # 东方财富要闻
    ]
    return any(re.search(p, path) for p in patterns)


async def _fetch_article(
    client: httpx.AsyncClient, url: str, source_name: str
) -> RawArticle | None:
    """抓取单篇文章详情"""
    resp = await client.get(url, timeout=ARTICLE_FETCH_TIMEOUT)
    if resp.status_code >= 400:
        return None

    resp.encoding = _detect_encoding(resp)
    soup = _make_soup(resp.text)

    # 提取标题
    title = _extract_title(soup)
    if not title or len(title) < 4:
        return None

    # 提取正文
    content = _extract_content(soup)
    if not content:
        return None

    # 提取发布时间
    published = _extract_published_time(soup)

    return RawArticle(
        id=RawArticle.make_id(url),
        title=title[:200],
        url=url,
        content=content[:MAX_CONTENT_CHARS],
        summary=None,
        source="crawler",
        source_name=source_name,
        language="zh",
        published_at=published,
        metadata={},
    )


def _detect_encoding(resp: httpx.Response) -> str:
    """从响应头或内容检测编码"""
    if resp.encoding:
        return resp.encoding
    # 从 HTML meta 标签检测
    match = re.search(rb'charset=["\']?([a-zA-Z0-9\-]+)', resp.content[:2048])
    if match:
        return match.group(1).decode("ascii")
    return "utf-8"


def _extract_title(soup: BeautifulSoup) -> str:
    """从文章页提取标题"""
    # 优先级：og:title → h1 → title 标签
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()

    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)

    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text(strip=True)

    return ""


def _extract_content(soup: BeautifulSoup) -> str:
    """从文章页提取正文"""
    # 尝试常见文章内容容器
    selectors = [
        "article",
        ".article-content",
        ".article-body",
        ".content",
        "#article-content",
        "#content",
        ".post-content",
        ".news-content",
        ".entry-content",
    ]

    for sel in selectors:
        container = soup.select_one(sel)
        if container:
            # 移除 script/style 标签
            for tag in container.find_all(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = container.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    # 回退：取 body 文本（去除导航等）
    body = soup.find("body")
    if body:
        for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = body.get_text(separator="\n", strip=True)
        return text[:MAX_CONTENT_CHARS]

    return ""


def _extract_published_time(soup: BeautifulSoup) -> datetime | None:
    """尝试从 meta 标签或 time 元素提取发布时间"""
    # meta 标签: article:published_time
    for meta_name in ["article:published_time", "pubdate", "publish-date"]:
        meta = soup.find("meta", {"name": meta_name}) or soup.find("meta", {"property": meta_name})
        if meta and meta.get("content"):
            try:
                return datetime.fromisoformat(meta["content"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

    # time 元素
    time_el = soup.find("time")
    if time_el and time_el.get("datetime"):
        try:
            return datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    return None

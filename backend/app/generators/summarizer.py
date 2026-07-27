"""
LLM 调用封装 — DeepSeek API + Query 改写 + 摘要生成

DeepSeek API 与 OpenAI 完全兼容，使用 httpx 直接调用。
所有调用均支持优雅降级：API 不可用时返回 None。
内置指数退避重试（最多 3 次），应对瞬时网络波动。
"""

import asyncio
import json
import logging
import re

import httpx

from app.config import get_settings
from app.generators.prompts import QUERY_REWRITE_PROMPT, SUMMARY_PROMPT

logger = logging.getLogger(__name__)

# 重试配置
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # 秒，指数退避：2s / 4s / 8s
_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


async def call_deepseek(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str | None:
    """
    调用 DeepSeek API（含指数退避重试）

    Args:
        messages: OpenAI 格式的消息列表
        temperature: 生成温度（0-2）
        max_tokens: 最大生成 token 数

    Returns:
        模型回复文本，失败返回 None

    可重试场景：超时 · 连接错误 · 5xx · 429 限流
    不重试场景：4xx（参数/认证错误，重试无意义）
    """
    settings = get_settings()
    api_key = settings.llm.DEEPSEEK_API_KEY

    if not api_key or api_key == "sk-xxx":
        logger.warning("DeepSeek API key 未配置，跳过 LLM 调用")
        return None

    url = f"{settings.llm.DEEPSEEK_BASE_URL}/chat/completions"

    payload = {
        "model": settings.llm.DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error: str | None = None

    for attempt in range(1 + _MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=80) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            last_error = f"HTTP {status}"
            if status in _RETRYABLE_HTTP_STATUS and attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "DeepSeek API HTTP %d（可重试），第 %d/%d 次，%.1fs 后重试",
                    status, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue
            # 4xx 等不可重试错误直接退出
            logger.error("DeepSeek API HTTP 错误 %d（不可重试）: %s", status, e.response.text[:300])
            return None

        except httpx.TimeoutException:
            last_error = "timeout"
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "DeepSeek API 超时，第 %d/%d 次重试，%.1fs 后重试",
                    attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("DeepSeek API 请求超时（已用尽 %d 次重试）", _MAX_RETRIES)
            return None

        except Exception as e:
            last_error = str(e)[:200]
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "DeepSeek API 调用异常（%s），第 %d/%d 次重试，%.1fs 后重试",
                    last_error, attempt + 1, _MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("DeepSeek API 调用失败（已用尽 %d 次重试）: %s", _MAX_RETRIES, e)
            return None

    logger.error("DeepSeek API 最终失败（%s），已重试 %d 次", last_error, _MAX_RETRIES)
    return None


async def rewrite_queries(
    topic_label: str,
    keywords: list[str],
    n: int = 4,
) -> list[str]:
    """
    Query 改写 — 将研究主题扩展为多角度检索查询

    Args:
        topic_label: 主题标签（如 "美联储加息 · A股影响"）
        keywords: 关键词列表
        n: 生成查询数量

    Returns:
        检索查询列表（LLM 不可用时回退为关键词组合）
    """
    prompt = QUERY_REWRITE_PROMPT.format(
        topic_label=topic_label,
        keywords=" · ".join(keywords) if keywords else topic_label,
        n=n,
    )

    response = await call_deepseek(
        messages=[
            {"role": "system", "content": "你是一名信息检索专家。请严格按照输出格式要求回答。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=500,
    )

    if response:
        # 解析 "- 查询文本" 格式
        queries = re.findall(r"-\s*(.+)", response)
        if queries:
            return [q.strip() for q in queries[:n]]

    # 回退：直接用主题和关键词作为查询
    fallback = [topic_label]
    if keywords:
        fallback.append(" · ".join(keywords[:2]))
    logger.info("Query 改写使用回退方案: %s", fallback)
    return fallback


async def generate_summary(
    title: str,
    content: str,
) -> str | None:
    """
    将长文章浓缩为核心摘要

    Args:
        title: 文章标题
        content: 文章正文

    Returns:
        核心要点文本，失败返回 None
    """
    # 控制输入长度
    content_snippet = content[:3000] if len(content) > 3000 else content

    prompt = SUMMARY_PROMPT.format(
        title=title,
        content=content_snippet,
    )

    return await call_deepseek(
        messages=[
            {"role": "system", "content": "你是一名专业新闻编辑，擅长提炼文章核心信息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=600,
    )

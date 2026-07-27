"""
研报撰写器 — 四段式结构化研报生成

基于 RAG 检索上下文 + DeepSeek，生成专业研报。
"""

import hashlib
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.generators.prompts import RESEARCH_REPORT_PROMPT
from app.generators.summarizer import call_deepseek

logger = logging.getLogger(__name__)


async def generate_report(
    cluster_label: str,
    keywords: list[str],
    context_text: str,
    references: list[dict],
    cluster_sources: str = "",
    review_feedback: dict | None = None,
) -> dict:
    """
    生成四段式结构化研报

    Args:
        cluster_label: 主题标签
        keywords: 关键词列表
        context_text: RAG 检索上下文（补充材料）
        references: 引用来源列表
        cluster_sources: 簇内文章内容（核心来源材料，来自聚类直出）
        review_feedback: 审核反馈 {fact_errors, hallucination_issues, suggestions}
                         重试时传入，用于指导 LLM 修正上一版的问题

    Returns:
        {
            "title": str,
            "background": str,
            "analysis": str,
            "outlook": str,
            "risk": str,
            "raw_text": str,
        }
    """
    settings = get_settings()
    model_name = settings.llm.DEEPSEEK_MODEL

    # 格式化引用（簇内文章 + RAG 补充）
    refs_text = ""
    for i, ref in enumerate(references):
        refs_text += f"[来源{i + 1}] {ref.get('title', '')} ({ref.get('source', '')})\n"

    # 兜底：如果没有簇内源材料，用 RAG 上下文填充
    if not cluster_sources.strip():
        cluster_sources = context_text or "（无可用来源材料）"

    title = f"「{cluster_label}」深度研报"
    prompt = RESEARCH_REPORT_PROMPT.format(
        title=title,
        cluster_sources=cluster_sources,
        context=context_text or "（无补充上下文）",
        references=refs_text if refs_text else "（无可用来源索引）",
    )

    # 重试时：注入审核反馈，指导 LLM 修正具体问题
    if review_feedback:
        feedback_text = _format_review_feedback(review_feedback)
        prompt += f"\n\n---\n⚠️ **上一版审核反馈 — 请务必修正以下问题：**\n{feedback_text}"

    response = await call_deepseek(
        messages=[
            {
                "role": "system",
                "content": "你是一名资深行业研究分析师。请严格按照四段式结构撰写专业研报，使用 Markdown 格式。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=4096,
    )

    if response:
        return _parse_report_sections(title, response, model_name)

    # LLM 不可用：返回关键词摘要
    logger.warning("LLM 不可用，返回回退研报")
    return _fallback_report(cluster_label, keywords, references)


def _parse_report_sections(title: str, raw_text: str, model: str) -> dict:
    """解析 LLM 输出为四段式结构"""
    import re

    # 提取各章节
    background = _extract_section(raw_text, r"一、事件背景", r"二、现状分析")
    analysis = _extract_section(raw_text, r"二、现状分析", r"三、趋势研判")
    outlook = _extract_section(raw_text, r"三、趋势研判", r"四、风险提示")
    risk = _extract_section(raw_text, r"四、风险提示", None)

    # 如果正则解析失败，返回原始文本
    if not any([background, analysis, outlook, risk]):
        return {
            "title": title,
            "background": "（解析失败，见原始文本）",
            "analysis": "",
            "outlook": "",
            "risk": "",
            "raw_text": raw_text,
            "model_used": model,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "title": title,
        "background": background.strip() or "（暂无内容）",
        "analysis": analysis.strip() or "（暂无内容）",
        "outlook": outlook.strip() or "（暂无内容）",
        "risk": risk.strip() or "（暂无内容）",
        "model_used": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_section(text: str, start_pattern: str, end_pattern: str | None) -> str:
    """从 Markdown 文本中提取指定章节"""
    import re

    # 匹配章节标题（支持 ### 和 ## 前缀）
    start_match = re.search(rf"(?:###\s*)?{start_pattern}", text)
    if not start_match:
        return ""

    start_pos = start_match.end()

    if end_pattern:
        end_match = re.search(rf"(?:###\s*)?{end_pattern}", text[start_pos:])
        if end_match:
            return text[start_pos : start_pos + end_match.start()].strip()

    return text[start_pos:].strip()


def _format_review_feedback(feedback: dict) -> str:
    """将审核反馈格式化为 LLM 可理解的修正指引"""
    lines = []

    fact_errors = feedback.get("fact_errors", [])
    if fact_errors:
        lines.append("**事实性错误（与原文不符，必须修正）：**")
        for err in fact_errors:
            lines.append(f"  - {err}")

    hallucinations = feedback.get("hallucination_issues", [])
    if hallucinations:
        lines.append("**幻觉问题（引用了不存在的实体/数据，必须删除或更正）：**")
        for h in hallucinations:
            lines.append(f"  - {h}")

    suggestions = feedback.get("suggestions", [])
    if suggestions:
        lines.append("**修改建议：**")
        for s in suggestions:
            lines.append(f"  - {s}")

    if not lines:
        return "（无具体反馈）"

    return "\n".join(lines)


def _fallback_report(topic_label: str, keywords: list[str], references: list[dict]) -> dict:
    """LLM 不可用时的回退报告"""
    kw_text = "、".join(keywords) if keywords else topic_label

    return {
        "title": f"「{topic_label}」摘要简报（离线模式）",
        "background": f"主题涉及关键词：{kw_text}。当前为离线模式生成的简报，未使用 LLM 深度分析。",
        "analysis": f"共引用 {len(references)} 篇相关报道。请配置 DeepSeek API Key 以获得完整的 AI 分析。",
        "outlook": "（离线模式暂不支持趋势研判）",
        "risk": "（离线模式暂不支持风险分析）",
        "raw_text": "",
        "model_used": "fallback",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

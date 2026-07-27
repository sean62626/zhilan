"""
ReviewAgent — 事实核查 + 幻觉检测 + 平衡性/完整性审核

职责：
  1. 对每篇研报进行四维度审核（事实、幻觉、平衡、完整）
  2. 调用 DeepSeek 结构化审核，解析输出为 ReviewResult
  3. LLM 不可用时自动宽松通过（不阻塞管道）

输入: ResearchReport dict[] + 原始语料 CleanArticle[]
输出: ReviewResult[]
"""

import logging
import re
from datetime import datetime, timezone

from app.models.report import ReviewResult
from app.generators.prompts import REVIEW_PROMPT
from app.generators.summarizer import call_deepseek

logger = logging.getLogger(__name__)


async def run_review(
    research_reports: list[dict],
    unique_articles: list[dict] | None = None,
) -> list[ReviewResult]:
    """
    对研报列表执行四维度审核

    Args:
        research_reports: 序列化的研报结果列表
           每个元素含 cluster_id, report(ResearchReport dict), queries_used 等
        unique_articles: 去重后的原始文章（用于事实核查溯源），可选

    Returns:
        ReviewResult 列表
    """
    if not research_reports:
        logger.info("无研报需要审核")
        return []

    # 构建文章索引（供事实核查溯源）
    article_index = _build_article_index(unique_articles or [])

    results: list[ReviewResult] = []

    for r in research_reports:
        report_dict = r.get("report")
        if not report_dict:
            # 研报生成失败，直接标记为不通过
            results.append(ReviewResult(
                report_id=r.get("cluster_id", "unknown"),
                cluster_id=r.get("cluster_id", 0),
                passed=False,
                completeness_passed=False,
                suggestions=["研报生成失败，无法审核"],
                model_used="system",
            ))
            continue

        report_id = report_dict.get("report_id", "")
        cluster_id = r.get("cluster_id", 0)
        cluster_label = report_dict.get("title", "")

        logger.info("审核研报: %s — %s", report_id, cluster_label)

        try:
            result = await _review_single(
                report_dict=report_dict,
                article_index=article_index,
                cluster_id=cluster_id,
            )
        except Exception as e:
            logger.error("审核异常 — %s: %s", report_id, e)
            result = ReviewResult(
                report_id=report_id,
                cluster_id=cluster_id,
                passed=True,  # 异常时宽松通过，不阻塞管道
                suggestions=[f"审核过程异常: {e}"],
                model_used="error",
            )

        results.append(result)

    passed_count = sum(1 for r in results if r.passed)
    logger.info("审核完成: %d/%d 通过", passed_count, len(results))

    return results


async def _review_single(
    report_dict: dict,
    article_index: dict[int, list[dict]],
    cluster_id: int,
) -> ReviewResult:
    """审核单篇研报"""

    report_id = report_dict.get("report_id", "")
    report_text = _format_report_for_review(report_dict)

    # 获取该簇关联的原始文章文本
    source_texts = _get_cluster_sources(cluster_id, article_index)

    # 调用 LLM 审核
    prompt = REVIEW_PROMPT.format(
        report_text=report_text,
        source_texts=source_texts,
    )

    response = await call_deepseek(
        messages=[
            {
                "role": "system",
                "content": "你是一名严格的审核编辑。请严格按照输出格式进行事实核查，输出结构化审核结果。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,  # 与 Research 保持一致
        max_tokens=1024,
    )

    if response:
        return _parse_review_response(report_id, cluster_id, response)

    # LLM 不可用 — 宽松通过
    logger.warning("LLM 不可用，审核宽松通过: %s", report_id)
    return ReviewResult(
        report_id=report_id,
        cluster_id=cluster_id,
        passed=True,
        suggestions=["（离线模式：审核宽松通过，建议配置 DeepSeek API Key 以获得自动审核）"],
        model_used="fallback",
    )


def _format_report_for_review(report: dict) -> str:
    """将研报 dict 格式化为审核用的纯文本"""
    parts = [
        f"标题: {report.get('title', '')}",
        f"一、事件背景:\n{report.get('background', '')}",
        f"二、现状分析:\n{report.get('analysis', '')}",
        f"三、趋势研判:\n{report.get('outlook', '')}",
        f"四、风险提示:\n{report.get('risk', '')}",
    ]
    return "\n\n".join(parts)


def _build_article_index(articles: list[dict]) -> dict[int, list[dict]]:
    """按 cluster_id 构建文章索引，用于审核时精准溯源"""
    index: dict[int, list[dict]] = {}
    for a in articles:
        cid = a.get("cluster_id")
        if cid is not None:
            index.setdefault(cid, []).append(a)
    # -1 为全局兜底（cluster_id 为 null 的文章 + 全部文章）
    index[-1] = articles
    return index


def _get_cluster_sources(cluster_id: int, article_index: dict[int, list[dict]]) -> str:
    """获取指定簇的原始来源文本（优先匹配簇内文章，回退全局）"""
    articles = article_index.get(cluster_id) or article_index.get(-1, [])

    if not articles:
        return "（无原始来源数据）"

    lines = []
    for i, a in enumerate(articles[:10]):
        title = a.get("title", "")
        content = a.get("cleaned_content", a.get("content", ""))[:500]
        source = a.get("source_name", a.get("source", ""))
        lines.append(f"[{i + 1}] {title} ({source})\n{content}\n")

    return "\n".join(lines) if lines else "（无原始来源数据）"


def _parse_review_response(report_id: str, cluster_id: int, raw_text: str) -> ReviewResult:
    """解析 LLM 审核输出为结构化 ReviewResult"""

    # 解析 "通过: [是/否]"
    passed = True
    passed_match = re.search(r"通过[：:]\s*(.+)", raw_text)
    if passed_match:
        passed_str = passed_match.group(1).strip()
        passed = "是" in passed_str and "否" not in passed_str

    # 解析各维度
    fact_errors = _extract_list_item(raw_text, r"事实错误[：:]")
    hallucination = _extract_list_item(raw_text, r"幻觉问题[：:]")
    suggestions = _extract_list_item(raw_text, r"修改建议[：:]")

    balance_passed = _check_dimension(raw_text, r"平衡性[：:]")
    completeness_passed = _check_dimension(raw_text, r"完整性[：:]")

    return ReviewResult(
        report_id=report_id,
        cluster_id=cluster_id,
        passed=passed,
        fact_errors=fact_errors,
        hallucination_issues=hallucination,
        balance_passed=balance_passed,
        completeness_passed=completeness_passed,
        suggestions=suggestions,
        raw_response=raw_text,
        model_used="deepseek",
    )


def _check_dimension(text: str, pattern: str) -> bool:
    """检查某维度是否通过"""
    match = re.search(rf"{pattern}\s*(.+)", text)
    if match:
        value = match.group(1).strip()
        return "通过" in value and "不通过" not in value
    return True  # 未找到则默认通过


def _extract_list_item(text: str, pattern: str) -> list[str]:
    """从审核输出中提取列表项"""
    match = re.search(rf"{pattern}\s*(.+?)(?=\n(?:通过|事实|幻觉|平衡|完整|修改)|$)", text, re.DOTALL)
    if not match:
        return []

    raw = match.group(1).strip()
    if not raw or raw in ("无", "无。", "（无）", "暂无"):
        return []

    # 尝试按行拆分
    items = []
    for line in raw.split("\n"):
        line = line.strip().lstrip("- ").lstrip("• ").strip()
        if line and len(line) > 3:
            items.append(line)

    return items if items else [raw]

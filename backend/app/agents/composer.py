"""
ComposeAgent — 日报/简报组装

职责：
  1. 汇总研报、聚类数据、审核结果
  2. 调用 DeepSeek 组装为结构化每日简报（DailyBrief）
  3. LLM 不可用时使用模板规则组装回退简报

输入: ResearchReport[] + ReviewResult[] + TopicCluster[] + 统计信息
输出: DailyBrief
"""

import logging
from datetime import datetime, timezone

from app.models.report import DailyBrief
from app.generators.prompts import COMPOSE_BRIEF_PROMPT
from app.generators.summarizer import call_deepseek

logger = logging.getLogger(__name__)


async def run_compose(
    research_reports: list[dict],
    review_results: list[dict] | None = None,
    topic_clusters: list[dict] | None = None,
    topics_detail: list[dict] | None = None,
    target_date: str = "",
    article_count: int = 0,
    run_id: str = "",
) -> DailyBrief:
    """
    组装每日简报

    Args:
        research_reports: 研报结果列表（含 report dict 和元信息）
        review_results: 审核结果列表
        topic_clusters: 主题簇列表
        topics_detail: 用户配置的结构化主题 [{"name": "科技", "keywords": [...]}, ...]
        target_date: 目标日期
        article_count: 原始文章总数
        run_id: 工作流运行 ID

    Returns:
        DailyBrief 对象
    """
    if review_results is None:
        review_results = []
    if topic_clusters is None:
        topic_clusters = []
    if topics_detail is None:
        topics_detail = []

    # 建立审核结果索引
    review_map: dict[str, dict] = {}
    for rv in review_results:
        review_map[rv.get("report_id", "")] = rv

    # 统计
    total_clusters = len(topic_clusters)
    total_reports = len(research_reports)
    passed_count = sum(1 for rv in review_results if rv.get("passed", False))

    # 构建研报摘要文本（供 LLM 使用）
    report_summaries = _build_report_summaries(research_reports, review_map)

    # 构建主题簇概览
    cluster_overview = _build_cluster_overview(topic_clusters)

    # 构建用户监控主题体系（供 LLM 对齐归类）
    user_topics_text = _build_user_topics_text(topics_detail)

    # 尝试 LLM 生成
    prompt = COMPOSE_BRIEF_PROMPT.format(
        total_articles=article_count,
        total_clusters=total_clusters,
        total_reports=total_reports,
        passed_reports=passed_count,
        report_summaries=report_summaries,
        cluster_overview=cluster_overview,
        user_topics=user_topics_text,
    )

    response = await call_deepseek(
        messages=[
            {
                "role": "system",
                "content": "你是一名资深财经主编，擅长编写信息密度高、结构清晰的每日简报。请严格按照输出格式使用 Markdown。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=4096,
    )

    if response:
        logger.info("LLM 日报生成成功")
        logger.info("LLM 日报 raw_text (前 800 字):\n%s", response[:800])
        return _build_brief_from_llm(
            raw_text=response,
            research_reports=research_reports,
            review_map=review_map,
            topic_clusters=topic_clusters,
            target_date=target_date,
            article_count=article_count,
            total_clusters=total_clusters,
            total_reports=total_reports,
            passed_count=passed_count,
            model_used="deepseek",
            run_id=run_id,
        )

    # 回退模式 — 模板组装
    logger.warning("LLM 不可用，使用模板组装日报")
    return _build_fallback_brief(
        research_reports=research_reports,
        review_map=review_map,
        topic_clusters=topic_clusters,
        topics_detail=topics_detail,
        target_date=target_date,
        article_count=article_count,
        total_clusters=total_clusters,
        total_reports=total_reports,
        passed_count=passed_count,
        run_id=run_id,
    )


# ========== 辅助函数 ==========


def _build_report_summaries(research_reports: list[dict], review_map: dict[str, dict]) -> str:
    """构建研报摘要文本（供 LLM prompt）"""
    if not research_reports:
        return "（暂无研报）"

    lines = []
    for i, r in enumerate(research_reports):
        report = r.get("report", {})
        if not report:
            continue

        title = report.get("title", "未命名")
        background = report.get("background", "")[:300]
        analysis = report.get("analysis", "")[:300]
        outlook = report.get("outlook", "")[:200]
        risk = report.get("risk", "")[:200]

        report_id = report.get("report_id", "")
        review = review_map.get(report_id, {})
        passed_str = "✅ 通过" if review.get("passed", True) else "⚠️ 有保留"

        lines.append(f"""### 研报 {i + 1}: {title} [{passed_str}]
**事件背景**: {background}
**现状分析**: {analysis}
**趋势研判**: {outlook}
**风险提示**: {risk}
""")

    return "\n---\n".join(lines)


def _build_cluster_overview(topic_clusters: list[dict]) -> str:
    """构建主题簇概览文本"""
    if not topic_clusters:
        return "（暂无聚类数据）"

    lines = []
    for c in sorted(topic_clusters, key=lambda x: x.get("importance", 0), reverse=True):
        label = c.get("label", "未命名")
        importance = c.get("importance", 0)
        count = c.get("article_count", 0)
        keywords = " · ".join(c.get("keywords", [])[:5])
        lines.append(f"- **{label}** (重要性: {importance}/10, {count} 篇) — {keywords}")

    return "\n".join(lines)


def _build_user_topics_text(topics_detail: list[dict]) -> str:
    """构建用户监控主题体系文本（供 LLM 理解用户关心的主题维度）

    用户配置了哪些主题、每个主题关注什么方向，LLM 需要将聚类结果归类到这些主题下。
    """
    if not topics_detail:
        return "（用户未配置特定监控主题，请自由组织日报结构）"

    lines = ["以下是用户配置的监控主题体系，请将今日的聚类结果和研报**归类到这些主题下**：\n"]
    for i, t in enumerate(topics_detail):
        name = t.get("name", f"主题{i + 1}")
        keywords = "、".join(t.get("keywords", []))
        lines.append(f"{i + 1}. **{name}** — 关注关键词: {keywords}")
    lines.append("\n⚠️ 要求：日报中的「行业动态速览」和「深度研报摘要」章节必须按上述主题归类组织，不要用聚类自动生成的标签作为章节标题。")
    return "\n".join(lines)


def _build_brief_from_llm(
    raw_text: str,
    research_reports: list[dict],
    review_map: dict[str, dict],
    topic_clusters: list[dict],
    target_date: str,
    article_count: int,
    total_clusters: int,
    total_reports: int,
    passed_count: int,
    model_used: str,
    run_id: str = "",
) -> DailyBrief:
    """从 LLM 输出构建 DailyBrief（提取各章节）"""
    import re

    # 提取各章节
    top_news = _extract_top_news(raw_text)
    industry_briefs = _extract_industry_briefs(raw_text, topic_clusters)
    tomorrow_focus = _extract_tomorrow_focus(raw_text)

    # 研报摘要直接用结构化数据
    report_cards = []
    for r in research_reports:
        report = r.get("report", {})
        if not report:
            continue
        rid = report.get("report_id", "")
        rv = review_map.get(rid, {})
        report_cards.append({
            "title": report.get("title", ""),
            "cluster_id": r.get("cluster_id", 0),
            "summary": report.get("background", "")[:200],
            "passed_review": rv.get("passed", True),
            "suggestions": rv.get("suggestions", []),
        })

    brief_id = f"brief-{target_date or 'unknown'}-{run_id}" if run_id else f"brief-{target_date or 'unknown'}"

    return DailyBrief(
        brief_id=brief_id,
        target_date=target_date,
        top_news=top_news,
        research_reports=report_cards,
        industry_briefs=industry_briefs,
        data_board={
            "total_articles": article_count,
            "total_clusters": total_clusters,
            "reports_generated": total_reports,
            "reports_passed": passed_count,
            "sentiment_summary": "（离线模式暂不支持情感分析）",
            "_llm_raw_preview": raw_text[:500] if raw_text else "(无)",
            "_run_id": run_id,
        },
        tomorrow_focus=tomorrow_focus,
        model_used=model_used,
    )


def _build_fallback_brief(
    research_reports: list[dict],
    review_map: dict[str, dict],
    topic_clusters: list[dict],
    topics_detail: list[dict],
    target_date: str,
    article_count: int,
    total_clusters: int,
    total_reports: int,
    passed_count: int,
    run_id: str = "",
) -> DailyBrief:
    """LLM 不可用时的模板回退简报"""

    # TOP5 要闻：取 importance 最高的 5 个簇
    sorted_clusters = sorted(topic_clusters, key=lambda x: x.get("importance", 0), reverse=True)
    top_news = []
    for c in sorted_clusters[:5]:
        top_news.append({
            "title": c.get("representative_title", c.get("label", "")),
            "summary": c.get("label", ""),
            "source_name": "",
            "importance": c.get("importance", 0),
            "cluster_label": c.get("label", ""),
        })

    # 研报卡片
    report_cards = []
    for r in research_reports:
        report = r.get("report", {})
        if not report:
            continue
        rid = report.get("report_id", "")
        rv = review_map.get(rid, {})
        report_cards.append({
            "title": report.get("title", ""),
            "cluster_id": r.get("cluster_id", 0),
            "summary": report.get("background", "")[:200],
            "passed_review": rv.get("passed", True),
            "suggestions": rv.get("suggestions", []),
        })

    # 行业动态：优先按用户配置的主题体系组织
    industry_briefs = []
    if topics_detail:
        # 有用户主题配置：按用户主题分组
        for t in topics_detail:
            name = t.get("name", "")
            kws = t.get("keywords", [])
            # 找到与该主题关键词匹配的簇
            matching_clusters = [
                c for c in topic_clusters
                if any(
                    kw.lower() in (c.get("label", "")).lower()
                    or kw.lower() in " ".join(c.get("keywords", [])).lower()
                    for kw in kws
                )
            ]
            if matching_clusters:
                total_articles = sum(c.get("article_count", 0) for c in matching_clusters)
                labels = "、".join(c.get("label", "") for c in matching_clusters[:3])
                industry_briefs.append({
                    "industry": name,
                    "summary": f"涉及 {len(matching_clusters)} 个话题: {labels}（共 {total_articles} 篇）",
                    "article_count": total_articles,
                })
            else:
                industry_briefs.append({
                    "industry": name,
                    "summary": "今日暂无相关报道",
                    "article_count": 0,
                })
    else:
        # 无用户主题配置：回退到按簇标签组织
        for c in topic_clusters:
            industry_briefs.append({
                "industry": c.get("label", "未分类"),
                "summary": f"共 {c.get('article_count', 0)} 篇相关报道",
                "article_count": c.get("article_count", 0),
            })

    # 明日关注 — 基于最高重要性簇
    tomorrow_focus = []
    for c in sorted_clusters[:3]:
        kw = " · ".join(c.get("keywords", [])[:3])
        if kw:
            tomorrow_focus.append(f"持续关注「{c.get('label', '')}」动态: {kw}")

    brief_id = f"brief-{target_date or 'unknown'}-{run_id}" if run_id else f"brief-{target_date or 'unknown'}"

    return DailyBrief(
        brief_id=brief_id,
        target_date=target_date,
        top_news=top_news,
        research_reports=report_cards,
        industry_briefs=industry_briefs,
        data_board={
            "total_articles": article_count,
            "total_clusters": total_clusters,
            "reports_generated": total_reports,
            "reports_passed": passed_count,
            "sentiment_summary": "（离线模式暂不支持情感分析）",
            "_run_id": run_id,
        },
        tomorrow_focus=tomorrow_focus,
        model_used="fallback",
    )


def _extract_top_news(raw_text: str) -> list[dict]:
    """从 LLM 输出提取 TOP5 要闻"""
    items = _extract_numbered_items(raw_text, r"🔴\s*今日要闻\s*TOP\d*")
    if not items:
        items = _extract_numbered_items(raw_text, r"今日要闻")
    return [{"title": t, "summary": t, "source_name": "", "importance": 5, "cluster_label": ""} for t in items[:5]]


def _extract_industry_briefs(raw_text: str, topic_clusters: list[dict]) -> list[dict]:
    """从 LLM 输出提取行业动态"""
    items = _extract_numbered_items(raw_text, r"🏭\s*行业动态速览")
    if not items:
        # 回退到簇标签
        items = [c.get("label", "") for c in topic_clusters]
    return [{"industry": t[:30], "summary": t, "article_count": 0} for t in items]


def _extract_tomorrow_focus(raw_text: str) -> list[str]:
    """从 LLM 输出提取明日关注"""
    return _extract_numbered_items(raw_text, r"🔮\s*明日关注")


def _extract_numbered_items(text: str, section_pattern: str) -> list[str]:
    """从 Markdown 文本中提取编号列表项

    支持多种编号格式：
      - "1. 标题 — 摘要"
      - "#1 标题"
      - "- 要点"
      - "**标题**"
    """
    import re

    # 定位章节
    section_match = re.search(section_pattern, text)
    if not section_match:
        return []

    # 截取该章节到下一个 ### 标题
    start = section_match.end()
    next_section = re.search(r"\n(?:###|##)\s", text[start:])
    section_text = text[start:start + next_section.start()] if next_section else text[start:]

    # 尝试多种编号格式，优先级从高到低
    item_patterns = [
        # "1. 标题 — 摘要" 或 "1) 标题"
        r"^\d+[\.\)、]\s*(.+)",
        # "#1 标题" 或 "#1. 标题"
        r"^#\d+[\.\)、]?\s*(.+)",
        # "- 标题" 或 "• 标题"（但不能是分隔线 --- 或表格 |---|）
        r"^[-•](?![-•\s]*$)\s*(.+)",
        # "**标题**" 开头的行
        r"^\*\*(.+?)\*\*",
    ]

    for pattern in item_patterns:
        items = re.findall(pattern, section_text, re.MULTILINE)
        # 过滤掉明显无效的项
        items = [
            item.strip()
            for item in items
            if item.strip() and item.strip() not in ("--", "---", "—", "…", "无", "暂无")
        ]
        if items:
            return items

    return []

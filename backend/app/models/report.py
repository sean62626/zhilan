"""
研报审核、日报组装、导出相关数据模型

ReviewResult  — 审核 Agent 输出
DailyBrief    — 日报组装 Agent 输出
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ReviewResult(BaseModel):
    """ReviewAgent 对单篇研报的审核结果"""

    report_id: str = Field(description="被审核的研报 ID")
    cluster_id: int = Field(description="关联的主题簇 ID")
    passed: bool = Field(default=False, description="是否通过审核")
    fact_errors: list[str] = Field(default_factory=list, description="事实性错误")
    hallucination_issues: list[str] = Field(default_factory=list, description="幻觉问题（原文不存在的实体/数据）")
    balance_passed: bool = Field(default=True, description="平衡性检查是否通过（多源交叉验证）")
    completeness_passed: bool = Field(default=True, description="完整性检查是否通过（四段式结构完整）")
    suggestions: list[str] = Field(default_factory=list, description="修改建议（逐条）")
    raw_response: str = Field(default="", description="LLM 原始审核输出（调试用）")
    model_used: str = Field(default="", description="使用的模型名称")
    reviewed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="审核时间",
    )


class DailyBrief(BaseModel):
    """ComposeAgent 生成的每日简报"""

    brief_id: str = Field(description="简报唯一标识")
    target_date: str = Field(description="目标日期 YYYY-MM-DD")
    top_news: list[dict] = Field(
        default_factory=list,
        description="今日要闻 TOP5 [{title, summary, source_name, importance, cluster_label}]",
    )
    research_reports: list[dict] = Field(
        default_factory=list,
        description="深度研报摘要列表 [{title, summary, cluster_label, passed_review}]",
    )
    industry_briefs: list[dict] = Field(
        default_factory=list,
        description="行业动态速览 [{industry, summary, article_count}]",
    )
    data_board: dict = Field(
        default_factory=dict,
        description="数据看板 {total_articles, total_clusters, reports_generated, reports_passed, sentiment_summary}",
    )
    tomorrow_focus: list[str] = Field(
        default_factory=list,
        description="明日关注要点列表",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="生成时间",
    )
    model_used: str = Field(default="", description="使用的模型名称")

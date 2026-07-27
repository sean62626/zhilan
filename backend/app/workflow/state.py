"""
LangGraph 工作流状态定义

PlatformState — 贯穿整个管道生命周期的共享状态
使用 TypedDict（LangGraph 原生方式），全部存 dict 以兼容 JSON 序列化 / checkpoint
"""

import operator
from typing import Annotated, TypedDict


class PlatformState(TypedDict):
    """平台工作流全局状态

    各阶段 Agent 的输出存入对应字段，下一阶段从对应字段读取。
    所有文章/簇/研报均以 dict 形式存储（Pydantic model_dump 输出），
    避免 Checkpoint JSON 序列化问题。
    """

    # ========== 采集阶段 ==========
    raw_articles: list[dict]
    """序列化的 RawArticle 列表"""

    collection_errors: list[str]
    """各采集源的错误信息"""

    # ========== 预处理阶段 ==========
    clean_articles: list[dict]
    """序列化的 CleanArticle 列表"""

    # ========== 去重阶段 ==========
    unique_articles: list[dict]
    """去重后的 CleanArticle 列表"""

    dedup_stats: dict
    """去重统计 {l1_removed, l2_removed, l3_removed, total_in, total_out}"""

    # ========== 聚类阶段 ==========
    topic_clusters: list[dict] | None
    """序列化的 TopicCluster 列表，None 表示尚未执行"""

    # ========== 研报生成阶段 ==========
    research_reports: list[dict] | None
    """研报结果列表（含元信息：cluster_id, report, queries_used 等），None 表示尚未执行"""

    # ========== 审核阶段 ==========
    review_results: list[dict] | None
    """审核结果列表（ReviewResult model_dump），None 表示尚未执行"""

    review_passed: bool
    """是否全部研报通过审核"""

    retry_count: int
    """审核不通过 → 返回 ResearchAgent 的重试次数（0-3，>=3 强制通过）"""

    # ========== 组装导出阶段 ==========
    daily_brief: dict | None
    """每日简报（DailyBrief model_dump），None 表示未生成"""

    export_paths: list[str]
    """导出文件路径列表"""

    # ========== 全局控制 ==========
    errors: Annotated[list[str], operator.add]
    """全局错误日志（append-only，operator.add 合并）"""

    target_date: str
    """目标日期 YYYY-MM-DD"""

    topics: list[str]
    """监控主题关键词（扁平列表，用于采集检索）"""

    topics_detail: list[dict]
    """结构化主题配置 [{"name": "科技", "keywords": ["AI","芯片"]}, ...]，用于日报对齐归类"""

    workflow_status: str
    """工作流状态: running | completed | failed"""

    run_id: str
    """工作流运行 ID（用于文件命名去重）"""

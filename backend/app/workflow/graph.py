"""
LangGraph StateGraph 构建

工作流:
  collect → [有文章?] → preprocess → dedup → [有文章?] → cluster → research
     ↑                                                                      ↓
     └──────────────────── 审核不通过 (retry < 3) ←────────────────────── review
                                                                             ↓ (通过 或 retry >= 3)
                                                                          compose → export → END
                ↓ 无                               ↓ 无
               END                                END
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.workflow.state import PlatformState
from app.workflow.nodes import (
    collect_node,
    preprocess_node,
    dedup_node,
    cluster_node,
    research_node,
    review_node,
    compose_node,
    export_node,
)

logger = logging.getLogger(__name__)

# 全局 compiled graph 实例（单例，复用 MemorySaver 中的 checkpoint）
_compiled_graph = None

# 最大审核重试次数
MAX_REVIEW_RETRIES = 3


# ========== 条件路由函数 ==========

def should_continue_after_collect(state: PlatformState) -> str:
    """采集完成后路由：有文章 → 预处理，无文章 → 结束"""
    if state.get("raw_articles"):
        logger.info("[路由] 采集到 %d 篇文章，继续预处理", len(state["raw_articles"]))
        return "preprocess"
    logger.warning("[路由] 采集无结果，终止工作流")
    return "end"


def should_continue_after_dedup(state: PlatformState) -> str:
    """去重完成后路由：有文章 → 聚类，无文章 → 结束"""
    if state.get("unique_articles"):
        logger.info("[路由] 去重后保留 %d 篇，继续聚类", len(state["unique_articles"]))
        return "cluster"
    logger.warning("[路由] 去重后无文章，终止工作流")
    return "end"


def review_router(state: PlatformState) -> str:
    """
    审核后路由 — 审核-重试闭环核心逻辑

    - 全部通过 → compose（进入日报组装）
    - 不通过 + retry < 3 → research（重新生成研报）
    - 不通过 + retry >= 3 → compose（强制通过，附带审核意见）
    """
    review_passed = state.get("review_passed", False)
    retry_count = state.get("retry_count", 0)

    if review_passed:
        logger.info("[路由] 审核全部通过 → 日报组装")
        return "compose"

    if retry_count >= MAX_REVIEW_RETRIES:
        logger.warning(
            "[路由] 审核 %d 次仍未通过（上限 %d）→ 强制进入日报组装（附带审核意见）",
            retry_count, MAX_REVIEW_RETRIES,
        )
        return "compose"

    logger.info("[路由] 审核不通过 → 返回 ResearchAgent 重试 (第 %d/%d 次)", retry_count, MAX_REVIEW_RETRIES)
    return "research"


# ========== 图构建 ==========

def build_workflow() -> StateGraph:
    """
    构建并编译 LangGraph 工作流

    8 节点 + 3 条件边 + 1 循环边（审核-重试）

    Returns:
        编译后的 StateGraph（含 MemorySaver checkpointer）
    """
    global _compiled_graph

    if _compiled_graph is not None:
        return _compiled_graph

    logger.info("[workflow] 构建 LangGraph 工作流 (Phase 6: 8 节点 + 审核闭环)")

    graph = StateGraph(PlatformState)

    # ---- 添加节点 ----
    graph.add_node("collect", collect_node)
    graph.add_node("preprocess", preprocess_node)
    graph.add_node("dedup", dedup_node)
    graph.add_node("cluster", cluster_node)
    graph.add_node("research", research_node)
    graph.add_node("review", review_node)
    graph.add_node("compose", compose_node)
    graph.add_node("export", export_node)

    # ---- 添加边 ----
    graph.add_edge(START, "collect")

    # 采集 → [有文章?]
    graph.add_conditional_edges(
        "collect",
        should_continue_after_collect,
        {"preprocess": "preprocess", "end": END},
    )

    graph.add_edge("preprocess", "dedup")

    # 去重 → [有文章?]
    graph.add_conditional_edges(
        "dedup",
        should_continue_after_dedup,
        {"cluster": "cluster", "end": END},
    )

    graph.add_edge("cluster", "research")
    graph.add_edge("research", "review")

    # 审核 → [通过?] → compose | research（重试循环）
    graph.add_conditional_edges(
        "review",
        review_router,
        {"compose": "compose", "research": "research"},
    )

    graph.add_edge("compose", "export")
    graph.add_edge("export", END)

    # ---- 编译（含内存 checkpointer） ----
    memory = MemorySaver()
    _compiled_graph = graph.compile(checkpointer=memory)

    logger.info("[workflow] 工作流编译完成 (Phase 6)")
    return _compiled_graph


def get_graph() -> StateGraph:
    """获取编译后的工作流图（单例）"""
    return build_workflow()

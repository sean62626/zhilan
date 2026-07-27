"""
LangGraph 工作流模块

导出：
  PlatformState  — 共享状态 TypedDict
  build_workflow — 构建 StateGraph
  event_bus      — 全局事件总线
  run_workflow_async — 后台执行工作流
"""

from app.workflow.state import PlatformState
from app.workflow.graph import build_workflow, get_graph
from app.workflow.streaming import event_bus, run_workflow_async

__all__ = [
    "PlatformState",
    "build_workflow",
    "get_graph",
    "event_bus",
    "run_workflow_async",
]

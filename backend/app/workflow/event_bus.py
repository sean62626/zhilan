"""
工作流事件总线 — asyncio.Queue Pub/Sub

独立模块，避免 streaming.py ↔ nodes.py 循环导入。
WebSocket 端点订阅 run_id，graph node 发布节点事件。
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def publish_event_safe(run_id: str, event: dict):
    """Fire-and-forget: 向事件总线发布事件，不阻塞调用方

    在 async 上下文中通过 asyncio.create_task 发送，
    避免因事件发布阻塞工作流主流程。
    """
    if not run_id:
        logger.debug("[eventbus] 跳过发布（run_id 为空）: %s", event.get("type"))
        return
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(event_bus.publish(run_id, event))
            logger.info("[eventbus] 已发布 %s → %s", event.get("type"), event.get("message", event.get("node", "")))
        else:
            logger.warning("[eventbus] 事件循环未运行，跳过发布: %s", event.get("type"))
    except RuntimeError:
        logger.warning("[eventbus] 不在 async 上下文中，跳过发布: %s", event.get("type"))


class WorkflowEventBus:
    """事件总线 — 连接 LangGraph nodes 与 WebSocket

    单例模式，全局共享。
    """

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        """订阅指定 run_id 的事件流，返回新 Queue"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = []
            self._subscribers[run_id].append(queue)
            logger.debug("[eventbus] +订阅 %s (共 %d 个)", run_id, len(self._subscribers[run_id]))
        return queue

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        """取消订阅"""
        async with self._lock:
            subs = self._subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)
                logger.debug("[eventbus] -取消订阅 %s (剩余 %d)", run_id, len(subs))
            if not subs and run_id in self._subscribers:
                del self._subscribers[run_id]

    async def publish(self, run_id: str, event: dict):
        """向所有订阅者推送事件"""
        async with self._lock:
            subs = self._subscribers.get(run_id, [])[:]  # 快照，避免遍历时修改

        if not subs:
            logger.debug("[eventbus] 无订阅者，丢弃事件: run_id=%s type=%s", run_id, event.get("type"))
            return

        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("[eventbus] 队列已满，丢弃事件: %s", event.get("type"))


# 全局单例
event_bus = WorkflowEventBus()

"""
WebSocket 端点

WS /ws/v1/workflow/{run_id}  — 订阅工作流实时进度事件
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.workflow.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/v1/workflow/{run_id}")
async def workflow_progress(websocket: WebSocket, run_id: str):
    """
    订阅指定工作流运行的实时进度事件

    事件格式:
      {"type": "node_complete", "node": "collect", "timestamp": "..."}
      {"type": "workflow_complete", "run_id": "...", "state_summary": {...}}
      {"type": "workflow_error", "run_id": "...", "error": "..."}
    """
    await websocket.accept()
    logger.info("[ws] 客户端连接: run_id=%s", run_id)

    queue = await event_bus.subscribe(run_id)

    try:
        # 发送确认连接事件
        await websocket.send_json({
            "type": "connected",
            "run_id": run_id,
        })

        # 循环读取事件并转发
        while True:
            try:
                # 带超时的等待，便于检测客户端断开
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info("[ws] 客户端断开: run_id=%s", run_id)
    except Exception as e:
        logger.error("[ws] WebSocket 异常: %s", e)
    finally:
        await event_bus.unsubscribe(run_id, queue)

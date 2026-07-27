"""
定时任务管理 API

GET  /api/v1/jobs                  — 列出所有定时任务及状态
POST /api/v1/jobs/{job_id}/trigger — 手动触发一次任务
GET  /api/v1/jobs/history          — 任务执行历史
POST /api/v1/jobs/{job_id}/enable  — 启用任务
POST /api/v1/jobs/{job_id}/disable — 禁用任务
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.scheduler import get_jobs_info, enable_job, disable_job, trigger_job_now
from app.scheduler.history import get_history_tracker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs")
async def list_jobs():
    """列出所有定时任务及当前状态"""
    jobs = get_jobs_info()
    tracker = get_history_tracker()
    stats = tracker.get_stats()

    return {
        "status": "ok",
        "count": len(jobs),
        "jobs": jobs,
        "overall_stats": stats,
    }


@router.get("/jobs/history")
async def get_job_history(
    job_id: str | None = Query(default=None, description="按任务 ID 过滤"),
    limit: int = Query(default=20, ge=1, le=100, description="返回条数"),
):
    """查询任务执行历史"""
    tracker = get_history_tracker()
    history = tracker.get_history(job_id=job_id, limit=limit)
    return {
        "status": "ok",
        "job_id": job_id,
        "count": len(history),
        "history": history,
    }


@router.post("/jobs/{job_id}/trigger")
async def trigger_job(job_id: str):
    """手动立即触发一次定时任务"""
    if job_id not in ("collect_all_sources", "generate_daily_brief", "health_check"):
        raise HTTPException(status_code=404, detail=f"未知的任务: {job_id}")

    execution_id = await trigger_job_now(job_id)
    if execution_id is None:
        raise HTTPException(status_code=500, detail=f"触发任务失败: {job_id}")

    logger.info("[api] 手动触发任务: %s → execution_id=%s", job_id, execution_id)

    return {
        "status": "ok",
        "message": f"任务 {job_id} 已触发",
        "execution_id": execution_id,
    }


@router.post("/jobs/{job_id}/enable")
async def enable_job_route(job_id: str):
    """启用一个被禁用的定时任务"""
    if job_id not in ("collect_all_sources", "generate_daily_brief", "health_check"):
        raise HTTPException(status_code=404, detail=f"未知的任务: {job_id}")

    changed = enable_job(job_id)
    return {
        "status": "ok",
        "job_id": job_id,
        "enabled": True,
        "changed": changed,
    }


@router.post("/jobs/{job_id}/disable")
async def disable_job_route(job_id: str):
    """禁用一个定时任务（不删除，可重新启用）"""
    if job_id not in ("collect_all_sources", "generate_daily_brief", "health_check"):
        raise HTTPException(status_code=404, detail=f"未知的任务: {job_id}")

    changed = disable_job(job_id)
    return {
        "status": "ok",
        "job_id": job_id,
        "enabled": False,
        "changed": changed,
    }

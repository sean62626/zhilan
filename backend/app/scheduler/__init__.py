"""
APScheduler 定时调度核心

提供:
  - scheduler: AsyncIOScheduler 单例
  - start_scheduler(): FastAPI startup 事件 — 加载并启动所有定时任务
  - shutdown_scheduler(): FastAPI shutdown 事件 — 优雅关闭
  - reload_schedule(): 配置变更后重新加载调度规则
  - get_jobs_info(): 获取所有已注册任务的状态信息
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

# ========== 全局调度器单例 ==========

scheduler = AsyncIOScheduler(
    timezone="Asia/Shanghai",
    job_defaults={
        "coalesce": True,           # 错过的时间点合并执行
        "max_instances": 1,         # 同一任务最多同时运行 1 个实例
        "misfire_grace_time": 300,  # 5 分钟内错过的仍可执行
    },
)

# ========== 任务配置 ==========

# 内置任务注册表 — 启动时根据配置动态添加
BUILTIN_JOBS = [
    {
        "job_id": "collect_all_sources",
        "name": "定时采集",
        "func": "app.scheduler.jobs:collect_all_sources_job",
        "trigger_type": "interval",
        "enabled": True,
    },
    {
        "job_id": "generate_daily_brief",
        "name": "日报生成",
        "func": "app.scheduler.jobs:generate_daily_brief_job",
        "trigger_type": "cron",
        "enabled": True,
    },
    {
        "job_id": "health_check",
        "name": "健康检查",
        "func": "app.scheduler.jobs:health_check_job",
        "trigger_type": "interval",
        "enabled": True,
    },
]


def _build_trigger(job_def: dict):
    """根据任务定义构建 APScheduler trigger"""
    settings = get_settings()

    trigger_type = job_def["trigger_type"]
    job_id = job_def["job_id"]

    if job_id == "collect_all_sources":
        hours = settings.collector.COLLECTION_INTERVAL_HOURS
        return IntervalTrigger(hours=hours)
    elif job_id == "generate_daily_brief":
        time_str = settings.collector.BRIEF_GENERATION_TIME
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return CronTrigger(hour=hour, minute=minute)
    elif job_id == "health_check":
        return IntervalTrigger(minutes=5)
    else:
        # 默认每小时间隔
        return IntervalTrigger(hours=1)


async def start_scheduler():
    """
    启动调度器 — 在 FastAPI startup 事件中调用

    1. 清理旧任务
    2. 按配置动态添加任务
    3. 启动调度器
    """
    logger.info("[scheduler] 正在初始化定时调度器...")

    # 清理现有任务
    existing_ids = {job.id for job in scheduler.get_jobs()}
    for job_id in existing_ids:
        scheduler.remove_job(job_id)

    # 添加任务
    added = 0
    for job_def in BUILTIN_JOBS:
        if not job_def.get("enabled", True):
            logger.info("[scheduler] 跳过已禁用的任务: %s", job_def["job_id"])
            continue

        try:
            trigger = _build_trigger(job_def)
            scheduler.add_job(
                func=job_def["func"],
                trigger=trigger,
                id=job_def["job_id"],
                name=job_def["name"],
                replace_existing=True,
            )
            added += 1
            logger.info("[scheduler] + 已添加任务: %s (%s)", job_def["job_id"], job_def["name"])
        except Exception as e:
            logger.error("[scheduler] 添加任务失败: %s — %s", job_def["job_id"], e)

    # 启动
    scheduler.start()
    logger.info("[scheduler] ✅ 调度器已启动（%d 个任务）", added)


async def shutdown_scheduler():
    """
    关闭调度器 — 在 FastAPI shutdown 事件中调用

    等待正在执行的任务完成（最长 10 秒），然后强制关闭。
    """
    logger.info("[scheduler] 正在关闭调度器...")
    try:
        scheduler.shutdown(wait=True)
    except Exception as e:
        logger.warning("[scheduler] 关闭异常: %s", e)
    logger.info("[scheduler] 调度器已关闭")


def reload_schedule():
    """
    重新加载调度规则 — 配置变更后调用

    同步执行（可在路由处理函数中直接调用）。
    """
    logger.info("[scheduler] 重新加载调度配置...")

    for job_def in BUILTIN_JOBS:
        job_id = job_def["job_id"]
        existing = scheduler.get_job(job_id)

        if existing is None:
            if job_def.get("enabled", True):
                try:
                    trigger = _build_trigger(job_def)
                    scheduler.add_job(
                        func=job_def["func"],
                        trigger=trigger,
                        id=job_id,
                        name=job_def["name"],
                        replace_existing=True,
                    )
                    logger.info("[scheduler] + 已恢复任务: %s", job_id)
                except Exception as e:
                    logger.error("[scheduler] 恢复任务失败: %s — %s", job_id, e)
        else:
            if job_def.get("enabled", True):
                try:
                    new_trigger = _build_trigger(job_def)
                    existing.reschedule(trigger=new_trigger)
                    logger.info("[scheduler] ↻ 已更新调度: %s", job_id)
                except Exception as e:
                    logger.error("[scheduler] 更新调度失败: %s — %s", job_id, e)


def get_jobs_info() -> list[dict]:
    """获取所有已注册任务的状态信息（供 API 使用）"""
    tracker = None
    try:
        from app.scheduler.history import get_history_tracker
        tracker = get_history_tracker()
    except Exception:
        pass

    jobs_info = []
    for job in scheduler.get_jobs():
        info = {
            "job_id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }

        # 解析 trigger 信息
        trigger = job.trigger
        if isinstance(trigger, IntervalTrigger):
            info["trigger"] = "interval"
            td = trigger.interval
            info["interval_hours"] = round(td.total_seconds() / 3600, 1)
        elif isinstance(trigger, CronTrigger):
            info["trigger"] = "cron"
            fields = {f.name: str(f) for f in trigger.fields if not f.is_default}
            info["cron_fields"] = fields

        # 找到对应的 BUILTIN_JOBS 配置
        for jd in BUILTIN_JOBS:
            if jd["job_id"] == job.id:
                info["enabled"] = jd.get("enabled", True)
                break
        else:
            info["enabled"] = True

        # 最近一次执行记录
        if tracker:
            history = tracker.get_history(job_id=job.id, limit=1)
            if history:
                last = history[0]
                info["last_run"] = {
                    "execution_id": last["execution_id"],
                    "started_at": last["started_at"],
                    "finished_at": last["finished_at"],
                    "success": last["success"],
                    "duration_ms": last["duration_ms"],
                    "error": last["error"],
                }
            else:
                info["last_run"] = None
        else:
            info["last_run"] = None

        jobs_info.append(info)

    return jobs_info


def enable_job(job_id: str) -> bool:
    """启用指定任务"""
    for jd in BUILTIN_JOBS:
        if jd["job_id"] == job_id:
            if jd.get("enabled"):
                return False  # 已经启用
            jd["enabled"] = True
            reload_schedule()
            return True
    return False


def disable_job(job_id: str) -> bool:
    """禁用指定任务"""
    for jd in BUILTIN_JOBS:
        if jd["job_id"] == job_id:
            if not jd.get("enabled", True):
                return False  # 已经禁用
            jd["enabled"] = False
            try:
                scheduler.remove_job(job_id)
                logger.info("[scheduler] - 已移除任务: %s", job_id)
            except Exception as e:
                logger.warning("[scheduler] 移除任务失败: %s — %s", job_id, e)
            return True
    return False


async def trigger_job_now(job_id: str) -> str | None:
    """立即手动触发一次任务，返回 execution_id"""
    from app.scheduler.history import get_history_tracker
    from app.scheduler import jobs as job_module

    job_funcs = {
        "collect_all_sources": job_module.collect_all_sources_job,
        "generate_daily_brief": job_module.generate_daily_brief_job,
        "health_check": job_module.health_check_job,
    }

    func = job_funcs.get(job_id)
    if func is None:
        return None

    logger.info("[scheduler] 🔧 手动触发任务: %s", job_id)

    # 在后台执行，不阻塞 API 响应
    import asyncio
    asyncio.create_task(func(), name=f"manual-{job_id}")

    # 返回最近一条记录的 execution_id
    tracker = get_history_tracker()
    history = tracker.get_history(job_id=job_id, limit=1)
    return history[0]["execution_id"] if history else None

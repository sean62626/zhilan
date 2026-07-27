"""
Celery 应用实例

Broker: Redis
任务模块: 待后续 Phase 注册
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

# ---------- 创建 Celery 应用 ----------
celery_app = Celery(
    "zhilan",
    broker=settings.redis.REDIS_URL,
    backend=settings.redis.REDIS_URL,
    include=["app.scheduler.worker"],  # 任务模块
)

# ---------- 配置 ----------
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 单任务最长 30 分钟
    task_soft_time_limit=25 * 60,  # 软限制 25 分钟
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# ---------- 定时任务（占位，后续 Phase 配置） ----------
celery_app.conf.beat_schedule = {
    # "collect-news": {
    #     "task": "app.scheduler.worker.collect_all_sources",
    #     "schedule": crontab(minute=0, hour=f"*/{settings.collector.COLLECTION_INTERVAL_HOURS}"),
    # },
}

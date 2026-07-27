"""
Celery Worker 任务定义（占位）

后续 Phase 将在此定义具体的采集、摘要、导出任务
"""

from app.scheduler.celery_app import celery_app


@celery_app.task(name="health_check")
def health_check() -> str:
    """健康检查任务 — 验证 Celery Worker 正常运行"""
    return "ok"


# 后续 Phase 将添加：
# @celery_app.task(name="collect_all_sources")
# def collect_all_sources():
#     ...
#
# @celery_app.task(name="generate_daily_brief")
# def generate_daily_brief():
#     ...

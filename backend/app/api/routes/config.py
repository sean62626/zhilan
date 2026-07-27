"""
系统配置路由

GET /api/v1/config  — 获取系统配置摘要
PUT /api/v1/config  — 更新可写配置项

脱敏返回：隐藏 API Key、密码等敏感信息
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()


# ========== 响应/请求模型 ==========

class ConfigSummary(BaseModel):
    """系统配置摘要（返回给前端，脱敏）"""
    app_name: str = "智览"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # LLM
    llm_model: str = ""
    llm_api_configured: bool = False

    # 采集
    collection_interval_hours: int = 2
    brief_generation_time: str = "08:00"

    # 基础设施状态
    es_host: str = ""
    es_configured: bool = False
    mysql_configured: bool = False
    redis_configured: bool = False

    # 数据源
    newsapi_configured: bool = False
    crawler_enabled: bool = True


class ConfigUpdate(BaseModel):
    """可更新配置项"""
    collection_interval_hours: int | None = Field(default=None, ge=1, le=24, description="采集间隔（小时）")
    brief_generation_time: str | None = Field(default=None, description="日报生成时间 HH:MM")
    log_level: str | None = Field(default=None, description="日志级别")


# ========== 工具函数 ==========

def _is_configured(value: str) -> bool:
    """检查值是否为有效配置（非占位符）"""
    return bool(value) and value not in ("xxx", "sk-xxx", "")


def _build_config_summary() -> ConfigSummary:
    """构建当前配置摘要"""
    return ConfigSummary(
        environment=settings.app.APP_ENV,
        log_level=settings.app.LOG_LEVEL,
        llm_model=settings.llm.DEEPSEEK_MODEL,
        llm_api_configured=_is_configured(settings.llm.DEEPSEEK_API_KEY),
        collection_interval_hours=settings.collector.COLLECTION_INTERVAL_HOURS,
        brief_generation_time=settings.collector.BRIEF_GENERATION_TIME,
        es_host=settings.os.OS_HOST,
        es_configured=settings.os.OS_HOST not in ("http://opensearch:9200", ""),
        mysql_configured=settings.mysql.MYSQL_PASSWORD not in ("zhilan_secret", ""),
        redis_configured=settings.redis.REDIS_URL not in ("redis://redis:6379/0", ""),
        newsapi_configured=_is_configured(settings.collector.NEWSAPI_KEY),
    )


# ========== API 端点 ==========

@router.get("/config")
async def get_config():
    """获取系统配置摘要"""
    return {
        "status": "ok",
        "config": _build_config_summary().model_dump(),
    }


@router.put("/config")
async def update_config(body: ConfigUpdate):
    """更新系统配置"""
    updated: list[str] = []

    if body.log_level is not None:
        level = body.log_level.upper()
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
            raise HTTPException(status_code=400, detail=f"无效的日志级别: {body.log_level}")
        settings.app.LOG_LEVEL = level
        logging.getLogger().setLevel(getattr(logging, level))
        updated.append("log_level")

    if body.collection_interval_hours is not None:
        settings.collector.COLLECTION_INTERVAL_HOURS = body.collection_interval_hours
        updated.append("collection_interval_hours")

    if body.brief_generation_time is not None:
        # 简单格式校验 HH:MM
        parts = body.brief_generation_time.split(":")
        if len(parts) != 2 or not (0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
            raise HTTPException(status_code=400, detail=f"时间格式无效: {body.brief_generation_time}")
        settings.collector.BRIEF_GENERATION_TIME = body.brief_generation_time
        updated.append("brief_generation_time")

    # 配置变更后重新加载调度规则
    if updated:
        try:
            from app.scheduler import reload_schedule
            reload_schedule()
            logger.info("[config] 配置变更后已重新加载调度规则")
        except Exception as e:
            logger.warning("[config] 重新加载调度规则失败: %s", e)

    logger.info("[config] 配置已更新: %s", updated)

    return {
        "status": "ok",
        "updated": updated,
        "config": _build_config_summary().model_dump(),
    }

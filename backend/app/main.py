"""
FastAPI 应用入口

创建应用、注册中间件、注册路由、管理调度器生命周期
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置 Python logging — uvicorn 不会自动传播到应用 logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

from app.api.routes.health import router as health_router
from app.api.routes.collect import router as collect_router
from app.api.routes.pipeline import router as pipeline_router
from app.api.routes.workflow import router as workflow_router
from app.api.routes.topics import router as topics_router
from app.api.routes.briefs import router as briefs_router
from app.api.routes.reports import router as reports_router
from app.api.routes.clusters import router as clusters_router
from app.api.routes.config import router as config_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.crawl_targets import router as crawl_targets_router
from app.api.websocket import router as ws_router

logger = logging.getLogger(__name__)


# ---------- 生命周期管理 ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """管理 APScheduler 调度器的启动和关闭"""
    logger.info("[main] 正在启动调度器...")
    from app.scheduler import start_scheduler, shutdown_scheduler
    await start_scheduler()
    logger.info("[main] 调度器启动完成")
    yield
    await shutdown_scheduler()
    logger.info("[main] 调度器已关闭")


# ---------- 创建应用 ----------
app = FastAPI(
    title="智览 API",
    description="多 Agent + 爬虫 AI 自动化研报/新闻摘要生成平台",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------- CORS 中间件 ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段全放行，生产需收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 注册路由 ----------
app.include_router(health_router, prefix="/api/v1", tags=["健康检查"])
app.include_router(collect_router, prefix="/api/v1", tags=["采集"])
app.include_router(pipeline_router, prefix="/api/v1", tags=["处理管道"])
app.include_router(workflow_router, prefix="/api/v1", tags=["工作流"])
app.include_router(topics_router, prefix="/api/v1", tags=["主题管理"])
app.include_router(briefs_router, prefix="/api/v1", tags=["日报"])
app.include_router(reports_router, prefix="/api/v1", tags=["研报"])
app.include_router(clusters_router, prefix="/api/v1", tags=["聚类分析"])
app.include_router(config_router, prefix="/api/v1", tags=["配置"])
app.include_router(jobs_router, prefix="/api/v1", tags=["定时任务"])
app.include_router(crawl_targets_router, prefix="/api/v1", tags=["爬取目标"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/health")
async def root_health():
    """根路径健康检查 — 供 Nginx 代理探测"""
    return {"status": "ok", "service": "zhilan-backend"}

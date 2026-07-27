"""
健康检查路由

GET /api/v1/status  — 综合运行状态（依赖检查并行，1.5s 硬超时）
GET /api/v1/ready   — k8s 就绪探针（连通性检查）

注意：使用 concurrent.futures.wait 而非 ThreadPoolExecutor.__exit__，
因为后者会等待所有线程完成（无视 future.result(timeout)），导致 API 响应被阻塞。
"""

from concurrent.futures import ThreadPoolExecutor, wait as futures_wait

from fastapi import APIRouter
from redis import Redis
from opensearchpy import OpenSearch
from sqlalchemy import text

from app.config import get_settings
from app.models.base import engine
from app.cache.cache_manager import get_redis

router = APIRouter()
settings = get_settings()

# 健康检查超时（秒）
_CHECK_TIMEOUT = 1.5


def check_redis() -> dict:
    """检查 Redis 连通性"""
    try:
        r: Redis = get_redis()
        r.ping()
        return {"status": "connected", "url": settings.redis.REDIS_URL}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


def check_opensearch() -> dict:
    """检查 OpenSearch 连通性"""
    try:
        client = OpenSearch(settings.os.OS_HOST, request_timeout=_CHECK_TIMEOUT)
        info = client.info()
        return {
            "status": "connected",
            "host": settings.os.OS_HOST,
            "version": info.get("version", {}).get("number", "unknown"),
        }
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


def check_mysql() -> dict:
    """检查数据库连通性（MySQL 或 SQLite）"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_url = settings.mysql.database_url
        host = "sqlite" if "sqlite" in db_url else settings.mysql.MYSQL_HOST
        return {"status": "connected", "host": host}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


def _run_parallel_checks() -> dict:
    """并行执行 3 个依赖检查，总耗时严格 ≤ _CHECK_TIMEOUT 秒"""
    executor = ThreadPoolExecutor(max_workers=3)
    try:
        check_names = {
            executor.submit(check_redis): "redis",
            executor.submit(check_opensearch): "opensearch",
            executor.submit(check_mysql): "mysql",
        }
        done, not_done = futures_wait(check_names.keys(), timeout=_CHECK_TIMEOUT)
        results = {}
        for future in done:
            name = check_names[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"status": "disconnected", "error": str(e)}
        for future in not_done:
            name = check_names[future]
            results[name] = {"status": "disconnected", "error": f"timeout after {_CHECK_TIMEOUT}s"}
            future.cancel()
        return results
    finally:
        executor.shutdown(wait=False)


def _get_scheduler_status() -> dict:
    """获取调度器状态"""
    try:
        from app.scheduler import scheduler, get_jobs_info
        jobs = get_jobs_info()
        running = scheduler.running
        jobs_healthy = {
            j["job_id"]: "healthy" if j["last_run"] is None or j["last_run"].get("success") is None or j["last_run"].get("success") else "last_run_failed"
            for j in jobs
        }
        return {
            "status": "running" if running else "stopped",
            "jobs_count": len(jobs),
            "jobs": jobs_healthy,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/status")
async def system_status():
    """综合系统运行状态（依赖检查并行，1.5s 硬超时）"""
    results = _run_parallel_checks()

    all_healthy = all(
        h["status"] == "connected" for h in results.values()
    )

    scheduler_status = _get_scheduler_status()

    return {
        "service": "zhilan-backend",
        "version": "0.1.0",
        "environment": settings.app.APP_ENV,
        "healthy": all_healthy,
        "dependencies": results,
        "scheduler": scheduler_status,
    }


@router.get("/ready")
async def readiness():
    """Kubernetes 就绪探针 — 检查关键依赖连通性"""
    results = _run_parallel_checks()
    checks = {name: r["status"] == "connected" for name, r in results.items()}

    return {
        "ready": all(checks.values()),
        "checks": checks,
    }

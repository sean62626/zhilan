"""
CollectorAgent — 多源数据采集编排

职责:
  1. 加载 sources.yaml 配置
  2. 并行运行所有启用的采集器
  3. 处理超时与错误隔离
  4. 合并结果并统计
  5. 可选写入 OpenSearch
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from app.collectors import COLLECTOR_REGISTRY
from app.models.article import RawArticle
from app.workflow.event_bus import publish_event_safe

logger = logging.getLogger(__name__)

# 默认配置路径
SOURCES_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "sources.yaml"
SETTINGS_CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "settings.yaml"

# 单个采集器默认超时（秒）
DEFAULT_COLLECTOR_TIMEOUT = 90


class CollectionResult:
    """一次采集的运行结果"""

    def __init__(self):
        self.started_at: datetime = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None
        self.articles: list[RawArticle] = []
        self.source_stats: dict[str, dict] = {}  # source_name → {status, count, error}
        self.total_sources: int = 0
        self.successful_sources: int = 0


async def run_collection(
    sources_config: dict | None = None,
    timeout_per_source: int = DEFAULT_COLLECTOR_TIMEOUT,
    topics: list[str] | None = None,
    run_id: str = "",
) -> CollectionResult:
    """
    执行一次全量采集

    Args:
        sources_config: 数据源配置（不传则从 sources.yaml 加载）
        timeout_per_source: 每个采集器的超时时间（秒）
        topics: 用户配置的监控主题（优先于 sources.yaml 中的 query_topics）

    Returns:
        CollectionResult: 采集结果，包含文章列表与统计信息
    """
    result = CollectionResult()

    # 加载配置
    if sources_config is None:
        sources_config = _load_yaml(SOURCES_CONFIG_PATH)
        if sources_config is None:
            logger.error("无法加载数据源配置: %s", SOURCES_CONFIG_PATH)
            return result

    settings_config = _load_yaml(SETTINGS_CONFIG_PATH)
    collection_cfg = settings_config.get("collection", {}) if settings_config else {}
    timeout_per_source = collection_cfg.get("request_timeout", timeout_per_source)

    # 筛选启用的采集源
    tasks: dict[str, asyncio.Task] = {}
    for source_key, collect_func in COLLECTOR_REGISTRY.items():
        source_cfg = sources_config.get(source_key)
        if not source_cfg:
            continue
        if not source_cfg.get("enabled", True):
            logger.info("采集源已禁用: %s", source_key)
            continue

        # 注入用户配置的主题关键词（优先于 sources.yaml 中的 query_topics）
        source_cfg = dict(source_cfg)
        logger.info("[DEBUG-collector] run_collection topics=%s, source_key=%s", topics, source_key)
        if topics:
            source_cfg["_topics"] = topics
            logger.info("采集源 [%s] 使用用户主题: %s", source_key, topics)
        else:
            logger.warning("采集源 [%s] topics 为空/None，将使用 sources.yaml 默认 query_topics", source_key)

        # 合并用户自定义爬取目标到 crawlers
        if source_key == "crawlers":
            from app.api.routes.crawl_targets import get_enabled_user_targets, get_deleted_system_names

            # 1) 过滤掉用户已删除的系统预设目标
            deleted_names = get_deleted_system_names()
            if deleted_names:
                original_count = len(source_cfg.get("targets", []))
                source_cfg["targets"] = [
                    t for t in source_cfg.get("targets", [])
                    if t.get("name") not in deleted_names
                ]
                removed = original_count - len(source_cfg["targets"])
                if removed > 0:
                    logger.info(
                        "采集源 [crawlers] 已排除 %d 个已删除的系统目标: %s",
                        removed, deleted_names,
                    )

            # 2) 合并用户自定义（启用的、非系统排除的）目标
            user_targets = get_enabled_user_targets()
            if user_targets:
                existing_names = {t["name"] for t in source_cfg.get("targets", [])}
                for ut in user_targets:
                    if ut["name"] not in existing_names:
                        source_cfg.setdefault("targets", []).append(ut)
                        existing_names.add(ut["name"])
                logger.info("采集源 [crawlers] 合并用户目标: +%d 个 (总计 %d 个)",
                            len(user_targets), len(source_cfg.get("targets", [])))

        result.total_sources += 1
        task = asyncio.create_task(
            _collect_with_timeout(source_key, collect_func, source_cfg, timeout_per_source),
            name=f"collect-{source_key}",
        )
        tasks[source_key] = task

    if not tasks:
        logger.warning("没有启用的采集源")
        return result

    # 并行执行所有采集器
    logger.info("开始并行采集，共 %d 个数据源（超时: %ds）", len(tasks), timeout_per_source)
    publish_event_safe(run_id, {
        "type": "node_progress",
        "node": "collect",
        "message": f"📥 正在并行采集 {len(tasks)} 个数据源（超时: {timeout_per_source}s）...",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    collected = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # 汇总结果
    for (source_key, task), articles_or_exc in zip(tasks.items(), collected):
        if isinstance(articles_or_exc, Exception):
            result.source_stats[source_key] = {
                "status": "failed",
                "count": 0,
                "error": str(articles_or_exc),
            }
            logger.error("采集源 [%s] 异常: %s", source_key, articles_or_exc)
        elif isinstance(articles_or_exc, list):
            result.articles.extend(articles_or_exc)
            stat = {
                "status": "success",
                "count": len(articles_or_exc),
                "error": None,
            }
            # 提取采集器的诊断信息
            diagnostic = _get_source_diagnostic(source_key)
            if diagnostic:
                stat["diagnostic"] = diagnostic
            result.source_stats[source_key] = stat
            result.successful_sources += 1
            if len(articles_or_exc) == 0:
                reason = diagnostic or "原因未知"
                logger.warning("采集源 [%s]: 未获取到文章 — %s", source_key, reason)
            else:
                logger.info("采集源 [%s]: 成功，获取 %d 篇文章", source_key, len(articles_or_exc))
        else:
            result.source_stats[source_key] = {
                "status": "failed",
                "count": 0,
                "error": f"未知返回类型: {type(articles_or_exc)}",
            }

    result.finished_at = datetime.now(timezone.utc)
    elapsed = (result.finished_at - result.started_at).total_seconds()
    logger.info(
        "采集完成: %d/%d 源成功，共 %d 篇文章，耗时 %.1fs",
        result.successful_sources,
        result.total_sources,
        len(result.articles),
        elapsed,
    )
    publish_event_safe(run_id, {
        "type": "node_progress",
        "node": "collect",
        "message": f"📥 采集完成: {result.successful_sources}/{result.total_sources} 源成功，共 {len(result.articles)} 篇文章（耗时 {elapsed:.1f}s）",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return result


async def _collect_with_timeout(
    source_key: str,
    collect_func,
    config: dict,
    timeout: int,
) -> list[RawArticle]:
    """为单个采集器添加超时保护

    与 asyncio.wait_for 不同：超时时不丢弃已采集的结果。
    改为将 timeout 注入 config，由采集器内部自行检查 deadline。
    """
    # 注入超时 deadline（Unix 时间戳），采集器内部可用来提前退出
    import time as _time
    config = dict(config)
    config["_deadline"] = _time.monotonic() + timeout

    try:
        return await asyncio.wait_for(
            collect_func(config),
            timeout=timeout + 5,  # 给 5s 缓冲让采集器自己收尾
        )
    except asyncio.TimeoutError:
        logger.warning("采集源 [%s] 超时 (%ds)，已跳过（硬超时）", source_key, timeout)
        return []
    except Exception:
        raise


def _load_yaml(path: Path) -> dict | None:
    """加载 YAML 配置文件"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("配置文件不存在: %s", path)
        return None
    except yaml.YAMLError as e:
        logger.error("配置文件解析失败 %s: %s", path, e)
        return None


def _get_source_diagnostic(source_key: str) -> str | None:
    """从各采集器模块获取诊断信息"""
    if source_key == "newsapi":
        try:
            from app.collectors.newsapi import get_diagnostics
            diag = get_diagnostics()
            return diag.get("reason")
        except Exception:
            return None
    if source_key == "crawlers":
        return "爬虫目标页面可能需 JS 渲染，httpx + BeautifulSoup 无法提取动态内容"
    return None

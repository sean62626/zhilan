"""
数据采集器模块

每个采集器暴露统一的异步接口:
    async def collect(config: dict) -> list[RawArticle]

通过 COLLECTOR_REGISTRY 注册所有采集器
"""

from app.collectors import newsapi, crawler, mock

# 采集器注册表 — 键名对应 sources.yaml 中的 section 名称
COLLECTOR_REGISTRY = {
    "newsapi": newsapi.collect,
    "crawlers": crawler.collect,
    "mock": mock.collect,
}

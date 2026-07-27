"""
OpenSearch 索引工具

提供文章批量写入 OpenSearch 的能力，不可用时优雅降级
"""

import logging
from datetime import datetime, timezone

from opensearchpy import OpenSearch, helpers

from app.config import get_settings
from app.models.article import RawArticle, OS_ARTICLE_MAPPING

logger = logging.getLogger(__name__)


def get_os_client() -> OpenSearch | None:
    """获取 OpenSearch 客户端（连接失败返回 None）"""
    settings = get_settings()
    try:
        client = OpenSearch(
            settings.os.OS_HOST,
            request_timeout=5,
            max_retries=1,
            retry_on_timeout=False,
        )
        # 快速连通性检查
        if client.ping():
            return client
        else:
            logger.warning("OpenSearch ping 失败: %s", settings.os.OS_HOST)
            return None
    except Exception as e:
        logger.warning("OpenSearch 连接失败 (%s): %s", settings.os.OS_HOST, e)
        return None


def ensure_index(client: OpenSearch) -> bool:
    """确保索引存在，不存在则创建"""
    settings = get_settings()
    index_name = settings.os.OS_INDEX

    try:
        if not client.indices.exists(index=index_name):
            client.indices.create(index=index_name, body=OS_ARTICLE_MAPPING)
            logger.info("OpenSearch 索引已创建: %s", index_name)
        return True
    except Exception as e:
        logger.error("OpenSearch 创建索引失败: %s", e)
        return False


def index_articles(articles: list[RawArticle]) -> int:
    """
    批量写入文章到 OpenSearch

    Returns:
        成功写入的文章数量（OpenSearch 不可用时返回 0）
    """
    if not articles:
        return 0

    client = get_os_client()
    if client is None:
        logger.warning("OpenSearch 不可用，跳过索引写入（%d 篇文章未写入）", len(articles))
        return 0

    if not ensure_index(client):
        return 0

    settings = get_settings()
    index_name = settings.os.OS_INDEX

    # 构建批量写入 actions
    actions = []
    for article in articles:
        doc = article.model_dump(mode="json")
        # 使用文章 id 作为文档 _id，天然去重
        actions.append({
            "_index": index_name,
            "_id": article.id,
            "_source": doc,
        })

    try:
        success, errors = helpers.bulk(
            client,
            actions,
            stats_only=True,
            raise_on_error=False,
        )
        if errors:
            logger.warning("OpenSearch 批量写入: %d 成功, %d 失败", success, len(errors) if isinstance(errors, list) else errors)
        else:
            logger.info("OpenSearch 批量写入成功: %d 篇文章 → %s", success, index_name)
        return success
    except Exception as e:
        logger.error("OpenSearch 批量写入异常: %s", e)
        return 0

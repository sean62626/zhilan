"""
文章数据模型

RawArticle — 采集阶段统一文章格式
OS_ARTICLE_MAPPING — OpenSearch 索引映射
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RawArticle(BaseModel):
    """采集器输出的统一文章格式"""

    id: str = Field(description="文章唯一标识（URL 的 MD5 哈希）")
    title: str = Field(description="标题")
    url: str = Field(description="原始 URL")
    content: str = Field(default="", description="正文内容（已清洗）")
    summary: Optional[str] = Field(default=None, description="摘要/导语")
    source: str = Field(description="采集源类型: newsapi / crawler")
    source_name: str = Field(default="", description="具体来源名称")
    language: str = Field(default="zh", description="语言代码")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="采集时间",
    )
    metadata: dict = Field(default_factory=dict, description="扩展元数据（作者、标签等）")

    @classmethod
    def make_id(cls, url: str) -> str:
        """基于 URL 生成文章唯一 ID"""
        return hashlib.md5(url.strip().encode("utf-8")).hexdigest()


class CleanArticle(BaseModel):
    """
    预处理后的文章格式

    在 RawArticle 基础上增加清洗后正文和语言标识
    """

    id: str = Field(description="文章唯一标识")
    title: str = Field(description="标题")
    url: str = Field(description="原始 URL")
    content: str = Field(default="", description="原始正文")
    cleaned_content: str = Field(default="", description="清洗后正文（去除 HTML/广告/导航文本）")
    summary: Optional[str] = Field(default=None, description="摘要/导语")
    source: str = Field(default="", description="采集源类型")
    source_name: str = Field(default="", description="具体来源名称")
    language: str = Field(default="zh", description="语言代码: zh / en")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="采集时间",
    )
    metadata: dict = Field(default_factory=dict, description="扩展元数据")

    @property
    def text_for_embedding(self) -> str:
        """用于向量化的组合文本"""
        return f"{self.title} {self.cleaned_content[:500]}"

    @property
    def text_for_simhash(self) -> str:
        """用于 SimHash 指纹的文本"""
        return f"{self.title} {self.cleaned_content[:1000]}"


class TopicCluster(BaseModel):
    """
    聚类结果 — 一个主题簇
    """

    cluster_id: int = Field(description="簇 ID")
    label: str = Field(description="主题标签（由 LLM 或关键词提取生成）")
    importance: int = Field(default=5, ge=1, le=10, description="重要性评分 1-10")
    articles: list[CleanArticle] = Field(default_factory=list, description="簇内文章列表")
    article_count: int = Field(default=0, description="文章数量")
    representative_title: str = Field(default="", description="代表文章标题")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")


class ResearchReport(BaseModel):
    """
    RAG 深度研报

    ResearchAgent 对每个主题簇生成的完整四段式研报
    """

    report_id: str = Field(description="研报唯一标识")
    cluster_id: int = Field(description="关联的主题簇 ID")
    title: str = Field(description="研报标题")
    background: str = Field(default="", description="一、事件背景")
    analysis: str = Field(default="", description="二、现状分析")
    outlook: str = Field(default="", description="三、趋势研判")
    risk: str = Field(default="", description="四、风险提示")
    raw_text: str = Field(default="", description="LLM 原始输出（用于调试）")
    references: list[dict] = Field(default_factory=list, description="引用来源列表")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="生成时间",
    )
    model_used: str = Field(default="", description="使用的模型名称")

    @classmethod
    def make_id(cls, cluster_id: int, title: str) -> str:
        """基于 cluster_id + title 生成研报 ID"""
        raw = f"{cluster_id}:{title}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


# OpenSearch 索引映射
OS_ARTICLE_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "zh_analyzer": {
                    "type": "standard",  # Phase 2 先用 standard，后续换 ik
                }
            }
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "title": {"type": "text", "analyzer": "zh_analyzer", "fields": {"raw": {"type": "keyword"}}},
            "url": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "zh_analyzer"},
            "summary": {"type": "text", "analyzer": "zh_analyzer"},
            "source": {"type": "keyword"},
            "source_name": {"type": "keyword"},
            "language": {"type": "keyword"},
            "published_at": {"type": "date"},
            "collected_at": {"type": "date"},
            "metadata": {"type": "object", "enabled": False},
        }
    },
}

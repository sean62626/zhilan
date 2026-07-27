"""
主题管理路由

GET    /api/v1/topics          — 获取所有监控主题
POST   /api/v1/topics          — 新增监控主题
DELETE /api/v1/topics/{topic_id} — 删除监控主题

存储：configs/topics.json（启动时加载，变更时写盘）

关键词拆分：用户输入的关键词可能包含 、/,/空格等分隔符，
创建时自动拆分为独立关键词，例如 "supreme、国潮" → ["supreme", "国潮"]
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# 存储文件路径
TOPICS_FILE = Path(__file__).parent.parent.parent.parent / "configs" / "topics.json"

# 关键词分隔符正则
_KEYWORD_SEPARATOR = re.compile(r"[、,，；;；\s]+")


def split_keywords(raw_keywords: list[str]) -> list[str]:
    """将可能包含分隔符的关键词列表拆分为独立关键词（去重去空）

    例如: ["supreme、国潮、奢侈品回收"] → ["supreme", "国潮", "奢侈品回收"]
          ["AI, 芯片", "半导体"] → ["AI", "芯片", "半导体"]
    """
    result: list[str] = []
    seen: set[str] = set()
    for kw in raw_keywords:
        kw = kw.strip()
        if not kw:
            continue
        # 按分隔符拆分
        parts = [p.strip() for p in _KEYWORD_SEPARATOR.split(kw) if p.strip()]
        for p in parts:
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


# ========== 数据模型 ==========

class TopicConfig(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="主题唯一标识")
    name: str = Field(description="主题名称")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")
    enabled: bool = Field(default=True, description="是否启用")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="创建时间",
    )


class TopicCreate(BaseModel):
    name: str = Field(description="主题名称")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")


# ========== 持久化 ==========

def _load_topics() -> list[TopicConfig]:
    """从 JSON 文件加载主题列表"""
    if not TOPICS_FILE.exists():
        # 首次启动：写入默认主题
        defaults = [
            TopicConfig(name="科技", keywords=["AI", "人工智能", "芯片", "半导体", "大模型"]),
            TopicConfig(name="金融", keywords=["A股", "美股", "央行", "利率", "汇率"]),
            TopicConfig(name="国际", keywords=["地缘政治", "贸易", "制裁", "外交"]),
        ]
        _save_topics(defaults)
        return defaults
    try:
        data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
        return [TopicConfig(**item) for item in data]
    except Exception as e:
        logger.warning("[topics] 加载失败，使用默认值: %s", e)
        return []


def _save_topics(topics: list[TopicConfig]) -> None:
    """写回 JSON 文件"""
    TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [t.model_dump() for t in topics]
    TOPICS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# 内存中缓存
_topics_cache: Optional[list[TopicConfig]] = None


def _get_topics() -> list[TopicConfig]:
    global _topics_cache
    if _topics_cache is None:
        _topics_cache = _load_topics()
    return _topics_cache


def _refresh_topics() -> list[TopicConfig]:
    global _topics_cache
    _topics_cache = _load_topics()
    return _topics_cache


def get_enabled_topic_keywords() -> list[str]:
    """获取所有启用主题的关键词（扁平去重、自动拆分分隔符）

    供采集器等模块复用。每次都刷新缓存，确保读到最新配置。
    """
    topics = _refresh_topics()
    keywords: list[str] = []
    for t in topics:
        if t.enabled:
            keywords.extend(t.keywords)
    return _deduplicate_keywords(keywords)


def get_enabled_topics_detail() -> list[dict]:
    """获取所有启用主题的结构化信息 [{"name": "科技", "keywords": [...]}, ...]

    供工作流日报组装等模块复用。每次都刷新缓存，确保读到最新配置。
    """
    topics = _refresh_topics()
    return [
        {"name": t.name, "keywords": t.keywords}
        for t in topics
        if t.enabled
    ]


def _deduplicate_keywords(keywords: list[str]) -> list[str]:
    """关键词去重（保持顺序）"""
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


# ========== API 端点 ==========

@router.get("/topics")
async def list_topics():
    """获取所有监控主题"""
    topics = _get_topics()
    return {
        "status": "ok",
        "count": len(topics),
        "topics": [t.model_dump() for t in topics],
    }


@router.post("/topics", status_code=201)
async def create_topic(body: TopicCreate):
    """新增监控主题"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="主题名称不能为空")

    topics = _refresh_topics()

    # 检查重名
    if any(t.name == body.name.strip() for t in topics):
        raise HTTPException(status_code=409, detail=f"主题「{body.name}」已存在")

    topic = TopicConfig(
        name=body.name.strip(),
        keywords=split_keywords(body.keywords),
    )
    topics.append(topic)
    _save_topics(topics)

    logger.info("[topics] 新增主题: %s", topic.name)
    return {"status": "ok", "topic": topic.model_dump()}


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str):
    """删除监控主题"""
    topics = _refresh_topics()

    target = next((t for t in topics if t.id == topic_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"主题 {topic_id} 不存在")

    topics.remove(target)
    _save_topics(topics)

    logger.info("[topics] 删除主题: %s (%s)", target.name, topic_id)
    return {"status": "ok", "deleted": topic_id}

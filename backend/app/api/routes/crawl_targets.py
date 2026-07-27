"""
爬取目标管理路由

GET    /api/v1/crawl-targets           — 获取所有爬取目标（系统预设 + 用户自定义）
POST   /api/v1/crawl-targets           — 新增用户自定义爬取目标
DELETE /api/v1/crawl-targets/{target_id} — 删除用户自定义爬取目标

存储：configs/crawl_targets.json（仅用户自定义目标）
系统预设目标来自 sources.yaml，通过 API 只读返回。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# 存储文件路径
CRAWL_TARGETS_FILE = Path(__file__).parent.parent.parent.parent / "configs" / "crawl_targets.json"
SOURCES_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "sources.yaml"


# ========== 数据模型 ==========

class CrawlTarget(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], description="目标唯一标识")
    name: str = Field(description="网站名称")
    url: str = Field(description="网站 URL")
    source: str = Field(default="user", description="来源: system / user")
    enabled: bool = Field(default=True, description="是否启用")
    deleted_system: bool = Field(default=False, description="是否为已删除的系统预设（用于排除列表）")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="创建时间",
    )


class CrawlTargetCreate(BaseModel):
    name: str = Field(description="网站名称")
    url: str = Field(description="网站 URL")


# ========== 持久化 ==========

def _load_user_targets() -> list[CrawlTarget]:
    """从 JSON 文件加载用户自定义目标"""
    if not CRAWL_TARGETS_FILE.exists():
        return []
    try:
        data = json.loads(CRAWL_TARGETS_FILE.read_text(encoding="utf-8"))
        return [CrawlTarget(**item) for item in data]
    except Exception as e:
        logger.warning("[crawl_targets] 加载失败: %s", e)
        return []


def _save_user_targets(targets: list[CrawlTarget]) -> None:
    """写回 JSON 文件"""
    CRAWL_TARGETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [t.model_dump() for t in targets]
    CRAWL_TARGETS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_system_targets() -> list[dict]:
    """从 sources.yaml 加载系统预设爬取目标"""
    try:
        with open(SOURCES_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        crawlers = cfg.get("crawlers", {})
        targets = crawlers.get("targets", [])
        return targets
    except Exception as e:
        logger.warning("[crawl_targets] 加载 sources.yaml 失败: %s", e)
        return []


# 内存中缓存
_user_targets_cache: Optional[list[CrawlTarget]] = None


def _get_user_targets() -> list[CrawlTarget]:
    global _user_targets_cache
    if _user_targets_cache is None:
        _user_targets_cache = _load_user_targets()
    return _user_targets_cache


def _refresh_user_targets() -> list[CrawlTarget]:
    global _user_targets_cache
    _user_targets_cache = _load_user_targets()
    return _user_targets_cache


def get_enabled_user_targets() -> list[dict]:
    """获取所有启用的用户自定义爬取目标（供 collector.py 使用）

    每次都刷新缓存，确保读到最新配置。
    排除已标记为 deleted_system 的记录。
    """
    targets = _refresh_user_targets()
    return [
        {"name": t.name, "url": t.url}
        for t in targets
        if t.enabled and not getattr(t, 'deleted_system', False)
    ]


def _get_deleted_system_names() -> set[str]:
    """获取用户标记为删除的系统预设站点名称集合"""
    targets = _get_user_targets()
    return {t.name for t in targets if getattr(t, 'deleted_system', False)}


def get_deleted_system_names() -> set[str]:
    """公开接口：获取已删除的系统预设站点名称（供 collector.py 过滤用）"""
    return _get_deleted_system_names()


def _merge_all_targets() -> list[CrawlTarget]:
    """合并系统预设 + 用户自定义，返回统一列表

    用户可删除系统预设站点 — 被删除的会存入排除列表，不再显示。
    """
    result: list[CrawlTarget] = []
    deleted_names = _get_deleted_system_names()

    # 系统预设（排除用户已删除的）
    for t in _load_system_targets():
        name = t.get("name", "")
        if name in deleted_names:
            continue
        result.append(CrawlTarget(
            id=f"system-{name}",
            name=name,
            url=t.get("url", ""),
            source="system",
            enabled=True,
            created_at="",
        ))

    # 用户自定义（排除 deleted_system 标记的记录）
    user_targets = _get_user_targets()
    for t in user_targets:
        if not getattr(t, 'deleted_system', False):
            result.append(t)

    return result


def _get_deleted_targets() -> list[CrawlTarget]:
    """获取用户已删除的系统预设目标列表（供前端恢复用）

    注意：返回时 id 统一为 system-{name} 格式，
    确保前端调用 restore 接口时能通过 system- 前缀校验。
    """
    user_targets = _get_user_targets()
    result = []
    for t in user_targets:
        if getattr(t, 'deleted_system', False):
            t.id = f"system-{t.name}"
            result.append(t)
    return result


# ========== URL 校验 ==========

def _validate_url(url: str) -> str:
    """校验 URL 格式"""
    url = url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL 必须以 http:// 或 https:// 开头")
    return url


# ========== API 端点 ==========

@router.get("/crawl-targets")
async def list_crawl_targets():
    """获取所有爬取目标（系统预设 + 用户自定义）+ 已删除的系统预设"""
    targets = _merge_all_targets()
    deleted = _get_deleted_targets()
    return {
        "status": "ok",
        "count": len(targets),
        "targets": [t.model_dump() for t in targets],
        "deleted_targets": [t.model_dump() for t in deleted],
    }


@router.post("/crawl-targets", status_code=201)
async def create_crawl_target(body: CrawlTargetCreate):
    """新增用户自定义爬取目标"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="网站名称不能为空")

    url = _validate_url(body.url)

    # 检查重名
    all_targets = _merge_all_targets()
    if any(t.name == body.name.strip() for t in all_targets):
        raise HTTPException(status_code=409, detail=f"爬取目标「{body.name}」已存在")

    user_targets = _refresh_user_targets()

    target = CrawlTarget(
        name=body.name.strip(),
        url=url,
    )
    user_targets.append(target)
    _save_user_targets(user_targets)

    logger.info("[crawl_targets] 新增目标: %s → %s", target.name, target.url)
    return {"status": "ok", "target": target.model_dump()}


@router.delete("/crawl-targets/{target_id}")
async def delete_crawl_target(target_id: str):
    """删除爬取目标（系统预设会被标记为已删除并存入排除列表）"""
    if target_id.startswith("system-"):
        # 系统预设目标：标记为已删除，存入排除列表
        system_targets = _load_system_targets()
        target_name = target_id.replace("system-", "", 1)
        matched = next((t for t in system_targets if t.get("name") == target_name), None)
        if matched is None:
            raise HTTPException(status_code=404, detail=f"系统预设目标 {target_id} 不存在")

        user_targets = _refresh_user_targets()
        # 检查是否已在排除列表中
        already = any(t.name == target_name and t.deleted_system for t in user_targets)
        if already:
            raise HTTPException(status_code=409, detail=f"爬取目标「{target_name}」已删除")

        deleted_entry = CrawlTarget(
            name=target_name,
            url=matched.get("url", ""),
            deleted_system=True,
        )
        user_targets.append(deleted_entry)
        _save_user_targets(user_targets)
        logger.info("[crawl_targets] 系统预设目标已标记删除: %s", target_name)
        return {"status": "ok", "deleted": target_id}

    # 用户自定义目标：直接从列表中移除
    user_targets = _refresh_user_targets()

    target = next((t for t in user_targets if t.id == target_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"爬取目标 {target_id} 不存在")

    user_targets.remove(target)
    _save_user_targets(user_targets)

    logger.info("[crawl_targets] 删除目标: %s (%s)", target.name, target_id)
    return {"status": "ok", "deleted": target_id}


@router.post("/crawl-targets/{target_id}/restore")
async def restore_crawl_target(target_id: str):
    """恢复已删除的系统预设爬取目标"""
    if not target_id.startswith("system-"):
        raise HTTPException(status_code=400, detail="只能恢复系统预设目标")

    target_name = target_id.replace("system-", "", 1)
    user_targets = _refresh_user_targets()

    # 查找被标记为 deleted_system 的记录
    deleted = next(
        (t for t in user_targets if t.name == target_name and getattr(t, 'deleted_system', False)),
        None,
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"未找到已删除的系统目标「{target_name}」")

    user_targets.remove(deleted)
    _save_user_targets(user_targets)

    logger.info("[crawl_targets] 系统预设目标已恢复: %s", target_name)
    return {"status": "ok", "restored": target_id}

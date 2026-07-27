"""
研报路由

GET /api/v1/reports      — 研报列表
GET /api/v1/reports/{id} — 单篇研报详情（含审核结果）

数据来源：exports/latest_state.json
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

STATE_FILE = Path(__file__).parent.parent.parent.parent / "exports" / "latest_state.json"


def _load_state() -> dict:
    """加载最新工作流状态快照"""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[reports] 读取状态文件失败: %s", e)
        return {}


@router.get("/reports")
async def list_reports():
    """获取研报列表"""
    state = _load_state()

    reports = state.get("research_reports", [])
    reviews = {r.get("report_id"): r for r in state.get("review_results", [])}

    items = []
    for r in reports:
        # 研报数据嵌套在 "report" 字段中（与 latest_state.json 结构一致）
        inner = r.get("report", r)
        rid = inner.get("report_id", "")
        review = reviews.get(rid, {})
        items.append({
            "report_id": rid,
            "cluster_id": r.get("cluster_id"),
            "title": inner.get("title", ""),
            "background_preview": (inner.get("background", "") or "")[:200],
            "importance": r.get("importance", 5),
            "review_passed": review.get("passed", False),
            "review_suggestions": review.get("suggestions", []),
            "generated_at": inner.get("generated_at"),
            "model_used": inner.get("model_used", ""),
        })

    return {
        "status": "ok",
        "count": len(items),
        "reports": items,
    }


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    """获取单篇研报详情（含完整四段式内容 + 审核结果）"""
    state = _load_state()

    reports = state.get("research_reports", [])
    # 匹配时从内层 report 对象读取 report_id
    report_wrapper = next(
        (r for r in reports if r.get("report", {}).get("report_id") == report_id), None
    )

    if report_wrapper is None:
        raise HTTPException(status_code=404, detail=f"研报 {report_id} 不存在")

    report = report_wrapper.get("report", report_wrapper)

    # 关联审核结果
    reviews = state.get("review_results", [])
    review = next((rv for rv in reviews if rv.get("report_id") == report_id), None)

    # 关联聚类信息
    cluster_id = report_wrapper.get("cluster_id")
    cluster = next(
        (c for c in state.get("topic_clusters", []) if c.get("cluster_id") == cluster_id),
        None,
    )

    return {
        "status": "ok",
        "report": {
            "report_id": report.get("report_id"),
            "cluster_id": cluster_id,
            "title": report.get("title", ""),
            "background": report.get("background", ""),
            "analysis": report.get("analysis", ""),
            "outlook": report.get("outlook", ""),
            "risk": report.get("risk", ""),
            "references": report.get("references", []),
            "generated_at": report.get("generated_at"),
            "model_used": report.get("model_used", ""),
            "rag_info": {
                "queries_used": report_wrapper.get("queries_used", []),
                "docs_retrieved": report_wrapper.get("docs_retrieved", 0),
                "docs_reranked": report_wrapper.get("docs_reranked", 0),
            },
        },
        "review": review if review else None,
        "cluster": {
            "label": cluster.get("label", "") if cluster else "",
            "importance": cluster.get("importance", 5) if cluster else 5,
            "keywords": cluster.get("keywords", []) if cluster else [],
        } if cluster else None,
    }

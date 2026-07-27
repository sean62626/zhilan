"""
每日简报路由

GET /api/v1/briefs           — 历史日报列表
GET /api/v1/briefs/{date}    — 指定日期日报内容 (JSON)
GET /api/v1/briefs/{date}/pdf — 下载 PDF 文件（按需生成）

数据来源：
- 列表：扫描 exports/ 目录下的 daily-brief-*.md 文件
- 详情：解析对应 .md 文件内容为结构化 JSON
- PDF：返回 .pdf 文件，不存在时从 .md 按需生成
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter()

EXPORTS_DIR = Path(__file__).parent.parent.parent.parent / "exports"
STATE_FILE = EXPORTS_DIR / "latest_state.json"


# ========== 工具函数 ==========

def _list_brief_files() -> list[Path]:
    """扫描 exports 目录下的简报文件（按修改时间倒序）"""
    if not EXPORTS_DIR.exists():
        return []
    files = sorted(
        EXPORTS_DIR.glob("daily-brief-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def _extract_date(filename: str) -> str:
    """从文件名中提取日期: daily-brief-2026-07-25-a1b2c3.md → 2026-07-25"""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else ""


def _extract_run_id(filename: str) -> str:
    """从文件名中提取 run_id: daily-brief-2026-07-25-a1b2c3.md → a1b2c3"""
    # 匹配日期后的 run_id（去掉 .md 后缀）
    match = re.search(r"(\d{4}-\d{2}-\d{2})-([a-f0-9]+)\.md$", filename)
    return match.group(2) if match else ""


def _parse_brief_md(filepath: Path) -> dict:
    """简单解析简报 Markdown 为结构化 dict"""
    text = filepath.read_text(encoding="utf-8")

    brief: dict = {
        "target_date": _extract_date(filepath.name),
        "top_news": [],
        "research_reports": [],
        "industry_briefs": [],
        "data_board": {},
        "tomorrow_focus": [],
        "full_text": text,
    }

    # 解析 TOP5
    top_section = _extract_section(text, r"##\s*🔴\s*今日要闻\s*TOP5", r"##\s*📝")
    if top_section:
        items = re.findall(r"\d+\.\s*\*\*(.+?)\*\*\s*([⭐★]+)?", top_section)
        for title, stars in items:
            brief["top_news"].append({
                "title": title.strip(),
                "importance": len(stars) if stars else 1,
            })

    # 解析研报
    report_section = _extract_section(text, r"##\s*📝\s*深度研报", r"##\s*🏭")
    if report_section:
        report_blocks = re.split(r"\n###\s+", report_section)
        for block in report_blocks:
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            title_line = lines[0] if lines else ""
            brief["research_reports"].append({
                "title": title_line.strip(),
                "summary": "\n".join(lines[1:]).strip()[:500] if len(lines) > 1 else "",
            })

    # 解析行业动态表格
    industry_section = _extract_section(text, r"##\s*🏭\s*行业动态", r"##\s*📉")
    if industry_section:
        rows = re.findall(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)?\s*\|", industry_section)
        for row in rows:
            if "---" not in row[0] and "行业" not in row[0]:
                brief["industry_briefs"].append({
                    "industry": row[0].strip(),
                    "summary": row[1].strip(),
                    "article_count": int(row[2]) if row[2] and row[2].isdigit() else 0,
                })

    # 解析数据看板
    data_section = _extract_section(text, r"##\s*📉\s*数据看板", r"##\s*🔮")
    if data_section:
        kv = re.findall(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|", data_section)
        for k, v in kv:
            if "---" not in k and "指标" not in k:
                brief["data_board"][k.strip()] = v.strip()

    # 解析明日关注
    focus_section = _extract_section(text, r"##\s*🔮\s*明日关注", r"---")
    if focus_section:
        brief["tomorrow_focus"] = [
            line.strip("- ").strip()
            for line in focus_section.strip().split("\n")
            if line.strip().startswith("-")
        ]

    return brief


def _extract_section(text: str, start_pattern: str, end_pattern: str) -> str:
    """提取两个 Markdown 标题之间的文本"""
    start_match = re.search(start_pattern, text)
    if not start_match:
        return ""
    start_pos = start_match.start()

    end_match = re.search(end_pattern, text[start_pos + 1:])
    if end_match:
        return text[start_pos:start_pos + 1 + end_match.start()]
    return text[start_pos:]


def _generate_pdf_from_md(md_path: Path, pdf_path: Path) -> None:
    """从 Markdown 文件生成 PDF（需要 weasyprint + markdown 库）"""
    import weasyprint
    import markdown

    md_text = md_path.read_text(encoding="utf-8")

    # 预处理：修复 AI 生成内容中的不规范 Markdown 标记
    md_text = re.sub(r"\*{4,}", "**", md_text)  # 合并 4+ 个连续星号 → 避免 "****" 被误解析
    md_text = re.sub(r"\*\*#", "#", md_text)    # 移除标题标签前的多余加粗标记

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans", sans-serif; max-width: 100%; color: #1a1a1a; background: #ffffff; line-height: 1.8; }}
  h1 {{ border-bottom: 3px solid #d32f2f; padding-bottom: 0.5em; color: #1a1a1a; }}
  h2 {{ color: #d32f2f; margin-top: 1.5em; }}
  h3 {{ color: #333; }}
  strong, b {{ color: #1a1a1a; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; color: #1a1a1a; }}
  th {{ background: #f5f5f5; font-weight: bold; }}
  blockquote {{ border-left: 4px solid #ff9800; padding-left: 1em; color: #555; }}
  p, li, span, div {{ color: #1a1a1a; }}
</style>
</head>
<body>{body}</body>
</html>"""

    weasyprint.HTML(string=html).write_pdf(str(pdf_path))
    logger.info("PDF 按需生成完成: %s → %s", md_path.name, pdf_path.name)


# ========== API 端点 ==========

@router.get("/briefs")
async def list_briefs():
    """获取历史日报列表（同一天可有多份，不覆盖）"""
    files = _list_brief_files()

    dates = []
    for f in files:
        date = _extract_date(f.name)
        run_id = _extract_run_id(f.name)
        if date:
            stat_info = f.stat()
            dates.append({
                "date": date,
                "run_id": run_id,
                "size_bytes": stat_info.st_size,
                "generated_at": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            })

    # 同时检查 latest_state.json 中的简报
    latest_date = None
    if STATE_FILE.exists():
        try:
            latest_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            daily_brief = latest_state.get("daily_brief") or {}
            latest_date = daily_brief.get("target_date")
        except Exception:
            pass

    return {
        "status": "ok",
        "count": len(dates),
        "latest_date": latest_date,
        "dates": dates,
    }


@router.get("/briefs/{date}")
async def get_brief(date: str, run_id: str = ""):
    """获取指定日期的日报内容（JSON）

    支持两种模式：
    - GET /briefs/{date}              返回该日期最新的一份简报
    - GET /briefs/{date}?run_id=xxx   返回指定 run_id 的简报
    """
    # 校验日期格式
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="日期格式无效，应为 YYYY-MM-DD")

    # 构建文件名
    if run_id:
        filepath = EXPORTS_DIR / f"daily-brief-{date}-{run_id}.md"
        if filepath.exists():
            brief = _parse_brief_md(filepath)
            return {"status": "ok", "date": date, "run_id": run_id, "brief": brief}
        raise HTTPException(status_code=404, detail=f"简报 {date}/{run_id} 不存在")

    # 无 run_id：找该日期最新的简报文件
    pattern = f"daily-brief-{date}*.md"
    candidates = sorted(
        EXPORTS_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        filepath = candidates[0]
        brief = _parse_brief_md(filepath)
        found_run_id = _extract_run_id(filepath.name)
        return {"status": "ok", "date": date, "run_id": found_run_id, "brief": brief}

    # fallback: latest_state.json
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            daily_brief = state.get("daily_brief") or {}
            if daily_brief.get("target_date") == date:
                return {"status": "ok", "date": date, "brief": daily_brief}
        except Exception:
            pass

    raise HTTPException(status_code=404, detail=f"日期 {date} 的日报不存在")


@router.get("/briefs/{date}/pdf")
async def download_brief_pdf(date: str, run_id: str = ""):
    """下载指定日期日报的 PDF 文件（不存在时按需生成）"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="日期格式无效，应为 YYYY-MM-DD")

    # 定位 MD 文件
    if run_id:
        md_path = EXPORTS_DIR / f"daily-brief-{date}-{run_id}.md"
    else:
        candidates = sorted(
            EXPORTS_DIR.glob(f"daily-brief-{date}*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        md_path = candidates[0] if candidates else None

    if not md_path or not md_path.exists():
        raise HTTPException(status_code=404, detail=f"日期 {date} 的日报不存在")

    pdf_path = EXPORTS_DIR / f"{md_path.stem}.pdf"

    # 已有 PDF，直接返回
    if pdf_path.exists():
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename=f"智览日报-{date}.pdf",
        )

    try:
        _generate_pdf_from_md(md_path, pdf_path)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="PDF 导出需要 weasyprint，当前服务未安装。请联系管理员安装 weasyprint 及系统依赖。",
        )
    except Exception as e:
        logger.exception("PDF 生成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {e}")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"智览日报-{date}.pdf",
    )

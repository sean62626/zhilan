"""
ExportAgent — Markdown / PDF 导出

职责：
  1. 将 DailyBrief 导出为 Markdown 文件
  2. PDF 导出（需 weasyprint，不可用时降级为 .md）

输入: DailyBrief dict
输出: 导出文件路径列表
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 导出目录
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "exports")


async def run_export(
    daily_brief: dict | None,
    output_dir: str | None = None,
    formats: list[str] | None = None,
    run_id: str = "",
) -> list[str]:
    """
    导出每日简报

    Args:
        daily_brief: DailyBrief 序列化 dict（或 None）
        output_dir: 输出目录（默认 backend/exports/）
        formats: 导出格式列表 ['md', 'pdf']，默认仅 md
        run_id: 工作流运行 ID（用于文件名去重，同一天多次运行不覆盖）

    Returns:
        导出文件路径列表
    """
    if formats is None:
        formats = ["md"]

    if daily_brief is None:
        logger.warning("无简报数据，跳过导出")
        return []

    output_dir = output_dir or EXPORT_DIR
    os.makedirs(output_dir, exist_ok=True)

    target_date = daily_brief.get("target_date", datetime.now(timezone.utc).date().isoformat())
    # 文件名包含 run_id，同一天多份简报不会覆盖
    suffix = f"-{run_id}" if run_id else ""
    base_name = f"daily-brief-{target_date}{suffix}"

    exported_paths: list[str] = []

    # Markdown 导出
    if "md" in formats:
        md_path = _export_markdown(daily_brief, output_dir, base_name)
        exported_paths.append(md_path)
        logger.info("Markdown 导出完成: %s", md_path)

    # PDF 导出
    if "pdf" in formats:
        pdf_path = _export_pdf(daily_brief, output_dir, base_name)
        if pdf_path:
            exported_paths.append(pdf_path)
            logger.info("PDF 导出完成: %s", pdf_path)
        else:
            logger.warning("PDF 导出不可用（未安装 weasyprint），已跳过")

    return exported_paths


def _export_markdown(brief: dict, output_dir: str, base_name: str) -> str:
    """导出为 Markdown 文件"""
    md_content = _render_markdown(brief)

    file_path = os.path.join(output_dir, f"{base_name}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return file_path


def _export_pdf(brief: dict, output_dir: str, base_name: str) -> str | None:
    """导出为 PDF 文件（需要 weasyprint）"""
    try:
        import weasyprint
    except ImportError:
        logger.warning("weasyprint 未安装，跳过 PDF 导出。安装: pip install weasyprint")
        return None

    md_content = _render_markdown(brief)
    html_content = _md_to_html(md_content)

    file_path = os.path.join(output_dir, f"{base_name}.pdf")
    weasyprint.HTML(string=html_content).write_pdf(file_path)
    return file_path


def _render_markdown(brief: dict) -> str:
    """将 DailyBrief dict 渲染为 Markdown 字符串"""

    target_date = brief.get("target_date", "")
    # 生成时间转为北京时间显示
    gen_at = brief.get("generated_at", "")
    if gen_at:
        try:
            from datetime import timezone as _tz, timedelta as _td
            gen_dt = datetime.fromisoformat(str(gen_at))
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            beijing_time = gen_dt.astimezone(timezone(_td(hours=8)))
            gen_at = beijing_time.strftime("%Y-%m-%d %H:%M:%S BJT")
        except Exception:
            pass

    lines = [
        f"# 智览 · 每日简报",
        f"**日期**: {target_date}",
        f"**生成时间**: {gen_at}",
        "",
        "---",
        "",
    ]

    # 🔴 今日要闻 TOP5
    lines.append("## 🔴 今日要闻 TOP5\n")
    top_news = brief.get("top_news", [])
    if top_news:
        for i, news in enumerate(top_news[:5]):
            title = news.get("title", news.get("summary", ""))
            summary = news.get("summary", "")
            importance = news.get("importance", "")
            star = "⭐" * min(importance // 2, 5) if isinstance(importance, int) else ""
            lines.append(f"{i + 1}. **{title}** {star}")
            if summary and summary != title:
                lines.append(f"   {summary}")
            lines.append("")
    else:
        lines.append("（暂无要闻）\n")

    # 📝 深度研报
    lines.append("## 📝 深度研报\n")
    reports = brief.get("research_reports", [])
    if reports:
        for i, r in enumerate(reports):
            title = r.get("title", "未命名")
            summary = r.get("summary", "")
            passed = "✅" if r.get("passed_review", True) else "⚠️"
            lines.append(f"### {i + 1}. {title} {passed}")
            if summary:
                lines.append(f"{summary}")
            suggestions = r.get("suggestions", [])
            if suggestions:
                lines.append("> 审核建议: " + "; ".join(suggestions))
            lines.append("")
    else:
        lines.append("（暂无深度研报）\n")

    # 🏭 行业动态速览
    lines.append("## 🏭 行业动态速览\n")
    industry_briefs = brief.get("industry_briefs", [])
    if industry_briefs:
        lines.append("| 行业/主题 | 动态 |")
        lines.append("|----------|------|")
        for item in industry_briefs:
            industry = item.get("industry", "")
            summary = item.get("summary", "")
            lines.append(f"| {industry} | {summary} |")
        lines.append("")
    else:
        lines.append("（暂无行业动态）\n")

    # 📉 数据看板
    lines.append("## 📉 数据看板\n")
    data = brief.get("data_board", {})
    if data:
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 采集文章总数 | {data.get('total_articles', 0)} |")
        lines.append(f"| 主题簇数量 | {data.get('total_clusters', 0)} |")
        lines.append(f"| 研报数量 | {data.get('reports_generated', 0)} |")
        lines.append(f"| 审核通过 | {data.get('reports_passed', 0)} |")
        lines.append(f"| 情感摘要 | {data.get('sentiment_summary', '')} |")
        lines.append("")

    # 🔮 明日关注
    lines.append("## 🔮 明日关注\n")
    tomorrow = brief.get("tomorrow_focus", [])
    if tomorrow:
        for item in tomorrow:
            lines.append(f"- {item}")
        lines.append("")
    else:
        lines.append("（暂无）\n")

    lines.append("---")
    lines.append(f"*本简报由智览平台自动生成 · {brief.get('model_used', 'AI')}*")

    return "\n".join(lines)


def _md_to_html(md_text: str) -> str:
    """将 Markdown 转为 HTML（用于 PDF 导出）"""
    try:
        import markdown
        body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except ImportError:
        # 无 markdown 库时，简单换行转 <br>
        body = md_text.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
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

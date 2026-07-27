"""
内容生成模块

prompts      — LLM Prompt 模板管理
summarizer   — DeepSeek API 调用 + Query 改写 + 摘要
report_writer — 四段式研报生成
"""

from app.generators import prompts, summarizer, report_writer

__all__ = ["prompts", "summarizer", "report_writer"]

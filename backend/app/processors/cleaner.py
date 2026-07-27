"""
文本清洗处理器

功能：
  - HTML 标签去除
  - 空白字符规范化
  - 广告/导航文本过滤
  - 中英文语言检测
"""

import re
import unicodedata


def clean_html(text: str) -> str:
    """去除 HTML 标签、脚本、样式，保留纯文本"""
    if not text:
        return ""

    # 去除 script / style 标签及其内容
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 去除 HTML 注释
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # 去除所有 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    # 解码 HTML 实体
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # 解码 Unicode 转义
    text = unicodedata.normalize("NFKC", text)

    return text.strip()


def normalize_whitespace(text: str) -> str:
    """规范化空白字符：合并多余空格/换行"""
    if not text:
        return ""
    # 合并连续空格
    text = re.sub(r"[ \t]+", " ", text)
    # 合并连续换行（最多保留 2 个）
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 去除每行首尾空白
    text = "\n".join(line.strip() for line in text.splitlines())
    return text.strip()


def strip_boilerplate(text: str) -> str:
    """
    去除常见的广告/导航/页脚文本

    基于模式匹配，匹配中文财经新闻中常见的噪音行
    """
    if not text:
        return ""

    noise_patterns = [
        r"^(广告|推广|赞助|免责声明|风险提示|投资有风险).*$",
        r"^(关于我们|联系我们|友情链接|网站地图|帮助中心).*$",
        r"^(Copyright|©|All Rights Reserved|版权所有).*$",
        r"^(分享到|收藏|点赞|评论\s*\d+|阅读\s*\d+).*$",
        r"^(上一页|下一页|返回顶部|回顶部).*$",
        r"^(相关阅读|热门推荐|最新评论|猜你喜欢|为您推荐).*$",
        r"^责任编辑[:：].*$",
        r"^.{0,3}(来源|作者)[:：].{0,20}$",
    ]

    lines = text.splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 4:
            continue
        is_noise = any(re.match(p, stripped) for p in noise_patterns)
        if not is_noise:
            filtered.append(line)

    return "\n".join(filtered)


def detect_language(text: str) -> str:
    """
    基于字符集检测语言

    Returns:
        "zh" — CJK 字符占比 > 30%
        "en" — 否则
    """
    if not text:
        return "zh"

    cjk_count = 0
    total = 0
    for ch in text:
        cp = ord(ch)
        if (
            (0x4E00 <= cp <= 0x9FFF)  # CJK 统一汉字
            or (0x3400 <= cp <= 0x4DBF)  # CJK 扩展 A
            or (0xF900 <= cp <= 0xFAFF)  # CJK 兼容汉字
        ):
            cjk_count += 1
        if ch.isalpha():
            total += 1

    if total == 0:
        return "zh"
    return "zh" if cjk_count / total > 0.3 else "en"


def clean_text(text: str) -> str:
    """一站式清洗管道"""
    text = clean_html(text)
    text = strip_boilerplate(text)
    text = normalize_whitespace(text)
    return text

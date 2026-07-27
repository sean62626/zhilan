"""
SimHash 文本指纹处理器

L2 近似去重 — 对标题/正文进行局部敏感哈希
汉明距离 < 阈值 → 视为重复

算法：
  1. 文本分词（字符级 n-gram，n=3）
  2. 每个 token 哈希为 64 位二进制向量
  3. 加权求和 → 降维为 64-bit 指纹
  4. 汉明距离比较
"""

import hashlib
import re
from typing import Callable

# 默认指纹位数
FINGERPRINT_BITS = 64
# 默认汉明距离阈值
# 中文 3-gram: < 12 → 相似度 > 0.85
# 英文 word n-gram: < 3 → 相似度 > 0.95
# 取 12 兼顾中英文混合场景
DEFAULT_THRESHOLD = 12


def _tokenize(text: str) -> list[str]:
    """
    字符级 n-gram 分词

    对中文按字符 3-gram，对英文按单词边界处理
    """
    if not text:
        return []

    # 去除标点，保留中英文字符和空格
    text = re.sub(r"[^\w\s一-鿿]", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()

    tokens = []
    # 中文字符 3-gram
    chars = re.findall(r"[一-鿿]", text)
    for i in range(len(chars) - 2):
        tokens.append(chars[i] + chars[i + 1] + chars[i + 2])

    # 英文单词 2-gram
    words = re.findall(r"[a-z]+", text)
    for w in words:
        if len(w) >= 4:
            tokens.append(w)
            for i in range(len(w) - 1):
                tokens.append(w[i : i + 2])

    return tokens


def compute_fingerprint(text: str, bits: int = FINGERPRINT_BITS) -> int:
    """
    计算文本的 SimHash 指纹

    Args:
        text: 输入文本
        bits: 指纹位数（默认 64）

    Returns:
        64-bit 整数指纹
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    # 初始化向量
    v = [0] * bits

    for token in tokens:
        # 将 token 哈希为 bits 位整数
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        # 对每一位加权
        for i in range(bits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    # 降维为指纹
    fingerprint = 0
    for i in range(bits):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """计算两个指纹的汉明距离"""
    return (a ^ b).bit_count()


def is_duplicate(fp_a: int, fp_b: int, threshold: int = DEFAULT_THRESHOLD) -> bool:
    """判断两个指纹是否属于重复（汉明距离 < 阈值）"""
    return hamming_distance(fp_a, fp_b) < threshold


def dedup_by_simhash(
    fingerprints: list[int],
    threshold: int = DEFAULT_THRESHOLD,
) -> list[int]:
    """
    基于 SimHash 指纹去重，返回保留的索引列表

    策略：每个指纹与第一个重复项配对，后续相同指纹被移除
    时间复杂度 O(n²)，适合小批量（< 1000 篇）
    """
    n = len(fingerprints)
    keep: list[int] = []
    # 已保留的指纹列表
    kept_fps: list[int] = []

    for i in range(n):
        fp = fingerprints[i]
        is_dup = any(
            hamming_distance(fp, kept_fp) < threshold
            for kept_fp in kept_fps
        )
        if not is_dup:
            keep.append(i)
            kept_fps.append(fp)

    return keep

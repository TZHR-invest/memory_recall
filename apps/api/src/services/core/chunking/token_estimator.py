"""Token estimation utilities using non-whitespace character count."""

import re
from typing import Tuple


def estimate_tokens_nws(text: str) -> int:
    """
    Estimate tokens using non-whitespace character count.

    Based on Supermemory's code-chunk approach:
    - For Chinese: 1 char ≈ 1 token
    - For English: 4 chars ≈ 1 token
    """
    if not text:
        return 0

    non_whitespace = len(re.findall(r"\S", text))

    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    total_chars = max(len(text), 1)
    chinese_ratio = chinese_chars / total_chars

    if chinese_ratio > 0.3:
        return non_whitespace
    return max(non_whitespace // 4, 1)


def estimate_tokens_legacy(text: str) -> int:
    """Legacy token estimation for backward compatibility."""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    numbers = len(re.findall(r"\d+", text))
    symbols = len(re.findall(r"[^\w\s\u4e00-\u9fff]", text))

    return chinese_chars + english_words + numbers + symbols // 2


def compare_estimations(text: str) -> Tuple[int, int, float]:
    """
    Compare NWS vs legacy token estimations.

    Returns:
        (nws_estimate, legacy_estimate, ratio)
    """
    nws = estimate_tokens_nws(text)
    legacy = estimate_tokens_legacy(text)

    ratio = nws / legacy if legacy > 0 else 0

    return nws, legacy, ratio

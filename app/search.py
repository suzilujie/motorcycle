# -*- coding: utf-8 -*-
"""Pinyin-aware matching shared by every search box.

Each candidate string is expanded into two lowercase keys:

    full     全拼 + 原样字母数字    奥迪Q5  ->  "aodiq5"
    initials 首字母 + 原样字母数字  奥迪Q5  ->  "adq5"

A query matches when it is a substring of either key or of the raw text, so
"aodi" / "ad" / "adq5" / "q5" / "奥迪" all hit 奥迪Q5. No tone marks are used.

Ranking is exact -> prefix -> substring, then the original order is kept.
pypinyin is optional: without it only the raw text is matched (app stays usable).
"""

from __future__ import annotations

try:
    from pypinyin import lazy_pinyin
except ImportError:      # 拼音库缺失时降级为字面匹配
    lazy_pinyin = None

_CHAR_CACHE = {}
_KEYS_CACHE = {}

# 多音字（polyphone）按行业习惯固定读音。pypinyin 给「长」的默认读音是
# zhǎng（zhang），而品牌/车型里一律读 cháng —— 不覆盖的话 长城/长安/
# 长征汽车 会被分到 Z 组，输入 C 也搜不到 changcheng。
_POLYPHONE = {"长": "chang"}


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _char_pinyin(char: str):
    """(full, first-letter) for one CJK char, cached."""
    cached = _CHAR_CACHE.get(char)
    if cached is None:
        syllable = _POLYPHONE.get(char)
        if syllable is None:
            try:
                syllable = lazy_pinyin(char)[0] if lazy_pinyin else char
            except Exception:      # 生僻字等异常输入不应影响搜索
                syllable = char
        syllable = syllable.lower()
        cached = (syllable, syllable[0])
        _CHAR_CACHE[char] = cached
    return cached


def keys(text: str):
    """(full, initials) keys for one candidate string."""
    if not text:
        return "", ""
    cached = _KEYS_CACHE.get(text)
    if cached is not None:
        return cached
    full_parts, initial_parts = [], []
    for char in text:
        if _is_cjk(char):
            syllable, first = _char_pinyin(char)
            full_parts.append(syllable)
            initial_parts.append(first)
        elif not char.isspace():
            low = char.lower()
            full_parts.append(low)
            initial_parts.append(low)
    cached = ("".join(full_parts), "".join(initial_parts))
    _KEYS_CACHE[text] = cached
    return cached


def _normalize(query: str) -> str:
    return "".join(query.split()).lower()


def matches(query: str, text: str) -> bool:
    """True when query matches text by literal, full pinyin or initials."""
    needle = _normalize(query)
    if not needle:
        return True
    full, initials = keys(text)
    haystacks = (text.lower(), full, initials)
    return any(needle in hay for hay in haystacks)


def filter_items(items, query: str, limit: int = 200) -> list:
    """Filtered + ranked candidates; empty query returns the first `limit`."""
    needle = _normalize(query)
    if not needle:
        return list(items)[:limit]
    exact, prefix, partial = [], [], []
    for item in items:
        full, initials = keys(item)
        low = item.lower()
        if needle in (low, full, initials):
            exact.append(item)
        elif low.startswith(needle) or full.startswith(needle) or initials.startswith(needle):
            prefix.append(item)
        elif needle in low or needle in full or needle in initials:
            partial.append(item)
        if len(exact) + len(prefix) + len(partial) >= limit * 4:
            break
    return (exact + prefix + partial)[:limit]


def unique(items) -> list:
    """De-duplicate while keeping order (QComboBox may hold duplicates)."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

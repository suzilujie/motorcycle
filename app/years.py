# -*- coding: utf-8 -*-
"""Year text parsing for the manual entry page.

The scraper already owns the canonical parser (scraper/normalize.py) and it is
imported here so a hand-typed row is normalized exactly like a scraped one.

normalize_years() silently drops out-of-range tokens, so "2021款 2060款" would
come back as 2021 and look perfectly valid. parse_years() therefore validates
every year token first and only then delegates the actual parsing.

If scraper/normalize.py is missing (the app was copied without the scraper
folder) a small built-in fallback takes over instead of crashing on import:
4-digit years and "2019到2024" style ranges keep working, 2-digit years ("14款")
do not.
"""

from __future__ import annotations

import json
import os
import re
import sys

import config

EMPTY_JSON = "[]"

# 严格写法：数字紧跟 款 / 费（常见错字）/ 年
_STRICT = re.compile(r"(?<!\d)(\d{2,4})\s*[\u6b3e\u8d39\u5e74]")
# 宽松写法：整段没有「款」时才认可裸的 4 位年份（2021-2024 / 2021,2022）
_BARE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
# 降级解析用
_FALLBACK_RANGE = re.compile(r"(?<!\d)(\d{4})\s*[款年]?\s*(?:到|-|~|—|至)\s*(\d{4})")
_FALLBACK_YEAR = re.compile(r"(?<!\d)(\d{4})(?!\d)")


class _FallbackYears:
    """Minimal stand-in for scraper/normalize.py (degraded mode only)."""

    ALL_YEAR_WORDS = ("全系", "全部")
    MIN_YEAR = 1980
    MAX_YEAR = 2035

    @staticmethod
    def is_valid_year(year: int) -> bool:
        return _FallbackYears.MIN_YEAR <= year <= _FallbackYears.MAX_YEAR

    @staticmethod
    def to_full_year(token: str) -> int:
        value = int(token)
        return 2000 + value if len(token) == 2 else value

    @staticmethod
    def normalize_years(raw: str) -> tuple:
        text = (raw or "").replace("\u3000", " ").strip()
        if not text or any(word in text for word in _FallbackYears.ALL_YEAR_WORDS):
            return None, None, EMPTY_JSON
        found = set()
        for start, end in _FALLBACK_RANGE.findall(text):
            low, high = sorted((int(start), int(end)))
            found.update(range(low, high + 1))
        found.update(int(token) for token in _FALLBACK_YEAR.findall(text))
        ordered = sorted(year for year in found
                         if _FallbackYears.is_valid_year(year))
        if not ordered:
            return None, None, EMPTY_JSON
        return ordered[0], ordered[-1], json.dumps(ordered)


def _scraper_dir() -> str:
    """scraper/ 的物理位置：源码态在项目根，冻结态打在 _MEIPASS 里。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.join(base, "scraper")
    return config.SCRAPER_DIR


def _load_normalizer():
    try:
        folder = _scraper_dir()
        if folder not in sys.path:
            sys.path.append(folder)
        import normalize      # scraper/normalize.py，只依赖 re/json
        return normalize
    except ImportError:        # 没有 scraper 目录时降级，不让应用起不来
        return _FallbackYears


normalize = _load_normalizer()


def year_tokens(text: str) -> list:
    """Year-looking tokens, strict form first."""
    tokens = _STRICT.findall(text)
    if tokens:
        return tokens
    return _BARE.findall(text)


def parse_years(raw: str) -> tuple:
    """(year_from, year_to, years_json, ok, message).

    ok=False means the text is out of range or unreadable; the caller shows
    ``message`` and blocks the save. Empty text and 全系/全部 mean "all years"
    and come back as (None, None, "[]", True, "").
    """
    text = (raw or "").strip()
    if not text or any(word in text for word in normalize.ALL_YEAR_WORDS):
        return None, None, EMPTY_JSON, True, ""
    for token in year_tokens(text):
        if not normalize.is_valid_year(normalize.to_full_year(token)):
            return (None, None, EMPTY_JSON, False,
                    "「%s」超出 %d – %d"
                    % (token, normalize.MIN_YEAR, normalize.MAX_YEAR))
    start, end, years_json = normalize.normalize_years(text)
    if start is None:
        return (None, None, EMPTY_JSON, False,
                "看不懂这个写法，试试 2021款 2022款 / 2021-2024")
    return start, end, years_json, True, ""


def display_range(start, end) -> str:
    """Readable range for a parsed year pair."""
    if not start or not end:
        return "全部年款"
    return str(start) if start == end else "%s – %s" % (start, end)

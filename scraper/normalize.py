# -*- coding: utf-8 -*-
"""Year normalization for the four observed raw formats:

1. "2020款 2021款 2022款"          -> enumerated years
2. "2017款到2019款"               -> inclusive range
3. "14款，15款，16款"              -> 2-digit years -> 2014/2015/2016
4. "全系"                          -> None (applies to every model year)
"""

from __future__ import annotations

import re
import json

# Ranges accept both 4-digit and 2-digit start years ("03款到2011款").
RANGE_RE = re.compile(r"(\d{2,4})\s*款\s*到\s*(\d{2,4})\s*款")
# Range written without 款 at all, e.g. "2010到2014". Requires 4-digit
# years so typos like "2001款到20004款" are not matched.
RANGE_BARE_RE = re.compile(r"(\d{4})\s*到\s*(\d{4})")
# Strict form: a year followed by 款 (or the common typo 费, or 年).
# This keeps displacement codes such as "30 TFSI" out of the result.
YEAR_KUAN_RE = re.compile(r"(\d{2,4})\s*(?:\u6b3e|\u8d39|\u5e74)")
# Fallback only when the whole field carries no 款/年 at all ("2009",
# "2015手动自动舒适版"). Digit lookarounds are used instead of \b because
# Chinese characters are word characters, so \b never fires next to them.
BARE_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
YEAR_TOKEN = re.compile(r"\d{2,4}\s*款")
ALL_YEAR_WORDS = ("\u5168\u7cfb", "\u5168\u90e8")  # 全系 / 全部
MIN_YEAR = 1980
MAX_YEAR = 2035
MAX_TWO_DIGIT = 29  # "30 TFSI" must not become year 2030


def is_valid_year(year: int) -> bool:
    """Reject typos such as "2001款到20004款" (parsed as year 4)."""
    return MIN_YEAR <= year <= MAX_YEAR


def to_full_year(token: str) -> int:
    value = int(token)
    if len(token) == 2:
        return 2000 + value
    return value


def _two_digit_ok(token: str) -> bool:
    """Two-digit years above 29 are displacement codes, not model years."""
    return len(token) != 2 or int(token) <= MAX_TWO_DIGIT


def _collect_years(text: str) -> set:
    """Union of every range and every strict "N款" token in the text."""
    years = set()
    for start_token, end_token in RANGE_RE.findall(text):
        if not (_two_digit_ok(start_token) and _two_digit_ok(end_token)):
            continue
        start = to_full_year(start_token)
        end = to_full_year(end_token)
        if not (is_valid_year(start) and is_valid_year(end)):
            continue
        if start > end:
            start, end = end, start
        years.update(range(start, end + 1))
    for start_token, end_token in RANGE_BARE_RE.findall(text):
        start, end = int(start_token), int(end_token)
        if not (is_valid_year(start) and is_valid_year(end)):
            continue
        if start > end:
            start, end = end, start
        years.update(range(start, end + 1))
    for token in YEAR_KUAN_RE.findall(text):
        if not _two_digit_ok(token):
            continue
        year = to_full_year(token)
        if is_valid_year(year):
            years.add(year)
    return years


def normalize_years(raw: str) -> tuple:
    """Return (year_from, year_to, years_json).

    Ranges and enumerated years are merged (a row may contain both, e.g.
    "2004款到2012款 2013款舒适型"), so the resulting interval is the union
    instead of the first range only. year_from/year_to are None when the
    text means "all model years".
    """
    text = (raw or "").replace("\u3000", " ").strip()
    empty = (None, None, json.dumps([], ensure_ascii=False))
    if not text or any(word in text for word in ALL_YEAR_WORDS):
        return empty
    years = _collect_years(text)
    if not years:
        for token in BARE_YEAR_RE.findall(text):
            year = int(token)
            if is_valid_year(year):
                years.add(year)
    if not years:
        return empty
    ordered = sorted(years)
    return ordered[0], ordered[-1], json.dumps(ordered, ensure_ascii=False)


def canonical_model(brand: str, model: str) -> str:
    """Build a comparable model key for cross-validation.

    Route A stores the model without brand prefix ("搏胜") while route B
    stores it with prefix ("中国重汽搏胜"). Prefixing the brand when the
    model does not already start with it makes both sides comparable.
    """
    brand = (brand or "").strip()
    model = (model or "").strip()
    if not brand or not model:
        return model or brand
    if model.startswith(brand):
        return model
    return brand + model


def clean_text(raw: str) -> str:
    """Strip entities/tags/extra spaces from a scraped fragment."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_model_years(fragment: str) -> tuple:
    """Split "model &nbsp; years" into (model, years_raw).

    Three layouts occur on the site: <p>years</p>, a double separator
    ("&nbsp;&nbsp;" / two spaces), and a bare trailing year block such as
    "ACADIA 2007款到2013款" where the model and years are separated by a
    single space. The third case used to leak years into the model name.
    """
    text = fragment or ""
    match = re.search(r"<p>(.*?)</p>", text, re.S)
    if match:
        # Text after </p> belongs to the same entry, e.g.
        # "... <p>03款到2011款</p>2012款基本型 laramie limited".
        head = text[:match.start()]
        tail = match.group(1) + " " + text[match.end():]
    else:
        parts = [p for p in re.split(r"(?:&nbsp;|\s){2,}", text) if p.strip()]
        if len(parts) > 1:
            head, tail = parts[0], " ".join(parts[1:])
        else:
            head, tail = text, ""
    head = clean_text(head)
    tail = clean_text(tail)

    token = YEAR_TOKEN.search(head)
    if token:
        tail = (head[token.start():] + " " + tail).strip()
        head = head[:token.start()].strip()
    else:
        # "全部" / "全系" also act as a year block, e.g. "DS 5 全部"
        for word in ALL_YEAR_WORDS:
            position = head.rfind(word)
            if position > 0:
                tail = (head[position:] + " " + tail).strip()
                head = head[:position].strip()
                break
    if not head:
        # Only year text is present (e.g. "2023款 2024款 2025款"): there is
        # no model name, so the row is unusable and gets dropped upstream.
        return "", ""
    return head, tail

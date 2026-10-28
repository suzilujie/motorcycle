# -*- coding: utf-8 -*-
"""Parsers for route A: bracket -> fitment list (/2 and /Car_show/?idd=X)."""

from __future__ import annotations

import re

import normalize

BRACKET_LINK_RE = re.compile(r'\.\./Car_show/\?idd=([^"\']+)')
TITLE_RE = re.compile(r"型号:\s*([^\s]+)\s*支架大图")
IMAGE_RE = re.compile(
    r"UploadFileHome/([^\"']+?\.(?:jpg|jpeg|png|gif|webp))", re.I)
FIT_RE = re.compile(r'<td width="97%">(.*?)</td>', re.S)


def parse_bracket_ids(html: str) -> list:
    """Extract every bracket id (idd) from the /2 index page."""
    seen, ids = set(), []
    for value in BRACKET_LINK_RE.findall(html or ""):
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


def parse_bracket_page(html: str, idd: str) -> dict:
    """Extract bracket label and big image from one /Car_show page."""
    text = html or ""
    title = TITLE_RE.search(normalize.clean_text(text))
    label = title.group(1) if title else (idd + "\u53f7")
    image = IMAGE_RE.search(text)
    image_url = "../web/UploadFileHome/" + image.group(1) if image else None
    return {"idd": idd, "label": label, "image_url": image_url}


def parse_fitments(html: str) -> list:
    """Parse fitment blocks of a /Car_show page.

    Layout is "brand &nbsp;model&nbsp;<p>years</p>", so the brand is the
    segment before the first &nbsp; and the rest is model + years.
    Returns a list of (brand, model, years_raw).
    """
    rows = []
    for fragment in FIT_RE.findall(html or ""):
        parts = re.split(r"&nbsp;", fragment)
        brand = normalize.clean_text(parts[0])
        model, years = normalize.split_model_years("&nbsp;".join(parts[1:]))
        if not brand or not model:
            continue
        # Pages that list only a year word ("全部") carry no model name.
        if model in normalize.ALL_YEAR_WORDS:
            continue
        rows.append((brand, model, years))
    return rows

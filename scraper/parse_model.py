# -*- coding: utf-8 -*-
"""Parsers for route B: brand list -> model list -> product fitments."""

from __future__ import annotations

import re

import http_client
import normalize

BRAND_RE = re.compile(
    r'<a href="\.\./Car2/\?BigClassName=([^"]+)"[\s\S]{0,600}?'
    r'<img src="([^"]+)"[\s\S]{0,300}?<td width="93%">(.*?)</td>', re.S)
MODEL_RE = re.compile(
    r'<a href="\.\./Products/\?BigClassName=[^"&]*&amp;?SmallClassName=([^"]+)"',
    re.S)
P_BRAND_RE = re.compile(r'<td width="97%">[\s\S]{0,200}?#0093DF">(.*?)</font>', re.S)
P_MODEL_RE = re.compile(r'font-size: 12pt;font-family:黑体; ">(.*?)</font>', re.S)
P_BRACKET_RE = re.compile(
    r'适用支架：<a href="\.\./Car_show/\?idd=([^"]+)"><strong><font[^>]*>(.*?)</font>',
    re.S)


def parse_brands(html: str) -> list:
    """Parse /Car/ into (brand, logo_url) pairs."""
    rows = []
    for raw_brand, logo, _label in BRAND_RE.findall(html or ""):
        brand = http_client.gbk_decode(raw_brand.replace("&amp;", "&")).strip()
        if not brand:
            continue
        rows.append((brand, logo.strip()))
    return rows


def parse_models(html: str) -> list:
    """Parse /Car2/ into a list of model names."""
    rows = []
    for raw in MODEL_RE.findall(html or ""):
        model = http_client.gbk_decode(raw.replace("&amp;", "&")).strip()
        if model:
            rows.append(model)
    return rows


def parse_products(html: str) -> list:
    """Parse /Products/ into (brand, model, years_raw, bracket_id) rows.

    The three lists are emitted in document order, so they are zipped by
    index; the shortest list wins to avoid misalignment.
    """
    text = html or ""
    brands = [normalize.clean_text(b) for b in P_BRAND_RE.findall(text)]
    models = P_MODEL_RE.findall(text)
    brackets = P_BRACKET_RE.findall(text)
    size = min(len(brands), len(models), len(brackets))
    rows = []
    for i in range(size):
        model, years = normalize.split_model_years(models[i])
        if not model:
            continue
        bracket_id = brackets[i][0].strip()
        rows.append((brands[i], model, years, bracket_id))
    return rows

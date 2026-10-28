# -*- coding: utf-8 -*-
"""Cross-validation between route A (bracket -> models) and route B
(model -> bracket). Writes data/report/crosscheck.csv plus a summary.
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

import config
import normalize
import store

ALL_YEARS = "*"


def _rows_by_source(conn, source: str) -> dict:
    """Map (brand, canonical model, year) -> set of bracket ids."""
    buckets = defaultdict(set)
    cursor = conn.execute(
        "SELECT brand, model, years_json, bracket_id FROM fitments WHERE source=?",
        (source,))
    for brand, model, years_json, bracket_id in cursor:
        key_model = normalize.canonical_model(brand, model)
        try:
            years = json.loads(years_json or "[]")
        except (ValueError, TypeError):
            years = []
        if not years:
            buckets[(brand, key_model, ALL_YEARS)].add(bracket_id)
            continue
        for year in years:
            buckets[(brand, key_model, str(year))].add(bracket_id)
    return buckets


def build(conn) -> list:
    """Build cross-check rows: brand, model, year, a, b, status."""
    source_a = _rows_by_source(conn, "A")
    source_b = _rows_by_source(conn, "B")
    rows = []
    for key in sorted(set(source_a) | set(source_b)):
        brand, model, year = key
        set_a = source_a.get(key)
        set_b = source_b.get(key)
        if set_a and set_b:
            if set_a & set_b:
                status = "MATCH"
            elif year == ALL_YEARS or _has_wildcard(source_a, brand, model) \
                    or _has_wildcard(source_b, brand, model):
                status = "CONFLICT_LOW"
            else:
                status = "CONFLICT"
        elif set_a:
            status = "ONLY_A"
        else:
            status = "ONLY_B"
        rows.append((brand, model, year, "|".join(sorted(set_a or [])),
                     "|".join(sorted(set_b or [])), status))
    return rows


def _has_wildcard(buckets, brand: str, model: str) -> bool:
    return any(k[0] == brand and k[1] == model and k[2] == ALL_YEARS
               for k in buckets)


def write_report(rows) -> str:
    path = os.path.join(config.REPORT_DIR, "crosscheck.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["brand", "model", "year", "bracket_a", "bracket_b",
                         "status"])
        writer.writerows(rows)
    return path


def summarize(rows) -> dict:
    result = defaultdict(int)
    for row in rows:
        result[row[5]] += 1
    return dict(result)


def run(conn, log=print) -> dict:
    rows = build(conn)
    store.replace_crosscheck(conn, rows)
    conn.commit()
    path = write_report(rows)
    summary = summarize(rows)
    total = max(len(rows), 1)
    log("crosscheck rows=%d -> %s" % (len(rows), path))
    for status in sorted(summary):
        log("  %-12s %6d  (%.2f%%)" % (status, summary[status],
                                       100.0 * summary[status] / total))
    compared = sum(v for k, v in summary.items() if k.startswith("MATCH")
                   or k.startswith("CONFLICT"))
    rate = 100.0 * summary.get("CONFLICT", 0) / max(compared, 1)
    log("  conflict rate over compared pairs: %.2f%%" % rate)
    return {"rows": len(rows), "summary": summary, "conflict_rate": rate,
            "report": path}

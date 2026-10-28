# -*- coding: utf-8 -*-
"""CLI entry point of the KY bracket scraper.

Usage:
    python run.py brackets              # route A (all 301 bracket pages)
    python run.py catalog               # route B1 (brands + model lists)
    python run.py products --sample 0.2 # route B2 (sampled product pages)
    python run.py images                # download bracket photos and logos
    python run.py crosscheck            # cross-validate route A against B
    python run.py stats                 # print database summary
    python run.py all                   # brackets + catalog + products + images
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import crosscheck
import http_client
import images
import normalize
import parse_bracket
import parse_model
import store

LOG = logging.getLogger("ky")


def setup_logging() -> None:
    LOG.setLevel(logging.INFO)
    if LOG.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    LOG.addHandler(stream)
    path = os.path.join(config.LOG_DIR, "scraper.log")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    LOG.addHandler(file_handler)


def run_pool(jobs, worker, tag: str):
    """Fetch pages concurrently; the worker must be pure (no DB writes)."""
    results, errors = [], 0
    total = len(jobs)
    with ThreadPoolExecutor(max_workers=config.WORKERS) as pool:
        futures = [pool.submit(worker, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001 - keep crawling
                errors += 1
                LOG.warning("%s failed: %s", tag, exc)
            if index % 50 == 0 or index == total:
                LOG.info("%s progress %d/%d (errors=%d)", tag, index, total,
                         errors)
    LOG.info("%s done: ok=%d errors=%d", tag, len(results), errors)
    return results


def stage_brackets(conn) -> int:
    """Route A: every bracket page -> bracket rows + fitments (source A)."""
    html = http_client.fetch_text(config.BRACKET_LIST_URL)
    ids = parse_bracket.parse_bracket_ids(html)
    LOG.info("route A: %d bracket ids found", len(ids))

    def worker(idd):
        # One bracket id contains a Chinese character ("254B款"), so the
        # query string must be GBK percent-encoded like every other param.
        url = config.CAR_SHOW_URL.format(idd=http_client.gbk_encode(idd))
        page = http_client.fetch_text(url)
        head = parse_bracket.parse_bracket_page(page, idd)
        return head, parse_bracket.parse_fitments(page)

    added = 0
    for head, fitments in run_pool(ids, worker, "brackets"):
        store.upsert_bracket(conn, head["idd"], head["image_url"])
        for brand, model, years in fitments:
            year_from, year_to, years_json = normalize.normalize_years(years)
            if store.add_fitment(conn, "A", head["idd"], brand, model, years,
                                 year_from, year_to, years_json):
                added += 1
    conn.commit()
    LOG.info("route A: %d fitment rows stored", added)
    return added


def stage_catalog(conn) -> int:
    """Route B1: brand list + model lists (authoritative model catalog)."""
    html = http_client.fetch_text(config.BRAND_LIST_URL)
    brands = parse_model.parse_brands(html)
    LOG.info("route B1: %d brands found", len(brands))
    for brand, logo in brands:
        store.upsert_brand(conn, brand, logo)
    conn.commit()

    def worker(brand):
        url = config.CAR2_URL.format(brand=http_client.gbk_encode(brand))
        return brand, parse_model.parse_models(http_client.fetch_text(url))

    total = 0
    for brand, models in run_pool([b for b, _ in brands], worker, "catalog"):
        for model in models:
            store.upsert_model(conn, brand, model)
            total += 1
    conn.commit()
    LOG.info("route B1: %d models stored", total)
    return total


def pick_sample(conn, ratio: float, seed: int = 20261024) -> list:
    """Stratified sample: at least one model per brand, ratio of the rest."""
    rng = random.Random(seed)
    picked = []
    cursor = conn.execute("SELECT brand, model FROM models")
    grouped = {}
    for brand, model in cursor.fetchall():
        grouped.setdefault(brand, []).append(model)
    for brand, models in grouped.items():
        models = sorted(models)
        count = len(models)
        take = max(1, int(round(count * ratio)))
        take = min(take, count)
        picked.extend((brand, m) for m in rng.sample(models, take))
    return picked


def stage_products(conn, ratio: float) -> int:
    """Route B2: sampled product pages -> fitments (source B)."""
    jobs = pick_sample(conn, ratio)
    LOG.info("route B2: %d product pages sampled (ratio=%.2f)", len(jobs), ratio)

    def worker(job):
        brand, model = job
        url = config.PRODUCTS_URL.format(brand=http_client.gbk_encode(brand),
                                         model=http_client.gbk_encode(model))
        return parse_model.parse_products(http_client.fetch_text(url))

    added = 0
    for rows in run_pool(jobs, worker, "products"):
        for brand, model, years, bracket_id in rows:
            year_from, year_to, years_json = normalize.normalize_years(years)
            if store.add_fitment(conn, "B", bracket_id, brand, model, years,
                                 year_from, year_to, years_json):
                added += 1
    conn.commit()
    LOG.info("route B2: %d fitment rows stored", added)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="KY bracket scraper")
    parser.add_argument("stage", choices=["brackets", "catalog", "products",
                                          "images", "crosscheck", "stats", "all"])
    parser.add_argument("--sample", type=float, default=config.DEFAULT_SAMPLE)
    parser.add_argument("--workers", type=int, default=config.WORKERS)
    parser.add_argument("--interval", type=float, default=config.MIN_INTERVAL)
    args = parser.parse_args()

    setup_logging()
    config.WORKERS = args.workers
    config.MIN_INTERVAL = args.interval
    LOG.info("stage=%s workers=%d interval=%.2fs db=%s", args.stage,
             config.WORKERS, config.MIN_INTERVAL, config.DB_PATH)

    conn = store.connect()
    try:
        if args.stage in ("brackets", "all"):
            stage_brackets(conn)
        if args.stage in ("catalog", "all"):
            stage_catalog(conn)
        if args.stage in ("products", "all"):
            stage_products(conn, args.sample)
        if args.stage in ("images", "all"):
            images.download_all(conn, LOG.info)
        if args.stage in ("crosscheck", "all"):
            crosscheck.run(conn, LOG.info)
        LOG.info("summary=%s", store.summary(conn))
        LOG.info("http=%s", http_client.stats())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

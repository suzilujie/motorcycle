# -*- coding: utf-8 -*-
"""Binary download of bracket photos and brand logos."""

from __future__ import annotations

import os
import re

import config
import http_client


def to_absolute(path: str) -> str:
    """Convert a site-relative path ("../web/...") into an absolute URL."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    return config.SITE_ROOT + path.replace("../", "/")


def extension_of(url: str) -> str:
    """Keep the original image extension (the site mixes jpg and png)."""
    ext = os.path.splitext((url or "").split("?")[0])[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp") else ".jpg"


def safe_name(value: str) -> str:
    """Build a filesystem-safe file name from a Chinese/ASCII label."""
    name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", (value or "").strip())
    return name or "unnamed"


def download_all(conn, log=print) -> dict:
    """Download bracket images and brand logos; returns counters."""
    stats = {"brackets": 0, "brands": 0}
    cursor = conn.execute(
        "SELECT bracket_id, image_url FROM brackets WHERE image_url IS NOT NULL")
    for bracket_id, image_url in cursor.fetchall():
        url = to_absolute(image_url)
        dest = os.path.join(config.IMAGE_DIR,
                            "bracket_%s%s" % (safe_name(bracket_id),
                                              extension_of(url)))
        if http_client.download_file(url, dest):
            stats["brackets"] += 1
        conn.execute("UPDATE brackets SET image_file=? WHERE bracket_id=?",
                     (os.path.basename(dest), bracket_id))
    conn.commit()
    log("images: bracket photos downloaded=%d" % stats["brackets"])

    cursor = conn.execute(
        "SELECT brand, logo_url FROM brands WHERE logo_url IS NOT NULL")
    for brand, logo_url in cursor.fetchall():
        url = to_absolute(logo_url)
        dest = os.path.join(config.IMAGE_DIR,
                            "brand_%s%s" % (safe_name(brand), extension_of(url)))
        if http_client.download_file(url, dest):
            stats["brands"] += 1
        conn.execute("UPDATE brands SET logo_file=? WHERE brand=?",
                     (os.path.basename(dest), brand))
    conn.commit()
    log("images: brand logos downloaded=%d" % stats["brands"])
    return stats

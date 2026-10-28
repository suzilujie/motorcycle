# -*- coding: utf-8 -*-
"""SQLite storage layer for the KY scraper."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS brackets (
    bracket_id TEXT PRIMARY KEY,
    image_url  TEXT,
    image_file TEXT,
    -- 备注（2026-10-28）：手工维护，upsert_bracket 刻意不碰这一列
    note       TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS brands (
    brand      TEXT PRIMARY KEY,
    logo_url   TEXT,
    logo_file  TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS models (
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    PRIMARY KEY (brand, model)
);
CREATE TABLE IF NOT EXISTS fitments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    bracket_id TEXT NOT NULL,
    brand      TEXT NOT NULL,
    model      TEXT NOT NULL,
    years_raw  TEXT,
    year_from  INTEGER,
    year_to    INTEGER,
    years_json TEXT,
    fetched_at TEXT,
    UNIQUE (source, bracket_id, brand, model, years_raw)
);
CREATE INDEX IF NOT EXISTS idx_fit_brand_model ON fitments (brand, model);
CREATE INDEX IF NOT EXISTS idx_fit_source ON fitments (source);
CREATE TABLE IF NOT EXISTS crosscheck (
    brand      TEXT NOT NULL,
    model      TEXT NOT NULL,
    year       TEXT NOT NULL,
    bracket_a  TEXT,
    bracket_b  TEXT,
    status     TEXT NOT NULL,
    PRIMARY KEY (brand, model, year)
);
-- 支架多图（2026-10-28）：brackets.image_file 仍是封面（sort_index = 0），
-- 这里存完整图片列表，手工录入页支持上传/删除/换封面。
CREATE TABLE IF NOT EXISTS bracket_images (
    bracket_id TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    sort_index INTEGER NOT NULL DEFAULT 0,
    added_at   TEXT,
    PRIMARY KEY (bracket_id, file_name)
);
CREATE INDEX IF NOT EXISTS idx_bracket_images ON bracket_images (bracket_id, sort_index);
"""


def now_local() -> str:
    """Current time in the local timezone (UTC+8), as an ISO string."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_bracket(conn, bracket_id: str, image_url: str = None,
                   image_file: str = None) -> None:
    conn.execute(
        "INSERT INTO brackets (bracket_id, image_url, image_file, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(bracket_id) DO UPDATE SET "
        "image_url=COALESCE(excluded.image_url, brackets.image_url), "
        "image_file=COALESCE(excluded.image_file, brackets.image_file), "
        "updated_at=excluded.updated_at",
        (bracket_id, image_url, image_file, now_local()))


def upsert_brand(conn, brand: str, logo_url: str = None,
                 logo_file: str = None) -> None:
    conn.execute(
        "INSERT INTO brands (brand, logo_url, logo_file, updated_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(brand) DO UPDATE SET "
        "logo_url=COALESCE(excluded.logo_url, brands.logo_url), "
        "logo_file=COALESCE(excluded.logo_file, brands.logo_file), "
        "updated_at=excluded.updated_at",
        (brand, logo_url, logo_file, now_local()))


def upsert_model(conn, brand: str, model: str) -> None:
    conn.execute("INSERT OR IGNORE INTO models (brand, model) VALUES (?, ?)",
                 (brand, model))


def add_fitment(conn, source: str, bracket_id: str, brand: str, model: str,
                years_raw: str, year_from, year_to, years_json: str) -> bool:
    """Insert one fitment row; returns True when a new row was added."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO fitments (source, bracket_id, brand, model, "
        "years_raw, year_from, year_to, years_json, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source, bracket_id, brand, model, years_raw, year_from, year_to,
         years_json or json.dumps([], ensure_ascii=False), now_local()))
    return cur.rowcount > 0


def replace_crosscheck(conn, rows) -> None:
    conn.execute("DELETE FROM crosscheck")
    conn.executemany(
        "INSERT OR REPLACE INTO crosscheck "
        "(brand, model, year, bracket_a, bracket_b, status) VALUES (?,?,?,?,?,?)",
        rows)


def count(conn, table: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0]


def summary(conn) -> dict:
    result = {}
    for table in ("brackets", "brands", "models", "crosscheck"):
        result[table] = count(conn, table)
    for source in ("A", "B"):
        result["fitments_" + source] = conn.execute(
            "SELECT COUNT(*) FROM fitments WHERE source=?", (source,)).fetchone()[0]
    result["fitments_total"] = count(conn, "fitments")
    return result

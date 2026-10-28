# -*- coding: utf-8 -*-
"""Data access layer over ky.db.

Read path (unchanged, mode=ro):
Q1 model_brackets  : brand + model -> bracket numbers
Q2 bracket_models  : bracket number -> compatible models

Write path (manual entry page, source 'M'):
add_manual() opens a short-lived connection, snapshots the database into
data/backup/ first and keeps brands / models / brackets / fitments inside one
transaction, so a failed save leaves nothing behind.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import config
import years

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_fit_source_bracket "
    "ON fitments(source, bracket_id)",
    "CREATE INDEX IF NOT EXISTS idx_fit_years ON fitments(year_from, year_to)",
    "CREATE INDEX IF NOT EXISTS idx_fit_model ON fitments(model)",
    # 支架多图（2026-10-28）：老库在启动时自动补表，无需手工迁移。
    # brackets.image_file 继续存封面（= sort_index 0 的那张），
    # 反查页大图 / 按支架查卡片 / 按车型查缩略图因此都不用改。
    "CREATE TABLE IF NOT EXISTS bracket_images ("
    " bracket_id TEXT NOT NULL, file_name TEXT NOT NULL,"
    " sort_index INTEGER NOT NULL DEFAULT 0, added_at TEXT,"
    " PRIMARY KEY (bracket_id, file_name))",
    "CREATE INDEX IF NOT EXISTS idx_bracket_images "
    "ON bracket_images(bracket_id, sort_index)",
)

MANUAL_SOURCE = "M"       # 手工录入；A = 爬虫反查，B = 爬虫目录
BACKUP_KEEP = 10          # data/backup/ 里保留的快照份数
WRITE_TIMEOUT = 15        # 与爬虫并发写时的等待秒数


def ensure_schema_ready() -> bool:
    """Create helper indexes / 补列 once (idempotent); needs write access.

    返回本次是否真的改了表结构（True = 首次补上 brackets.note）。
    """
    if not os.path.exists(config.DB_PATH):
        raise FileNotFoundError("数据库不存在：%s" % config.DB_PATH)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    try:
        for statement in INDEXES:
            conn.execute(statement)
        conn.commit()                 # 新建的表 / 索引先落盘，再做结构迁移
        changed = _add_bracket_note(conn)
        conn.commit()
    finally:
        conn.close()
    return changed


def _add_bracket_note(conn) -> bool:
    """brackets.note（2026-10-28）：老库缺列时补上，改结构前先存一份快照。

    ADD COLUMN 本身很快也不重写数据，但这是本程序唯一会动表结构的动作，
    所以先 backup_database() 再 ALTER；列已存在时直接返回，可反复调用。
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(brackets)")}
    if not columns or "note" in columns:
        return False
    backup_database()
    conn.execute("ALTER TABLE brackets ADD COLUMN note TEXT")
    return True


def connect_readonly() -> sqlite3.Connection:
    uri = Path(config.DB_PATH).as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(cursor) -> list:
    return [dict(row) for row in cursor.fetchall()]


def _marks(items) -> str:
    """'?,?,?' for an IN (...) list."""
    return ",".join("?" * len(items))


def _chunks(values, size: int = 400):
    """Keep IN (...) lists well below SQLite's bound-variable limit."""
    for start in range(0, len(values), size):
        yield values[start:start + size]


# ---------- write path ----------
def _now() -> str:
    """Local time (UTC+8) as an ISO string, same format as the scraper."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_error(error: sqlite3.Error, action: str = "保存") -> ValueError:
    """Turn a SQLite failure into a message the UI can show as it is.

    Callers only handle ValueError, so every sqlite3.Error raised inside a write
    transaction is translated here; otherwise a UNIQUE clash (editing a record
    into an existing one) or a lock timeout would surface as a bare traceback
    and the dialog would look frozen — nothing happens, no hint.
    """
    text = str(error)
    lowered = text.lower()
    if isinstance(error, sqlite3.IntegrityError):
        if "unique" in lowered:
            return ValueError(
                "库里已有一条完全相同的记录（同支架 / 品牌 / 车型 / 年款），"
                "请改一下年款原文，或先删除重复的那一条")
        return ValueError("数据不完整，%s被拒绝：%s" % (action, text))
    if "locked" in lowered or "busy" in lowered:
        return ValueError("数据库正被别的程序占用（可能爬虫正在抓取），请稍后重试")
    return ValueError("%s失败：%s" % (action, text))


def write_connection() -> sqlite3.Connection:
    """Short-lived writable connection; closed right after one transaction."""
    conn = sqlite3.connect(config.DB_PATH, timeout=WRITE_TIMEOUT)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.Error:      # 爬虫正持写锁时保持默认设置即可
        pass
    conn.row_factory = sqlite3.Row
    return conn


def backup_database(keep: int = BACKUP_KEEP) -> str:
    """Consistent snapshot of ky.db into data/backup/ (WAL safe)."""
    folder = os.path.join(config.DATA_DIR, "backup")
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = os.path.join(folder, "ky-%s.db" % stamp)
    suffix = 1
    while os.path.exists(target_path):   # 同一秒内连按保存不能互相覆盖
        suffix += 1
        target_path = os.path.join(folder, "ky-%s-%d.db" % (stamp, suffix))
    source = connect_readonly()
    target = sqlite3.connect(target_path)
    failure = None
    try:
        source.backup(target)      # 走 SQLite backup API，不复制 -wal/-shm
    except sqlite3.Error as error:
        failure = error
    finally:
        target.close()
        source.close()
    if failure is not None:
        # 半成品快照没有价值，删掉；否则它会占掉「保留 10 份」里的一个名额。
        # 必须在两个连接都关闭之后再删，Windows 上打开的文件删不掉。
        try:
            os.remove(target_path)
        except OSError:
            pass
        raise _write_error(failure, "备份数据库") from failure
    _prune_backups(folder, keep)
    return target_path


def _prune_backups(folder: str, keep: int) -> None:
    """Drop the oldest snapshots; ordered by mtime, not by name."""
    paths = [os.path.join(folder, name) for name in os.listdir(folder)
             if name.startswith("ky-") and name.endswith(".db")]
    paths.sort(key=lambda path: (os.path.getmtime(path), path))
    for path in (paths[:-keep] if keep > 0 else paths):
        try:
            os.remove(path)
        except OSError:
            pass


def ensure_bracket(conn, bracket_id: str, image_file: str = None) -> None:
    """Create the bracket row, or only fill in a missing photo."""
    conn.execute(
        "INSERT INTO brackets (bracket_id, image_file, updated_at) "
        "VALUES (?, ?, ?) ON CONFLICT(bracket_id) DO UPDATE SET "
        "image_file = COALESCE(excluded.image_file, brackets.image_file), "
        "updated_at = excluded.updated_at",
        (bracket_id, image_file, _now()))


class Repository:
    """Cached dictionary access plus the two query dimensions."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        ensure_schema_ready()
        self.conn = connect_readonly()
        self._brands = None
        self._brackets = None
        self._models = {}

    # ---------- dictionaries ----------
    def brands(self) -> list:
        if self._brands is None:
            self._brands = _rows(self.conn.execute(
                "SELECT b.brand, b.logo_file, "
                "(SELECT COUNT(*) FROM models m WHERE m.brand = b.brand) "
                "AS model_count FROM brands b ORDER BY b.brand"))
        return self._brands

    def models(self, brand: str) -> list:
        if brand not in self._models:
            self._models[brand] = [row[0] for row in self.conn.execute(
                "SELECT model FROM models WHERE brand = ? ORDER BY model",
                (brand,))]
        return self._models[brand]

    def brackets(self) -> list:
        if self._brackets is None:
            self._brackets = _rows(self.conn.execute(
                "SELECT k.bracket_id, k.image_file, k.note, "
                "(SELECT COUNT(*) FROM fitments f WHERE f.bracket_id = "
                "k.bracket_id AND f.source IN ('A', 'M')) AS fitment_count "
                "FROM brackets k ORDER BY LENGTH(k.bracket_id), k.bracket_id"))
        return self._brackets

    def bracket_ids(self) -> list:
        return [row["bracket_id"] for row in self.brackets()]

    def bracket_images(self, bracket_id: str) -> list:
        """Photo list of one bracket, cover first (sort_index 0)."""
        if not bracket_id:
            return []
        rows = _rows(self.conn.execute(
            "SELECT file_name, sort_index FROM bracket_images "
            "WHERE bracket_id = ? ORDER BY sort_index, file_name", (bracket_id,)))
        if rows:
            return rows
        # 老数据 / 爬虫：只有 brackets.image_file 一张封面
        cover = self.conn.execute(
            "SELECT image_file FROM brackets WHERE bracket_id = ?",
            (bracket_id,)).fetchone()
        return [{"file_name": cover[0], "sort_index": 0}] if cover and cover[0] else []

    def bracket_note(self, bracket_id: str) -> str:
        """Remark of one bracket ('' when unset / unknown)."""
        if not bracket_id:
            return ""
        row = self.conn.execute(
            "SELECT note FROM brackets WHERE bracket_id = ?",
            (bracket_id,)).fetchone()
        return (row[0] or "") if row else ""

    # ---------- Q1: model -> bracket ----------
    def model_brackets(self, brand: str, model: str = None,
                       year: int = None) -> list:
        # id 供查询页就地改写 / 删除记录定位，不参与显示
        sql = ("SELECT id, bracket_id, years_raw, year_from, year_to, years_json, "
               "source, model FROM fitments WHERE brand = ?")
        params = [brand]
        if model:
            sql += " AND model LIKE ?"
            params.append("%" + model + "%")
        if year:
            sql += (" AND (years_json LIKE ? OR year_from IS NULL)")
            params.append("%" + str(year) + "%")
        sql += " ORDER BY source DESC, year_from"
        return _rows(self.conn.execute(sql, params))

    # ---------- Q2: bracket -> models ----------
    def bracket_models(self, bracket_id: str, brand: str = None) -> list:
        # 'M' 必须一起查，否则刚手工录入的支架在反查页看不到自己
        sql = ("SELECT id, brand, model, years_raw, year_from, year_to, source "
               "FROM fitments WHERE bracket_id = ? AND source IN ('A', 'M')")
        params = [bracket_id]
        if brand:
            sql += " AND brand = ?"
            params.append(brand)
        sql += " ORDER BY brand, model"
        return _rows(self.conn.execute(sql, params))

    # ---------- write path: manual entry ----------
    def reload(self) -> None:
        """Drop the dictionary caches after a write."""
        self._brands = None
        self._brackets = None
        self._models = {}

    def manual_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM fitments WHERE source = ?",
            (MANUAL_SOURCE,)).fetchone()[0]

    def manual_recent(self, limit: int = 6) -> list:
        return _rows(self.conn.execute(
            "SELECT bracket_id, brand, model, years_raw, year_from, year_to, "
            "fetched_at FROM fitments WHERE source = ? "
            "ORDER BY fetched_at DESC, id DESC LIMIT ?",
            (MANUAL_SOURCE, limit)))

    def add_manual(self, pairs, years_raw: str = "", targets=(),
                   bracket: dict = None) -> dict:
        """Insert one manual batch in a single transaction.

        pairs   : [(bracket_id, brand, model), ...] — one fitment per entry
        targets : [(brand, model), ...]             — created even without pairs
        bracket : {"bracket_id":…, "image_file":…}  — created / photo filled in
                  {"bracket_id":…, "images":[…] }   — 图片整表对账（首张=封面，
                                                     不在列表里的旧图被删行）
        """
        start, end, years_json, ok, message = years.parse_years(years_raw)
        if not ok:
            raise ValueError(message)
        # 空年款存空串而不是 NULL：UNIQUE 认为 NULL 互不相等，存 NULL 会漏判重
        stored_raw = (years_raw or "").strip()
        stamp = _now()
        snapshot = backup_database()
        conn = write_connection()
        added = skipped = 0
        try:
            with conn:                      # 成功提交，异常整批回滚
                if bracket:
                    self._save_bracket(conn, bracket, stamp)
                for brand, model in targets:
                    self._ensure_model(conn, brand, model, stamp)
                for bracket_id, brand, model in pairs:
                    self._ensure_model(conn, brand, model, stamp)
                    # 先判重再插入：INSERT OR IGNORE 会把 NOT NULL 之类的真错误
                    # 也一起吞掉并计入「已存在」，回执就会撒谎。
                    # 判重故意不看 source：爬虫（A/B）已经收录了同一组合时，
                    # 再写一条 M 行只会在两个查询页里变成两条一样的记录。
                    # COALESCE 让爬虫写下的 NULL 年款与手录的空串视为同一行。
                    exists = conn.execute(
                        "SELECT source FROM fitments WHERE bracket_id = ? AND "
                        "brand = ? AND model = ? AND "
                        "COALESCE(years_raw, '') = ? LIMIT 1",
                        (bracket_id, brand, model, stored_raw)).fetchone()
                    if exists:
                        skipped += 1
                        continue
                    conn.execute(
                        "INSERT INTO fitments (source, bracket_id, brand, model, "
                        "years_raw, year_from, year_to, years_json, fetched_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (MANUAL_SOURCE, bracket_id, brand, model, stored_raw,
                         start, end, years_json, stamp))
                    added += 1
        except sqlite3.Error as error:
            raise _write_error(error) from error
        finally:
            conn.close()
        self.reload()
        return {"added": added, "skipped": skipped, "backup": snapshot}

    def add_brand_models(self, brand: str, models=()) -> dict:
        """Create one brand plus any number of models (dictionary only).

        Snapshot first, then one transaction — same policy as add_manual().
        fitments 一行都不写：这里只是把字典补全，适配关系仍由主表单保存。
        """
        brand = (brand or "").strip()
        if not brand:
            raise ValueError("请填写品牌名")
        names, seen = [], set()
        for name in models:
            name = (name or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        stamp = _now()
        snapshot = backup_database()
        conn = write_connection()
        created = skipped = 0
        existed = False
        try:
            with conn:
                existed = conn.execute(
                    "SELECT 1 FROM brands WHERE brand = ?", (brand,)).fetchone() is not None
                conn.execute(
                    "INSERT INTO brands (brand, updated_at) VALUES (?, ?) "
                    "ON CONFLICT(brand) DO UPDATE SET updated_at = excluded.updated_at",
                    (brand, stamp))
                for name in names:
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO models (brand, model) VALUES (?, ?)",
                        (brand, name))
                    if cursor.rowcount:
                        created += 1
                    else:
                        skipped += 1
        except sqlite3.Error as error:
            raise _write_error(error) from error
        finally:
            conn.close()
        self.reload()
        return {"brand": brand, "brand_created": not existed,
                "models_added": created, "models_skipped": skipped,
                "backup": snapshot}

    def save_bracket_meta(self, bracket_id: str, note=None, images=None) -> dict:
        """Rewrite one bracket's remark and/or its photo list (2026-10-28).

        两个参数互相独立：``note=None`` 不动备注，``images=None`` 不动图片，
        所以「只改备注」不会碰图片行，「只换图」也不会清掉备注。
        支架号不可改（用户明确要求）：改号要级联 fitments / bracket_images，
        且磁盘文件名还压着旧号，收益远小于风险。
        """
        bracket_id = (bracket_id or "").strip()
        if not bracket_id:
            raise ValueError("缺少支架号")
        if note is not None:
            note = (note or "").strip()
        stamp = _now()
        snapshot = backup_database()
        conn = write_connection()
        try:
            with conn:                     # 成功提交，异常整批回滚
                exists = conn.execute(
                    "SELECT 1 FROM brackets WHERE bracket_id = ?",
                    (bracket_id,)).fetchone()
                if not exists:
                    raise ValueError("支架 %s 不存在，可能已被删除" % bracket_id)
                if note is not None:
                    conn.execute(
                        "UPDATE brackets SET note = ?, updated_at = ? "
                        "WHERE bracket_id = ?", (note, stamp, bracket_id))
                if images is not None:
                    # 复用整表对账：首张=封面，不在列表里的旧图删行不删文件
                    self._save_bracket(
                        conn, {"bracket_id": bracket_id, "images": list(images)}, stamp)
        except sqlite3.Error as error:
            raise _write_error(error) from error
        finally:
            conn.close()
        self.reload()
        return {"bracket_id": bracket_id, "note": note,
                "images": None if images is None else list(images),
                "backup": snapshot}

    @staticmethod
    def _save_bracket(conn, bracket: dict, stamp: str) -> None:
        """Create / refresh one bracket row and (when given) its photo list.

        ``images`` 是「期望的完整列表」而不是增量：顺序即 sort_index，
        第一张同时写进 brackets.image_file 当封面；列表里没有的旧图只删
        bracket_images 行，磁盘文件保留（删文件不可逆，交给用户自己清理）。
        """
        bracket_id = bracket["bracket_id"]
        images = bracket.get("images")
        if images is None:                      # 爬虫 / 老调用：只补封面
            ensure_bracket(conn, bracket_id, bracket.get("image_file"))
            return
        images = [name for name in images if name]
        conn.execute(
            "INSERT INTO brackets (bracket_id, image_file, updated_at) "
            "VALUES (?, ?, ?) ON CONFLICT(bracket_id) DO UPDATE SET "
            "image_file = excluded.image_file, updated_at = excluded.updated_at",
            (bracket_id, images[0] if images else None, stamp))
        # 备注（2026-10-28）：只有显式给了 note 才写，None 表示「这条调用不管备注」
        note = bracket.get("note")
        if note is not None:
            conn.execute("UPDATE brackets SET note = ? WHERE bracket_id = ?",
                         (note, bracket_id))
        keep = set(images)
        existing = {row[0] for row in conn.execute(
            "SELECT file_name FROM bracket_images WHERE bracket_id = ?",
            (bracket_id,))}
        for name in existing - keep:
            conn.execute("DELETE FROM bracket_images "
                         "WHERE bracket_id = ? AND file_name = ?",
                         (bracket_id, name))
        for index, name in enumerate(images):
            conn.execute(
                "INSERT INTO bracket_images "
                "(bracket_id, file_name, sort_index, added_at) VALUES (?,?,?,?) "
                "ON CONFLICT(bracket_id, file_name) DO UPDATE SET "
                "sort_index = excluded.sort_index",
                (bracket_id, name, index, stamp))

    @staticmethod
    def _ensure_model(conn, brand: str, model: str, stamp: str) -> None:
        conn.execute("INSERT OR IGNORE INTO brands (brand, updated_at) "
                     "VALUES (?, ?)", (brand, stamp))
        conn.execute("INSERT OR IGNORE INTO models (brand, model) VALUES (?, ?)",
                     (brand, model))

    # ---------- in-place edit / delete (query pages) ----------
    def update_fitment(self, row_id: int, changes: dict) -> dict:
        """Rewrite one fitment row; the year text is re-parsed when supplied.

        Snapshot first, then a single transaction — same policy as add_manual.
        """
        brand = (changes.get("brand") or "").strip()
        model = (changes.get("model") or "").strip()
        if not brand or not model:
            raise ValueError("品牌和车型不能为空")
        stored_raw = changes.get("years_raw")
        start = end = years_json = None
        if stored_raw is not None:
            stored_raw = stored_raw.strip()
            start, end, years_json, ok, message = years.parse_years(stored_raw)
            if not ok:
                raise ValueError(message)
        snapshot = backup_database()
        stamp = _now()
        conn = write_connection()
        try:
            with conn:
                self._ensure_model(conn, brand, model, stamp)
                if stored_raw is None:
                    cursor = conn.execute(
                        "UPDATE fitments SET brand = ?, model = ? WHERE id = ?",
                        (brand, model, row_id))
                else:
                    cursor = conn.execute(
                        "UPDATE fitments SET brand = ?, model = ?, years_raw = ?, "
                        "year_from = ?, year_to = ?, years_json = ? WHERE id = ?",
                        (brand, model, stored_raw, start, end, years_json, row_id))
                if cursor.rowcount == 0:
                    raise ValueError("这条记录已不存在，可能被别处删掉了")
        except sqlite3.Error as error:
            raise _write_error(error) from error
        finally:
            conn.close()
        self.reload()
        return {"backup": snapshot}

    def delete_fitment(self, row_id: int) -> dict:
        """Delete one fitment row; only fitments is touched, not the字典表."""
        snapshot = backup_database()
        conn = write_connection()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM fitments WHERE id = ?", (row_id,))
                if cursor.rowcount == 0:
                    raise ValueError("这条记录已不存在，可能被别处删掉了")
        except sqlite3.Error as error:
            raise _write_error(error, "删除") from error
        finally:
            conn.close()
        self.reload()
        return {"backup": snapshot}

    def delete_fitments(self, row_ids) -> dict:
        """Delete several fitment rows: one snapshot, one transaction (2026-10-28).

        逐条调 delete_fitment() 会为每条写一份快照、各开一次事务
        （data/backup/ 只留 10 份，连删十几条就把更早的备份挤掉），
        而且中途失败会留下「删了一半」的状态。批量版：先查哪些 id 还在，
        再备份一次，最后在同一个事务里删完 —— 要么全删、要么全不删。

        已经不存在（被别的窗口 / 爬虫删掉）的 id 不算失败，单独计入 missing。
        """
        ids = sorted({int(row_id) for row_id in row_ids
                      if row_id not in (None, "")})
        if not ids:
            raise ValueError("没有勾选要删除的记录")
        alive = []
        for part in _chunks(ids):
            alive.extend(row[0] for row in self.conn.execute(
                "SELECT id FROM fitments WHERE id IN (%s)" % _marks(part),
                tuple(part)))
        if not alive:
            return {"deleted": 0, "missing": len(ids), "backup": ""}
        snapshot = backup_database()
        conn = write_connection()
        deleted = 0
        try:
            with conn:                     # 成功提交，异常整批回滚
                for part in _chunks(alive):
                    cursor = conn.execute(
                        "DELETE FROM fitments WHERE id IN (%s)" % _marks(part),
                        tuple(part))
                    deleted += cursor.rowcount
        except sqlite3.Error as error:
            raise _write_error(error, "删除") from error
        finally:
            conn.close()
        self.reload()
        return {"deleted": deleted, "missing": len(ids) - deleted,
                "backup": snapshot}

    # ---------- crosscheck aggregate (status bar hint) ----------
    def diff_counts(self) -> list:
        return _rows(self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM crosscheck GROUP BY status "
            "ORDER BY n DESC"))

    # ---------- global search ----------
    def global_search(self, keyword: str, limit: int = 20) -> dict:
        like = "%" + keyword + "%"
        brands = [row[0] for row in self.conn.execute(
            "SELECT brand FROM brands WHERE brand LIKE ? LIMIT ?", (like, limit))]
        models = _rows(self.conn.execute(
            "SELECT brand, model FROM models WHERE model LIKE ? LIMIT ?",
            (like, limit)))
        brackets = [row[0] for row in self.conn.execute(
            "SELECT bracket_id FROM brackets WHERE bracket_id LIKE ? LIMIT ?",
            (like, limit))]
        return {"brands": brands, "models": models, "brackets": brackets}

    def stats(self) -> dict:
        def count(table: str) -> int:
            return self.conn.execute(
                "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
        return {"brackets": count("brackets"), "brands": count("brands"),
                "models": count("models"), "fitments": count("fitments"),
                "crosscheck": count("crosscheck"),
                "db_mtime": os.path.getmtime(self.db_path)}

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

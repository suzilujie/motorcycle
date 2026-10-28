# -*- coding: utf-8 -*-
"""Application configuration: paths, name, and the two switchable palettes.

Two runtime shapes are supported:

* source tree — data lives in ``<root>/scraper/data`` next to the code;
* frozen exe  — data lives in ``<exe>/data`` when that folder is writable
  (portable copy), otherwise in ``%LOCALAPPDATA%/KYBracket/data``. The copy
  shipped next to the exe is seeded into the fallback folder on first launch.
"""

from __future__ import annotations

import os
import shutil
import sys

FROZEN = bool(getattr(sys, "frozen", False))
USER_DIR_NAME = "KYBracket"      # %LOCALAPPDATA% 下的文件夹名（纯 ASCII，避免路径问题）


def _writable(folder: str) -> bool:
    """True when a file can be created inside folder (data must be writable)."""
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write_probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _seed_data(target: str, bundled: str) -> None:
    """Copy the shipped database / images into a fresh fallback folder."""
    if os.path.exists(os.path.join(target, "ky.db")):
        return
    if not os.path.exists(os.path.join(bundled, "ky.db")):
        return
    for name in ("ky.db", "images", "thumbs"):
        source = os.path.join(bundled, name)
        destination = os.path.join(target, name)
        if not os.path.exists(source) or os.path.exists(destination):
            continue
        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            shutil.copyfile(source, destination)


if FROZEN:
    # 打包后没有源码目录：exe 所在目录即根目录
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    ROOT_DIR = APP_DIR
    SCRAPER_DIR = os.path.join(APP_DIR, "scraper")
    bundled_data = os.path.join(APP_DIR, "data")
    if _writable(bundled_data):            # 绿色便携：数据就在 exe 旁边
        DATA_DIR = bundled_data
    else:                                  # 只读安装位置：退到用户目录
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        DATA_DIR = os.path.join(base, USER_DIR_NAME, "data")
        _seed_data(DATA_DIR, bundled_data)
    LOG_DIR = os.path.join(os.path.dirname(DATA_DIR), "logs")
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(APP_DIR)
    SCRAPER_DIR = os.path.join(ROOT_DIR, "scraper")
    DATA_DIR = os.path.join(SCRAPER_DIR, "data")
    LOG_DIR = os.path.join(ROOT_DIR, "logs")

DB_PATH = os.path.join(DATA_DIR, "ky.db")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
REPORT_DIR = os.path.join(DATA_DIR, "report")

APP_NAME = "后视镜支架查询"
APP_SUBTITLE = "车型 / 支架 双向反查"
APP_VERSION = "1.0.0"

THUMB_SIZE = (168, 126)

# Two switchable palettes. Every color used by the UI lives here, so a theme
# switch only needs "re-apply the stylesheet" (no widget rebuild).
PALETTES = {
    # 深色主题：提亮一档的深灰（深色牌方案 A）
    "dark": {
        "bg": "#2c2c2c",
        "panel": "#363636",
        "panel2": "#303030",
        "card": "#3a3a3a",
        "input": "#262626",
        "alt_row": "#434343",
        "header": "#484848",
        "border": "#4c4c4c",
        "scroll": "#5f5f5f",
        "scroll_hover": "#6e6e6e",
        "text": "#f2f2f2",
        "dim": "#b4b4b4",
        "faint": "#868686",
        "on_accent": "#ffffff",
        "accent": "#6cc9ff",
        "accent_bg": "#1a86d9",
        "ok": "#6cc788",
        "warn": "#e3a008",
        "bad": "#f1707b",
        # 徽标（chip）、图版（photo plate）专用
        "chip_bg": "#3f3f3f",
        "chip_line": "#555555",
        "plate": "#ececec",
        "sel_bg": "#3c4a55",
    },
    # 浅色主题：白底深字（方案 C）
    "light": {
        "bg": "#f3f3f3",
        "panel": "#fafafa",
        "panel2": "#ffffff",
        "card": "#ffffff",
        "input": "#ffffff",
        "alt_row": "#f7f7f7",
        "header": "#ececec",
        "border": "#d4d4d4",
        "scroll": "#bfbfbf",
        "scroll_hover": "#a8a8a8",
        "text": "#1d1d1d",
        "dim": "#5c5c5c",
        "faint": "#8a8a8a",
        "on_accent": "#ffffff",
        "accent": "#0f6cbd",
        "accent_bg": "#0f6cbd",
        "ok": "#1a7f37",
        "warn": "#b45309",
        "bad": "#b91c1c",
        # 徽标（chip）、图版（photo plate）专用
        "chip_bg": "#eef2f7",
        "chip_line": "#d4d4d4",
        "plate": "#f4f4f4",
        "sel_bg": "#dce9f7",
    },
}

THEME_ORDER = ("dark", "light")
THEME_LABELS = {"dark": "深色", "light": "浅色"}
# 默认浅色（2026-10-27 用户指定）；用户手动切换后由 QSettings "ui/theme" 覆盖本默认
DEFAULT_THEME = "light"

_active_theme = DEFAULT_THEME
# 当前生效的调色板（set_theme 会重新指向另一套字典）
C = PALETTES[_active_theme]


def current_theme() -> str:
    """Name of the theme currently in use."""
    return _active_theme


def set_theme(name: str) -> str:
    """Switch the active palette; unknown names fall back to the default."""
    global _active_theme, C
    if name not in PALETTES:
        name = DEFAULT_THEME
    _active_theme = name
    C = PALETTES[name]
    return _active_theme


def next_theme() -> str:
    """Name of the theme a toggle click should switch to."""
    return "light" if _active_theme == "dark" else "dark"


def image_path(file_name: str) -> str:
    """Absolute path of a downloaded image, or empty string."""
    if not file_name:
        return ""
    return os.path.join(IMAGE_DIR, file_name)


for _directory in (LOG_DIR, THUMB_DIR):
    os.makedirs(_directory, exist_ok=True)

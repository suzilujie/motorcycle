# -*- coding: utf-8 -*-
"""Image loading with a disk thumbnail cache (keeps the gallery smooth)."""

from __future__ import annotations

import os

import config

_PIXMAP_CACHE = {}


def source_path(file_name: str) -> str:
    return config.image_path(file_name) if file_name else ""


def thumb_path(file_name: str) -> str:
    stem, _ext = os.path.splitext(file_name)
    return os.path.join(config.THUMB_DIR, stem + ".png")


def ensure_thumb(file_name: str) -> str:
    """Return a cached thumbnail path, generating it on first use."""
    src = source_path(file_name)
    if not src or not os.path.exists(src):
        return ""
    dest = thumb_path(file_name)
    if os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(src):
        return dest
    from PySide6.QtGui import QImageReader  # imported lazily for testability

    reader = QImageReader(src)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid():
        scale = min(config.THUMB_SIZE[0] / max(size.width(), 1),
                    config.THUMB_SIZE[1] / max(size.height(), 1))
        if scale < 1:
            reader.setScaledSize(size * scale)
    image = reader.read()
    if image.isNull():
        return ""
    if not image.save(dest, "PNG"):
        return src
    return dest


def pixmap(file_name: str, thumb: bool = True):
    """QPixmap for a downloaded image, with an in-memory cache."""
    key = (file_name, thumb)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    from PySide6.QtGui import QPixmap

    path = ensure_thumb(file_name) if thumb else source_path(file_name)
    if not path or not os.path.exists(path):
        return None
    result = QPixmap(path)
    if result.isNull():
        return None
    _PIXMAP_CACHE[key] = result
    return result


def clear_cache() -> None:
    _PIXMAP_CACHE.clear()

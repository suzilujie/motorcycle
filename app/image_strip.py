# -*- coding: utf-8 -*-
"""缩略图条：支架多图的增删与封面选择（录入页与编辑弹窗共用）。

条目格式 {"src": 已存文件名 或 待导入的本地路径, "new": bool}，
第一张即封面（写回 brackets.image_file）。删除只把条目移出列表，
磁盘文件不动 —— 真正落库发生在调用方的事务里。
"""

from __future__ import annotations

import os
import re
import shutil

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

import config
import thumbs


def import_image(bracket_id: str, path: str, index: int = 1) -> str:
    """Copy a picked photo into data/images as bracket_<id>_<n>.<ext>.

    一个支架可以有多张图，文件名带序号，同名时往后顺延，
    不会像以前那样重选一次就把上一张覆盖掉。
    """
    extension = os.path.splitext(path)[1].lower() or ".jpg"
    safe_id = re.sub(r"[^0-9A-Za-z_-]", "_", bracket_id)
    os.makedirs(config.IMAGE_DIR, exist_ok=True)
    number = max(1, index)
    while True:
        file_name = "bracket_%s_%02d%s" % (safe_id, number, extension)
        target = os.path.join(config.IMAGE_DIR, file_name)
        if not os.path.exists(target):
            break
        number += 1
    shutil.copyfile(path, target)
    thumbs.clear_cache()
    return file_name


class ImageStrip(QWidget):
    """Grid of thumbnails; click = set cover, × = drop, add_paths() = append."""

    changed = Signal()

    def __init__(self, thumb=(100, 76), columns=3, limit=6, parent=None):
        super().__init__(parent)
        self.THUMB = thumb
        self.COLUMNS = max(1, columns)
        self.LIMIT = max(1, limit)
        self._images = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(6)

    # ---------- state ----------
    def images(self) -> list:
        return list(self._images)

    def count(self) -> int:
        return len(self._images)

    def full(self) -> bool:
        return len(self._images) >= self.LIMIT

    def set_images(self, images) -> None:
        self._images = [dict(item) for item in images][:self.LIMIT]
        self._rebuild()

    def add_paths(self, paths) -> int:
        """Append local files; returns how many were skipped (bad or over limit)."""
        skipped = 0
        for path in paths:
            if self.full() or QPixmap(path).isNull():
                skipped += 1
                continue
            self._images.append({"src": path, "new": True})
        self._rebuild()
        return skipped

    # ---------- render ----------
    def _pixmap_of(self, entry: dict, width: int, height: int):
        if entry.get("new"):
            pixmap = QPixmap(entry["src"])
        else:
            pixmap = thumbs.pixmap(entry["src"]) or QPixmap()
        if pixmap.isNull():
            return None
        return pixmap.scaled(width, height,
                             Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for index, entry in enumerate(self._images):
            self._grid.addWidget(self._thumb(index, entry),
                                 index // self.COLUMNS, index % self.COLUMNS)
        self.changed.emit()

    def _thumb(self, index: int, entry: dict) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(*self.THUMB)
        button.setIconSize(QSize(*self.THUMB))
        pixmap = self._pixmap_of(entry, *self.THUMB)
        if pixmap is not None:
            button.setIcon(QIcon(pixmap))
        button.setToolTip("%s（点击设为封面）"
                          % ("封面 · 第 1 张" if index == 0
                             else "第 %d 张" % (index + 1)))
        button.clicked.connect(
            lambda _checked=False, position=index: self._move_to_cover(position))
        close = QPushButton("×", button)
        close.setObjectName("flat")
        close.setFixedSize(16, 16)
        close.move(self.THUMB[0] - 18, 1)
        close.setToolTip("移除这张（保存时生效，磁盘文件保留）")
        close.clicked.connect(
            lambda _checked=False, position=index: self._remove(index))
        if index == 0:
            badge = QLabel("封面", button)
            badge.setObjectName("chip")
            badge.move(1, self.THUMB[1] - 18)
        return button

    def _move_to_cover(self, index: int) -> None:
        if 0 <= index < len(self._images) and index:
            self._images.insert(0, self._images.pop(index))
            self._rebuild()

    def _remove(self, index: int) -> None:
        if 0 <= index < len(self._images):
            self._images.pop(index)
            self._rebuild()

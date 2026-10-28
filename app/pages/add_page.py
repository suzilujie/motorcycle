# -*- coding: utf-8 -*-
"""Manual entry page: mode switch + the two entry forms + recent manual rows.

Page shell only; the forms live in pages/entry_forms.py. Every successful save
emits ``saved`` so MainWindow can drop its search index and refresh the two
query pages.
"""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QVBoxLayout,
                               QWidget)

import config
import ui
import years
from pages.entry_forms import BracketForm, ModelForm

MODE_LABELS = ("新增车型", "新增支架")
# 2026-10-28 用户要求隐藏「新增车型」页签，只留「新增支架」。
# 与 main.py 的 HIDDEN_VIEWS 同一思路：表单还留在 stack 里（set_mode(0) 仍可用），
# 只是顶栏不露按钮；想恢复删掉这一行即可。
HIDDEN_MODES = ("新增车型",)
DEFAULT_MODE = "新增支架"

COLUMNS = [
    ("bracket_id", "支架号", 92),
    ("brand", "品牌", 130),
    ("model", "车型", 0),
    ("range", "年款", 118),
    ("source", "来源", 58),
    ("fetched_at", "录入时间", 128),
]


def _local_stamp(text: str) -> str:
    """ISO string (with offset) -> local 'MM-DD HH:MM'."""
    if not text:
        return ""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return text
    if moment.tzinfo is None:
        moment = moment.astimezone()      # 库里存的是本地时间
    return moment.astimezone().strftime("%m-%d %H:%M")


class AddPage(QWidget):
    """录入页：两个模式共用一个 stack。

    2026-10-28 起「新增车型」页签被隐藏（HIDDEN_MODES），默认直接进「新增支架」；
    表单本身仍在 stack 里，需要时 set_mode(0) 或删掉 HIDDEN_MODES 就能恢复。
    """

    saved = Signal(dict)

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("filterBar")
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(8)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons = []
        for index, label in enumerate(MODE_LABELS):
            button = QPushButton(label)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.mode_group.addButton(button, index)
            row.addWidget(button)
            self.mode_buttons.append(button)
        visible = [button for button in self.mode_buttons
                   if button.text() not in HIDDEN_MODES]
        for button in self.mode_buttons:
            button.setVisible(button in visible)
        if len(visible) <= 1:
            # 只剩一个模式时页签毫无意义（点了也不会变），连那一个也收起来，
            # 顶栏退化成一条细信息条（右侧仍显示手工条数与数据时间）。
            for button in visible:
                button.setVisible(False)
            bar.setFixedHeight(40)
        self.mode_group.buttons()[MODE_LABELS.index(DEFAULT_MODE)].setChecked(True)
        self.mode_group.idClicked.connect(self.set_mode)
        row.addStretch(1)
        self.hint = ui.hint("")
        row.addWidget(self.hint)
        outer.addWidget(bar)

        self.stack = QStackedWidget()
        self.model_form = ModelForm(repo)
        self.bracket_form = BracketForm(repo)
        for form in (self.model_form, self.bracket_form):
            self.stack.addWidget(form)
            form.saved.connect(self._on_saved)
            form.dictionary_changed.connect(self._on_dictionary_changed)
        outer.addWidget(self.stack, 1)
        self.set_mode(MODE_LABELS.index(DEFAULT_MODE))

        recent = QWidget()
        recent_column = QVBoxLayout(recent)
        recent_column.setContentsMargins(16, 4, 16, 8)
        recent_column.setSpacing(4)
        recent_column.addWidget(ui.hint(
            "最近手工录入（source = M，按时间倒序）"))
        self.table = ui.Page.make_table(COLUMNS, chips=(3,), dots=(4,))
        self.table.setFixedHeight(160)
        recent_column.addWidget(self.table)
        outer.addWidget(recent)

        self.refresh()

    # ---------- navigation ----------
    def set_mode(self, index: int) -> None:
        index = max(0, min(len(MODE_LABELS) - 1, index))
        self.stack.setCurrentIndex(index)
        self.mode_group.buttons()[index].setChecked(True)

    # ---------- data ----------
    def refresh(self) -> None:
        """Reload dictionaries, the recent table and the header hint."""
        self.model_form.refresh()
        self.bracket_form.refresh()
        self._load_recent()
        stamp = ""
        if os.path.exists(config.DB_PATH):
            stamp = datetime.fromtimestamp(
                os.path.getmtime(config.DB_PATH)).strftime("%m-%d %H:%M")
        self.hint.setText("手工适配 %d 条 · 数据 %s · 保存前自动备份到 data/backup/"
                          % (self.repo.manual_count(), stamp))

    def _load_recent(self) -> None:
        rows = []
        for row in self.repo.manual_recent(6):
            row["range"] = years.display_range(row.get("year_from"),
                                               row.get("year_to"))
            row["fetched_at"] = _local_stamp(row.get("fetched_at"))
            rows.append(row)
        self.table._model.set_rows(rows)

    def _on_saved(self, result: dict) -> None:
        self.refresh()
        self.saved.emit(result)

    def _on_dictionary_changed(self) -> None:
        """新增车型：本页已自己刷过，这里只通知主窗口重载其他页字典。"""
        self.saved.emit({"added": 0, "skipped": 0, "backup": "",
                         "dictionary": True})

    def refresh_theme(self) -> None:
        self.table.viewport().update()

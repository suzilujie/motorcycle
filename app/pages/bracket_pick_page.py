# -*- coding: utf-8 -*-
"""Bracket picker: every bracket number in one two-column card grid."""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

import search
import ui

GROUP_TITLE = "所有车架"
_NUM = re.compile(r"^(\d+)(.*)$")


def sort_key(bracket_id: str):
    """Natural order: 1, 2, 3A, 3B, 4 … 10, 11 (not 1, 10, 11, 2).

    repo.brackets() orders by LENGTH(id) then the raw string, which pushes 3A
    behind 10; the picker needs the order a human reads.
    """
    text = str(bracket_id or "")
    match = _NUM.match(text)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (1, 0, text)


class BracketPickerPage(ui.Page):
    """Browse every bracket number as cards; picking one prefills 「按支架查」."""

    bracket_chosen = Signal(str)

    def __init__(self, repo, parent=None):
        super().__init__(repo, parent)
        self._rows = []

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("输入关键字…（如 3A、10）")
        self.search_box.setFixedWidth(320)
        self.add_filter(self.search_box)
        self.add_filter_stretch()
        self.count_label = ui.hint("")
        self.filter_row.addWidget(self.count_label)

        self.grid = ui.PickGrid()
        self.grid.picked.connect(self.bracket_chosen.emit)
        self.body.addWidget(self.grid, 1)

        self.search_box.textChanged.connect(self._rerender)
        self.refresh_data()

    # ---------- data ----------
    def refresh_data(self) -> None:
        self._rows = sorted(self.repo.brackets(),
                            key=lambda row: sort_key(row["bracket_id"]))
        self._rerender()

    def refresh_if_changed(self) -> None:
        """Cheap path after an edit / delete: rebuild only if the set moved.

        支架集合通常不变，变的只是「N 适配」；整体重建 300 张卡片约 130ms，
        每次编辑都付这笔钱没必要。
        """
        rows = sorted(self.repo.brackets(),
                      key=lambda row: sort_key(row["bracket_id"]))
        if tuple(str(row["bracket_id"]) for row in rows) != tuple(
                str(row["bracket_id"]) for row in self._rows):
            self._rows = rows
            self._rerender()
            return
        self._rows = rows
        self.grid.set_metas({str(row["bracket_id"]):
                             "%d 适配" % row["fitment_count"] for row in rows})

    def _rerender(self, *_args) -> None:
        rows = self._rows
        text = self.search_box.text().strip()
        if text:
            ids = search.filter_items([str(row["bracket_id"]) for row in rows],
                                      text, len(rows) or 1)
            order = {bid: index for index, bid in enumerate(ids)}
            rows = sorted((row for row in rows
                           if str(row["bracket_id"]) in order),
                          key=lambda row: order[str(row["bracket_id"])])
        items = [{"title": "%s号" % row["bracket_id"],
                  "value": str(row["bracket_id"]),
                  "meta": "%d 适配" % row["fitment_count"],
                  "bullet": True}
                 for row in rows]
        self.count_label.setText(
            "命中 %d 个车架" % len(items) if text else "共 %d 个车架" % len(items))
        self.grid.set_groups([(GROUP_TITLE, "", items)] if items else [])

    def focus_search(self) -> None:
        self.search_box.setFocus()
        self.search_box.selectAll()

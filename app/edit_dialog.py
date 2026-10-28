# -*- coding: utf-8 -*-
"""Modal panel for rewriting one fitment record (brand / model / years)."""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

import years

# 来源说明：A/B 是爬虫抓来的行，改了它下次抓取仍可能再写一条同内容的记录
SOURCE_LABELS = {"A": "爬虫 A 路（按支架反查）",
                 "B": "爬虫 B 路（目录页）",
                 "M": "手工录入"}
CRAWLER_NOTE = "修改不会被下次抓取覆盖，但抓取可能再补一条同样内容的记录"


class RecordEditDialog(QDialog):
    """Brand / model / year text of a single fitment, edited in one panel.

    The dialog owns the write: on 「保存」 it calls repo.update_fitment() and
    keeps itself open — showing the reason inline — when validation fails, so
    the user never loses what they typed.
    """

    def __init__(self, repo, row, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.repo = repo
        self.row = row
        self.setWindowTitle("修改适配记录")
        self.setModal(True)
        self.setMinimumWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)

        title = QLabel("修改适配记录")
        title.setObjectName("dialogTitle")
        outer.addWidget(title)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("dialogSub")
            outer.addWidget(sub)
        source = str(row.get("source") or "")
        if source:
            note = QLabel(self._source_note(source))
            note.setObjectName("dialogSub")
            note.setWordWrap(True)
            outer.addWidget(note)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.brand = QLineEdit(row.get("brand") or "")
        self.model = QLineEdit(row.get("model") or "")
        self.years = QLineEdit(row.get("years_raw") or "")
        self.years.setPlaceholderText("留空 = 全部年款")
        fields = (("品牌", self.brand), ("车型", self.model), ("年款原文", self.years))
        for position, (label, widget) in enumerate(fields):
            tag = QLabel(label)
            tag.setObjectName("dialogSub")
            grid.addWidget(tag, position, 0)
            grid.addWidget(widget, position, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)

        self.hint = QLabel("")
        self.hint.setObjectName("dialogHint")
        outer.addWidget(self.hint)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primary")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.save_btn)
        outer.addLayout(actions)

        self.years.textChanged.connect(self.preview_years)
        self.preview_years(self.years.text())
        self.brand.setFocus()
        self.brand.selectAll()

    # ---------- source note ----------
    @staticmethod
    def _source_note(source: str) -> str:
        label = SOURCE_LABELS.get(source, "来源 %s" % source)
        if source == "M":
            return "来源：%s" % label
        return "来源：%s · %s" % (label, CRAWLER_NOTE)

    # ---------- year hint ----------
    def preview_years(self, text: str) -> None:
        start, end, _json, ok, message = years.parse_years(text or "")
        if not ok:
            self.set_hint("⚠ " + message, error=True)
            return
        self.set_hint("识别为 %d – %d" % (start, end) if start else "全部年款")

    def set_hint(self, text: str, error: bool = False) -> None:
        name = "dialogError" if error else "dialogHint"
        if self.hint.objectName() != name:
            self.hint.setObjectName(name)
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
        self.hint.setText(text)

    # ---------- save ----------
    def save(self) -> None:
        changes = {"brand": self.brand.text(),
                   "model": self.model.text(),
                   "years_raw": self.years.text()}
        try:
            self.repo.update_fitment(int(self.row["id"]), changes)
        except ValueError as error:
            self.set_hint("⚠ " + str(error), error=True)
            return
        except (sqlite3.Error, OSError) as error:   # 连接 / 备份一类的兜底
            self.set_hint("⚠ 保存失败：%s" % error, error=True)
            return
        self.accept()

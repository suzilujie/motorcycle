# -*- coding: utf-8 -*-
"""Modal panel for creating models under a brand (2026-10-28 改为以「车型」为主)。

用户要求把按钮从「新增品牌」改成「新增车型」：日常补的是车型，品牌多半已经有。
所以品牌改成「可编辑下拉」——已有品牌直接选，没有的品牌仍可直接输入（会一并创建）；
每个车型一个独立输入框（不是一整块 textarea），可以逐行增删、单独改错的那一行。
保存只写 brands / models 两张字典表，不产生 fitments 记录。
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

import ui

MAX_ROWS = 20
ROW_HEIGHT = 150          # 车型区可视高度（约 4 行，超出滚动）


class NewModelDialog(QDialog):
    """品牌（可新建）+ 若干车型行；成功后 brand_name / model_list / result 回传。"""

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.brand_name = ""
        self.model_list = []
        self.result = {}
        self.rows = []              # [{"box": QWidget, "edit": QLineEdit}]

        self.setWindowTitle("新增车型")
        self.setModal(True)
        self.setMinimumWidth(480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)

        title = QLabel("新增车型")
        title.setObjectName("dialogTitle")
        outer.addWidget(title)
        sub = QLabel("车型挂在品牌下：已有品牌直接选，新品牌名会一并创建")
        sub.setObjectName("dialogSub")
        sub.setWordWrap(True)
        outer.addWidget(sub)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        tag = QLabel("品牌")
        tag.setObjectName("dialogSub")
        tag.setFixedWidth(40)
        brand_row.addWidget(tag)
        self.brand_box = QComboBox()
        self.brand_box.setEditable(True)
        self.brand_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.brand_box.addItems([row["brand"] for row in repo.brands()])
        self.brand_box.setCurrentIndex(-1)
        self.brand_box.lineEdit().setPlaceholderText("选择已有品牌，或输入新品牌名")
        ui.attach_completer(self.brand_box)
        self.brand_box.currentTextChanged.connect(self._sync_chip)
        brand_row.addWidget(self.brand_box, 1)
        self.chip = QLabel("将新建")
        self.chip.setObjectName("chipNew")
        brand_row.addWidget(self.chip)
        outer.addLayout(brand_row)

        holder = QWidget()
        self.rows_box = QVBoxLayout(holder)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(6)
        self.rows_box.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(holder)
        self.scroll.setFixedHeight(ROW_HEIGHT)
        outer.addWidget(self.scroll)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.add_btn = QPushButton("＋ 再添一行")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(lambda: self.add_model_row(focus=True))
        tools.addWidget(self.add_btn)
        tools.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("dialogSub")
        tools.addWidget(self.count_label)
        outer.addLayout(tools)

        self.hint = QLabel("")
        self.hint.setObjectName("dialogHint")
        self.hint.setWordWrap(True)
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

        self.add_model_row()
        self._sync_chip()
        self._sync_count()
        self.brand_box.setFocus()

    # ---------- 车型行 ----------
    def add_model_row(self, text: str = "", focus: bool = False) -> None:
        if len(self.rows) >= MAX_ROWS:
            self.set_hint("最多 %d 行，剩下的请保存后再加一次" % MAX_ROWS,
                          error=True)
            return
        box = QWidget()
        line = QHBoxLayout(box)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        edit = QLineEdit(text)
        edit.setPlaceholderText("车型名，如 启源A05")
        edit.textChanged.connect(self._sync_count)
        line.addWidget(edit, 1)
        close = QPushButton("×", box)
        close.setObjectName("flat")
        close.setFixedSize(24, 24)
        close.setToolTip("删除这一行")
        close.clicked.connect(lambda _checked=False, cell=box: self._drop_row(cell))
        line.addWidget(close)
        self.rows.append({"box": box, "edit": edit})
        self.rows_box.insertWidget(self.rows_box.count() - 1, box)
        self._sync_count()
        if focus:
            edit.setFocus()

    def _drop_row(self, cell) -> None:
        entry = next((row for row in self.rows if row["box"] is cell), None)
        if entry is None:
            return
        self.rows.remove(entry)
        cell.setParent(None)
        cell.deleteLater()
        if not self.rows:               # 始终留一个空行，删错了也能继续填
            self.add_model_row()
        self._sync_count()

    def model_names(self) -> list:
        """去空白、去重后的车型名（空行忽略）。"""
        names, seen = [], set()
        for row in self.rows:
            name = row["edit"].text().strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    # ---------- 实时提示 ----------
    def _sync_count(self, *_args) -> None:
        count = len(self.model_names())
        self.count_label.setText("将新增 %d 个车型" % count)
        self.save_btn.setText("保存（%d 个车型）" % count if count else "保存")
        self.save_btn.setEnabled(bool(count))

    def _sync_chip(self, *_args) -> None:
        brand = self.brand_box.currentText().strip()
        known = bool(brand) and any(row["brand"] == brand
                                    for row in self.repo.brands())
        name = "chip" if known else "chipNew"
        if self.chip.objectName() != name:
            self.chip.setObjectName(name)
            self.chip.style().unpolish(self.chip)
            self.chip.style().polish(self.chip)
        self.chip.setText("已存在" if known else "将新建")

    def set_hint(self, text: str, error: bool = False) -> None:
        name = "dialogError" if error else "dialogHint"
        if self.hint.objectName() != name:
            self.hint.setObjectName(name)
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
        self.hint.setText(text)

    # ---------- 保存 ----------
    def save(self) -> None:
        brand = self.brand_box.currentText().strip()
        models = self.model_names()
        if not brand:
            self.set_hint("⚠ 请先选或填一个品牌", error=True)
            return
        if not models:
            # 改成「新增车型」之后不再支持「只建品牌」：那属于品牌维护，不是这里的事
            self.set_hint("⚠ 请至少填一个车型名", error=True)
            return
        try:
            result = self.repo.add_brand_models(brand, models)
        except ValueError as error:
            self.set_hint("⚠ " + str(error), error=True)
            return
        except (sqlite3.Error, OSError) as error:   # 连接 / 备份一类的兜底
            self.set_hint("⚠ 保存失败：%s" % error, error=True)
            return
        self.brand_name = brand
        self.model_list = models
        self.result = result
        self.accept()

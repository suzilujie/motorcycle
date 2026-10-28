# -*- coding: utf-8 -*-
"""Q2: query compatible models by bracket number (bracket -> models)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

import delegates
import models
import ui
from bracket_dialog import BracketEditDialog, FitmentPickDialog
from edit_dialog import RecordEditDialog
from pages.model_page import year_range

COLUMNS = [
    # 勾选列（2026-10-28）：批量删除用；删除入口已上移到表格上方的工具条
    (models.DictTableModel.CHECK_KEY, "", 36),
    ("brand", "品牌", 130),
    ("model", "车型", 0),
    ("range", "年款区间", 110),
    ("years_raw", "年款原文", 260),
    ("source", "来源", 60),
    ("__ops__", "操作", 60),
]

OPS_COLUMN = len(COLUMNS) - 1


class BracketPage(ui.Page):
    def __init__(self, repo, parent=None):
        super().__init__(repo, parent)
        self._catalog = {}
        self._current = ("", "")

        self.bracket_box = QComboBox()
        self.bracket_box.setEditable(True)
        self.bracket_box.setFixedWidth(140)
        self.bracket_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.add_filter(self.bracket_box, "支架号")

        self.brand_box = QComboBox()
        self.brand_box.setEditable(True)
        self.brand_box.setFixedWidth(170)
        self.brand_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.add_filter(self.brand_box, "品牌")
        self.add_filter_stretch()
        ui.attach_completer(self.bracket_box)
        ui.attach_completer(self.brand_box)

        counts = {row["status"]: row["n"] for row in self.repo.diff_counts()}
        only_b = counts.get("ONLY_B", 0)
        total = sum(counts.values()) or 1
        self.filter_row.addWidget(ui.hint(
            "反查有少量缺口（%d 条 / %.2f%%），以「按车型查」为准"
            % (only_b, 100.0 * only_b / total)))

        left = QWidget()
        left.setFixedWidth(300)
        left_column = QVBoxLayout(left)
        left_column.setContentsMargins(16, 16, 16, 0)
        left_column.setSpacing(10)
        self.plate = ui.photo_plate(268, 240)
        left_column.addWidget(self.plate, 0, Qt.AlignmentFlag.AlignLeft)
        self.number = QLabel("—")
        self.number.setObjectName("detailNum")
        left_column.addWidget(self.number)
        self.subline = QLabel("")
        self.subline.setObjectName("hint")
        self.subline.setWordWrap(True)
        left_column.addWidget(self.subline)
        # 备注（2026-10-28）：空备注整行隐藏，不留占位
        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.note.hide()
        left_column.addWidget(self.note)
        self.copy_btn = QPushButton("复制支架号")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy_bracket)
        self.edit_btn = QPushButton("编辑支架")
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setToolTip("改这个支架的图片与备注（支架号不可改）")
        self.edit_btn.clicked.connect(self.edit_bracket)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        meta_row.addWidget(self.copy_btn)
        meta_row.addWidget(self.edit_btn)
        meta_row.addStretch(1)
        left_column.addLayout(meta_row)
        self.goto_btn = QPushButton("在按车型查中查看")
        self.goto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.goto_btn.clicked.connect(self._goto_model)
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.addWidget(self.goto_btn)
        action_row.addStretch(1)
        left_column.addLayout(action_row)
        left_column.addStretch(1)
        self.body.addWidget(left)

        right = QWidget()
        right_column = QVBoxLayout(right)
        right_column.setContentsMargins(0, 12, 0, 0)
        right_column.setSpacing(0)
        self.bar = ui.BatchBar()
        right_column.addWidget(self.bar)
        self.table = self.make_table(COLUMNS, chips=(3,), dots=(5,))
        right_column.addWidget(self.table)
        self.bar.bind(self.table)
        self.bar.delete_requested.connect(self.delete_checked)
        # 「＋ 添加车型」从左侧详情栏上移到工具条，紧跟「删除选中」（2026-10-28）
        self.fitment_btn = QPushButton("＋ 添加车型")
        self.fitment_btn.setToolTip("把库里已有的车型加到当前支架（来源 = M）")
        self.fitment_btn.clicked.connect(self.add_fitments)
        self.bar.add_action(self.fitment_btn)

        self.error_bar = QLabel("")
        self.error_bar.setObjectName("errBar")
        self.error_bar.setFixedHeight(28)
        self.error_bar.hide()
        right_column.addWidget(self.error_bar)
        self.table._model.edit_failed.connect(self.show_error)
        self.table.viewport().setMouseTracking(True)
        # 行内只留「编辑」：删除已上移到工具条
        self.ops = delegates.LinkDelegate(("编辑",), ("accent",), self.table)
        self.table.setItemDelegateForColumn(OPS_COLUMN, self.ops)
        self.ops.clicked.connect(self.on_ops_click)
        self.body.addWidget(right, 1)

        self.bracket_box.activated.connect(lambda _=0: self.run_query())
        self.bracket_box.lineEdit().returnPressed.connect(self.run_query)
        self.brand_box.activated.connect(lambda _=0: self.run_query())
        self.brand_box.lineEdit().returnPressed.connect(self.run_query)
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.delete_checked)
        self._load()

    # ---------- data ----------
    def _load(self) -> None:
        self._catalog = {row["bracket_id"]: row for row in self.repo.brackets()}
        ids = list(self._catalog.keys())
        self.bracket_box.addItems(ids)
        brands = ["全部品牌"] + [row["brand"] for row in self.repo.brands()]
        self.brand_box.addItems(brands)
        if ids:
            self.bracket_box.setCurrentText("1")
        self.run_query()

    def run_query(self) -> None:
        self.clear_error()
        bracket_id = self.bracket_box.currentText().strip()
        if not bracket_id:
            return
        brand = self.brand_box.currentText().strip()
        if brand in ("全部品牌", ""):
            brand = None
        rows = self.repo.bracket_models(bracket_id, brand)
        for row in rows:
            row["range"] = year_range(row)
        self.table._model.set_rows(rows)

        info = self._catalog.get(bracket_id, {})
        ui.fill_plate(self.plate, info.get("image_file", ""), 268, 240, thumb=False)
        self.number.setText("%s 号" % bracket_id)
        brands = {row["brand"] for row in rows}
        self.subline.setText("适配车型 %d 条 · 覆盖品牌 %d 个%s"
                             % (len(rows), len(brands),
                                "" if rows else "\n该支架暂无反查记录"))
        self._show_note(info.get("note") or "")
        self._current = (bracket_id, rows[0]["brand"] if rows else "")

    # ---------- 支架本身（图片 / 备注）与新增车型 ----------
    NOTE_CHARS = 90             # 约 3 行；更长的去 tooltip 看全文

    def _show_note(self, note: str) -> None:
        note = (note or "").strip()
        self.note.setVisible(bool(note))
        if not note:
            self.note.setText("")
            self.note.setToolTip("")
            return
        short = (note if len(note) <= self.NOTE_CHARS
                 else note[:self.NOTE_CHARS].rstrip() + "…")
        self.note.setText("备注：" + short)
        self.note.setToolTip(note)

    def edit_bracket(self) -> None:
        bracket_id = self.bracket_box.currentText().strip()
        if not bracket_id:
            return
        dialog = BracketEditDialog(self.repo, bracket_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._after_write()

    def add_fitments(self) -> None:
        bracket_id = self.bracket_box.currentText().strip()
        if not bracket_id:
            # 按钮在工具条上很容易被空点，静默 return 会像「点了没反应」
            self._status("请先选择支架号，再添加车型")
            return
        dialog = FitmentPickDialog(self.repo, bracket_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.payload
            self._after_write()
            text = "已添加 %d 条" % result["added"]
            if result["skipped"]:
                text += " · %d 条已存在被跳过" % result["skipped"]
            self._status(text)

    # ---------- in-place edit / batch delete ----------
    def show_error(self, message: str) -> None:
        self.error_bar.setText("⚠ " + message)
        self.error_bar.show()

    def clear_error(self) -> None:
        self.error_bar.hide()

    def on_ops_click(self, row_index: int, _part: int = 0) -> None:
        self.edit_row(row_index)

    def edit_row(self, row_index: int) -> None:
        """Open the modal panel for one row."""
        row = self.table._model.row_at(row_index)
        if not row.get("id"):
            return
        dialog = RecordEditDialog(
            self.repo, row,
            "支架号 %s" % self.bracket_box.currentText().strip(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._after_write()

    def delete_checked(self) -> None:
        """工具条「删除选中」与 Delete 键共用：只删勾选，无勾选不动作。"""
        rows = self.table._model.checked_rows()
        if not rows:
            return
        bracket_id = self.bracket_box.currentText().strip()
        if not ui.confirm_delete(self, rows, bracket_id):
            return
        ids = [int(row["id"]) for row in rows]
        try:
            result = self.repo.delete_fitments(ids)
        except ValueError as error:
            self.show_error(str(error))
            return
        except (sqlite3.Error, OSError) as error:
            self.show_error("删除失败：%s" % error)
            return
        self._after_write()
        text = "已删除 %d 条" % result["deleted"]
        if result["missing"]:
            text += " · %d 条已不存在" % result["missing"]
        self._status(text)

    def _after_write(self) -> None:
        self.clear_error()
        # 图 / 备注 / 适配记录都写在本页，refresh_data 会重载字典并重跑查询；
        # 先 repo.reload() 清掉仓储层缓存，否则备注与封面的旧值会留在 _catalog 里。
        self.repo.reload()
        self.refresh_data()
        window = self.window()
        if hasattr(window, "on_records_changed"):
            window.on_records_changed()

    # ---------- actions ----------
    def _status(self, text: str, timeout: int = 4000) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text, timeout)

    def copy_bracket(self) -> None:
        bracket_id = self.bracket_box.currentText().strip()
        if not bracket_id:
            return
        QGuiApplication.clipboard().setText(bracket_id)
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage("已复制支架号 %s" % bracket_id, 4000)

    def refresh_data(self) -> None:
        """Reload bracket / brand lists after a manual entry."""
        bracket_id = self.bracket_box.currentText()
        brand = self.brand_box.currentText()
        self._catalog = {row["bracket_id"]: row for row in self.repo.brackets()}
        ids = list(self._catalog.keys())
        self.bracket_box.blockSignals(True)
        self.bracket_box.clear()
        self.bracket_box.addItems(ids)
        self.bracket_box.setCurrentText(bracket_id or (ids[0] if ids else ""))
        self.bracket_box.blockSignals(False)
        brands = ["全部品牌"] + [row["brand"] for row in self.repo.brands()]
        self.brand_box.blockSignals(True)
        self.brand_box.clear()
        self.brand_box.addItems(brands)
        self.brand_box.setCurrentText(brand if brand in brands else "全部品牌")
        self.brand_box.blockSignals(False)
        self.run_query()

    def focus_bracket(self, bracket_id: str) -> None:
        self.brand_box.setCurrentText("全部品牌")
        self.bracket_box.setCurrentText(bracket_id)
        self.run_query()

    def _goto_model(self) -> None:
        bracket_id, brand = self._current
        if not bracket_id:
            return
        window = self.window()
        if hasattr(window, "open_model_page"):
            window.open_model_page(brand, "")

    def refresh_theme(self) -> None:
        self.table.viewport().update()

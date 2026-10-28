# -*- coding: utf-8 -*-
"""Q1: query brackets by car model (model -> bracket), master-detail layout."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QLineEdit, QPushButton)

import ui
from edit_dialog import RecordEditDialog


def year_range(row) -> str:
    """Readable year range for one fitment row."""
    start, end = row.get("year_from"), row.get("year_to")
    if not start or not end:
        return "全部年款"
    return str(start) if start == end else "%s – %s" % (start, end)


class ModelPage(ui.Page):
    open_bracket = Signal(str)

    def __init__(self, repo, parent=None):
        super().__init__(repo, parent)
        self._catalog = {}
        self._rows = []

        self.brand_box = QComboBox()
        self.brand_box.setEditable(True)
        self.brand_box.setFixedWidth(170)
        self.brand_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.add_filter(self.brand_box, "品牌")

        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.setFixedWidth(230)
        self.model_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.add_filter(self.model_box, "车型")
        ui.attach_completer(self.brand_box)
        ui.attach_completer(self.model_box)

        self.year_edit = QLineEdit()
        self.year_edit.setPlaceholderText("如 2018（可选）")
        self.year_edit.setFixedWidth(140)
        self.add_filter(self.year_edit, "年款")

        self.query_btn = QPushButton("查询")
        self.query_btn.setObjectName("primary")
        self.query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_filter(self.query_btn)
        self.add_filter_stretch()
        self.count_label = ui.hint("")
        self.filter_row.addWidget(self.count_label)

        self.list = ui.ResultList(420)
        self.detail = ui.DetailPane(self.make_table)
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.detail.table)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        # Delete 键与工具条「删除选中」同一条路径：只删勾选的行
        shortcut.activated.connect(self.detail.delete_selected)
        self.body.addWidget(self.list)
        self.body.addWidget(self.detail, 1)

        self.list.bracket_selected.connect(self._show_bracket)
        self.detail.copy_requested.connect(self.copy_bracket)
        self.detail.reverse_requested.connect(self.open_bracket.emit)
        self.detail.edit_requested.connect(self.edit_row)
        self.detail.delete_many_requested.connect(self.delete_rows)
        self.brand_box.currentTextChanged.connect(self._reload_models)
        self.query_btn.clicked.connect(self.run_query)
        self.model_box.lineEdit().returnPressed.connect(self.run_query)
        self.brand_box.lineEdit().returnPressed.connect(self.run_query)
        self.year_edit.returnPressed.connect(self.run_query)
        for key, delta in ((Qt.Key.Key_Down, 1), (Qt.Key.Key_Up, -1)):
            shortcut = QShortcut(QKeySequence(key), self.list)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda step=delta: self.list.step(step))

        self._load_brands()

    # ---------- dictionaries ----------
    def _load_brands(self) -> None:
        self._catalog = {row["bracket_id"]: row for row in self.repo.brackets()}
        brands = [row["brand"] for row in self.repo.brands()]
        self.brand_box.addItems(brands)
        if brands:
            self.brand_box.setCurrentText(brands[0])

    def _reload_models(self, brand: str) -> None:
        self.model_box.blockSignals(True)
        self.model_box.clear()
        if brand:
            self.model_box.addItems(self.repo.models(brand))
        self.model_box.setCurrentText("")
        self.model_box.blockSignals(False)

    # ---------- query ----------
    def run_query(self) -> None:
        brand = self.brand_box.currentText().strip()
        if not brand:
            return
        model = self.model_box.currentText().strip()
        year = None
        text = self.year_edit.text().strip()
        if text.isdigit() and len(text) == 4:
            year = int(text)
        rows = self.repo.model_brackets(brand, model or None, year)
        for row in rows:
            row.setdefault("brand", brand)
            row["range"] = year_range(row)
        self._rows = rows
        items = self._group(rows)
        self.list.set_items(
            items, "%d 条记录 · %d 个支架" % (len(rows), len(items)))
        self.count_label.setText(
            "%s %s%s" % (brand, model or "", "" if rows else " · 无适配记录"))

    def _group(self, rows) -> list:
        """One master-list entry per bracket, ordered by fitment count."""
        groups = {}
        for row in rows:
            groups.setdefault(row["bracket_id"], []).append(row)
        items = []
        for bracket_id, group in groups.items():
            spans = [row for row in group if row.get("year_from")]
            if spans:
                start = min(row["year_from"] for row in spans)
                end = max(row["year_to"] for row in spans)
                span = str(start) if start == end else "%s – %s" % (start, end)
            else:
                span = "全部年款"
            sources = sorted({row.get("source") for row in group if row.get("source")})
            items.append({
                "bracket_id": bracket_id,
                "image_file": self._catalog.get(bracket_id, {}).get("image_file", ""),
                "range": span,
                "sub": "%d 条适配 · 来源 %s" % (len(group), "/".join(sources)),
                "group": group,
            })
        items.sort(key=lambda item: (-len(item["group"]), item["bracket_id"]))
        return items

    # ---------- detail ----------
    def _show_bracket(self, bracket_id: str) -> None:
        if not bracket_id:
            self.detail.clear()
            return
        group = [row for row in self._rows if row["bracket_id"] == bracket_id]
        item = next((row for row in self._group(self._rows)
                     if row["bracket_id"] == bracket_id), None)
        if item is None:
            self.detail.clear()
            return
        catalog = self._catalog.get(bracket_id, {})
        models = []
        for row in group:
            name = row.get("model") or ""
            if name and name not in models:
                models.append(name)
        shown = "、".join(models[:3]) + ("…" if len(models) > 3 else "")
        sources = sorted({row.get("source") for row in group if row.get("source")})
        info = {
            "bracket_id": bracket_id,
            "image_file": catalog.get("image_file", ""),
            "range": item["range"],
            "sub": "后视镜支架",
            "kvs": [
                ("适配车型", shown or "—"),
                ("适配年款", item["range"]),
                ("年款原文", self._longest_years(group)),
                ("数据来源", "%s 路 · 该支架全库 %d 条（A 路反查）"
                 % ("/".join(sources) or "—", catalog.get("fitment_count", 0))),
            ],
        }
        self.detail.show_bracket(info, group)

    @staticmethod
    def _longest_years(group) -> str:
        texts = [row.get("years_raw") or "" for row in group]
        return max(texts, key=len) if texts else "—"

    # ---------- edit / delete ----------
    def edit_row(self, row_id: int) -> None:
        """Open the modal panel for one row of the detail table."""
        row = next((item for item in self.detail.table._model.rows()
                    if item.get("id") == row_id), {})
        if not row:
            return
        dialog = RecordEditDialog(
            self.repo, row,
            "%s / %s" % (row.get("brand", ""), row.get("model", "")), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._after_write()

    def delete_rows(self, ids) -> None:
        """工具条「删除选中」与 Delete 键共用：批量删当前支架下的勾选记录。"""
        ids = [int(row_id) for row_id in ids if row_id]
        if not ids:
            return
        rows = [row for row in self.detail.table._model.rows()
                if row.get("id") in ids]
        if not ui.confirm_delete(self, rows):
            return
        try:
            result = self.repo.delete_fitments(ids)
        except ValueError as error:
            self.detail.show_error(str(error))
            return
        except (sqlite3.Error, OSError) as error:
            self.detail.show_error("删除失败：%s" % error)
            return
        self._after_write()
        text = "已删除 %d 条" % result["deleted"]
        if result["missing"]:
            text += " · %d 条已不存在" % result["missing"]
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(text, 4000)

    def _after_write(self) -> None:
        keep = self.list.current_id()
        self.detail.clear_error()
        self.run_query()
        ids = [item["bracket_id"] for item in self._group(self._rows)]
        if keep and keep in ids:
            self.list.select(ids.index(keep))
        window = self.window()
        if hasattr(window, "on_records_changed"):
            window.on_records_changed()

    # ---------- actions ----------
    def copy_bracket(self, bracket_id: str) -> None:
        if not bracket_id:
            return
        QGuiApplication.clipboard().setText(bracket_id)
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage("已复制支架号 %s" % bracket_id, 4000)

    # ---------- reload ----------
    def refresh_data(self) -> None:
        """Reload dictionaries after a manual entry, then rerun the query.

        车型只有「品牌没变」时才保留：品牌变了旧的车型本来就不属于新品牌。
        末尾必须 run_query()，否则筛选条件已刷新、表格却还是上一次的结果
        （按车型查与按支架查的行为也因此保持一致）。
        """
        brand_before = self.brand_box.currentText()
        model_before = self.model_box.currentText()
        self._catalog = {row["bracket_id"]: row for row in self.repo.brackets()}
        brands = [row["brand"] for row in self.repo.brands()]
        keep = brand_before if brand_before in brands else (brands[0] if brands else "")
        self.brand_box.blockSignals(True)
        self.brand_box.clear()
        self.brand_box.addItems(brands)
        self.brand_box.setCurrentText(keep)
        self.brand_box.blockSignals(False)
        models = self.repo.models(keep)
        self.model_box.blockSignals(True)
        self.model_box.clear()
        self.model_box.addItems(models)
        same_brand = keep == brand_before
        self.model_box.setCurrentText(
            model_before if same_brand and model_before in models else "")
        self.model_box.blockSignals(False)
        self.run_query()

    def focus_model(self, brand: str, model: str) -> None:
        self.brand_box.setCurrentText(brand)
        self._reload_models(brand)
        self.model_box.setCurrentText(model)
        self.run_query()

    def refresh_theme(self) -> None:
        self.detail.refresh_theme()

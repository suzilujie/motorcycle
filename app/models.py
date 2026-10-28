# -*- coding: utf-8 -*-
"""Generic Qt table model that renders a list of dict rows."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QHeaderView


class DictTableModel(QAbstractTableModel):
    """columns = [(key, title, width), ...]; rows = list of dict.

    ``editable`` names the keys the user may change in place. Every commit is
    handed to ``edit_handler(row, key, text) -> (ok, message)`` so the page owns
    validation and the write; the model only refreshes the cell on success.

    列键 ``CHECK_KEY`` 表示「勾选列」（2026-10-28）：该列没有文本，只有
    CheckStateRole，勾选状态按行的 ``id`` 记录，供批量删除使用。
    """

    CHECK_KEY = "__check__"
    edit_failed = Signal(str)
    checked_changed = Signal()      # 勾选增删 / 全选 / set_rows 之后发出

    def __init__(self, columns, rows=None, parent=None, editable=(),
                 edit_handler=None):
        super().__init__(parent)
        self._columns = list(columns)
        self._rows = list(rows or [])
        self._editable = set(editable)
        self._edit_handler = edit_handler
        self._checked = set()       # 已勾选的行 id

    # ---------- Qt API ----------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        check = self._is_check(index.column())
        if check and role == Qt.ItemDataRole.CheckStateRole:
            key = self._row_id(self._rows[index.row()])
            return (Qt.CheckState.Checked if key in self._checked
                    else Qt.CheckState.Unchecked)
        if role == Qt.DisplayRole:
            if check:
                return ""           # 勾选列没有文字
            row = self._rows[index.row()]
            value = row.get(self._columns[index.column()][0], "")
            if value is None:
                return ""
            return str(value)
        if role == Qt.TextAlignmentRole:
            if check:
                return int(Qt.AlignCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            if check:
                return None
            # 列宽不足被省略号截断时，悬停可看全文
            value = self._rows[index.row()].get(self._columns[index.column()][0], "")
            return str(value) if value not in (None, "") else None
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._columns[section][1]
        return str(section + 1)

    # ---------- in-place editing ----------
    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        if self._is_check(index.column()):
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if self._key(index) in self._editable:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        if role == Qt.ItemDataRole.CheckStateRole and self._is_check(index.column()):
            key = self._row_id(self._rows[index.row()])
            if key is None:
                return False
            state = Qt.CheckState(value)
            if state == Qt.CheckState.Checked:
                if key in self._checked:
                    return False
                self._checked.add(key)
            else:
                if key not in self._checked:
                    return False
                self._checked.discard(key)
            self.dataChanged.emit(index, index,
                                  [Qt.ItemDataRole.CheckStateRole])
            self.checked_changed.emit()
            return True
        if role != Qt.ItemDataRole.EditRole:
            return False
        key = self._key(index)
        if key not in self._editable or self._edit_handler is None:
            return False
        row = self._rows[index.row()]
        text = "" if value is None else str(value).strip()
        if text == str(row.get(key) or ""):
            return False
        try:
            ok, message = self._edit_handler(row, key, text)
        except Exception as error:          # 兜底：绝不让异常穿透 Qt 事件循环
            self.edit_failed.emit(str(error))
            return False
        if not ok:
            self.edit_failed.emit(message or "修改未保存")
            return False
        row[key] = text
        self.dataChanged.emit(index, index)
        return True

    # ---------- helpers ----------
    def _key(self, index) -> str:
        if not index.isValid():
            return ""
        return self._columns[index.column()][0]

    def _is_check(self, column: int) -> bool:
        return 0 <= column < len(self._columns) and \
            self._columns[column][0] == self.CHECK_KEY

    @staticmethod
    def _row_id(row) -> int:
        value = row.get("id") if isinstance(row, dict) else None
        if value in (None, ""):
            return None
        return int(value)

    # ---------- 勾选 ----------
    def checked_ids(self) -> list:
        """勾选的行 id，按表格顺序返回（不含已被清掉的行）。"""
        return [key for key in (self._row_id(row) for row in self._rows)
                if key is not None and key in self._checked]

    def checked_rows(self) -> list:
        return [row for row in self._rows
                if self._row_id(row) in self._checked]

    def checked_count(self) -> int:
        return len(self.checked_ids())

    def set_all_checked(self, flag: bool = True) -> None:
        ids = {key for key in (self._row_id(row) for row in self._rows)
               if key is not None}
        self._checked = (self._checked | ids) if flag else set()
        self._repaint_checks()
        self.checked_changed.emit()

    def clear_checked(self) -> None:
        self._checked = set()
        self._repaint_checks()
        self.checked_changed.emit()

    def _repaint_checks(self) -> None:
        column = next((position for position in range(len(self._columns))
                       if self._is_check(position)), None)
        if column is None or not self._rows:
            return
        self.dataChanged.emit(self.index(0, column),
                              self.index(len(self._rows) - 1, column),
                              [Qt.ItemDataRole.CheckStateRole])

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows or [])
        self.endResetModel()
        # 换查询后旧 id 可能已不存在：只留下仍然可见的勾选
        alive = {key for key in (self._row_id(row) for row in self._rows)
                 if key is not None}
        self._checked &= alive
        self.checked_changed.emit()

    def row_at(self, index: int) -> dict:
        if 0 <= index < len(self._rows):
            return self._rows[index]
        return {}

    def rows(self) -> list:
        return self._rows

    def apply_widths(self, view) -> None:
        header = view.horizontalHeader()
        for section, column in enumerate(self._columns):
            width = column[2] if len(column) > 2 else 120
            if width <= 0:
                header.setSectionResizeMode(section, QHeaderView.ResizeMode.Stretch)
            else:
                view.setColumnWidth(section, width)

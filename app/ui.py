# -*- coding: utf-8 -*-
"""Shared widgets: page scaffold, master list rows, detail pane, chips."""

from __future__ import annotations

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QCompleter, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy,
                               QStackedLayout, QTableView, QVBoxLayout, QWidget)

import delegates
import models
import search
import thumbs

ROW_HEIGHT = 66
ROW_THUMB = 44
TABLE_ROW = 38


# ---------- small builders ----------
def chip(text: str, accent: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName("chipNew" if accent else "chip")
    return label


def hint(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    return label


def photo_plate(width: int, height: int) -> QLabel:
    label = QLabel("无图")
    label.setObjectName("photoPlate")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(width, height)
    return label


def fill_plate(label: QLabel, image_file: str, width: int, height: int,
               thumb: bool = False) -> None:
    """Center a downloaded photo inside its light plate."""
    pix = thumbs.pixmap(image_file, thumb=thumb)
    if pix is None:
        label.setPixmap(QPixmap())
        label.setText("无图")
        return
    inner = (max(width - 12, 24), max(height - 12, 24))
    label.setText("")
    label.setPixmap(pix.scaled(inner[0], inner[1], Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))


def attach_completer(field, provider=None, limit: int = 200, on_pick=None):
    """Pinyin-aware completer for a QComboBox or a QLineEdit.

    The candidate list is filtered here (全拼 / 首字母 / 中英混输), so the
    completer must run in UnfilteredPopupCompletion: with the default mode Qt
    re-filters our list by the raw prefix, which drops every pinyin hit.
    """
    edit = field.lineEdit() if hasattr(field, "lineEdit") else field
    completer = QCompleter(field)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    if hasattr(field, "setCompleter"):
        field.setCompleter(completer)

    def source():
        if provider is not None:
            return provider()
        if hasattr(field, "count"):
            return [field.itemText(index) for index in range(field.count())]
        return []

    def refresh(text):
        items = search.filter_items(search.unique(source()), text, limit)
        model = QStringListModel(items, completer)
        completer._model = model           # 防止 Python 侧回收
        completer.setModel(model)
        completer.setCompletionPrefix("")
        if text.strip() and items:
            completer.complete()
        else:
            completer.popup().hide()

    edit.textEdited.connect(refresh)
    if on_pick is not None:
        completer.activated.connect(on_pick)
    field._completer = completer
    return completer


def kv_row(label: str, value: str) -> QWidget:
    """One label / value line with a hairline underneath."""
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    line = QHBoxLayout()
    line.setContentsMargins(0, 7, 0, 7)
    line.setSpacing(12)
    key = QLabel(label)
    key.setObjectName("kvLabel")
    key.setFixedWidth(70)
    key.setAlignment(Qt.AlignmentFlag.AlignTop)
    text = QLabel(value)
    text.setObjectName("kvValue")
    text.setWordWrap(True)
    line.addWidget(key)
    line.addWidget(text, 1)
    layout.addLayout(line)
    hair = QFrame()
    hair.setObjectName("kvLine")
    hair.setFixedHeight(1)
    layout.addWidget(hair)
    return holder


# ---------- master list ----------
class BracketRow(QFrame):
    """Row of the left list: photo, bracket number, year chip, fitment count."""

    clicked = Signal(int)

    def __init__(self, index: int, item: dict, parent=None):
        super().__init__(parent)
        self.index = index
        self.bracket_id = item["bracket_id"]
        self.setObjectName("listRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(ROW_HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 6, 14, 6)
        row.setSpacing(10)
        self.thumb = photo_plate(ROW_THUMB, ROW_THUMB)
        row.addWidget(self.thumb)
        column = QVBoxLayout()
        column.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.number = QLabel(item["bracket_id"] + " 号")
        self.number.setObjectName("listNum")
        top.addWidget(self.number)
        top.addWidget(chip(item.get("range") or "全部年款"))
        top.addStretch(1)
        column.addLayout(top)
        self.sub = QLabel(item.get("sub") or "")
        self.sub.setObjectName("listSub")
        column.addWidget(self.sub)
        row.addLayout(column, 1)
        fill_plate(self.thumb, item.get("image_file", ""), ROW_THUMB, ROW_THUMB)

    def set_selected(self, flag: bool) -> None:
        self.setObjectName("listRowSel" if flag else "listRow")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)
        super().mousePressEvent(event)


class ResultList(QFrame):
    """Scrollable master pane built from BracketRow widgets."""

    bracket_selected = Signal(str)

    def __init__(self, width: int = 420, parent=None):
        super().__init__(parent)
        self.setFixedWidth(width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._rows = []
        self._items = []
        self._current = -1
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QFrame()
        head.setObjectName("listHead")
        head.setFixedHeight(34)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(14, 0, 14, 0)
        self.head_text = QLabel("")
        self.head_text.setObjectName("listHeadText")
        head_row.addWidget(self.head_text)
        head_row.addStretch(1)
        outer.addWidget(head)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        self.box = QVBoxLayout(inner)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(0)
        self.box.addStretch(1)
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll, 1)
        self.empty_wrap = QWidget()
        empty_layout = QVBoxLayout(self.empty_wrap)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.addStretch(1)
        self.empty = QLabel("没有匹配的支架")
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty)
        empty_layout.addStretch(1)
        self.empty_wrap.hide()
        outer.addWidget(self.empty_wrap, 1)

    # ---------- data ----------
    def set_items(self, items, head_text: str = "") -> None:
        self.head_text.setText(head_text)
        self._clear()
        self._items = list(items)
        for index, item in enumerate(self._items):
            row = BracketRow(index, item)
            row.clicked.connect(self.select)
            self.box.insertWidget(index, row)
            self._rows.append(row)
        self.scroll.setVisible(bool(self._rows))
        self.empty_wrap.setVisible(not self._rows)
        if self._rows:
            self.select(0)
        else:
            self._current = -1
            self.bracket_selected.emit("")

    def _clear(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        self._current = -1

    def select(self, index: int) -> None:
        if not (0 <= index < len(self._rows)):
            return
        for position, row in enumerate(self._rows):
            row.set_selected(position == index)
        self._current = index
        self.scroll.ensureWidgetVisible(self._rows[index], 0, 40)
        self.bracket_selected.emit(self._rows[index].bracket_id)

    def step(self, delta: int) -> None:
        if not self._rows:
            return
        self.select(max(0, min(len(self._rows) - 1, self._current + delta)))

    def current_id(self) -> str:
        return self._rows[self._current].bracket_id if self._current >= 0 else ""


# ---------- batch operations on a checked table ----------
LISTED_ROWS = 8              # 删除确认框里最多逐条列几行


class BatchBar(QWidget):
    """勾选表上方的操作条：全选 + 删除选中（N）+ 计数。

    ``bind(table)`` 之后自动跟随表格模型的勾选状态：全选框三态、
    按钮可用性与数量、右侧「共 N 条 · 已选 M」。
    """

    delete_requested = Signal()      # 点「删除选中」；勾选的 id 由页面自己取

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("batchBar")
        self.setFixedHeight(34)
        self._model = None
        self._all_checked = False
        self._action_count = 0        # 已挂到「删除选中」右边的动作数量
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(10)
        self._row = row
        self.all_box = QCheckBox("全选")
        self.all_box.setTristate(True)
        self.all_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.all_box.clicked.connect(self._toggle_all)
        row.addWidget(self.all_box)
        self.delete_btn = QPushButton("删除选中（0）")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.delete_requested)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        self.count = QLabel("")
        self.count.setObjectName("hint")
        row.addWidget(self.count)

    def add_action(self, widget, primary: bool = False) -> None:
        """挂在「删除选中」右边的页面级动作（新增等），排在弹簧与计数之前。

        位置用计数器推算而不是每次插到 ``delete_btn + 1``：后者会让多次调用
        的顺序反过来。``primary`` 靠 objectName 生效，所以本方法必须在控件
        首次 show / polish 之前调用，显示后再改 objectName 不会重绘样式。
        """
        if primary:
            widget.setObjectName("primary")
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        position = self._row.indexOf(self.delete_btn) + 1 + self._action_count
        self._action_count += 1
        self._row.insertWidget(position, widget)

    def bind(self, table) -> None:
        self._model = table._model
        self._model.checked_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        if self._model is None:
            return
        total = self._model.rowCount()
        checked = self._model.checked_count()
        self._all_checked = total > 0 and checked == total
        self.delete_btn.setText("删除选中（%d）" % checked)
        self.delete_btn.setEnabled(checked > 0)
        self.count.setText("共 %d 条 · 已选 %d" % (total, checked))
        self.all_box.setEnabled(total > 0)
        self.all_box.blockSignals(True)       # 只画状态，不再触发 clicked
        if not total or not checked:
            self.all_box.setCheckState(Qt.CheckState.Unchecked)
        elif checked == total:
            self.all_box.setCheckState(Qt.CheckState.Checked)
        else:
            self.all_box.setCheckState(Qt.CheckState.PartiallyChecked)
        self.all_box.blockSignals(False)

    def _toggle_all(self, _checked: bool = False) -> None:
        if self._model is None:
            return
        self._model.set_all_checked(not self._all_checked)
        self.refresh()


def confirm_delete(parent, rows, bracket_id: str = "") -> bool:
    """One confirmation for a batch of fitment rows (1 条也走这里)。"""
    rows = [row for row in rows if row.get("id")]
    if not rows:
        return False
    box = QMessageBox(parent)
    box.setWindowTitle("删除适配记录")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText("删除 %d 条适配记录？" % len(rows))
    lines = ["%s / %s · %s" % (row.get("brand", ""), row.get("model", ""),
                               row.get("years_raw") or "全部年款")
             for row in rows[:LISTED_ROWS]]
    if len(rows) > LISTED_ROWS:
        lines.append("……另 %d 条" % (len(rows) - LISTED_ROWS))
    crawler = sum(1 for row in rows
                  if str(row.get("source") or "") in ("A", "B"))
    notes = []
    if bracket_id:
        notes.append("支架号 %s · 涉及 %d 个品牌"
                     % (bracket_id, len({row.get("brand") for row in rows})))
    notes.extend(lines)
    if crawler:
        notes.append("其中 %d 条来自爬虫（A / B 路），下次增量抓取可能重新写入。"
                     % crawler)
    notes.append("删除前会自动备份数据库（data/backup/）。")
    box.setInformativeText("\n".join(notes))
    cancel = box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
    confirm = box.addButton("删除 %d 条" % len(rows),
                            QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is confirm


# ---------- detail pane ----------
class DetailPane(QFrame):
    """Right-hand pane: big photo, key/value block, buttons, detail table."""

    copy_requested = Signal(str)
    reverse_requested = Signal(str)
    edit_requested = Signal(int)
    delete_many_requested = Signal(list)     # 批量删除：勾选的 id 列表

    COLUMNS = [
        (models.DictTableModel.CHECK_KEY, "", 36),
        ("brand", "品牌", 110),
        ("model", "车型", 190),
        ("range", "年款区间", 116),
        ("years_raw", "年款原文", 0),
        ("source", "来源", 64),
        ("__ops__", "操作", 60),
    ]

    def __init__(self, table_factory, parent=None, editable=(), on_edit=None):
        super().__init__(parent)
        self._id = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 0)
        outer.setSpacing(0)
        self.stack = QStackedLayout()
        outer.addLayout(self.stack, 1)

        content = QWidget()
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.number = QLabel("—")
        self.number.setObjectName("detailNum")
        head.addWidget(self.number, 0, Qt.AlignmentFlag.AlignBottom)
        self.range_chip = chip("")
        head.addWidget(self.range_chip, 0, Qt.AlignmentFlag.AlignBottom)
        self.sub = QLabel("")
        self.sub.setObjectName("detailSub")
        head.addWidget(self.sub, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        column.addLayout(head)

        body = QHBoxLayout()
        body.setContentsMargins(0, 12, 0, 0)
        body.setSpacing(20)
        self.plate = photo_plate(330, 250)
        body.addWidget(self.plate, 0, Qt.AlignmentFlag.AlignTop)
        self.kvs = QVBoxLayout()
        self.kvs.setSpacing(0)
        body.addLayout(self.kvs, 1)
        column.addLayout(body)

        self.copy_btn = QPushButton("复制支架号")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(lambda: self.copy_requested.emit(self._id))
        self.reverse_btn = QPushButton("反查该支架全部车型")
        self.reverse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reverse_btn.clicked.connect(lambda: self.reverse_requested.emit(self._id))
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 14, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self.copy_btn)
        actions.addWidget(self.reverse_btn)
        actions.addStretch(1)
        self._actions = actions
        column.addLayout(actions)

        self.bar = BatchBar()
        column.addWidget(self.bar)

        self.table = table_factory(self.COLUMNS, chips=(3,), dots=(5,),
                                   editable=editable, on_edit=on_edit)
        self.table.setMinimumHeight(200)
        column.addWidget(self.table, 1)
        self.table._model.edit_failed.connect(self.show_error)
        self.table.viewport().setMouseTracking(True)
        self.bar.bind(self.table)
        self.bar.delete_requested.connect(self._on_delete_many)
        # 行内只留「编辑」：删除已上移到工具条（2026-10-28 用户要求）
        self.ops = delegates.LinkDelegate(("编辑",), ("accent",), self.table)
        self.table.setItemDelegateForColumn(len(self.COLUMNS) - 1, self.ops)
        self.ops.clicked.connect(self._on_ops_click)

        self.error_bar = QLabel("")
        self.error_bar.setObjectName("errBar")
        self.error_bar.setFixedHeight(28)
        self.error_bar.hide()
        column.addWidget(self.error_bar)

        self.stack.addWidget(content)

        blank = QWidget()
        blank_layout = QVBoxLayout(blank)
        blank_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("还没有查询结果")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel("选好品牌与车型后点「查询」，或直接在顶部搜索框输入支架号")
        text.setObjectName("emptyText")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        blank_layout.addWidget(title)
        blank_layout.addWidget(text)
        self.stack.addWidget(blank)
        self.stack.setCurrentIndex(1)

    # ---------- data ----------
    def clear(self) -> None:
        self._id = ""
        self.clear_error()
        self.table._model.set_rows([])
        self.bar.refresh()
        self.stack.setCurrentIndex(1)

    def show_bracket(self, info: dict, rows: list) -> None:
        self.clear_error()
        self._id = info.get("bracket_id", "")
        self.stack.setCurrentIndex(0)
        self.number.setText((self._id or "—") + " 号")
        self.range_chip.setText(info.get("range") or "全部年款")
        self.sub.setText(info.get("sub") or "")
        fill_plate(self.plate, info.get("image_file", ""), 330, 250)
        self._rebuild_kvs(info)
        rows = list(rows)
        for row in rows:
            row["range"] = row.get("range") or "全部年款"
        self.table._model.set_rows(rows)

    def _rebuild_kvs(self, info: dict) -> None:
        while self.kvs.count():
            item = self.kvs.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for label, value in (info.get("kvs") or []):
            self.kvs.addWidget(kv_row(label, value))
        self.kvs.addStretch(1)

    # ---------- in-place edit / delete ----------
    def show_error(self, message: str) -> None:
        self.error_bar.setText("⚠ " + message)
        self.error_bar.show()

    def clear_error(self) -> None:
        self.error_bar.hide()

    def selected_row(self) -> dict:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return {}
        return self.table._model.row_at(indexes[0].row())

    def checked_rows(self) -> list:
        return self.table._model.checked_rows()

    def delete_selected(self) -> None:
        """Delete 键：只删勾选的行；没有勾选就不动作（2026-10-28 用户决定）。"""
        self._on_delete_many()

    def _on_ops_click(self, row_index: int, _part: int = 0) -> None:
        row_id = self.table._model.row_at(row_index).get("id")
        if row_id:
            self.edit_requested.emit(int(row_id))

    def _on_delete_many(self) -> None:
        ids = self.table._model.checked_ids()
        if ids:
            self.delete_many_requested.emit(ids)

    def refresh_theme(self) -> None:
        self.table.viewport().update()


# ---------- page scaffold ----------
class Page(QWidget):
    """Filter bar + body area; the two query pages fill the body themselves."""

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.filter_bar = QFrame()
        self.filter_bar.setObjectName("filterBar")
        self.filter_bar.setFixedHeight(56)
        self.filter_row = QHBoxLayout(self.filter_bar)
        self.filter_row.setContentsMargins(16, 10, 16, 10)
        self.filter_row.setSpacing(8)
        outer.addWidget(self.filter_bar)
        self.body = QHBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        outer.addLayout(self.body, 1)

    def add_filter(self, widget, label: str = "") -> None:
        if label:
            self.filter_row.addWidget(hint(label))
        self.filter_row.addWidget(widget)

    def add_filter_stretch(self) -> None:
        self.filter_row.addStretch(1)

    @staticmethod
    def make_table(columns, chips=(), dots=(), editable=(), on_edit=None) -> QTableView:
        """C-style table: 38px rows, hairline header, chip / dot delegates.

        ``editable`` / ``on_edit`` turn the named columns into in-place inputs;
        the handler owns validation and the write, the model only repaints.
        """
        view = QTableView()
        model = models.DictTableModel(columns, parent=view,
                                      editable=editable, edit_handler=on_edit)
        view.setModel(model)
        view.setShowGrid(False)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        # 有勾选列的表格不再画选中行底色（2026-10-28 用户要求：勾选代替高亮），
        # 行内「编辑」链接走 delegate 的 editorEvent，不依赖选中状态。
        checkable = any(str(column[0]) == models.DictTableModel.CHECK_KEY
                        for column in columns)
        view.setSelectionMode(
            QTableView.SelectionMode.NoSelection if checkable
            else QTableView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.AnyKeyPressed)
        view.setWordWrap(False)
        view.setSortingEnabled(False)
        view.verticalHeader().setVisible(False)
        view.verticalHeader().setDefaultSectionSize(TABLE_ROW)
        view.horizontalHeader().setHighlightSections(False)
        view.horizontalHeader().setStretchLastSection(False)
        model.apply_widths(view)
        for column in chips:
            view.setItemDelegateForColumn(column, delegates.ChipDelegate(view))
        for column in dots:
            view.setItemDelegateForColumn(column, delegates.DotDelegate(view))
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view._model = model
        return view


# ---------- manual entry: candidate list + picked panel ----------
class CheckList(QFrame):
    """候选列表：勾选框 + 拼音搜索 + 全选/清空（录入页左右两栏共用）。

    The checked set lives in ``_checked`` and survives filtering and rebuilds,
    so switching a brand filter never silently drops a selection.

    ``leading`` 是可选的前置筛选控件（新增支架页把「品牌」下拉放这里）：
    筛选和结果同处一行，左边表单就不用再重复一个品牌下拉。
    ``actions`` 是追加在「全选 / 清空」之后的动作按钮（如「＋ 新增车型」）。
    """

    changed = Signal()

    def __init__(self, title: str, placeholder: str = "", note: str = "",
                 leading=None, actions=(), parent=None):
        super().__init__(parent)
        self._items = []
        self._checked = {}
        self._rebuilding = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("formTitle")
        head.addWidget(self.title)
        if note:
            head.addWidget(hint(note))
        self.leading = leading
        if leading is not None:
            head.addWidget(leading)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.textChanged.connect(self._rebuild)
        head.addWidget(self.search, 1)
        # 文案取短（工具条要放得下），完整说明挂在 tooltip 上
        self.all_btn = QPushButton("全选")
        self.all_btn.setObjectName("flat")
        self.all_btn.setToolTip("勾选当前筛选结果里的全部候选")
        self.all_btn.clicked.connect(self.check_visible)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("flat")
        self.clear_btn.setToolTip("清空已选，不改动库里任何记录")
        self.clear_btn.clicked.connect(self.clear_checks)
        head.addWidget(self.all_btn)
        head.addWidget(self.clear_btn)
        for action in actions:
            head.addWidget(action)
        outer.addLayout(head)

        self.list = QListWidget()
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self.list, 1)

    # ---------- data ----------
    def set_items(self, items) -> None:
        """items = [{"key":…, "text":…, "payload":…}, ...]"""
        self._items = list(items)
        self._rebuild(self.search.text())

    def checked_items(self) -> list:
        return list(self._checked.values())

    def checked_keys(self) -> list:
        return list(self._checked.keys())

    def set_checked(self, keys, flag: bool = True) -> None:
        changed = False
        for key in keys:
            if flag and key not in self._checked:
                item = self._by_key(key)
                if item is not None:
                    self._checked[key] = item
                    changed = True
            elif not flag and key in self._checked:
                self._checked.pop(key, None)
                changed = True
        if changed:
            self._resync()
            self.changed.emit()

    def clear_checks(self) -> None:
        if not self._checked:
            return
        self._checked = {}
        self._resync()
        self.changed.emit()

    def check_visible(self) -> None:
        added = False
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.isHidden():
                continue
            key = item.data(Qt.ItemDataRole.UserRole)
            if key in self._checked:
                continue
            entry = self._by_key(key)
            if entry is not None:          # 找不到就不记，避免 _checked 里留 None
                self._checked[key] = entry
                added = True
        if added:
            self._resync()
            self.changed.emit()

    # ---------- internals ----------
    def _by_key(self, key):
        for item in self._items:
            if item["key"] == key:
                return item
        return None

    def _rebuild(self, query: str = "") -> None:
        self._rebuilding = True
        try:
            self.list.clear()
            mapping = {}
            for item in self._items:
                mapping.setdefault(item["text"], item)
            for text in search.filter_items(list(mapping), query, 200):
                item = mapping[text]
                row = QListWidgetItem(text)
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(
                    Qt.CheckState.Checked if item["key"] in self._checked
                    else Qt.CheckState.Unchecked)
                row.setData(Qt.ItemDataRole.UserRole, item["key"])
                self.list.addItem(row)
        finally:
            self._rebuilding = False

    def _resync(self) -> None:
        self._rebuilding = True
        try:
            for index in range(self.list.count()):
                row = self.list.item(index)
                key = row.data(Qt.ItemDataRole.UserRole)
                row.setCheckState(
                    Qt.CheckState.Checked if key in self._checked
                    else Qt.CheckState.Unchecked)
        finally:
            self._rebuilding = False

    def _on_item_changed(self, item) -> None:
        if self._rebuilding:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            entry = self._by_key(key)
            if entry:
                self._checked[key] = entry
        else:
            self._checked.pop(key, None)
        self.changed.emit()


class PickedList(QFrame):
    """已选面板：数量 + 每行一条 + 移除选中（双击也能移除）。"""

    remove_requested = Signal(list)

    def __init__(self, title: str = "已选", parent=None):
        super().__init__(parent)
        # 220：候选工具条要放 品牌 + 搜索 + 全选 + 清空 + 新增品牌，
        # 已选面板只显示「品牌 车型」短标签，250 太宽把搜索框挤没了。
        self.setFixedWidth(220)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(title)
        self.title.setObjectName("formTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.count = chip("0")
        head.addWidget(self.count)
        outer.addLayout(head)

        # 列表与空态提示放在同一块带描边的容器里：两种状态都有可见面板，
        # 按钮也不会因为某一方吃满剩余高度而上下跳
        self.body = QFrame()
        self.body.setObjectName("pickedBody")
        self.stack = QStackedLayout(self.body)
        self.stack.setContentsMargins(0, 0, 0, 0)

        self.list = QListWidget()
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(lambda _item: self.remove_current())
        self.stack.addWidget(self.list)

        self.empty = QLabel("未选择\n= 只建档，不生成适配记录")
        self.empty.setObjectName("hint")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.stack.addWidget(self.empty)
        self.stack.setCurrentWidget(self.empty)
        outer.addWidget(self.body, 1)

        self.remove_btn = QPushButton("移除选中")
        self.remove_btn.setObjectName("flat")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self.remove_current)
        outer.addWidget(self.remove_btn)

    def set_items(self, items) -> None:
        """items = [{"key":…, "text":…}, ...]"""
        self.list.clear()
        for item in items:
            row = QListWidgetItem(item["text"])
            row.setData(Qt.ItemDataRole.UserRole, item["key"])
            self.list.addItem(row)
        self.count.setText(str(len(items)))
        self.stack.setCurrentWidget(self.list if items else self.empty)
        self.remove_btn.setEnabled(bool(items))

    def remove_current(self) -> None:
        keys = [item.data(Qt.ItemDataRole.UserRole)
                for item in self.list.selectedItems()]
        if keys:
            self.remove_requested.emit(keys)


# ---------- picker pages: card grid (brand / bracket chooser) ----------
CARD_HEIGHT = 64
CARD_LOGO = 40
PICK_COLUMNS = 2


class PickCard(QFrame):
    """One selectable card: logo (or bullet) + name + right-hand meta."""

    clicked = Signal(str)

    def __init__(self, title: str, value: str = None, meta: str = "",
                 image_file: str = "", bullet: bool = False, parent=None):
        """title is what the user reads, value is what the signal carries.

        They must stay separate: the bracket card reads 「38号」 but the query
        needs the raw id 「38」.
        """
        super().__init__(parent)
        self.title = title
        self.value = title if value is None else value
        self.setObjectName("pickCard")
        self.setFixedHeight(CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(12)
        if bullet:
            dot = QLabel()
            dot.setObjectName("pickBullet")
            dot.setFixedSize(10, 10)
            row.addWidget(dot)
            row.addSpacing(6)
        else:
            plate = QLabel()
            plate.setObjectName("pickLogo")
            plate.setFixedSize(CARD_LOGO, CARD_LOGO)
            plate.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fill_plate(plate, image_file, CARD_LOGO, CARD_LOGO)
            row.addWidget(plate)
        name = QLabel(title)
        name.setObjectName("pickName")
        row.addWidget(name)
        row.addStretch(1)
        self.meta_label = None
        if meta:
            badge = QLabel(meta)
            badge.setObjectName("pickMeta")
            row.addWidget(badge)
            self.meta_label = badge

    def set_meta(self, text: str) -> None:
        """Rewrite the right-hand badge without rebuilding the card."""
        if self.meta_label is not None:
            self.meta_label.setText(text)

    def set_selected(self, selected: bool) -> None:
        self.setObjectName("pickCardSel" if selected else "pickCard")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.value)
        super().mousePressEvent(event)


class PickGrid(QScrollArea):
    """Scrollable two-column card grid grouped under section heads."""

    picked = Signal(str)

    def __init__(self, columns: int = PICK_COLUMNS, parent=None):
        super().__init__(parent)
        self._columns = max(1, columns)
        self._cards = []
        self._empty = None
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self._box = QVBoxLayout(holder)
        self._box.setContentsMargins(20, 4, 20, 16)
        self._box.setSpacing(0)
        self._box.addStretch(1)
        self.setWidget(holder)

    def set_groups(self, groups) -> None:
        """groups = [(title, subtitle, [item, ...]), ...]

        item = {"title":…, "meta":…, "image_file":…, "bullet": bool}
        """
        self._clear()
        total = 0
        for title, subtitle, items in groups:
            self._box.insertWidget(self._box.count() - 1,
                                   _group_head(title, subtitle))
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)
            for index, item in enumerate(items):
                card = PickCard(item["title"], value=item.get("value"),
                                meta=item.get("meta", ""),
                                image_file=item.get("image_file", ""),
                                bullet=item.get("bullet", False))
                card.clicked.connect(self._on_pick)
                grid.addWidget(card, index // self._columns,
                               index % self._columns)
                self._cards.append(card)
            for column in range(self._columns):
                grid.setColumnStretch(column, 1)
            box = QWidget()
            box.setLayout(grid)
            self._box.insertWidget(self._box.count() - 1, box)
            total += len(items)
        if not total:
            self._empty = QLabel("没有匹配的结果")
            self._empty.setObjectName("emptyTitle")
            self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._box.insertWidget(self._box.count() - 1, self._empty)

    def set_metas(self, mapping) -> None:
        """Update only the badges, keyed by card value (no widget rebuild).

        Used after a fitment edit / delete: the card set is unchanged, only the
        「N 适配」/「N 车型」count moves — rebuilding 500+ cards for that costs
        about half a second of frozen UI.
        """
        for card in self._cards:
            text = mapping.get(card.value)
            if text is not None:
                card.set_meta(text)

    def _clear(self) -> None:
        while self._box.count() > 1:          # 保留末尾 stretch
            item = self._box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._cards = []
        self._empty = None

    def _on_pick(self, value: str) -> None:
        for card in self._cards:
            card.set_selected(card.value == value)
        self.picked.emit(value)


def _group_head(title: str, subtitle: str = "") -> QFrame:
    """Section head for the card grid: ring + optional label + the letter."""
    head = QFrame()
    head.setObjectName("groupHead")
    row = QHBoxLayout(head)
    row.setContentsMargins(2, 14, 2, 8)
    row.setSpacing(8)
    ring = QLabel("▸")
    ring.setObjectName("groupDot")
    ring.setFixedSize(18, 18)
    ring.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(ring)
    if subtitle:
        label = QLabel(subtitle)
        label.setObjectName("groupLabel")
        row.addWidget(label)
    letter = QLabel(title)
    letter.setObjectName("groupLetter" if len(title) <= 2 else "groupTitle")
    row.addWidget(letter)
    row.addStretch(1)
    return head

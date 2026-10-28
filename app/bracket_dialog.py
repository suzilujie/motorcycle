# -*- coding: utf-8 -*-
"""按支架查页的两个弹窗：改支架本身（图片 / 备注）与给支架补一条车型。

支架号只读（2026-10-28 用户要求）：改号要级联 fitments / bracket_images，
且磁盘文件名还压着旧号，收益小于风险，所以这里只提供图片与备注。
两个弹窗都遵循「保存失败不关窗」的既有做法：原因写在 hint 里，输入不丢。
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout)

import ui
import years
from image_strip import ImageStrip, import_image

MAX_NOTE = 200
MAX_IMAGES = 6
# 与「新增支架」页同一套尺寸：100×76 × 3 列 = 312px，6 张两行整
THUMB = (100, 76)
THUMB_COLUMNS = 3


class _HintedDialog(QDialog):
    """Title / subtitle / hint / 取消+保存 的共用骨架。"""

    def __init__(self, title: str, subtitle: str, width: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(20, 18, 20, 16)
        self.outer.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("dialogTitle")
        self.outer.addWidget(head)
        sub = QLabel(subtitle)
        sub.setObjectName("dialogSub")
        sub.setWordWrap(True)
        self.outer.addWidget(sub)
        # 故意不叫 self.result：那会盖掉 QDialog.result() 这个 Qt 方法
        self.payload = {}

    def _finish(self) -> None:
        """Call after the body widgets are in place."""
        self.hint = QLabel("")
        self.hint.setObjectName("dialogHint")
        self.hint.setWordWrap(True)
        self.outer.addWidget(self.hint)
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
        self.outer.addLayout(actions)

    def set_hint(self, text: str, error: bool = False) -> None:
        name = "dialogError" if error else "dialogHint"
        if self.hint.objectName() != name:
            self.hint.setObjectName(name)
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
        self.hint.setText(text)

    def save(self) -> None:                 # pragma: no cover - subclass duty
        raise NotImplementedError


class BracketEditDialog(_HintedDialog):
    """图片（多图 / 封面）+ 备注；支架号只读。"""

    def __init__(self, repo, bracket_id: str, parent=None):
        super().__init__("编辑支架",
                         "支架号 %s · 支架号不可修改（换号请到「新增支架」页新建）"
                         % bracket_id, 540, parent)
        self.repo = repo
        self.bracket_id = bracket_id
        self.truncated = 0

        number_row = QHBoxLayout()
        number_row.setSpacing(8)
        number_row.addWidget(self._tag("支架号"))
        self.number = QLineEdit(bracket_id)
        self.number.setReadOnly(True)
        self.number.setToolTip("支架号不可修改")
        number_row.addWidget(self.number, 1)
        number_row.addWidget(ui.chip("只读"))
        self.outer.addLayout(number_row)

        photo_row = QHBoxLayout()
        photo_row.setSpacing(8)
        photo_row.addWidget(self._tag("图片"))
        self.photo_btn = QPushButton("＋ 添加图片")
        self.photo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.photo_btn.setToolTip("可多选；第一张为封面，点缩略图可换封面")
        self.photo_btn.clicked.connect(self._pick_images)
        photo_row.addWidget(self.photo_btn)
        self.photo_hint = ui.hint("")
        photo_row.addWidget(self.photo_hint, 1)
        self.outer.addLayout(photo_row)

        self.strip = ImageStrip(thumb=THUMB, columns=THUMB_COLUMNS,
                                limit=MAX_IMAGES)
        self.strip.changed.connect(self._sync_images)
        self.outer.addWidget(self.strip)

        note_row = QHBoxLayout()
        note_row.setSpacing(8)
        note_row.addWidget(self._tag("备注"))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("如 右侧进线 / 原厂件（可留空）")
        note_row.addWidget(self.note_edit, 1)
        self.note_chip = ui.chip("0 / %d" % MAX_NOTE)
        note_row.addWidget(self.note_chip)
        self.outer.addLayout(note_row)

        self._finish()
        # 信号放在 _finish 之后：_sync_note 要用到 hint，构造期不能触发
        self.note_edit.textChanged.connect(self._sync_note)

        self.strip.set_images([{"src": row["file_name"], "new": False}
                               for row in repo.bracket_images(bracket_id)])
        self.note_edit.setText(repo.bracket_note(bracket_id))
        self._sync_images()
        self._sync_note()
        self.photo_btn.setFocus()

    # ---------- builders ----------
    @staticmethod
    def _tag(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogSub")
        label.setFixedWidth(40)
        return label

    # ---------- 图片 ----------
    def _sync_images(self) -> None:
        count = self.strip.count()
        self.photo_btn.setEnabled(not self.strip.full())
        self.photo_hint.setText(
            "%d / %d 张 · 第一张为封面" % (count, MAX_IMAGES)
            if count else "jpg / png / webp，最多 %d 张（可跳过）" % MAX_IMAGES)

    def _pick_images(self) -> None:
        if self.strip.full():
            self.set_hint("最多 %d 张图片" % MAX_IMAGES, error=True)
            return
        paths, _filters = QFileDialog.getOpenFileNames(
            self, "选择支架图片（可多选）", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if not paths:
            return
        skipped = self.strip.add_paths(paths)
        if skipped:
            self.set_hint("已忽略 %d 张（读不出来或超出上限 %d 张）"
                          % (skipped, MAX_IMAGES), error=True)
        else:
            self.set_hint("")

    # ---------- 备注 ----------
    def _sync_note(self) -> None:
        length = len(self.note_edit.text())
        self.note_chip.setText("%d / %d" % (length, MAX_NOTE))
        over = length > MAX_NOTE
        self._restyle(self.note_chip, "chipNew" if over else "chip")
        warning = self.hint.text().startswith("⚠ 备注最多")
        if over:
            self.set_hint("⚠ 备注最多 %d 字，保存时会截断多出的 %d 个字"
                          % (MAX_NOTE, length - MAX_NOTE), error=True)
        elif warning:                       # 只清掉自己写的那条，别盖住保存错误
            self.set_hint("")

    @staticmethod
    def _restyle(widget, name: str) -> None:
        if widget.objectName() != name:
            widget.setObjectName(name)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    # ---------- 保存 ----------
    def save(self) -> None:
        note = self.note_edit.text().strip()
        self.truncated = max(0, len(note) - MAX_NOTE)
        if self.truncated:
            note = note[:MAX_NOTE].rstrip()
        try:
            # 新图先落盘成正式文件名（bracket_<id>_<n>），再一次性写库
            names = []
            for index, entry in enumerate(self.strip.images()):
                if entry.get("new"):
                    names.append(import_image(self.bracket_id, entry["src"],
                                              index + 1))
                else:
                    names.append(entry["src"])
            self.payload = self.repo.save_bracket_meta(
                self.bracket_id, note=note, images=names)
        except ValueError as error:
            self.set_hint("⚠ " + str(error), error=True)
            return
        except (sqlite3.Error, OSError) as error:   # 连接 / 拷贝 / 备份兜底
            self.set_hint("⚠ 保存失败：%s" % error, error=True)
            return
        self.accept()


ALL_BRANDS = "全部品牌"


class FitmentPickDialog(_HintedDialog):
    """在当前支架上「添加已有车型」（来源 = M）。

    车型只能从库里已有的 brands / models 里勾选：本弹窗不建字典，
    需要新品牌 / 新车型请到「新增」页 →「＋ 新增车型」，避免手输错字
    在库里造出一堆近似品牌（2026-10-28 用户纠正：不是「新增车型」，
    而是「在支架上添加车型」，车型数据库里都已存在）。
    """

    MAX_ROWS = 200

    def __init__(self, repo, bracket_id: str, parent=None):
        super().__init__("添加车型",
                         "为支架 %s 号添加适配记录：只能勾选库里已有的车型"
                         % bracket_id, 560, parent)
        self.repo = repo
        self.bracket_id = bracket_id
        self._years_ok = True

        self.brand_box = QComboBox()
        self.brand_box.addItem(ALL_BRANDS)
        self.brand_box.addItems([row["brand"] for row in repo.brands()])
        self.brand_box.setFixedWidth(120)
        self.brand_box.setToolTip("右侧候选只列该品牌的车型")

        self.checklist = ui.CheckList(
            "选择车型", "搜索车型 / 品牌（支持拼音）",
            "上限 %d 条" % self.MAX_ROWS, leading=self.brand_box)
        self.outer.addWidget(self.checklist, 1)

        self.years_edit = QLineEdit()
        self.years_edit.setPlaceholderText("留空 = 全部年款")
        self.years_chip = self._field("年款", self.years_edit, "全部年款")

        self._finish()
        # 信号统一在 _finish 之后接：_sync_* 要用 save_btn / hint
        self.brand_box.currentTextChanged.connect(
            lambda _text="": self._reload_candidates())
        self.years_edit.textChanged.connect(lambda _text="": self._sync_years())
        self.checklist.changed.connect(self._sync_count)
        self._reload_candidates()
        self._sync_years()
        self._sync_count()
        self.brand_box.setFocus()

    # ---------- builders ----------
    def _field(self, label: str, widget, chip_text: str = ""):
        row = QHBoxLayout()
        row.setSpacing(8)
        tag = QLabel(label)
        tag.setObjectName("dialogSub")
        tag.setFixedWidth(40)
        row.addWidget(tag)
        row.addWidget(widget, 1)
        badge = ui.chip(chip_text) if chip_text else None
        if badge is not None:
            row.addWidget(badge)
        self.outer.addLayout(row)
        return badge

    # ---------- candidates（只列已有字典） ----------
    def _candidates(self) -> list:
        brand = self.brand_box.currentText().strip()
        if brand and brand != ALL_BRANDS:
            brands = [brand]
        else:
            brands = [row["brand"] for row in self.repo.brands()]
        items = []
        for name in brands:
            for model in self.repo.models(name):
                items.append({"key": (name, model),
                              "text": "%s  %s" % (name, model),
                              "label": model,
                              "payload": (name, model)})
        return items

    def _reload_candidates(self) -> None:
        """换品牌只重建候选；已勾选的车型由 CheckList 自己保留。"""
        self.checklist.set_items(self._candidates())

    # ---------- live state ----------
    def _sync_years(self) -> None:
        start, end, _json, ok, _message = years.parse_years(self.years_edit.text())
        self._years_ok = ok
        self._set_chip(self.years_chip,
                       years.display_range(start, end) if ok else "格式错误",
                       accent=not ok)
        self._sync_count()
        if not ok:
            self.set_hint("⚠ 年款格式不对，例：2019-2023 / 2019 / 2019-", error=True)
        elif self.hint.text().startswith("⚠ 年款格式"):
            self.set_hint("")

    def _sync_count(self) -> None:
        count = len(self.checklist.checked_items())
        self.save_btn.setText("添加（%d 条）" % count if count else "添加（未选）")
        self.save_btn.setEnabled(bool(count) and self._years_ok)

    @staticmethod
    def _set_chip(label, text: str, accent: bool = False) -> None:
        label.setText(text)
        name = "chipNew" if accent else "chip"
        if label.objectName() != name:
            label.setObjectName(name)
            label.style().unpolish(label)
            label.style().polish(label)

    # ---------- 保存 ----------
    def save(self) -> None:
        pairs = [(self.bracket_id, brand, model)
                 for brand, model in self.checklist.checked_keys()]
        if not pairs:
            self.set_hint("⚠ 请先勾选要添加的车型", error=True)
            return
        if len(pairs) > self.MAX_ROWS:
            self.set_hint("⚠ 一次最多添加 %d 条，请分几次" % self.MAX_ROWS,
                          error=True)
            return
        try:
            result = self.repo.add_manual(pairs, self.years_edit.text().strip())
        except ValueError as error:
            self.set_hint("⚠ " + str(error), error=True)
            return
        except (sqlite3.Error, OSError) as error:
            self.set_hint("⚠ 保存失败：%s" % error, error=True)
            return
        if not result["added"]:
            # 判重命中：留在窗口里，换个年款或换车型还能继续
            self.set_hint("⚠ 勾选的车型在该支架下都已存在（同支架 / 车型 / 年款），"
                          "未写入", error=True)
            return
        self.payload = result
        self.accept()

# -*- coding: utf-8 -*-
"""Two manual-entry modes: 新增车型（多选支架） / 新增支架（多选车型）.

Both modes share EntryForm: a fixed 336px form column on the left, the candidate
list plus the picked panel on the right, one unified year box (empty = all model
years) and one save button whose label carries the row count.

Saving always goes through Repository.add_manual(), which backs the database up
first and keeps brands / models / brackets / fitments in a single transaction.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

import ui
import years
from bracket_dialog import MAX_NOTE
from brand_dialog import NewModelDialog
from image_strip import ImageStrip, import_image

ALL_BRANDS = "全部品牌"


class EntryForm(QWidget):
    """Shared scaffold of the two entry modes."""

    saved = Signal(dict)
    # 只是补字典（新增品牌/车型），没有写 fitments —— 主窗口刷新策略不同
    dictionary_changed = Signal()

    TITLE = ""
    INTRO = ""
    CHECK_TITLE = "候选"
    CHECK_NOTE = ""
    PLACEHOLDER = ""
    SHOW_YEARS = True          # 新增支架页关掉：按「全部年款」写库

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self._year_ok = True

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 10)
        outer.setSpacing(12)

        left = QWidget()
        left.setFixedWidth(336)
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        title = QLabel(self.TITLE)
        title.setObjectName("formTitle")
        column.addWidget(title)
        self._build_fields(column)
        self._build_year_row(column)
        intro = QLabel(self.INTRO)
        intro.setObjectName("hint")
        intro.setWordWrap(True)
        column.addWidget(intro)
        # 按钮紧跟字段，剩余空白留在栏底：以前 stretch 在按钮之前，
        # 图片区变高后按钮被顶到整栏最下面，与表单脱节。
        self._build_actions(column)
        column.addStretch(1)
        outer.addWidget(left)

        right = QWidget()
        right_row = QHBoxLayout(right)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(10)
        self.checklist = ui.CheckList(self.CHECK_TITLE, self.PLACEHOLDER,
                                      self.CHECK_NOTE,
                                      leading=self._checklist_leading(),
                                      actions=self._checklist_actions())
        self.picked = ui.PickedList()
        right_row.addWidget(self.checklist, 1)
        right_row.addWidget(self.picked)
        outer.addWidget(right, 1)

        self.checklist.changed.connect(self._sync_picked)
        self.picked.remove_requested.connect(
            lambda keys: self.checklist.set_checked(keys, False))
        self._sync_chips()
        self._sync_picked()

    # ---------- builders ----------
    def _build_fields(self, column) -> None:
        raise NotImplementedError

    def _build_year_row(self, column) -> None:
        # 控件永远创建（保存 / 回执 / 已选标签都要读它），SHOW_YEARS=False 时
        # 只是不放进布局：新增支架页按「全部年款」写库，不再让用户填。
        self.years_edit = QLineEdit()
        self.years_note = QLabel("")
        self.years_note.setObjectName("warn")
        self.years_note.setWordWrap(True)
        self.years_chip = None
        if self.SHOW_YEARS:
            # 不加占位符：右侧 chip 承担「留空 = 全部年款」的提示，
            # 两处写同一句话既重复，占位符在窄输入框里还会折行撑高行高。
            self.years_chip = self.field_row(column, "年款", self.years_edit,
                                             "全部年款")
            column.addWidget(self.years_note)
        self._years_state = years.parse_years("")
        self.years_edit.textChanged.connect(lambda _text="": self._sync_year())

    def _build_actions(self, column) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.save_btn = QPushButton("保存（仅建档）")
        self.save_btn.setObjectName("primary")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save)
        self.reset_btn = QPushButton("清空")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self.reset)
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        row.addWidget(self.save_btn)
        row.addWidget(self.reset_btn)
        row.addWidget(self.msg, 1)
        column.addLayout(row)

    def field_row(self, column, label: str, widget, chip_text: str = ""):
        """One labeled input line; returns its chip label (None when unused)."""
        row = QHBoxLayout()
        row.setSpacing(8)
        key = QLabel(label)
        key.setObjectName("kvLabel")
        key.setFixedWidth(52)
        row.addWidget(key)
        row.addWidget(widget, 1)
        badge = ui.chip(chip_text) if chip_text else None
        if badge is not None:
            row.addWidget(badge)
        column.addLayout(row)
        return badge

    # ---------- live state ----------
    def _sync_year(self) -> None:
        self._years_state = years.parse_years(self.years_edit.text())
        start, end, _json, ok, message = self._years_state
        self._year_ok = ok
        if self.years_chip is not None:      # 隐藏年款行的模式没有 chip
            self.years_chip.setText("格式错误" if not ok
                                    else years.display_range(start, end))
        self.years_note.setText("" if ok else "⚠ " + message)
        self._sync_picked()

    def _sync_picked(self) -> None:
        start, end, _json, ok, _message = self._years_state
        # 年款非法时不能显示「全部年款」，那等于给用户一个相反的暗示
        span = years.display_range(start, end) if ok else "年款待修正"
        items = []
        for entry in self.checklist.checked_items():
            items.append({"key": entry["key"],
                          "text": "%s · %s" % (entry.get("label") or entry["text"],
                                               span)})
        self.picked.set_items(items)
        count = len(items)
        self.save_btn.setText("保存（%d 条）" % count if count else "保存（仅建档）")
        self.save_btn.setEnabled(self._year_ok)

    def _checklist_leading(self):
        """Optional filter widget pinned in front of the candidate search box."""
        return None

    def _checklist_actions(self):
        """Extra buttons appended after 全选 / 清空 in the candidate toolbar."""
        return ()

    def _sync_chips(self) -> None:
        """Mode specific chips; overridden where there is something to show."""

    @staticmethod
    def _set_chip(label, text: str, accent: bool = False) -> None:
        label.setText(text)
        label.setObjectName("chipNew" if accent else "chip")
        label.style().unpolish(label)
        label.style().polish(label)

    def _say(self, text: str, bad: bool = False) -> None:
        self.msg.setText(text)
        self.msg.setObjectName("warn" if bad else "ok")
        self.msg.style().unpolish(self.msg)
        self.msg.style().polish(self.msg)

    # ---------- data ----------
    def candidates(self) -> list:
        raise NotImplementedError

    def write(self, years_raw: str) -> dict:
        raise NotImplementedError

    def refresh(self) -> None:
        """Rebuild the candidate list (repository was reloaded after a save)."""
        self.checklist.set_items(self.candidates())
        self._sync_chips()
        self._sync_picked()

    def reset(self) -> None:
        self.checklist.clear_checks()
        self._say("")

    # ---------- save ----------
    def save(self) -> None:
        start_end = years.parse_years(self.years_edit.text())
        if not start_end[3]:
            self._say(start_end[4], bad=True)
            return
        try:
            result = self.write(self.years_edit.text().strip())
        except ValueError as error:
            self._say(str(error), bad=True)
            return
        except Exception as error:              # 写库失败一律回滚并如实提示
            self._say("保存失败：%s" % error, bad=True)
            return
        self._say(self._receipt(result))
        self.saved.emit(result)

    @staticmethod
    def _receipt(result: dict) -> str:
        """Say what actually happened: 建档 / 全跳过 / 部分成功。"""
        added, skipped = result["added"], result["skipped"]
        if not added and not skipped:
            return "已建档（未生成适配记录）"
        if not added:
            return "跳过 %d 条（已存在，未写入）" % skipped
        if not skipped:
            return "成功 %d 条" % added
        return "成功 %d 条 · 跳过 %d 条（已存在）" % (added, skipped)


class ModelForm(EntryForm):
    """新增车型：填品牌/车型，右侧多选要挂上去的支架。"""

    TITLE = "车型信息"
    INTRO = "品牌/车型不存在时自动创建。年款留空 = 全部年款；填了就写给本次勾选的全部支架。"
    CHECK_TITLE = "选择适配支架"
    # 工具条要放 搜索 + 全选 + 清空 + ＋新增车型，提示文字留最短的一句
    CHECK_NOTE = "上限 200 条"
    PLACEHOLDER = "搜索支架号（支持拼音）"

    def _build_fields(self, column) -> None:
        self.brand_box = QComboBox()
        self.brand_box.setEditable(True)
        self.brand_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        ui.attach_completer(self.brand_box, provider=self._brand_suggestions)
        self.brand_chip = self.field_row(column, "品牌", self.brand_box, "已存在")

        self.new_brand_btn = QPushButton("＋ 新增车型")
        self.new_brand_btn.setObjectName("flat")
        self.new_brand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_brand_btn.setToolTip("弹窗给已有品牌补车型（新品牌名会一并创建），"
                                      "建完自动填进品牌框")
        self.new_brand_btn.clicked.connect(self._open_new_model)

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("如 一汽奥迪Q5L 2025")
        ui.attach_completer(self.model_edit, provider=self._model_suggestions)
        self.model_chip = self.field_row(column, "车型", self.model_edit, "将新建")

        self.brand_box.currentTextChanged.connect(lambda _text="": self.refresh())
        self.model_edit.textChanged.connect(lambda _text="": self._sync_chips())

    def _checklist_actions(self):
        return (self.new_brand_btn,)

    def _open_new_model(self) -> None:
        """和「新增支架」页同一个弹窗：建好车型后自动填进品牌框。"""
        dialog = NewModelDialog(self.repo, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result or {}
        self.dictionary_changed.emit()
        self.brand_box.setCurrentText(dialog.brand_name)
        self.refresh()
        self.model_edit.setFocus()
        self._say("已新增车型 %d 个（品牌「%s」）%s，接着填车型名即可"
                  % (result.get("models_added", 0), dialog.brand_name,
                     "（%d 个已存在）" % result.get("models_skipped", 0)
                     if result.get("models_skipped") else ""))

    def _brand_suggestions(self) -> list:
        return [row["brand"] for row in self.repo.brands()]

    def _model_suggestions(self) -> list:
        brand = self.brand_box.currentText().strip()
        return self.repo.models(brand) if brand else []

    def _sync_chips(self) -> None:
        brand = self.brand_box.currentText().strip()
        known_brand = bool(brand) and brand in self._brand_suggestions()
        self._set_chip(self.brand_chip, "已存在" if known_brand else "将新建",
                       accent=not known_brand)
        model = self.model_edit.text().strip()
        known_model = bool(model) and model in self._model_suggestions()
        self._set_chip(self.model_chip, "已存在" if known_model else "将新建",
                       accent=not known_model)

    def candidates(self) -> list:
        items = []
        for row in self.repo.brackets():
            bracket_id = row["bracket_id"]
            count = row.get("fitment_count") or 0
            items.append({
                "key": bracket_id,
                "text": "%s 号 · %d 条适配" % (bracket_id, count),
                "label": "%s 号" % bracket_id,
                "payload": bracket_id,
            })
        return items

    def write(self, years_raw: str) -> dict:
        brand = self.brand_box.currentText().strip()
        model = self.model_edit.text().strip()
        if not brand or not model:
            raise ValueError("请填写品牌与车型")
        pairs = [(bracket_id, brand, model)
                 for bracket_id in self.checklist.checked_keys()]
        return self.repo.add_manual(pairs, years_raw, targets=[(brand, model)])

    def reset(self) -> None:
        super().reset()
        self.model_edit.clear()


class BracketForm(EntryForm):
    """新增支架：填支架号 + 多张图片，右侧按品牌筛选后多选车型。

    图片是「一整条列表」而不是单张：第一张同时写进 brackets.image_file 当封面，
    其余存 bracket_images 表。品牌下拉放在右侧候选工具条（ui.CheckList.leading），
    左栏不再重复一个「筛选」行。
    """

    TITLE = "新增车架"
    INTRO = "支架号不存在时自动创建。适配记录统一按「全部年款」写入。"
    CHECK_TITLE = "选择适配车型"
    # 工具条要放 品牌 + 搜索 + 全选 + 清空 + 新增车型，提示文字让位给搜索框
    CHECK_NOTE = ""
    PLACEHOLDER = "搜索车型 / 品牌（支持拼音）"
    SHOW_YEARS = False          # 2026-10-28 用户要求：新增支架页不要年款行

    MAX_IMAGES = 6
    # 100×76 × 3 列 = 312px，正好把 336px 的左栏用满；6 张刚好两行整。
    # 不再额外放大图预览：首图即封面，缩略图本身已经看得清。
    THUMB = (100, 76)
    THUMB_COLUMNS = 3

    def _build_fields(self, column) -> None:
        self._loaded_id = ""          # 已经载入过图片 / 备注的支架号
        self._loaded_known = False    # 上一次载入的是否是库里已有的支架

        self.bracket_edit = QLineEdit()
        self.bracket_edit.setPlaceholderText("如 301A")
        self.bracket_chip = self.field_row(column, "支架号", self.bracket_edit,
                                           "将新建")
        self.bracket_edit.textChanged.connect(self._on_bracket_id_changed)

        photo_row = QHBoxLayout()
        photo_row.setSpacing(8)
        key = QLabel("图片")
        key.setObjectName("kvLabel")
        key.setFixedWidth(52)
        photo_row.addWidget(key)
        self.photo_btn = QPushButton("＋ 添加图片")
        self.photo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.photo_btn.setToolTip("可多选；第一张为封面，点缩略图可换封面")
        self.photo_btn.clicked.connect(self._pick_images)
        photo_row.addWidget(self.photo_btn)
        self.photo_hint = ui.hint("")
        photo_row.addWidget(self.photo_hint, 1)
        column.addLayout(photo_row)

        self.strip = ImageStrip(thumb=self.THUMB, columns=self.THUMB_COLUMNS,
                                limit=self.MAX_IMAGES)
        self.strip.changed.connect(self._on_images_changed)
        column.addWidget(self.strip)

        # 备注（2026-10-28）：与「按支架查」页的「编辑支架」弹窗是同一个字段
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("如 右侧进线 / 原厂件（可留空）")
        self.note_chip = self.field_row(column, "备注", self.note_edit,
                                        "0 / %d" % MAX_NOTE)
        self.note_edit.textChanged.connect(self._on_note_changed)

        self.brand_box = QComboBox()      # 实际挂在右侧候选工具条里
        self.brand_box.addItem(ALL_BRANDS)
        self.brand_box.setFixedWidth(120)
        self.brand_box.setToolTip("右侧候选只列该品牌的车型")
        self._brand_value = ALL_BRANDS
        self.brand_box.currentTextChanged.connect(self._on_brand_changed)

        self.new_brand_btn = QPushButton("＋ 新增车型")
        self.new_brand_btn.setObjectName("flat")
        self.new_brand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_brand_btn.setToolTip("弹窗给已有品牌补车型（新品牌名会一并创建），"
                                      "建完自动勾选")
        self.new_brand_btn.clicked.connect(self._open_new_model)

        self._on_images_changed()

    def _checklist_leading(self):
        return getattr(self, "brand_box", None)

    # ---------- 图片区 ----------
    def _on_images_changed(self) -> None:
        """缩略图条变了：同步「＋」可用态与计数提示。"""
        count = self.strip.count()
        self.photo_btn.setEnabled(not self.strip.full())
        self.photo_hint.setText(
            "%d / %d 张 · 第一张为封面" % (count, self.MAX_IMAGES)
            if count else "jpg / png / webp，最多 %d 张（可跳过）"
            % self.MAX_IMAGES)

    def _on_note_changed(self, _text: str = "") -> None:
        length = len(self.note_edit.text())
        self._set_chip(self.note_chip, "%d / %d" % (length, MAX_NOTE),
                       accent=length > MAX_NOTE)

    def _pick_images(self) -> None:
        if self.strip.full():
            self._say("最多 %d 张图片" % self.MAX_IMAGES, bad=True)
            return
        paths, _filters = QFileDialog.getOpenFileNames(
            self, "选择支架图片（可多选）", "", "图片 (*.jpg *.jpeg *.png *.webp)")
        if not paths:
            return
        skipped = self.strip.add_paths(paths)
        if skipped:
            self._say("已忽略 %d 张（读不出来或超出上限 %d 张）"
                      % (skipped, self.MAX_IMAGES), bad=True)
        else:
            self._say("")

    def _on_bracket_id_changed(self, _text: str = "") -> None:
        self._sync_chips()
        self._load_images()

    def _load_images(self) -> None:
        """支架号命中已有记录时，把它的图与备注带出来继续编辑。

        还有没保存的新图时不覆盖图片，免得把刚选的图弄丢；
        新支架号（库里没有）则清空图片与备注，回到「新建」状态。
        """
        bracket_id = self.bracket_edit.text().strip()
        if bracket_id == self._loaded_id:
            return
        self._loaded_id = bracket_id
        known = any(row["bracket_id"] == bracket_id for row in self.repo.brackets())
        if not known:
            # 只有「从已有支架切到一个新号」才清空上一个支架的内容；
            # 新建过程中用户自己改号（之前没载入过）则保留已填的图与备注。
            if self._loaded_known:
                if not any(entry.get("new") for entry in self.strip.images()):
                    self.strip.set_images([])
                self.note_edit.clear()
            self._loaded_known = False
            return
        self._loaded_known = True
        self.note_edit.setText(self.repo.bracket_note(bracket_id))
        if any(entry.get("new") for entry in self.strip.images()):
            return
        names = [row["file_name"] for row in self.repo.bracket_images(bracket_id)]
        self.strip.set_images([{"src": name, "new": False} for name in names])

    def _sync_chips(self) -> None:
        bracket_id = self.bracket_edit.text().strip()
        known = bool(bracket_id) and any(
            row["bracket_id"] == bracket_id for row in self.repo.brackets())
        self._set_chip(self.bracket_chip, "已存在" if known else "将新建",
                       accent=not known)

    def candidates(self) -> list:
        selected = self.brand_box.currentText().strip()
        if selected and selected != ALL_BRANDS:
            brands = [selected]
        else:
            brands = [row["brand"] for row in self.repo.brands()]
        items = []
        for brand in brands:
            for model in self.repo.models(brand):
                items.append({
                    "key": (brand, model),
                    "text": "%s %s" % (brand, model),
                    "label": "%s %s" % (brand, model),
                    "payload": (brand, model),
                })
        return items

    def write(self, years_raw: str) -> dict:
        bracket_id = self.bracket_edit.text().strip()
        if not bracket_id:
            raise ValueError("请填写支架号")
        names = []
        for index, entry in enumerate(self.strip.images()):
            if entry.get("new"):
                names.append(import_image(bracket_id, entry["src"], index + 1))
            else:
                names.append(entry["src"])
        pairs = [(bracket_id, brand, model)
                 for brand, model in self.checklist.checked_keys()]
        note = self.note_edit.text().strip()
        if len(note) > MAX_NOTE:                # 与「编辑支架」弹窗口径一致
            note = note[:MAX_NOTE].rstrip()
        result = self.repo.add_manual(
            pairs, years_raw,
            bracket={"bracket_id": bracket_id, "images": names, "note": note})
        # 新图已经落盘成正式文件名，就地转正，避免下次保存重复导入
        self.strip.set_images([{"src": name, "new": False} for name in names])
        self._loaded_id = bracket_id
        return result

    def _checklist_actions(self):
        return (self.new_brand_btn,)

    def _on_brand_changed(self, text: str) -> None:
        self._brand_value = text
        self.refresh()

    def _select_brand(self, name: str) -> None:
        self.brand_box.blockSignals(True)
        index = self.brand_box.findText(name)
        self.brand_box.setCurrentIndex(index if index >= 0 else 0)
        self.brand_box.blockSignals(False)
        self._brand_value = self.brand_box.currentText()
        self.refresh()

    def _open_new_model(self) -> None:
        """弹窗新增车型，成功后切到该品牌并把新车型直接勾上。"""
        dialog = NewModelDialog(self.repo, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return                   # 取消：下拉没被动过，不用复原
        result = dialog.result or {}
        self.dictionary_changed.emit()
        self._select_brand(dialog.brand_name)
        # 刚建的车型直接勾上，省一次「再找一遍」；已存在的车型勾上也会被判重跳过
        self.checklist.set_checked(
            [(dialog.brand_name, model) for model in dialog.model_list])
        self._say("已新增车型 %d 个（品牌「%s」）%s，已勾选"
                  % (result.get("models_added", 0), dialog.brand_name,
                     "（%d 个已存在）" % result.get("models_skipped", 0)
                     if result.get("models_skipped") else ""))

    def refresh(self) -> None:
        brands = [row["brand"] for row in self.repo.brands()]
        current = self._brand_value
        self.brand_box.blockSignals(True)
        self.brand_box.clear()
        self.brand_box.addItems([ALL_BRANDS] + brands)
        index = self.brand_box.findText(current)
        self.brand_box.setCurrentIndex(index if index >= 0 else 0)
        self._brand_value = self.brand_box.currentText()
        self.brand_box.blockSignals(False)
        super().refresh()

    def reset(self) -> None:
        super().reset()
        self._loaded_id = ""
        self._loaded_known = False
        self.strip.set_images([])
        self.note_edit.clear()
        self.bracket_edit.clear()

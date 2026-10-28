# -*- coding: utf-8 -*-
"""Brand picker: brand cards grouped by the pinyin initial (A/B/C…)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLineEdit

import search
import ui

CJK_START, CJK_END = "\u4e00", "\u9fa5"


def initial_of(brand: str) -> str:
    """Group key of a brand: pinyin initial for Chinese, '#' for the rest."""
    first = (brand or "")[:1]
    if not (CJK_START <= first <= CJK_END):
        return "#"
    _full, initials = search.keys(brand)
    letter = (initials or "")[:1].upper()
    return letter if "A" <= letter <= "Z" else "#"


def group_key(text: str):
    """A–Z 或 '#' 当分组键用；返回 None 表示按品牌名关键字搜索。

    只认输入的**第一个字符**：输入 ch 与输入 c 含义相同，都是「看 C 组」，
    而不是「名字里含 ch」——否则 北京汽车（bei**ch**e）这类别的分组的品牌
    会被拼音子串匹配带出来，看起来就是「搜 c 却出现别的字母」。
    """
    first = (text or "")[:1]
    if not first:
        return None
    upper = first.upper()
    if upper == "#":
        return "#"
    if upper.isascii() and upper.isalpha():
        return upper
    return None


class BrandPickerPage(ui.Page):
    """Browse every brand as cards; picking one prefills 「按车型查」."""

    brand_chosen = Signal(str)

    def __init__(self, repo, parent=None):
        super().__init__(repo, parent)
        self._rows = []

        self.search_box = QLineEdit()
        # 搜索框固定 320px，提示文案必须短于这个宽度，否则会被截断成省略号
        self.search_box.setPlaceholderText("字母看分组（A-Z / #），中文搜品牌")
        self.search_box.setFixedWidth(320)
        self.add_filter(self.search_box)
        self.add_filter_stretch()
        self.count_label = ui.hint("")
        self.filter_row.addWidget(self.count_label)

        self.grid = ui.PickGrid()
        self.grid.picked.connect(self.brand_chosen.emit)
        self.body.addWidget(self.grid, 1)

        self.search_box.textChanged.connect(self._rerender)
        self.refresh_data()

    # ---------- data ----------
    def refresh_data(self) -> None:
        self._rows = list(self.repo.brands())
        self._rerender()

    def refresh_if_changed(self) -> None:
        """Cheap path after an edit / delete: rebuild only if the set moved.

        品牌集合没变时只改「N 车型」徽标 —— 269 张卡片整体重建约 300ms，而
        编辑或删除一条适配记录通常只影响一个计数。
        """
        rows = list(self.repo.brands())
        if tuple(row["brand"] for row in rows) != tuple(
                row["brand"] for row in self._rows):
            self._rows = rows
            self._rerender()
            return
        self._rows = rows
        self.grid.set_metas({row["brand"]: "%d 车型" % row["model_count"]
                             for row in rows})

    def _rerender(self, *_args) -> None:
        rows = self._rows
        text = self.search_box.text().strip()
        letter = group_key(text)
        if letter is not None:
            # 字母开头 = 分组视图：只留该分组，别的分组直接隐藏
            rows = [row for row in rows if initial_of(row["brand"]) == letter]
        elif text:
            # 这里只剩中文（或数字）输入：按品牌名原文包含匹配，不展开拼音
            needle = text.lower()
            rows = [row for row in rows if needle in row["brand"].lower()]
        groups = self._group(rows)
        total = sum(len(items) for _title, _sub, items in groups)
        if letter is not None:
            self.count_label.setText("%s 组 · %d 个品牌" % (letter, total))
        elif text:
            self.count_label.setText("命中 %d 个品牌" % total)
        else:
            self.count_label.setText("共 %d 个品牌" % len(rows))
        self.grid.set_groups(groups)

    @staticmethod
    def _group(rows) -> list:
        """Bucket brands by initial; '#' goes last, inside sorted by pinyin."""
        buckets = {}
        for row in rows:
            buckets.setdefault(initial_of(row["brand"]), []).append(row)
        order = sorted(buckets, key=lambda key: (key == "#", key))
        groups = []
        for key in order:
            items = sorted(buckets[key],
                           key=lambda row: search.keys(row["brand"])[0])
            groups.append((key, "其他" if key == "#" else "字母", [
                {"title": row["brand"],
                 "meta": "%d 车型" % row["model_count"],
                 "image_file": row["logo_file"],
                 "bullet": not row["logo_file"]}
                for row in items]))
        return groups

    def focus_search(self) -> None:
        self.search_box.setFocus()
        self.search_box.selectAll()

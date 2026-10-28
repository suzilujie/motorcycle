# -*- coding: utf-8 -*-
"""Cell painters: chip badges and source dots for the detail tables.

QSS cannot draw rounded pills or a dot plus text inside one table cell, so the
two custom columns are painted by delegates. Colors are read from the active
palette on every paint, which keeps the dark/light switch working.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem)

import config

DOT_A = "#a78bfa"      # 来源 A（支架页反查）
DOT_M_KEY = "warn"     # 来源 M（手工录入）取调色板 warn 色，和 A/B 区分


def _draw_base(painter, option, index, delegate, text: str) -> QRect:
    """Paint the normal cell background/selection, then return the free rect.

    The rect is copied on purpose: QStyleOptionViewItem is a temporary and its
    rect wrapper dies with it (libshiboken keeps only a reference).
    """
    opt = QStyleOptionViewItem(option)
    delegate.initStyleOption(opt, index)
    opt.text = ""
    style = opt.widget.style() if opt.widget else QApplication.style()
    style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
    return QRect(opt.rect)


class ChipDelegate(QStyledItemDelegate):
    """Rounded pill around the cell text (used for the year range column)."""

    PAD = 8
    HEIGHT = 18

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        rect = _draw_base(painter, option, index, self, text)
        if not text:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = min(painter.fontMetrics().horizontalAdvance(text) + self.PAD * 2,
                    max(rect.width() - 12, 24))
        chip = QRect(rect.left() + 6, rect.center().y() - self.HEIGHT // 2 + 1,
                     width, self.HEIGHT)
        painter.setPen(QPen(QColor(config.C["chip_line"])))
        painter.setBrush(QColor(config.C["chip_bg"]))
        painter.drawRoundedRect(chip, self.HEIGHT / 2, self.HEIGHT / 2)
        painter.setPen(QColor(config.C["dim"]))
        painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class DotDelegate(QStyledItemDelegate):
    """A dot per source (A/B) followed by the plain letters."""


    SIZE = 6
    GAP = 5

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        rect = _draw_base(painter, option, index, self, text)
        if not text:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        x = rect.left() + 8
        center_y = rect.center().y() + 1
        for part in text.split("/"):
            if part == "A":
                color = QColor(DOT_A)
            elif part == "M":
                color = QColor(config.C[DOT_M_KEY])
            else:
                color = QColor(config.C["accent"])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRect(x, center_y - self.SIZE // 2, self.SIZE, self.SIZE))
            x += self.SIZE + self.GAP
        painter.setPen(QColor(config.C["dim"]))
        painter.drawText(QRect(x, rect.top(), rect.right() - x, rect.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         text)
        painter.restore()


class LinkDelegate(QStyledItemDelegate):
    """Clickable text links painted inside one cell (row-level actions).

    ``parts`` are laid out side by side, each centred in its own slot, so one
    narrow column can carry 「编辑 / 删除」 without extra widgets — 900+ real
    widgets would slow the table's scrolling down measurably.

    clicked(row, part_index)
    """

    clicked = Signal(int, int)

    def __init__(self, parts=("编辑", "删除"), colors=("accent", "bad"),
                 parent=None):
        super().__init__(parent)
        self._parts = tuple(parts)
        self._colors = tuple(colors)

    def paint(self, painter, option, index):
        rect = _draw_base(painter, option, index, self, "")
        if not self._parts:
            return
        painter.save()
        font = painter.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(max(font.pointSizeF(), 8.0))
        if option.state & QStyle.StateFlag.State_MouseOver:
            font.setUnderline(True)
        painter.setFont(font)
        step = max(rect.width(), 1) / len(self._parts)
        for position, text in enumerate(self._parts):
            key = self._colors[position] if position < len(self._colors) else "dim"
            painter.setPen(QColor(config.C[key]))
            slot = QRect(int(rect.left() + step * position), rect.top(),
                         int(step), rect.height())
            painter.drawText(slot, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def part_at(self, rect, x: int) -> int:
        """Which slot the horizontal position belongs to."""
        if not self._parts:
            return 0
        step = max(rect.width(), 1) / len(self._parts)
        part = int((x - rect.left()) / step)
        return min(max(part, 0), len(self._parts) - 1)

    def editorEvent(self, event, model, option, index):
        if (event.type() != QEvent.Type.MouseButtonRelease
                or event.button() != Qt.MouseButton.LeftButton
                or not option.rect.contains(event.pos())):
            return False
        self.clicked.emit(index.row(),
                          self.part_at(option.rect, event.pos().x()))
        return True

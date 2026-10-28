# -*- coding: utf-8 -*-
"""Token-driven QSS stylesheet; one template renders both palettes.

Every color in the template is a @token resolved from config.PALETTES, so a
theme switch is just "apply the stylesheet again" — widgets restyle in place.

Typography follows the A+C redesign: 13px base, 20/24px headline numbers,
11px hints, 38px table rows.
"""

from __future__ import annotations

import config

_QSS = """
QWidget { background: @bg; color: @text;
          font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
          font-size: 13px; }
QMainWindow { background: @bg; }

/* ---------- top bar ---------- */
QFrame#topBar { background: @panel; border: none; border-bottom: 1px solid @border; }
QLabel#appTitle { font-size: 15px; font-weight: 600; color: @text; }
QLabel#appSub { color: @faint; font-size: 11px; }

/* ---------- segmented control (view switch) ---------- */
QPushButton#seg { background: @card; border: 1px solid @border; border-radius: 0;
                  padding: 5px 14px; color: @dim; font-size: 12px; }
QPushButton#seg:checked { background: @accent_bg; border-color: @accent_bg;
                          color: @on_accent; font-weight: 600; }
QPushButton#seg:hover:!checked { color: @text; }

/* ---------- inputs ---------- */
QLineEdit, QComboBox, QSpinBox {
    background: @input; border: 1px solid @border; border-radius: 4px;
    padding: 5px 9px; color: @text; selection-background-color: @accent_bg;
    selection-color: @on_accent;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @accent; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: @card; border: 1px solid @border; selection-background-color: @accent_bg;
    selection-color: @on_accent; color: @text; outline: none;
}

/* ---------- filter bar ---------- */
QFrame#filterBar { background: @bg; border: none; border-bottom: 1px solid @border; }
QLabel#hint { color: @faint; font-size: 11px; }
QLabel#warn { color: @warn; font-size: 11px; }

/* ---------- result list (master pane) ---------- */
QFrame#listHead { background: @bg; border: none; border-bottom: 1px solid @border; }
QLabel#listHeadText { color: @faint; font-size: 11px; }
QFrame#listRow { background: transparent; border: none;
                 border-bottom: 1px solid @border; border-left: 2px solid transparent; }
QFrame#listRow:hover { background: @panel2; }
QFrame#listRowSel { background: @sel_bg; border: none;
                    border-bottom: 1px solid @border; border-left: 2px solid @accent; }
QLabel#listNum { font-family: Consolas, "Microsoft YaHei UI", monospace;
                 font-size: 15px; font-weight: 600; color: @text; }
QLabel#listSub { color: @faint; font-size: 11px; }

/* ---------- chip / photo plate ---------- */
QLabel#chip { background: @chip_bg; border: 1px solid @chip_line; border-radius: 9px;
              padding: 0 7px; color: @dim; font-size: 11px;
              font-family: Consolas, "Microsoft YaHei UI", monospace; }
QLabel#chipNew { background: @chip_bg; border: 1px solid @accent; border-radius: 9px;
                 padding: 0 7px; color: @accent; font-size: 11px;
                 font-family: Consolas, "Microsoft YaHei UI", monospace; }
QLabel#formTitle { font-size: 14px; font-weight: 600; color: @text; }

/* ---------- list widgets (manual entry) ---------- */
QListWidget { background: @card; border: 1px solid @border; border-radius: 4px;
              outline: none; }
QFrame#pickedBody { background: @card; border: 1px solid @border; border-radius: 4px; }
QFrame#pickedBody QListWidget { background: transparent; border: none; }
QListWidget::item { padding: 5px 8px; border-bottom: 1px solid @border; color: @text; }
QListWidget::item:selected { background: @sel_bg; color: @text; }
QListWidget::item:disabled { color: @faint; }
QLabel#photoPlate { background: @plate; border: 1px solid @border; border-radius: 4px;
                    color: #8a8a8a; font-size: 12px; }

/* ---------- detail pane ---------- */
QLabel#detailNum { font-family: Consolas, "Microsoft YaHei UI", monospace;
                   font-size: 24px; font-weight: 600; color: @text; }
QLabel#detailSub { color: @faint; font-size: 12px; }
QLabel#kvLabel { color: @faint; font-size: 12px; }
QLabel#kvValue { color: @text; font-size: 13px; }
QFrame#kvLine { background: @border; border: none; max-height: 1px; min-height: 1px; }

/* ---------- tables ---------- */
QTableView { background: @card; alternate-background-color: @panel2;
             gridline-color: transparent; border: none; border-top: 1px solid @border;
             selection-background-color: @sel_bg; selection-color: @text; color: @text; }
QTableView::item { padding: 0 8px; }
QHeaderView::section { background: @card; color: @faint; border: none;
                       border-bottom: 1px solid @border; padding: 8px;
                       font-weight: 600; font-size: 11px; }
QTableCornerButton::section { background: @card; border: none; }

/* ---------- batch bar / check boxes（勾选表，2026-10-28） ---------- */
QWidget#batchBar { background: @panel; border: none;
                   border-bottom: 1px solid @border; }
QCheckBox { background: transparent; color: @dim; font-size: 11px; spacing: 6px; }
QCheckBox:disabled { color: @faint; }
/* 表格里的勾选框与工具条「全选」共用一套方框：不设 image 时，
   选中态就是一块实心强调色（深色主题下比默认指示器清楚得多）。 */
QCheckBox::indicator, QTableView::indicator {
    width: 13px; height: 13px; border: 1px solid @scroll;
    border-radius: 3px; background: @input;
}
QCheckBox::indicator:hover:!checked, QTableView::indicator:hover:!checked {
    border-color: @accent;
}
QCheckBox::indicator:checked, QTableView::indicator:checked,
QCheckBox::indicator:indeterminate, QTableView::indicator:indeterminate {
    background: @accent_bg; border-color: @accent_bg;
}

/* ---------- buttons ---------- */
QPushButton { background: @card; border: 1px solid @border; border-radius: 4px;
              padding: 6px 12px; color: @text; }
QPushButton:hover { background: @alt_row; }
QPushButton#primary { background: @accent_bg; border-color: @accent_bg;
                      color: @on_accent; font-weight: 600; }
QPushButton#primary:hover { background: @accent; border-color: @accent; }
QPushButton#flat { background: transparent; color: @dim; }
QPushButton#danger { background: transparent; border-color: @bad; color: @bad; }
QPushButton#danger:hover { background: @card; }
QPushButton#danger:disabled { color: @faint; border-color: @border; }

/* ---------- chrome ---------- */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: @bg; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: @scroll; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: @scroll_hover; }
QScrollBar:horizontal { background: @bg; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: @scroll; min-width: 28px; border-radius: 4px; }
QScrollBar::handle:horizontal:hover { background: @scroll_hover; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QStatusBar { background: @panel; border-top: 1px solid @border;
             color: @faint; font-size: 11px; }
QStatusBar::item { border: none; }
QLabel#statusStats { background: transparent; color: @faint; font-size: 11px; }
QSplitter::handle { background: @border; width: 1px; }

/* ---------- picker pages (brand / bracket card grid) ---------- */
QFrame#groupHead { background: transparent; border: none;
                   border-bottom: 1px solid @border; }
QLabel#groupDot { background: transparent; border: 2px solid @accent;
                  border-radius: 9px; color: @accent; font-size: 9px; }
QLabel#groupLabel { background: transparent; color: @faint; font-size: 13px; }
QLabel#groupLetter { background: transparent; color: @accent;
                     font-size: 19px; font-weight: 600; }
QLabel#groupTitle { background: transparent; color: @text; font-size: 15px; }
QFrame#pickCard { background: @card; border: 1px solid @border; border-radius: 4px; }
QFrame#pickCard:hover { background: @alt_row; border-color: @accent; }
QFrame#pickCardSel { background: @sel_bg; border: 1px solid @accent;
                     border-radius: 4px; }
QLabel#pickLogo { background: @input; border: 1px solid @border;
                  border-radius: 2px; color: @faint; font-size: 12px; }
QLabel#pickBullet { background: @scroll; border: none; border-radius: 5px; }
QLabel#pickName { background: transparent; color: @text; font-size: 14px; }
QLabel#pickMeta { background: transparent; color: @faint; font-size: 11px; }

/* ---------- in-place edit feedback ---------- */
QLabel#errBar { background: @card; border: none; border-left: 3px solid @bad;
                color: @bad; font-size: 12px; padding: 0 12px; }

/* ---------- record edit dialog ---------- */
QDialog { background: @bg; }
QLabel#dialogTitle { background: transparent; color: @text;
                     font-size: 15px; font-weight: 600; }
QLabel#dialogSub { background: transparent; color: @faint; font-size: 12px; }
QLabel#dialogHint { background: transparent; color: @faint; font-size: 11px; }
QLabel#dialogError { background: transparent; color: @bad; font-size: 11px; }

/* ---------- empty state ---------- */
QLabel#emptyBox { background: transparent; border: 1px dashed @border; border-radius: 6px;
                  color: @faint; font-size: 11px; }
QLabel#emptyTitle { color: @dim; font-size: 15px; }
QLabel#emptyText { color: @faint; font-size: 12px; }
"""


def stylesheet(theme_name: str = None) -> str:
    """Render the QSS for a theme (defaults to the active one)."""
    palette = config.PALETTES[theme_name or config.current_theme()]
    qss = _QSS
    # longest token first: "@accent_bg" must win over "@accent"
    for token in sorted(palette, key=len, reverse=True):
        qss = qss.replace("@" + token, palette[token])
    return qss

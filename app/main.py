# -*- coding: utf-8 -*-
"""Entry point of the KY bracket desktop application (PySide6)."""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

import config
import db
import search
import theme
import ui
from pages.add_page import AddPage
from pages.bracket_page import BracketPage
from pages.bracket_pick_page import BracketPickerPage
from pages.brand_page import BrandPickerPage
from pages.model_page import ModelPage

VIEW_LABELS = ("按车型查", "按支架查", "品牌", "车架", "新增")
# 启动后默认显示的页面（按标签定位，避免写死索引；用户 2026-10-28 指定为品牌页）
DEFAULT_VIEW = "品牌"
# 导航栏不露出的页面（2026-10-28 用户要求）：结果页只从品牌 / 车架卡片进入，
# 页面本身留在 stack 里，索引与 Ctrl+1~5 都不变。
HIDDEN_VIEWS = ("按车型查", "按支架查")
# 顶栏全局搜索是否显示（2026-10-28 用户要求隐藏）
SHOW_GLOBAL_SEARCH = False


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings = None):
        super().__init__()
        self.settings = settings or QSettings()
        self.repo = db.Repository()
        self._search_index = None
        self._status_label = None
        self.setWindowTitle("%s · %s" % (config.APP_NAME, config.APP_SUBTITLE))
        self.resize(1280, 800)
        self.setMinimumSize(1120, 700)

        self._build_top_bar()
        self._build_pages()
        self._build_status()
        self._build_shortcuts()
        self._connect_pages()

    # ---------- layout ----------
    def _build_top_bar(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(52)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(10)

        title = QLabel(config.APP_NAME)
        title.setObjectName("appTitle")
        row.addWidget(title)
        sub = QLabel(config.APP_SUBTITLE)
        sub.setObjectName("appSub")
        row.addWidget(sub)
        row.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("全局搜索：车型 / 支架号 / 品牌（支持拼音）")
        self.search.setFixedWidth(320)
        self.search.returnPressed.connect(self.do_search)
        # 2026-10-28 用户要求：顶栏全局搜索隐藏（各页都有自己的筛选/搜索框）。
        # 控件与 do_search / 补全逻辑都保留，只是不显示，随时可以打开。
        self.search.setVisible(SHOW_GLOBAL_SEARCH)
        row.addWidget(self.search)
        ui.attach_completer(self.search, provider=self.search_suggestions,
                            limit=12, on_pick=self.pick_suggestion)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, label in enumerate(VIEW_LABELS):
            button = QPushButton(label)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(button, index)
            row.addWidget(button)
            button.setVisible(label not in HIDDEN_VIEWS)
            self.nav_buttons.append(button)
        self.nav_group.idClicked.connect(self.set_view)

        self.theme_btn = QPushButton()
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        row.addWidget(self.theme_btn)
        self._sync_theme_button()

        layout.addWidget(bar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _build_pages(self) -> None:
        self.model_page = ModelPage(self.repo)
        self.bracket_page = BracketPage(self.repo)
        self.brand_page = BrandPickerPage(self.repo)
        self.bracket_pick_page = BracketPickerPage(self.repo)
        self.add_page = AddPage(self.repo)
        for page in (self.model_page, self.bracket_page, self.brand_page,
                     self.bracket_pick_page, self.add_page):
            self.stack.addWidget(page)
        self.set_view(VIEW_LABELS.index(DEFAULT_VIEW))

    def _build_status(self) -> None:
        """Keep the statistics in a permanent widget, not in showMessage().

        A ``showMessage(text, timeout)`` (copy notice, failed search) replaces
        the whole left area and clears it when it expires — the counters would
        never come back. Permanent widgets sit in their own slot and survive.
        """
        stats = self.repo.stats()
        stamp = datetime.fromtimestamp(stats["db_mtime"]).strftime("%Y-%m-%d %H:%M")
        text = ("支架 %d · 品牌 %d · 车型 %d · 数据时间 %s"
                % (stats["brackets"], stats["brands"], stats["models"], stamp))
        if self._status_label is None:
            self._status_label = QLabel(text)
            self._status_label.setObjectName("statusStats")
            self.statusBar().addPermanentWidget(self._status_label)
        else:
            self._status_label.setText(text)

    def _build_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.set_view(0))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.set_view(1))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self.set_view(2))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self.set_view(3))
        QShortcut(QKeySequence("Ctrl+5"), self, activated=lambda: self.set_view(4))

    def _connect_pages(self) -> None:
        self.model_page.open_bracket.connect(self.open_bracket_page)
        self.add_page.saved.connect(self.on_data_changed)
        self.brand_page.brand_chosen.connect(self.open_brand_models)
        self.bracket_pick_page.bracket_chosen.connect(self.open_bracket_page)

    def on_data_changed(self, _result=None) -> None:
        """After a manual save: drop the search index and refresh every page."""
        self._search_index = None
        self._build_status()
        self.model_page.refresh_data()
        self.bracket_page.refresh_data()
        self.brand_page.refresh_data()
        self.bracket_pick_page.refresh_data()

    def on_records_changed(self) -> None:
        """After a record edit / delete: only counts move, not the dictionaries.

        The two query pages reran their own query already; both card pages take
        the cheap path that rewrites the badge text, and fall back to a full
        rebuild only when a brand / bracket was actually added or removed.
        """
        self._search_index = None
        self._build_status()
        self.brand_page.refresh_if_changed()
        self.bracket_pick_page.refresh_if_changed()

    # ---------- navigation ----------
    def set_view(self, index: int) -> None:
        index = max(0, min(len(VIEW_LABELS) - 1, index))
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def open_bracket_page(self, bracket_id: str) -> None:
        if not bracket_id:
            return
        self.set_view(1)
        self.bracket_page.focus_bracket(bracket_id)

    def open_brand_models(self, brand: str) -> None:
        """Brand card picked: jump to 「按车型查」 with that brand prefilled."""
        if not brand:
            return
        self.set_view(0)
        self.model_page.focus_model(brand, "")

    def open_model_page(self, brand: str, model: str) -> None:
        self.set_view(0)
        self.model_page.focus_model(brand, model)

    def index(self) -> dict:
        """Memory index for the global search (built once, pinyin aware)."""
        if self._search_index is None:
            brands = [row["brand"] for row in self.repo.brands()]
            model_brand = {}
            for brand in brands:
                for model in self.repo.models(brand):
                    model_brand.setdefault(model, brand)
            self._search_index = {
                "brands": brands,
                "models": list(model_brand.keys()),
                "model_brand": model_brand,
                "brackets": self.repo.bracket_ids(),
            }
        return self._search_index

    def search_suggestions(self) -> list:
        """Candidates shown in the global search popup (bracket -> model -> brand)."""
        index = self.index()
        return index["brackets"] + index["models"] + index["brands"]

    def pick_suggestion(self, text: str) -> None:
        self.search.setText(text)
        self.do_search()

    def do_search(self) -> None:
        """Global search: bracket id -> model -> brand, literal or pinyin."""
        text = self.search.text().strip()
        if not text:
            return
        index = self.index()
        brackets = search.filter_items(index["brackets"], text, 10)
        if brackets:
            self.open_bracket_page(brackets[0])
            return
        models = search.filter_items(index["models"], text, 10)
        if models:
            self.open_model_page(index["model_brand"].get(models[0], ""), models[0])
            return
        brands = search.filter_items(index["brands"], text, 10)
        if brands:
            self.set_view(0)
            self.model_page.focus_model(brands[0], "")
            return
        self.statusBar().showMessage(
            "未找到「%s」——可试中文、全拼（aodi）或首字母（ad）" % text, 6000)

    # ---------- theme ----------
    def _sync_theme_button(self) -> None:
        self.theme_btn.setText(config.THEME_LABELS[config.current_theme()])

    def toggle_theme(self) -> None:
        """Switch dark/light in place and remember the choice."""
        target = config.next_theme()
        config.set_theme(target)
        QApplication.instance().setStyleSheet(theme.stylesheet(target))
        self.settings.setValue("ui/theme", target)
        self._sync_theme_button()
        for page in (self.model_page, self.bracket_page, self.add_page):
            if hasattr(page, "refresh_theme"):
                page.refresh_theme()

    def closeEvent(self, event):
        self.repo.close()
        super().closeEvent(event)


def main() -> int:
    if not os.path.exists(config.DB_PATH):
        app = QApplication(sys.argv)
        QMessageBox.critical(None, config.APP_NAME,
                             "数据库不存在：\n%s\n\n请先运行爬虫抓取数据。" % config.DB_PATH)
        return 1
    app = QApplication(sys.argv)
    app.setOrganizationName("KY")
    app.setApplicationName(config.APP_NAME)
    settings = QSettings()
    config.set_theme(str(settings.value("ui/theme", config.DEFAULT_THEME)))
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

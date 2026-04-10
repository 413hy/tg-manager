"""Main window shell for Milestone 1.

Contains only static layout elements:
- Left navigation list
- Accounts table area
- Bottom log console
- Status bar
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import AppContext
from app.config.constants import APP_NAME, APP_VERSION
from app.ui.navigation.left_menu import LeftMenu


class MainWindow(QMainWindow):
    def __init__(self, app_context: AppContext) -> None:
        super().__init__()
        self.app_context = app_context
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - Milestone 1")
        self.resize(1280, 800)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QHBoxLayout(root)

        splitter = QSplitter()
        root_layout.addWidget(splitter)

        self.left_menu = LeftMenu()
        splitter.addWidget(self.left_menu)

        center = QWidget()
        center_layout = QVBoxLayout(center)

        center_layout.addWidget(QLabel("Accounts Inventory"))

        self.accounts_table = QTableWidget(0, 8)
        self.accounts_table.setHorizontalHeaderLabels(
            [
                "#",
                "Phone",
                "Banned",
                "Network",
                "Auth",
                "Restricted",
                "Display Name",
                "Proxy",
            ]
        )
        center_layout.addWidget(self.accounts_table)

        center_layout.addWidget(QLabel("Runtime Log Console"))
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setPlaceholderText("Live logs will appear here in later milestones.")
        center_layout.addWidget(self.log_console)

        splitter.addWidget(center)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        self.setCentralWidget(root)
        self.statusBar().showMessage(f"Database: {self.app_context.settings.database_path}")
        self._seed_placeholder_row()

    def _seed_placeholder_row(self) -> None:
        """Add one static row to make table framing visible in milestone 1."""
        row = self.accounts_table.rowCount()
        self.accounts_table.insertRow(row)
        placeholder = [
            "1",
            "+15550000000",
            "No",
            "Disconnected",
            "Unauthorized",
            "No",
            "Sample Account",
            "None",
        ]
        for col, value in enumerate(placeholder):
            self.accounts_table.setItem(row, col, QTableWidgetItem(value))

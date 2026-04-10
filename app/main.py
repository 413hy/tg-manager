"""Application entry point for Milestone 1 UI shell."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.bootstrap import bootstrap_app
from app.ui.main_window import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Telegram Account Manager (Milestone 1)")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the UI briefly and exit automatically (used for CI/local smoke tests).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_context = bootstrap_app()

    qt_app = QApplication(sys.argv)
    window = MainWindow(app_context)
    window.show()

    if args.smoke_test:
        QTimer.singleShot(800, qt_app.quit)

    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

import sys

from app.ui.qt import QApplication

from app.bootstrap import build_container
from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    container = build_container()

    window = MainWindow(
        repo=container.repo,
        account_service=container.account_service,
        logger=container.logger,
    )
    window.show()
    window.bootstrap()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

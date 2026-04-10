from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit


class LogConsoleWidget(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)

    def append_line(self, text: str) -> None:
        self.append(text)
        self.moveCursor(QTextCursor.End)

from app.ui.qt import QTextCursor, QTextEdit


class LogConsoleWidget(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)

    def append_line(self, text: str) -> None:
        self.append(text)
        end_op = getattr(QTextCursor, "End", None)
        if end_op is None and hasattr(QTextCursor, "MoveOperation"):
            end_op = QTextCursor.MoveOperation.End
        self.moveCursor(end_op)

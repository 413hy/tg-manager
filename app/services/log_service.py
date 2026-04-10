from collections.abc import Callable
from datetime import datetime


class LogService:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[str], None]] = []

    def subscribe(self, callback: Callable[[str], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, level: str, module: str, message: str) -> str:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] [{module}] {message}"
        for callback in self._subscribers:
            callback(line)
        return line

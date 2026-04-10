"""Left-side navigation used by the shell UI."""

from PySide6.QtWidgets import QListWidget


class LeftMenu(QListWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(220)
        self.addItems(
            [
                "Registration/Login",
                "Account Dashboard",
                "Proxy Management",
                "Profile Management",
                "Batch Operations",
                "Global Settings",
                "License / Activation",
            ]
        )

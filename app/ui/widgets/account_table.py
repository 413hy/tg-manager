from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class AccountTableWidget(QTableWidget):
    HEADERS = ["ID", "Phone", "Display Name", "Status", "Last Seen"]

    def __init__(self) -> None:
        super().__init__(0, len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setAlternatingRowColors(True)

    def load_rows(self, rows: list[dict]) -> None:
        self.setRowCount(0)
        for row in rows:
            idx = self.rowCount()
            self.insertRow(idx)
            self.setItem(idx, 0, QTableWidgetItem(str(row["id"])))
            self.setItem(idx, 1, QTableWidgetItem(row["phone"]))
            self.setItem(idx, 2, QTableWidgetItem(row.get("display_name") or ""))
            self.setItem(idx, 3, QTableWidgetItem(row.get("status") or "unknown"))
            self.setItem(idx, 4, QTableWidgetItem(row.get("last_seen") or "-"))

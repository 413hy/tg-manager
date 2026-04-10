from app.ui.qt import Qt
from app.ui.qt import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.services.account_service import AccountService
from app.services.log_service import LogService
from app.infra.sqlite_repo import SQLiteRepository
from app.ui.widgets.account_table import AccountTableWidget
from app.ui.widgets.log_console import LogConsoleWidget


class MainWindow(QMainWindow):
    def __init__(self, repo: SQLiteRepository, account_service: AccountService, logger: LogService) -> None:
        super().__init__()
        self.repo = repo
        self.account_service = account_service
        self.logger = logger

        self.setWindowTitle("TG Manager - M1")
        self.resize(1200, 760)

        self.account_table = AccountTableWidget()
        self.log_console = LogConsoleWidget()
        self.logger.subscribe(self.log_console.append_line)

        self._build_layout()
        self._bind_actions()

    def _build_layout(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        top_bar = QHBoxLayout()

        self.poll_once_btn = QPushButton("轮询账号状态(一次)")
        self.refresh_btn = QPushButton("刷新表格")
        top_bar.addWidget(self.poll_once_btn)
        top_bar.addWidget(self.refresh_btn)
        top_bar.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        upper_layout.addWidget(self._build_proxy_panel(), 2)
        upper_layout.addWidget(self.account_table, 8)

        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.addWidget(QLabel("实时操作终端日志"))
        lower_layout.addWidget(self.log_console)

        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setSizes([420, 260])

        main_layout.addLayout(top_bar)
        main_layout.addWidget(splitter)

    def _build_proxy_panel(self) -> QGroupBox:
        box = QGroupBox("代理配置")
        form = QFormLayout(box)

        self.proxy_type = QLineEdit("SOCKS5")
        self.proxy_host = QLineEdit("127.0.0.1")
        self.proxy_port = QLineEdit("1080")
        self.proxy_user = QLineEdit()
        self.proxy_pass = QLineEdit()
        self.proxy_test_btn = QPushButton("测试代理")

        form.addRow("类型", self.proxy_type)
        form.addRow("主机", self.proxy_host)
        form.addRow("端口", self.proxy_port)
        form.addRow("用户名", self.proxy_user)
        form.addRow("密码", self.proxy_pass)
        form.addRow(self.proxy_test_btn)

        return box

    def _bind_actions(self) -> None:
        self.poll_once_btn.clicked.connect(self.poll_once)
        self.refresh_btn.clicked.connect(self.reload_accounts)
        self.proxy_test_btn.clicked.connect(self.test_proxy)

    def bootstrap(self) -> None:
        self.account_service.ensure_seed_data()
        self.poll_once()

    def poll_once(self) -> None:
        self.account_service.poll_account_status_once()
        self.reload_accounts()

    def reload_accounts(self) -> None:
        rows = [dict(item) for item in self.repo.list_accounts()]
        self.account_table.load_rows(rows)
        self.logger.emit("INFO", "UI", f"Account table refreshed with {len(rows)} rows")

    def test_proxy(self) -> None:
        proxy = f"{self.proxy_type.text()}://{self.proxy_host.text()}:{self.proxy_port.text()}"
        self.logger.emit("INFO", "ProxyService", f"Proxy test requested: {proxy} (M1 mock)")

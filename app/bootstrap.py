from app.config import DB_PATH, ensure_runtime_dirs
from app.infra.sqlite_repo import SQLiteRepository
from app.services.account_service import AccountService
from app.services.log_service import LogService


class AppContainer:
    def __init__(self) -> None:
        ensure_runtime_dirs()

        self.repo = SQLiteRepository(DB_PATH)
        self.repo.init_schema()

        self.logger = LogService()
        self.account_service = AccountService(self.repo, self.logger)


def build_container() -> AppContainer:
    return AppContainer()

from datetime import datetime, timezone

from app.infra.sqlite_repo import SQLiteRepository
from app.services.log_service import LogService


class AccountService:
    def __init__(self, repo: SQLiteRepository, logger: LogService) -> None:
        self.repo = repo
        self.logger = logger

    def ensure_seed_data(self) -> None:
        if self.repo.list_accounts():
            return
        demo_phones = ["+10000000001", "+10000000002", "+10000000003"]
        for phone in demo_phones:
            self.repo.create_account(phone=phone)
        self.logger.emit("INFO", "AccountService", "Initialized demo accounts for M1 preview")

    def poll_account_status_once(self) -> None:
        accounts = self.repo.list_accounts()
        now = datetime.now(timezone.utc).isoformat()
        if not accounts:
            self.logger.emit("INFO", "AccountService", "No accounts to poll")
            return

        for row in accounts:
            # M1 阶段使用占位状态，M2+ 接入 Telethon 真实在线检测
            new_status = "ready"
            self.repo.update_account_status(account_id=row["id"], status=new_status, last_seen=now)
            self.logger.emit(
                "INFO",
                "AccountService",
                f"Polled account {row['phone']} status={new_status}",
            )

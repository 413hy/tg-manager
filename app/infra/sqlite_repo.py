import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class SQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    display_name TEXT,
                    status TEXT DEFAULT 'unknown',
                    proxy_id INTEGER,
                    session_path TEXT,
                    last_seen TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    password TEXT,
                    is_valid INTEGER DEFAULT 0,
                    last_check_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS app_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    account_id INTEGER,
                    module TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def list_accounts(self) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT id, phone, display_name, status, last_seen FROM accounts ORDER BY id"
            ).fetchall()

    def create_account(self, phone: str, display_name: str = "") -> int:
        with self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO accounts(phone, display_name) VALUES(?, ?)",
                (phone, display_name),
            )
            return int(cur.lastrowid)

    def update_account_status(self, account_id: int, status: str, last_seen: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE accounts
                SET status = ?,
                    last_seen = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, last_seen, account_id),
            )

    def append_log(self, level: str, module: str, message: str, account_id: int | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO app_logs(level, account_id, module, message) VALUES(?, ?, ?, ?)",
                (level, account_id, module, message),
            )

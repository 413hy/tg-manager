from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class AccountStore:
    PUBLIC_COLUMNS = (
        "id",
        "phone_e164",
        "country",
        "country_code",
        "local_phone",
        "status",
        "is_banned",
        "has_restrictions",
        "restriction_note",
        "status_checked_at",
        "switch_index",
        "added_by_chat_id",
        "added_by_user_id",
        "created_at",
        "updated_at",
        "last_login_at",
        "last_seen_at",
    )

    def __init__(self, db_path: str) -> None:
        self.path = Path(db_path)
        if self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.path))
        con.row_factory = sqlite3.Row
        return con

    @classmethod
    def _public_row(cls, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        return {key: data.get(key) for key in cls.PUBLIC_COLUMNS if key in data}

    def init_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_e164 TEXT NOT NULL UNIQUE,
                    country TEXT NOT NULL DEFAULT '',
                    country_code TEXT NOT NULL DEFAULT '',
                    local_phone TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'unknown',
                    is_banned INTEGER NOT NULL DEFAULT 0,
                    has_restrictions INTEGER NOT NULL DEFAULT 0,
                    restriction_note TEXT NOT NULL DEFAULT '',
                    status_checked_at TEXT,
                    switch_index INTEGER,
                    added_by_chat_id INTEGER,
                    added_by_user_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login_at TEXT,
                    last_seen_at TEXT
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_accounts_switch_index ON accounts(switch_index)")
            self._ensure_column(con, "accounts", "status_checked_at", "TEXT")
            con.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_accounts_updated_at
                AFTER UPDATE ON accounts
                FOR EACH ROW
                BEGIN
                    UPDATE accounts SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
                END
                """
            )

    @staticmethod
    def _ensure_column(con: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def normalize_phone(country_code: str, local_phone: str) -> str:
        code = "".join(ch for ch in country_code if ch.isdigit())
        phone = "".join(ch for ch in local_phone if ch.isdigit())
        return f"+{code}{phone}" if code else phone

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat(sep=" ")

    def upsert_account(
        self,
        *,
        country: str = "",
        country_code: str = "",
        local_phone: str = "",
        phone_e164: Optional[str] = None,
        status: Optional[str] = None,
        is_banned: Optional[bool] = None,
        has_restrictions: Optional[bool] = None,
        restriction_note: Optional[str] = None,
        switch_index: Optional[int] = None,
        added_by_chat_id: Optional[int] = None,
        added_by_user_id: Optional[int] = None,
        mark_login: bool = False,
        mark_seen: bool = False,
        mark_status_checked: bool = False,
    ) -> dict[str, Any]:
        phone = phone_e164 or self.normalize_phone(country_code, local_phone)
        if not phone:
            raise ValueError("phone_e164 or country_code/local_phone is required")

        with self._connect() as con:
            existing = con.execute("SELECT * FROM accounts WHERE phone_e164 = ?", (phone,)).fetchone()
            if existing:
                data = dict(existing)
                updates: dict[str, Any] = {}
                for key, value in {
                    "country": country,
                    "country_code": country_code,
                    "local_phone": local_phone,
                    "status": status,
                    "restriction_note": restriction_note,
                    "switch_index": switch_index,
                    "added_by_chat_id": added_by_chat_id,
                    "added_by_user_id": added_by_user_id,
                }.items():
                    if value is not None and value != "":
                        updates[key] = value
                if is_banned is not None:
                    updates["is_banned"] = int(is_banned)
                if has_restrictions is not None:
                    updates["has_restrictions"] = int(has_restrictions)
                if mark_login:
                    updates["last_login_at"] = "CURRENT_TIMESTAMP"
                if mark_seen:
                    updates["last_seen_at"] = "CURRENT_TIMESTAMP"
                if mark_status_checked:
                    updates["status_checked_at"] = "CURRENT_TIMESTAMP"

                if updates:
                    assignments = []
                    params = []
                    for key, value in updates.items():
                        if value == "CURRENT_TIMESTAMP":
                            assignments.append(f"{key} = CURRENT_TIMESTAMP")
                        else:
                            assignments.append(f"{key} = ?")
                            params.append(value)
                    params.append(phone)
                    con.execute(f"UPDATE accounts SET {', '.join(assignments)} WHERE phone_e164 = ?", params)
                row = con.execute("SELECT * FROM accounts WHERE phone_e164 = ?", (phone,)).fetchone()
                return self._public_row(row)

            if switch_index is None:
                max_index = con.execute("SELECT MAX(switch_index) FROM accounts").fetchone()[0]
                switch_index = 0 if max_index is None else int(max_index) + 1

            con.execute(
                """
                INSERT INTO accounts (
                    phone_e164, country, country_code, local_phone,
                    status, is_banned, has_restrictions, restriction_note, status_checked_at, switch_index,
                    added_by_chat_id, added_by_user_id, last_login_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    phone,
                    country,
                    country_code,
                    local_phone,
                    status or "unknown",
                    int(is_banned or False),
                    int(has_restrictions or False),
                    restriction_note or "",
                    self._now() if mark_status_checked else None,
                    switch_index,
                    added_by_chat_id,
                    added_by_user_id,
                    self._now() if mark_login else None,
                    self._now() if mark_seen else None,
                ),
            )
            row = con.execute("SELECT * FROM accounts WHERE phone_e164 = ?", (phone,)).fetchone()
            return self._public_row(row)

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM accounts ORDER BY switch_index IS NULL, switch_index, id"
            ).fetchall()
            return [self._public_row(row) for row in rows]

    def get_account(self, phone_e164: str) -> Optional[dict[str, Any]]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM accounts WHERE phone_e164 = ?", (phone_e164,)).fetchone()
            return self._public_row(row) if row else None

    def delete_account(self, phone_e164: str) -> bool:
        with self._connect() as con:
            cur = con.execute("DELETE FROM accounts WHERE phone_e164 = ?", (phone_e164,))
            return cur.rowcount > 0

    def update_account(self, phone_e164: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        allowed = {
            "status",
            "is_banned",
            "has_restrictions",
            "restriction_note",
            "status_checked_at",
            "switch_index",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_account(phone_e164)
        assignments = ", ".join(f"{k} = ?" for k in updates)
        with self._connect() as con:
            con.execute(f"UPDATE accounts SET {assignments} WHERE phone_e164 = ?", [*updates.values(), phone_e164])
            row = con.execute("SELECT * FROM accounts WHERE phone_e164 = ?", (phone_e164,)).fetchone()
            return self._public_row(row) if row else None

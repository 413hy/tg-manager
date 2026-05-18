#!/usr/bin/env python3
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AccountStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT,
                  telegram_user_id TEXT,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  status TEXT NOT NULL,
                  source TEXT NOT NULL DEFAULT 'telegram_x_redroid',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  last_seen_at TEXT,
                  raw_profile TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phone TEXT,
                  status TEXT NOT NULL,
                  message TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(telegram_user_id)")

    def record_event(self, phone: str | None, status: str, message: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO login_events(phone, status, message, created_at) VALUES (?, ?, ?, ?)",
                (phone, status, message, utc_now()),
            )

    def upsert_account(self, profile: dict[str, Any], phone: str | None, status: str = "logged_in") -> None:
        now = utc_now()
        tg_id = str(profile.get("telegram_user_id") or "")
        username = profile.get("username") or ""
        first_name = profile.get("first_name") or ""
        last_name = profile.get("last_name") or ""
        raw = profile.get("raw_profile") or ""
        with self.connect() as conn:
            row = None
            if tg_id:
                row = conn.execute("SELECT id FROM accounts WHERE telegram_user_id = ?", (tg_id,)).fetchone()
            if row is None and phone:
                row = conn.execute("SELECT id FROM accounts WHERE phone = ?", (phone,)).fetchone()

            if row:
                conn.execute(
                    """
                    UPDATE accounts
                       SET phone = COALESCE(NULLIF(?, ''), phone),
                           telegram_user_id = COALESCE(NULLIF(?, ''), telegram_user_id),
                           username = ?,
                           first_name = ?,
                           last_name = ?,
                           status = ?,
                           updated_at = ?,
                           last_seen_at = ?,
                           raw_profile = ?
                     WHERE id = ?
                    """,
                    (phone or "", tg_id, username, first_name, last_name, status, now, now, raw, row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO accounts(
                      phone, telegram_user_id, username, first_name, last_name, status,
                      created_at, updated_at, last_seen_at, raw_profile
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (phone, tg_id, username, first_name, last_name, status, now, now, now, raw),
                )

    def list_accounts(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT id, phone, telegram_user_id, username, first_name, last_name, status, last_seen_at
                      FROM accounts
                     ORDER BY updated_at DESC, id DESC
                     LIMIT ?
                    """,
                    (limit,),
                )
            )

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM accounts GROUP BY status").fetchall()
        data = {row["status"]: int(row["cnt"]) for row in rows}
        data["total"] = sum(data.values())
        return data

    def last_login_phone(self) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT phone
                  FROM login_events
                 WHERE phone IS NOT NULL AND phone != ''
                 ORDER BY id DESC
                 LIMIT 1
                """
            ).fetchone()
        return row["phone"] if row else None

"""SQLite engine and schema bootstrap for milestone 1."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    """Minimal SQLite database wrapper for initialization and connections."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize_schema(self) -> None:
        """Create milestone-1 core tables if they do not exist."""
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    phone TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    network_status TEXT DEFAULT 'UNKNOWN',
                    auth_status TEXT DEFAULT 'UNAUTHORIZED',
                    is_banned INTEGER DEFAULT 0,
                    proxy_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS proxies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    password_encrypted BLOB,
                    is_enabled INTEGER DEFAULT 1,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    account_id TEXT,
                    session_type TEXT,
                    session_path TEXT,
                    encrypted_session_blob BLOB,
                    authorized INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(account_id) REFERENCES accounts(id)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    source_module TEXT,
                    account_id TEXT,
                    message TEXT NOT NULL,
                    details_json TEXT,
                    occurred_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

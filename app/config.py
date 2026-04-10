from pathlib import Path

APP_NAME = "TG Manager"
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
SESSION_DIR = BASE_DIR / "sessions"
DB_PATH = DATA_DIR / "app.db"


def ensure_runtime_dirs() -> None:
    for path in (DATA_DIR, LOG_DIR, SESSION_DIR):
        path.mkdir(parents=True, exist_ok=True)

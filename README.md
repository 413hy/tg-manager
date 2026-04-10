# tg-manager

Milestone M1 implementation for a Windows desktop Telegram manager panel.

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python -m app.main
```

## Troubleshooting (Windows)

If your environment still fails to install pinned PySide6 wheels, install PyQt6 and run the app with the same codebase (the project has a Qt compatibility layer):

```bash
pip install PyQt6
python -m app.main
```

## Implemented in M1

- Project skeleton based on `app/ui/services/infra` layering.
- SQLite initialization for `accounts`, `proxies`, `app_logs`.
- Main dashboard UI with:
  - account status table,
  - proxy configuration panel,
  - real-time log console.
- Startup behavior: seed demo accounts and poll account status once.

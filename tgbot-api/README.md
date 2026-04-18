# tgbot-api

Modular Telegram X automation control plane.

## Goals
- Detect current Telegram X page from UI XML (not fixed flow-only).
- Route to per-page action modules.
- Expose HTTP API for external orchestration.
- Expose Telegram bot commands as a lightweight remote controller.

## Quick start
```bash
cd tgbot-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn tgx_automation.api.main:app --host 0.0.0.0 --port 8080
```

## Main endpoints
- `GET /health`
- `GET /state`
- `POST /actions/login/start`
- `POST /actions/login/submit-code`
- `POST /actions/login/submit-password`
- `POST /actions/username`
- `POST /actions/name`
- `POST /actions/recover-home`
- `POST /router/step`

## Notes
- This project is designed for redroid + ADB usage.
- Unknown pages do not hard-fail by default; router can attempt interstitial handling or home recovery.

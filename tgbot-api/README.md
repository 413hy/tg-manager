# tgbot-api

Telegram X account login and registration control plane.

This directory is now intentionally scoped to one job: add/login Telegram X
accounts through redroid + ADB, then record the resulting account status in
SQLite. Account profile/configuration tooling is outside this project scope.

## Quick Start

```bash
cd tgbot-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn tgx_automation.api.main:app --host 0.0.0.0 --port 8080
```

## Environment

```bash
ADB_SERIAL=127.0.0.1:5555
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
TGX_DB_PATH=tgx_automation.sqlite3
REDROID_NAME=redroid12
```

Do not commit real bot tokens, passwords, phone verification codes, or account
secrets.

## HTTP API

The API keeps only login/registration and minimal state endpoints:

- `GET /health`
- `GET /ui`
- `GET /state`
- `GET /accounts`
- `POST /router/step`
- `POST /router/auto`
- `POST /actions/handle-interstitials`
- `POST /actions/recover-home`
- `POST /actions/account/switch`
- `POST /actions/add-account/open`
- `POST /actions/login/next`
- `POST /actions/login/start`
- `POST /actions/login/submit-next`
- `POST /actions/login/submit-code`
- `POST /actions/login/submit-password`

The login flow is page-driven. `GET /state` and `POST /actions/login/next`
return `login_requirement`:

- `phone`: submit dial code and local phone.
- `code`: submit Telegram login code.
- `password`: submit 2FA password required by Telegram login.
- `email_or_email_code`: submit whatever email value Telegram X is asking for.
- `inspect`: unknown page; inspect `state.excerpt`.

## Account Database

The SQLite database is initialized automatically. The active fields for this
scope are:

- `phone_e164`, `country`, `country_code`, `local_phone`
- `status`
- `is_banned`, `has_restrictions`, `restriction_note`
- `switch_index`
- `added_by_chat_id`, `added_by_user_id`
- `created_at`, `updated_at`, `last_login_at`, `last_seen_at`

Older databases may still contain columns from previous broader builds; the
current API and bot no longer use those fields.

## Telegram Bot

Supported commands:

- `/add_account` asks the user to share their own phone number and starts the
  Telegram X add-account flow.
- `/users` lists accounts visible to the caller. Admins see all accounts.
- `/switch <phone_or_index>` switches Telegram X to a stored account.
- `/state` returns the current Telegram X detector state and key page elements.
- `/recover` restarts Telegram X back toward the home/chat-list state.
- `/cancel` clears the in-memory pending login flow for that chat.
- `/whoami` returns the Telegram user id and admin status.

During login, users can send the verification code or 2FA password directly
without `/code` or `/password`. Those command forms still work as aliases for
compatibility.

When a non-admin user adds an account, the bot records source metadata and
notifies configured admins.

## Checks

```bash
python3 -m compileall tgx_automation
git diff --check
```

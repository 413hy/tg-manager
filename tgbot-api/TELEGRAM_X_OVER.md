# Telegram X Login Scope

This branch now keeps only the Telegram X account add/login workflow.

All non-login account configuration and account-operation helpers were removed.

The remaining code is focused on running Telegram X in redroid, opening Add
Account, submitting the phone number, and continuing through whatever login
input Telegram X requests next.

## Runtime

Entry points:

- FastAPI API and web page: `tgx_automation.api.main:app`
- Telegram bot polling runner: `tgx_automation.bot.telegram_bot`

Required environment:

```bash
ADB_SERIAL=127.0.0.1:5555
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
TGX_DB_PATH=tgx_automation.sqlite3
REDROID_NAME=redroid12
```

## Web UI

Open:

```text
/ui
```

The page supports:

- listing stored accounts
- switching to a stored account by `switch_index`
- reading current Telegram X page state
- recovering Telegram X toward the home page
- opening Add Account
- submitting phone number
- submitting the current page's requested value
- submitting code and 2FA password shortcuts
- printing raw operation logs

## Login Flow

Use:

- `POST /actions/add-account/open`
- `POST /actions/login/next`
- `POST /actions/login/start`
- `POST /actions/login/submit-next`
- `POST /actions/login/submit-code`
- `POST /actions/login/submit-password`

`/actions/login/next` and `/state` return `login_requirement`:

- `phone`: needs dial code and local phone.
- `code`: needs Telegram login code.
- `password`: needs Telegram login 2FA password.
- `email_or_email_code`: needs the email value requested by Telegram X.
- `inspect`: unknown page; inspect `state.excerpt`.

When Telegram X reaches an active page after login, the account is marked
`active` and login metadata is written to SQLite. Failed or unfinished login
attempts are not marked active.

## Bot Commands

- `/add_account`
- `/users`
- `/switch <phone_or_index>`
- `/state`
- `/recover`
- `/cancel`
- `/whoami`

During a pending login, users can send codes/passwords directly. `/code <value>`
and `/password <value>` remain aliases only for compatibility.

## Database

The current login scope uses:

- phone number fields
- status
- ban/restriction flags
- Telegram X switch index
- source Telegram user/chat ids
- timestamps

Extra columns from older local databases are ignored.

## Checks

```bash
python3 -m compileall tgx_automation
git diff --check
```

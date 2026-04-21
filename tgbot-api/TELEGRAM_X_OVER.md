# Telegram X Over Notes

This document records the Telegram X account-management work in this branch.

## Runtime

The service has two entry points:

- FastAPI control plane: `tgx_automation.api.main:app`
- Telegram bot polling runner: `tgx_automation.bot.telegram_bot`

Required environment:

```bash
ADB_SERIAL=127.0.0.1:5555
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_IDS=
TGX_DB_PATH=tgx_automation.sqlite3
```

Do not commit real bot tokens, passwords, phone verification codes, or account secrets.

## Web UI

Open the dashboard at:

```text
/ui
```

The dashboard supports:

- Listing stored accounts from SQLite.
- Selecting one account and running account-scoped actions.
- Syncing visible Telegram profile fields into the database.
- Switching account by the stored `switch_index`.
- Opening Telegram X settings/security/device pages.
- Username change with Telegram X confirmation before database update.
- Avatar change with random image, custom upload, or gallery mode.
- Add-account and login flow with dynamic next-step prompts.
- Deeplink execution for the selected account.
- Operation log output for success and failure responses.

## Account Database

The SQLite store is initialized automatically on API or bot startup. The `accounts`
table tracks:

- `phone_e164`, `country_code`, `local_phone`
- `username`, `first_name`, `last_name`
- `status`, `is_banned`, `has_restrictions`, `restriction_note`
- `switch_index`
- bot source metadata: `added_by_chat_id`, `added_by_user_id`
- timestamps: `created_at`, `updated_at`, `last_login_at`, `last_seen_at`

Telegram X does not reliably expose the active account phone number through UI XML.
For that reason, account-scoped actions use the stored `switch_index` as the source
of truth and switch to the requested account before running the requested module.

## Account Guard

Every account-scoped UI API endpoint calls the account guard before doing work.

The guard:

1. Resolves the requested account by `phone_e164`, `phone`, or `index`.
2. Requires a stored `switch_index`.
3. Opens the Telegram X account switcher.
4. Taps the account row by index.
5. Marks the account as seen in the database.

The returned `steps` include lines such as:

```text
account guard target=+8613062371708 switch_index=0
switch account index=0
account guard switched target=+8613062371708
```

This is intentionally done before username, avatar, deeplink, security-page, and
sync operations.

## Login Flow

Login is page-driven rather than command-route-driven.

Use:

- `POST /actions/add-account/open`
- `POST /actions/login/next`
- `POST /actions/login/start`
- `POST /actions/login/submit-next`
- `POST /actions/login/submit-code`
- `POST /actions/login/submit-password`

`/actions/login/next` and `/state` return `login_requirement`, which describes the
current page and the required value:

- `phone`: needs dial code and local phone.
- `code`: needs Telegram login code.
- `password`: needs 2FA password.
- `email_or_email_code`: needs the value requested by Telegram X.
- `inspect`: unknown login page; inspect `state.excerpt`.

When Telegram X reaches an active page after login, the account is marked `active`
and login metadata is written to SQLite. Failed or unfinished login attempts should
not be treated as active accounts.

## Telegram Bot

The bot is configured by `TELEGRAM_BOT_TOKEN`. Admin IDs are configured through
`TELEGRAM_ADMIN_IDS` as a comma-separated list.

Supported flows include:

- User-triggered account addition through contact sharing.
- Admin/user account list and account panel helpers.
- Username, full-name, avatar, deeplink, spam-check, state, recover, and switch helpers.
- Direct login values while a login page is active, without requiring `/code` or
  `/password` command routes.

When a non-admin user adds an account, the bot records source metadata and can
notify configured admins.

## Avatar Flow

Avatar mode options:

- `custom`: upload an image through the web UI.
- `random`: download one image from `https://v2.xxapi.cn/api/head?return=json`.
- `gallery`: use Telegram X gallery flow without proving which image was selected.

For `custom` and `random`, the backend:

1. Writes a unique local temp file.
2. Pushes it to `/sdcard/Pictures/`.
3. Runs media scan.
4. Verifies Android MediaStore's latest image path is the expected file.
5. Opens Telegram X profile photo flow.
6. Selects the first gallery tile only after the MediaStore check passes.

If MediaStore does not show the expected file as newest, the API returns an error
instead of reporting success.

## Verified Checks

Before this branch was published, these checks passed locally:

```bash
python3 -m compileall tgbot-api/tgx_automation
git diff --check
```

The running API service also answered `/health` with:

```json
{"ok":"true"}
```

Manually exercised flows:

- Account guard switching from another account before setting username.
- Custom avatar upload for a selected account.
- Random avatar through the `v2.xxapi.cn` API.
- Username set flow with Telegram X confirmation.

## Known Limits

- Telegram X UI XML may not expose profile name fields reliably. The name-change UI
  path currently returns `verified=false` and does not update the database when the
  flow cannot be confirmed.
- Some security pages such as Devices/Login Email may return `verified=false` if the
  current Telegram X build exposes different accessibility markers.
- `gallery` avatar mode cannot prove which image was selected, so `custom` or
  `random` should be preferred.
- Account selection depends on `switch_index`; keep database rows aligned with the
  visible Telegram X account switcher order.

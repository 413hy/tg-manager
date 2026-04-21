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
- `GET /accounts`
- `POST /accounts`
- `PATCH /accounts/{phone_e164}`
- `POST /actions/account/switch`
- `POST /actions/add-account/open`
- `POST /actions/login/start`
- `POST /actions/login/submit-code`
- `POST /actions/login/submit-password`
- `POST /actions/username`
- `POST /actions/name`
- `POST /actions/recover-home`
- `POST /router/step`
- `POST /router/auto`

## Notes
- This project is designed for redroid + ADB usage.
- Unknown pages do not hard-fail by default; router can attempt interstitial handling or home recovery.
- Account metadata is stored in SQLite at `TGX_DB_PATH` and initialized automatically on API/bot startup.

## Account Database
The `accounts` table tracks:
- phone number (`phone_e164`, country code, local number)
- username, first name, last name
- login/status state (`unknown`, `code_sent`, `needs_password`, `active`, `banned`, etc.)
- ban and restriction flags (`is_banned`, `has_restrictions`, `restriction_note`)
- Telegram X switcher order (`switch_index`)
- source user metadata for bot-driven additions (`added_by_chat_id`, `added_by_user_id`)

Because Telegram X does not reliably expose account phone text in UI XML, switching by phone uses the stored `switch_index`. Keep it aligned with the account rows shown in the drawer account switcher.

## Telegram Bot Commands
- `/add_account` asks the user to share their phone number with a contact request button, opens Telegram X `Add Account`, and submits the received number.
- `/code 12345` submits the SMS/Telegram login code for the in-progress account.
- `/password your-password` submits the two-step verification password when Telegram X asks for it.
- `/cancel` clears the in-memory pending flow for that chat and removes the custom keyboard.
- `/state` returns the current Telegram X page detector state.
- `/recover` restarts Telegram X back toward the home/chat list state.

The bot intentionally does not restrict `/add_account` to an admin user, so non-admin users can add accounts by sharing their own phone number.

## Verified Telegram X Flows

Screen used for these coordinates: `720x1280`, density `320`.

### Change profile photo
1. Open profile/settings: `tg://settings`.
2. Tap the profile header photo area: `(450,300)`.
3. Tap `Set Profile Photo`: approximately `(260,1024)`.
4. If Android asks for media permission, tap `ALLOW`: approximately `(360,714)`.
5. Pick a visible grid thumbnail, for example `(360,770)`.
6. Confirm from the editor with `btn_send`: approximately `(664,1128)`.

Observed menu after step 2: `Open`, `Set Profile Photo`, `Delete`.

### Open Add Account page
1. From a chat, tap top-left back: `(52,104)` to reach the chat list.
2. Open main drawer: `(56,104)`.
3. Expand the account switcher: `(546,289)`.
4. Tap `btn_addAccount`, fallback `(220,512)`.
5. The destination page contains `Add Account`, `Country`, `Phone number`.

After step 5, call `POST /actions/login/start` with the target country, dialing code, and phone.

### Switch account
1. Open main drawer: `(56,104)`.
2. Expand account switcher: `(546,289)`.
3. Tap the account row by zero-based `switch_index`.

Use `POST /actions/account/switch` with either:
```json
{"index": 0}
```
or:
```json
{"phone_e164": "+94778807109"}
```
`phone` is also accepted as an alias for `phone_e164`.


## Auto behavior
- On `start messaging` page, router auto-clicks Start Messaging.
- On interstitial pages, router first tries BACK key (most stable), then falls back to `never/skip/not now/later/start/btn_done/x`.
- On unknown pages, router can recover to home by back/back/back + relaunch.

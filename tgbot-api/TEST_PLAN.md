# Telegram X Automation Test Plan

Last updated: 2026-04-22

## Scope

This project is currently scoped to account onboarding and account health checks:

- Open Telegram X add-account flow.
- Submit phone, verification code, 2FA password, or email-related login input according to the current page.
- Store an account only after Telegram X reaches a logged-in state.
- List stored accounts from SQLite.
- Switch Telegram X to a stored account before account-specific operations.
- Automatically check account status through Spam Info Bot and persist Telegram-derived status.
- Expose the same behavior through the web UI and Telegram bot control paths.

Out of scope for this stage:

- Username, first name, last name, avatar, 2FA management, login email management, device/session management.
- Manual status marking from the web UI.
- Any database record that is not backed by a successful Telegram X login or a Telegram-derived status check.

## Key Requirements

1. Failed login must not create an account row.
2. Re-login for an already active account must not restart the login flow; it must return existing account data and supported actions.
3. Login must be page-driven. The API must report the current required value instead of forcing `/code` or `/password`-style routing.
4. Country is not a user input; country display derives from country code.
5. Every account-specific operation must switch to the target `switch_index` first.
6. Database account status must come from Telegram X / Spam Info Bot, not manual marking.
7. SpamBot status checks must clear the message box and send exactly `/start`; `//start` or stale input is a test failure.
8. SpamBot status must be derived from the current bot response only, not historical chat messages.
9. The only accepted SpamBot classifications are:
   - Normal: `Good news, no limits are currently applied to your account. You’re free as a bird!`
   - Banned: `Your account was blocked for violations of the Telegram Terms of Service based on user reports confirmed by our moderators.`
   - Limited: `Unfortunately, some phone numbers may trigger a harsh response from our anti-spam systems. If you think this is the case with you, you can submit a complaint to our moderators or subscribe to Telegram Premium to get less strict limits.`
10. Any other SpamBot output is query failed and must not overwrite an existing known status.
11. Frontend operations must use the same API endpoints as direct API tests.

## API Test Cases

| ID | Endpoint | Purpose | Expected Result |
| --- | --- | --- | --- |
| T01 | `GET /health` | API liveness | Returns `{"ok":"true"}` |
| T02 | `GET /ui` | Web UI serves dashboard | HTTP 200 HTML |
| T03 | `GET /state` | Page detector and login requirement | Returns `page`, `hints`, `excerpt`, `login_requirement` |
| T04 | `GET /accounts` | Database list | Returns accounts with phone, switch index, status, restriction fields |
| T05 | `POST /actions/recover-home` | Recover Telegram X to stable state | Returns steps and current state |
| T06 | `POST /accounts/sync-telegram` | Sync visible Telegram X slots to known DB accounts | Returns visible count, synced known accounts, missing slots |
| T07 | `POST /actions/account/switch` | Switch by stored phone/index | Returns target account and state; updates last seen |
| T08 | `POST /actions/account/check-status` normal account | Switch target, open Spam Info Bot, classify normal | Writes `status=active`, `is_banned=0`, `has_restrictions=0` |
| T09 | `POST /actions/account/check-status` banned account | Switch target, send exact `/start`, classify current SpamBot response | Writes `status=banned`, `is_banned=1`, `has_restrictions=1` only when the exact blocked response is returned |
| T10 | `POST /actions/add-account/open` | Enter add-account flow | Returns phone login requirement or a clear recoverable error |
| T11 | `POST /actions/login/next` | Inspect current login requirement | Returns page-driven `login_requirement` |
| T12 | `POST /actions/login/start` for existing active account | Prevent duplicate login flow | Returns `already_logged_in=true` and existing account |
| T13 | `POST /actions/login/submit-next` invalid/missing value | Validate input page without writing DB | Returns an error and does not create account |
| T14 | `POST /actions/login/submit-code` wrong current page | Alias compatibility | Returns page-driven error, no DB write |
| T15 | `POST /actions/login/submit-password` wrong current page | Alias compatibility | Returns page-driven error, no DB write |
| T16 | `POST /router/step` | One router step | Handles known interstitial/start/unknown, otherwise no-op |
| T17 | `POST /router/auto` | Bounded router automation | Returns history and final state |
| T18 | `POST /actions/handle-interstitials` | Clear known Telegram X popups | Returns handled actions and current login requirement |

## Interaction Tests

| ID | Flow | Expected Result |
| --- | --- | --- |
| F01 | `switch -> check-status` | Check status runs against the selected target account, not current random account |
| F02 | `add-account/open -> login/next` | Login form state is reported through `login_requirement` |
| F03 | existing active `login/start` | Does not open or overwrite a login flow |
| F04 | failed/invalid submit | Does not insert new DB account |
| F05 | repeated status checks | Current exact SpamBot response wins; unknown/unrecognized OCR does not overwrite known status |

## Telegram Bot Test Coverage

The bot delegates to the same storage, navigation, and login modules. Manual bot chat verification should cover:

- `/add_account` requests Telegram contact sharing.
- Shared own contact starts add-account flow and records source metadata only after successful login.
- `/users` lists accounts; admin sees all accounts, non-admin sees owned accounts.
- `/switch <phone_or_index>` switches through the same `switch_account_by_index` module.
- `/state` returns current page detector output and key page elements.
- Login code/password can be sent directly without command prefixes.

## Execution Record

The latest execution results are recorded below after running the API tests on the VPS service.

### 2026-04-22 VPS Run

Environment:

- API service: `tgx-api.service` on `127.0.0.1:8080`
- ADB device: `127.0.0.1:5555`
- Database: `tgbot-api/tgx_automation.sqlite3`
- Branch: `telegram-x-over`

Results:

| ID | Result | Notes |
| --- | --- | --- |
| T01 | PASS | `GET /health` returned `{"ok":"true"}`. |
| T02 | PASS | `GET /ui` returned HTTP 200 and dashboard HTML. |
| T03 | PASS | `GET /state` returned page state plus `login_requirement`; unknown pages return `inspect`. |
| T04 | PASS | `GET /accounts` returned four stored accounts with status/restriction fields. |
| T05 | PASS | `POST /actions/recover-home` returned `home_chats`. |
| T06 | PASS after fix | Initial run exposed a bug: sync set `status=active` on banned accounts. Fixed sync to derive `banned/limited/active` from restriction flags and preserve known status. Retest passed. |
| T07 | PASS | Switching to `+94778807109` selected `switch_index=1` and returned `home_chats`. |
| T08 | PASS | `+94778807109` checked through Spam Info Bot and wrote `status=active`, `restriction_note=SpamBot: no restrictions detected`. |
| T09 | PASS | `+13149862659` checked through Spam Info Bot and wrote `status=banned`, `is_banned=1`, `has_restrictions=1`. |
| T10 | PASS | `POST /actions/add-account/open` opened the add-account phone page and returned `login_requirement.required=phone`. |
| T11 | PASS | `POST /actions/login/next` reported `phone` requirement on add-account page. |
| T12 | PASS | `POST /actions/login/start` for existing active `+94778807109` returned `already_logged_in=true`; no duplicate login flow started. |
| T13 | PASS | `POST /actions/login/submit-next` with missing `code/phone` on phone page returned an error; account count stayed unchanged. |
| T14 | PASS | `POST /actions/login/submit-code` on phone page returned the same page-driven error; no DB write. |
| T15 | PASS | `POST /actions/login/submit-password` on phone page returned the same page-driven error; no DB write. |
| T16 | PASS | `POST /router/step` on add-account page returned no-op, as expected. |
| T17 | PASS | `POST /router/auto` with `max_steps=1` returned one no-op step and final state. |
| T18 | PASS | `POST /actions/handle-interstitials` on add-account page returned no actions and preserved `phone` login requirement. |

Final account state after the run:

| Phone | Expected | Observed |
| --- | --- | --- |
| `+94778807109` | Normal active account | `status=active`, `is_banned=0`, `has_restrictions=0` |
| `+13149862659` | Banned account | `status=banned`, `is_banned=1`, `has_restrictions=1` |
| `+2349158725636` | Banned account | `status=banned`, `is_banned=1`, `has_restrictions=1` |

### 2026-04-22 SpamBot Fix Retest

Regression found:

- The message box could retain a stale slash and send `//start`.
- Status classification scanned older SpamBot history and used broad keyword matching.

Fix validated:

- `POST /actions/account/check-status` clears the input and sends exact `/start`.
- The API no longer swipes or scans SpamBot history.
- `+94778807109` returned `status_result=normal` from the current SpamBot reply and wrote `status=active`.
- `+13149862659` returned `status_result=banned` from the current SpamBot reply and wrote `status=banned`.
- OCR text from the retest did not contain `//start`; `/start` may appear as `Istart` due OCR, but the sent command was verified before tapping send.

### 2026-04-23 SpamBot Open-Flow Retest

Regression found:

- The SpamBot search overlay contains text such as `SpamBot`, `Chats and Contacts`, and `Global Search`.
- The old open-flow verifier could treat that search overlay as if it were the real SpamBot message view because the underlying current chat still exposed `msg_list` / `msg_input`.
- In that state, `/start` could be sent to the wrong current chat, and the status check would return `unknown` or a misleading result.

Fix validated:

- Search overlays are rejected explicitly and never considered a SpamBot chat.
- A candidate is accepted only after OCR confirms `Spam Info Bot` on a real message view.
- Retest with `+2349158725636` rejected two wrong candidates, opened the real Spam Info Bot on candidate 3, sent exact `/start`, read the current blocked response, and wrote `status=banned`.

Fresh new-number login was not completed in this run because it requires a new external phone verification code. The login write-path was validated by the already-logged-in guard and invalid-submit guard: failed/invalid login submissions did not create new database rows.

### Fixes From This Run

- `POST /accounts/sync-telegram` no longer overwrites banned or limited accounts with `status=active`.
- Status checks already had OCR hardening from the previous run and were revalidated:
  - generic SpamBot help text is not treated as a restriction,
  - unknown OCR does not overwrite known status,
  - repeated status checks keep banned accounts banned,
  - search waits for the input field and validates candidates with OCR.

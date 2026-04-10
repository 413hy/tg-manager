# Reverse-Engineered Technical Specification and Development Plan

> **Target:** Windows desktop clone of a Telegram account management panel inferred from a single screenshot.
>
> **Evidence quality disclaimer:** This specification is based on visual reverse engineering only. Any behavior not explicitly visible in the screenshot should be validated during discovery.

## 1) Product Intent and Functional Scope

### 1.1 Observed intent from the screenshot
The visible UI strongly suggests a multi-account Telegram operations console with:

- Left-side function navigator with many operation categories.
- Central account inventory grid.
- Batch operation toolbar and row selection controls.
- Account profile editing controls.
- Manual registration/login controls.
- Proxy selection and assignment controls.
- Live runtime log panel.

### 1.2 Functional areas implied by left navigation
The left-side menu appears to include these families (naming translated/inferred):

- Registration/Login
- Batch group/channel creation
- User collection (including v2 variants)
- Group/channel collection
- Batch invite (v1/v2/v3)
- Batch private message (v1/v2)
- Auto group chat / auto group send (v1/v2)
- Auto reply / auto invite detection / group reply-forward
- Auto private chat (v1/v2)
- Auto marketing
- Read-volume boosting
- Group synchronization
- Number screening (v1/v2)
- Batch registration
- Batch account warming
- Global settings
- License / activation

### 1.3 Safe scope for a modern compliant clone
Prioritize a legitimate operations core:

- Multi-account inventory and status management.
- Login/session lifecycle management.
- Proxy-aware connection management.
- Batch-safe maintenance actions (connect/refresh/logout/profile maintenance).
- Profile management.
- Logging, diagnostics, and operational visibility.

**Out of scope unless explicitly redesigned for compliant, opt-in use:** unsolicited outreach, large-scale invite automation, scraping, ban-evasion workflows, and abuse-oriented growth tactics.

## 2) Recommended Stack

- **Language:** Python 3.12
- **GUI:** PySide6 (Qt for Python)
- **Async bridge:** qasync
- **Telegram client:** Telethon (user account MTProto flows)
- **Database:** SQLite
- **ORM/migrations:** SQLAlchemy 2.x + Alembic
- **Validation/settings:** Pydantic v2
- **Background processing:** asyncio queues + bounded worker pool
- **Secret storage (Windows):** DPAPI-backed local secret vault
- **Logging:** standard logging with structured JSON handlers (or structlog)
- **Packaging:** PyInstaller first, optional Nuitka hardening later
- **Testing:** pytest + pytest-qt

## 3) Architecture and Runtime Flows

### 3.1 Layered architecture

1. **UI Layer**
   - Main window, navigation, table/grid, forms, log panel, status bar.
2. **Application Layer**
   - Account, auth, proxy, profile, task, settings, license services.
3. **Runtime Layer**
   - Connection manager, worker pool, retry policy, event bus, poll scheduler.
4. **Data Layer**
   - SQLite repositories for accounts/proxies/sessions/settings/tasks/logs.
5. **Integration Layer**
   - Telethon adapters, import/export adapters, OS security, packaging hooks.

### 3.2 Startup + polling flow

1. App launches.
2. Activation check runs.
3. Settings + schema migrations initialize.
4. UI composes (left menu, table, toolbar, log panel, status bar).
5. Accounts and proxy assignments load from DB.
6. Runtime scheduler enqueues status probes for eligible accounts.
7. Connection manager emits state transitions:
   - `INITIALIZING`
   - `CONNECTING`
   - `CONNECTED`
   - `AUTHORIZED`
   - `UNAUTHORIZED`
   - `BANNED_OR_LIMITED`
   - `ERROR`
8. UI table updates row state and counters in near real time.
9. Log panel streams structured account/task events.

### 3.3 Manual login flow (phone + code + 2FA)

1. Operator enters phone number + optional proxy/device profile.
2. Auth service validates input and requests code from Telegram.
3. UI moves to “awaiting code” state.
4. Operator enters verification code.
5. If required, prompt for Telegram 2FA password.
6. On success, persist session securely and upsert account record.
7. Refresh row in account grid and emit success log entry.

### 3.4 Proxy-aware connection flow

1. Resolve effective proxy (`account-level > global default > direct`).
2. Optionally run preflight connectivity test.
3. Build Telethon client with session + proxy + device profile.
4. Connect and publish runtime state changes to UI.
5. On proxy switch, gracefully teardown and recreate bound client.
6. Log proxy/account/result/latency/error for diagnostics.

## 4) Module Specifications

### 4.1 Account Management & Inventory

**Responsibilities**
- Account CRUD and metadata persistence.
- Grid source-of-truth for account state.
- Selection/filter/sort/bulk export/import support.
- Row-level live status updates.

**Core model: `Account`**
- id, phone, country_code
- display_name, first_name, last_name, username, bio, avatar_path
- device_profile
- proxy_id, session_id
- network_status, auth_status, restriction_status, is_banned
- last_connected_at, last_checked_at, created_at, updated_at

**Key APIs**
- `create_account_from_login(...)`
- `upsert_account(...)`
- `list_accounts(...)`
- `assign_proxy(...)`
- `update_profile_fields(...)`
- `mark_status(...)`
- `bulk_export(...)`, `bulk_import(...)`, `delete_accounts(...)`

### 4.2 Authentication & Session Vault

**Responsibilities**
- Login code and 2FA flows.
- Session creation/restore/logout/invalidation.
- Secure local session secret persistence.
- Clear auth state/error reporting.

**Core models**
- `SessionRecord`
- `PendingAuthChallenge`

**Key APIs**
- `request_login_code(...)`
- `complete_login_with_code(...)`
- `complete_login_with_password(...)`
- `restore_client(...)`
- `test_authorization(...)`
- Vault: `store_session/load_session/delete_session`

### 4.3 Proxy Management

**Responsibilities**
- Proxy profile CRUD and health checks.
- Default + per-account assignment.
- Protocol normalization and effective-proxy resolution.

**Core model: `ProxyProfile`**
- id, name, type, host, port, username, encrypted_password
- is_enabled, is_default
- last_test_status, latency, timestamps

**Key APIs**
- `create_proxy/update_proxy/delete_proxy/list_proxies`
- `set_default_proxy(...)`
- `assign_proxy_to_account(...)`
- `resolve_effective_proxy(...)`
- `test_proxy(...)`

### 4.4 Runtime Task Orchestration & Logging

**Responsibilities**
- Bounded-concurrency background jobs.
- Retry/backoff for transient failures.
- UI-safe progress updates.
- Durable task results and structured logs.

**Core models**
- `TaskJob`
- `TaskResult`
- `LogEvent`

**Key APIs**
- Task service: `enqueue/cancel/get_task_status/list_recent_tasks`
- Batch helpers: `run_batch_login/logout/refresh/profile_update/cache_cleanup`
- Log service: `append/stream_recent/clear_ui_buffer`
- Event bus: `publish/subscribe`

## 5) Suggested Repository Layout

```text
telegram_account_manager/
├─ app/
│  ├─ main.py
│  ├─ bootstrap.py
│  ├─ config/
│  ├─ ui/
│  ├─ domain/
│  ├─ services/
│  ├─ runtime/
│  ├─ infrastructure/
│  └─ tests/
├─ packaging/
├─ docs/
└─ README.md
```

## 6) Phased Implementation Plan

### Milestone 1 — Bootstrap + shell UI
- Launchable desktop shell.
- Left nav + account table + toolbar + log panel + status bar.
- SQLite + migrations initialized.

### Milestone 2 — Data model + table binding
- Account/proxy/session/settings/log schemas.
- Real DB-backed table rendering.
- Selection/filter/sort + summary counters.

### Milestone 3 — Manual login + session persistence
- Phone/code/2FA flows.
- Secure session persistence and restore on restart.
- Auth status reflected in grid and logs.

### Milestone 4 — Proxy management
- Proxy CRUD UI.
- Global + per-account assignment.
- Proxy test tooling and proxy-aware client factory.

### Milestone 5 — Polling + orchestration
- Startup polling and periodic checks.
- Worker pool with bounded concurrency.
- Event bus and real-time row updates.

### Milestone 6 — Batch-safe operations + profile editing
- Batch connect/logout/refresh.
- Profile update editor (name/username/bio/avatar).
- Import/export and housekeeping tools.

### Milestone 7 — Settings, license, packaging
- Activation and expiry display.
- Runtime setting controls and persistence.
- Packaged Windows executable artifacts.

### Milestone 8 — Hardening and diagnostics
- Crash-safe shutdown behaviors.
- Better diagnostics and exportable incident logs.
- Security review for session secret handling.
- Integration and UI regression coverage.

## 7) Discovery Checklist (Must Validate)

Because the reference was one screenshot, confirm these before implementation lock:

- Exact semantics of each visible status column.
- Bulk action behavior (idempotency, retry rules, cancellation).
- Error states and user messaging for each auth step.
- Session format/storage interoperability requirements.
- Proxy fallback policy and operator expectations.
- Licensing model requirements and offline behavior.
- Performance targets (account count, polling interval, expected latency).

## 8) Initial Build Slice Recommendation

Implement first:

1. Account inventory table.
2. Manual login + secure session restore.
3. Proxy-aware connect/status refresh.
4. Live structured logging.

This creates a stable core architecture that supports compliant feature expansion without rework.

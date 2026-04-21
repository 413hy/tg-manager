from __future__ import annotations

import base64
import binascii
import json
import string
import time
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from tgx_automation.actions import login as login_actions
from tgx_automation.actions import navigation as navigation_actions
from tgx_automation.actions import profile as profile_actions
from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.config import settings
from tgx_automation.service import AutomationService
from tgx_automation.storage import AccountStore

app = FastAPI(title="tgx-automation-api")
adb = AdbClient(settings.adb_serial)
svc = AutomationService(adb)
store = AccountStore(settings.db_path)
pending_login_phone: Optional[str] = None
pending_login_data: dict[str, str] = {}


class LoginStartReq(BaseModel):
    country: str = ""
    code: str = "86"
    phone: str


class CodeReq(BaseModel):
    code: str


class PasswordReq(BaseModel):
    password: str


class LoginSubmitNextReq(BaseModel):
    code: Optional[str] = None
    phone: Optional[str] = None
    value: Optional[str] = None


class UsernameReq(BaseModel):
    username: Optional[str] = None
    random_if_empty: bool = True


class NameReq(BaseModel):
    first_name: str
    last_name: str


class AutoRouterReq(BaseModel):
    max_steps: int = 6


class AccountUpsertReq(BaseModel):
    phone_e164: Optional[str] = None
    country: str = ""
    country_code: str = ""
    local_phone: str = ""
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: Optional[str] = None
    is_banned: Optional[bool] = None
    has_restrictions: Optional[bool] = None
    restriction_note: Optional[str] = None
    switch_index: Optional[int] = None


class AccountUpdateReq(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: Optional[str] = None
    is_banned: Optional[bool] = None
    has_restrictions: Optional[bool] = None
    restriction_note: Optional[str] = None
    switch_index: Optional[int] = None


class SwitchAccountReq(BaseModel):
    phone_e164: Optional[str] = None
    phone: Optional[str] = None
    index: Optional[int] = None


class AccountRefReq(BaseModel):
    phone_e164: Optional[str] = None
    phone: Optional[str] = None
    index: Optional[int] = None


class AccountDeeplinkReq(AccountRefReq):
    deeplink: str


class AccountUsernameReq(AccountRefReq):
    username: str


class AccountNameReq(AccountRefReq):
    first_name: str
    last_name: str = ""


class AccountOpenPageReq(AccountRefReq):
    page: str


class AccountAvatarReq(AccountRefReq):
    mode: str = "gallery"
    image_base64: Optional[str] = None
    filename: Optional[str] = None


def _resolve_account(req: AccountRefReq) -> tuple[Optional[dict], Optional[str]]:
    if req.index is not None:
        for account in store.list_accounts():
            if account.get("switch_index") == req.index:
                return account, None
        return None, "account not found"

    phone = req.phone_e164 or req.phone
    if not phone:
        return None, "phone_e164, phone, or index is required"
    account = store.get_account(phone)
    if not account:
        return None, "account not found"
    return account, None


def _switch_only(account: dict) -> list[str]:
    if account.get("switch_index") is None:
        raise RuntimeError("account has no switch_index; cannot select it in Telegram X")
    target = account["phone_e164"]
    index = int(account["switch_index"])
    steps = [f"account guard target={target} switch_index={index}"]
    try:
        steps.extend(navigation_actions.switch_account_by_index(adb, index))
    except Exception:
        recover_home(adb)
        steps.append("account guard recovered home after switch failure")
        steps.extend(navigation_actions.switch_account_by_index(adb, index))
    steps.append(f"account guard switched target={target}")
    store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
    return steps


def _ensure_account(account: dict) -> list[str]:
    # The account switcher is the source of truth for the active Telegram X
    # account. Calling it before each operation keeps modules composable even if
    # the previous page/action left Telegram X somewhere unexpected.
    return _switch_only(account)


def _switch_and_sync(account: dict) -> tuple[list[str], dict]:
    steps = _ensure_account(account)
    fields = profile_actions.read_visible_profile_fields(adb)
    updates: dict = {"status": "active"}
    for key in ("username", "first_name", "last_name"):
        if fields.get(key):
            updates[key] = fields[key]
    synced = store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True, **updates)
    return steps, synced


def _login_requirement(state: Optional[dict] = None) -> dict:
    state = state or svc.debug_info()
    page_obj = state.get("page", "unknown")
    page = getattr(page_obj, "value", str(page_obj))
    if page in {"add_account", "login_phone"}:
        return {
            "required": "phone",
            "fields": ["code", "phone"],
            "message": "当前页面需要区号和手机号；国家不用填写，Telegram X 会根据区号显示国家。",
        }
    if page == "login_code":
        return {
            "required": "code",
            "fields": ["value"],
            "message": "当前页面需要 Telegram 登录验证码。",
        }
    if page == "login_password":
        return {
            "required": "password",
            "fields": ["value"],
            "message": "当前页面需要 2FA 密码。",
        }
    if page == "login_email":
        return {
            "required": "email_or_email_code",
            "fields": ["value"],
            "message": "当前页面与登录邮箱有关，请根据手机界面输入邮箱地址或邮箱验证码。",
        }
    return {
        "required": "inspect",
        "fields": [],
        "message": "当前页面不是已识别的登录输入页，请查看 state.excerpt 的关键元素后再提交。",
    }


def _login_active_page(page: str) -> bool:
    return page in {"home_chats", "settings", "privacy_security", "devices", "two_fa", "login_email_settings"}


def _mark_pending_login(state: dict) -> None:
    global pending_login_phone, pending_login_data
    if not pending_login_phone:
        return
    page_obj = state.get("page", "unknown")
    page = getattr(page_obj, "value", str(page_obj))
    if page == "login_password":
        store.upsert_account(
            phone_e164=pending_login_phone,
            status="needs_password",
            mark_seen=True,
            **pending_login_data,
        )
        return
    if page in {"login_code", "login_email", "login_phone", "add_account", "unknown"}:
        return
    if _login_active_page(page):
        store.upsert_account(
            phone_e164=pending_login_phone,
            status="active",
            mark_login=True,
            mark_seen=True,
            **pending_login_data,
        )
        pending_login_phone = None
        pending_login_data = {}


def _page_matches(requested: str, actual: object) -> bool:
    page = getattr(actual, "value", str(actual))
    expected = requested.strip().lower()
    if expected == "settings":
        return page in {"settings", "profile_edit"}
    if expected in {"devices", "sessions", "active_sessions"}:
        return page == "devices"
    if expected in {"privacy", "security"}:
        return page == "privacy_security"
    if expected in {"2fa", "two_fa"}:
        return page in {"two_fa", "login_password"}
    if expected in {"login_email", "email"}:
        return page == "login_email_settings"
    return False


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    path = Path(__file__).resolve().parent / "dashboard.html"
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/state")
def state() -> dict:
    info = svc.debug_info()
    info["login_requirement"] = _login_requirement(info)
    return info


@app.post("/router/step")
def router_step() -> dict:
    rs = svc.step_router()
    return {"page": rs.page, "actions": rs.actions, "note": rs.note}




@app.post("/router/auto")
def router_auto(req: AutoRouterReq) -> dict:
    return svc.auto_router(max_steps=req.max_steps)


@app.post("/actions/handle-interstitials")
def handle_interstitials() -> dict:
    return {"actions": handle_common_interstitials(adb)}


@app.get("/accounts")
def list_accounts() -> dict:
    return {"accounts": store.list_accounts()}


@app.post("/accounts")
def upsert_account(req: AccountUpsertReq) -> dict:
    account = store.upsert_account(**req.model_dump())
    return {"account": account}


@app.patch("/accounts/{phone_e164:path}")
def update_account(phone_e164: str, req: AccountUpdateReq) -> dict:
    account = store.update_account(phone_e164, req.model_dump())
    if not account:
        return {"error": "account not found"}
    return {"account": account}


@app.post("/actions/account/switch")
def switch_account(req: SwitchAccountReq) -> dict:
    index = req.index
    account = None
    phone = req.phone_e164 or req.phone
    if phone:
        account = store.get_account(phone)
        if not account:
            return {"error": "account not found"}
        index = account.get("switch_index")
    if index is None:
        return {"error": "phone_e164, phone, or index is required"}
    steps = navigation_actions.switch_account_by_index(adb, int(index))
    if account:
        store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
    return {"steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/switch")
def ui_switch_account(req: AccountRefReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        steps.extend(_ensure_account(account))
        synced = store.get_account(account["phone_e164"]) or account
        return {"account": synced, "steps": steps, "state": svc.debug_info()}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/sync")
def ui_sync_account(req: AccountRefReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        steps, synced = _switch_and_sync(account)
        return {
            "account": synced,
            "steps": [*steps, "open settings", "read visible profile fields"],
            "state": svc.debug_info(),
            "note": "Telegram X may not expose username/name text through UI XML; empty fields are left unchanged.",
        }
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/deeplink")
def ui_deeplink(req: AccountDeeplinkReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        steps.extend(_ensure_account(account))
        synced = store.get_account(account["phone_e164"]) or account
        adb.open_deeplink(req.deeplink)
        steps.append(f"open deeplink {req.deeplink}")
        return {"account": synced, "steps": steps, "state": svc.debug_info()}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/open-page")
def ui_open_account_page(req: AccountOpenPageReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        steps.extend(_ensure_account(account))
        page = req.page.strip().lower()
        if page == "settings":
            steps.append(profile_actions.open_settings(adb))
        elif page == "devices":
            steps.extend(profile_actions.open_devices_page(adb))
        elif page in {"sessions", "active_sessions"}:
            steps.extend(profile_actions.open_active_sessions_page(adb))
        elif page in {"privacy", "security"}:
            steps.extend(profile_actions.open_privacy_page(adb))
        elif page in {"2fa", "two_fa"}:
            steps.extend(profile_actions.open_two_fa_page(adb))
        elif page in {"login_email", "email"}:
            steps.extend(profile_actions.open_login_email_page(adb))
        else:
            return {"error": f"unsupported page: {req.page}"}
        state = svc.debug_info()
        if not _page_matches(page, state.get("page")):
            return {
                "error": f"open page was not verified; requested={page}, actual={state.get('page')}",
                "verified": False,
                "steps": steps,
                "state": state,
            }
        synced = store.get_account(account["phone_e164"]) or account
        return {"account": synced, "steps": steps, "state": state, "verified": True}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/username")
def ui_set_username(req: AccountUsernameReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        username = req.username.strip().lstrip("@")
        if not username:
            return {"error": "username is required"}
        steps.extend(_ensure_account(account))
        steps.extend(profile_actions.change_username_for_current_account(adb, username))
        fields = profile_actions.read_visible_profile_fields(adb)
        actual = fields.get("username")
        if actual != username:
            return {
                "error": f"username was not confirmed by Telegram X; expected={username}, actual={actual or '-'}",
                "steps": steps,
                "state": svc.debug_info(),
            }
        synced = store.update_account(account["phone_e164"], {"username": actual}) or account
        return {"account": synced, "steps": steps, "state": svc.debug_info()}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/name")
def ui_set_name(req: AccountNameReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        if not req.first_name.strip():
            return {"error": "first_name is required"}
        steps.extend(_ensure_account(account))
        steps.extend(profile_actions.change_name(adb, req.first_name, req.last_name))
        state = svc.debug_info()
        return {
            "error": (
                "name change flow is not verifiable in this Telegram X build; "
                "database was not updated"
            ),
            "verified": False,
            "steps": steps,
            "state": state,
        }
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/ui/api/account/avatar")
def ui_set_avatar(req: AccountAvatarReq) -> dict:
    steps: list[str] = []
    try:
        account, error = _resolve_account(req)
        if error:
            return {"error": error}
        steps.extend(_ensure_account(account))
        mode = req.mode.strip().lower()
        if mode == "custom":
            if not req.image_base64:
                return {"error": "custom avatar requires image_base64", "steps": steps, "state": svc.debug_info()}
            prepare_steps, remote_path = _prepare_custom_avatar(req)
            steps.extend(prepare_steps)
        elif mode == "random":
            prepare_steps, remote_path = _prepare_random_avatar()
            steps.extend(prepare_steps)
        elif mode not in {"gallery", "random"}:
            return {"error": "avatar mode must be gallery, random, or custom"}
        else:
            remote_path = None
        steps.extend(profile_actions.change_avatar_from_gallery(adb, remote_path))
        synced = store.get_account(account["phone_e164"]) or account
        response = {"account": synced, "steps": steps, "state": svc.debug_info()}
        if remote_path:
            response["verified"] = True
            response["verification"] = "target was the newest MediaStore image before gallery selection"
        else:
            response["warning"] = "gallery mode cannot prove which image was selected"
        return response
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


def _prepare_custom_avatar(req: AccountAvatarReq) -> tuple[list[str], str]:
    raw = req.image_base64 or ""
    if "," in raw and raw.split(",", 1)[0].startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = base64.b64decode(raw, validate=True)
    except binascii.Error as exc:
        raise RuntimeError(f"invalid base64 avatar image: {exc}") from exc
    if not data:
        raise RuntimeError("avatar image is empty")
    if len(data) > 10 * 1024 * 1024:
        raise RuntimeError("avatar image is too large; max 10MB")

    suffix = Path(req.filename or "avatar.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    stem = f"tgx_custom_avatar_{int(time.time())}"
    local_path = Path("/tmp") / f"{stem}{suffix}"
    local_path.write_bytes(data)
    return profile_actions.prepare_avatar_media(adb, local_path, suffix, stem)


def _prepare_random_avatar() -> tuple[list[str], str]:
    data, suffix, source_url = _download_random_avatar()
    stem = f"tgx_random_avatar_{int(time.time())}"
    local_path = Path("/tmp") / f"{stem}{suffix}"
    local_path.write_bytes(data)
    steps, remote_path = profile_actions.prepare_avatar_media(adb, local_path, suffix, stem)
    return [f"download random avatar {source_url}", *steps], remote_path


def _download_random_avatar() -> tuple[bytes, str, str]:
    api_url = "https://v2.xxapi.cn/api/head?return=json"
    with urllib.request.urlopen(api_url, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    source_url = str(payload.get("data") or "")
    if payload.get("code") != 200 or not source_url.startswith(("http://", "https://")):
        raise RuntimeError(f"random avatar api returned invalid payload: {payload}")
    with urllib.request.urlopen(source_url, timeout=20) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    if not data:
        raise RuntimeError("random avatar api returned an empty image")
    if len(data) > 10 * 1024 * 1024:
        raise RuntimeError("random avatar image is too large; max 10MB")
    suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        if "png" in content_type:
            suffix = ".png"
        elif "webp" in content_type:
            suffix = ".webp"
        else:
            suffix = ".jpg"
    return data, suffix, source_url


@app.post("/actions/add-account/open")
def open_add_account() -> dict:
    steps: list[str] = []
    try:
        steps.extend(navigation_actions.open_add_account(adb))
        return {"steps": steps, "state": svc.debug_info()}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/start")
def login_start(req: LoginStartReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    try:
        pending_login_phone = AccountStore.normalize_phone(req.code, req.phone)
        pending_login_data = {"country": "", "country_code": req.code, "local_phone": req.phone}
        steps.extend(login_actions.fill_phone(adb, "", req.code, req.phone))
        state = svc.debug_info()
        return {"steps": steps, "state": state, "login_requirement": _login_requirement(state)}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/next")
def login_next() -> dict:
    state = svc.debug_info()
    return {"state": state, "login_requirement": _login_requirement(state)}


@app.post("/actions/login/submit-next")
def login_submit_next(req: LoginSubmitNextReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    try:
        state_before = svc.debug_info()
        requirement = _login_requirement(state_before)
        required = requirement["required"]
        if required == "phone":
            if not req.code or not req.phone:
                return {
                    "error": "当前页面需要 code 和 phone",
                    "steps": steps,
                    "state": state_before,
                    "login_requirement": requirement,
                }
            pending_login_phone = AccountStore.normalize_phone(req.code, req.phone)
            pending_login_data = {"country": "", "country_code": req.code, "local_phone": req.phone}
            steps.extend(login_actions.fill_phone(adb, "", req.code, req.phone))
        elif required == "code":
            if not req.value:
                return {"error": "当前页面需要验证码 value", "steps": steps, "state": state_before, "login_requirement": requirement}
            steps.extend(login_actions.submit_code(adb, req.value))
        elif required == "password":
            if not req.value:
                return {"error": "当前页面需要 2FA 密码 value", "steps": steps, "state": state_before, "login_requirement": requirement}
            steps.extend(login_actions.submit_password(adb, req.value))
        elif required == "email_or_email_code":
            if not req.value:
                return {"error": "当前页面需要邮箱地址或邮箱验证码 value", "steps": steps, "state": state_before, "login_requirement": requirement}
            steps.extend(login_actions.submit_current_text(adb, req.value, "email/email code"))
        else:
            return {
                "error": "当前页面未识别为可提交的登录输入页",
                "steps": steps,
                "state": state_before,
                "login_requirement": requirement,
            }
        state = svc.debug_info()
        _mark_pending_login(state)
        return {"steps": steps, "state": state, "login_requirement": _login_requirement(state)}
    except Exception as exc:
        state = svc.debug_info()
        return {"error": str(exc), "steps": steps, "state": state, "login_requirement": _login_requirement(state)}


@app.post("/actions/login/submit-code")
def login_submit_code(req: CodeReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    try:
        steps.extend(login_actions.submit_code(adb, req.code))
        state = svc.debug_info()
        _mark_pending_login(state)
        return {"steps": steps, "state": state, "login_requirement": _login_requirement(state)}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/submit-password")
def login_submit_password(req: PasswordReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    try:
        steps.extend(login_actions.submit_password(adb, req.password))
        state = svc.debug_info()
        _mark_pending_login(state)
        return {"steps": steps, "state": state, "login_requirement": _login_requirement(state)}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/username")
def change_username(req: UsernameReq) -> dict:
    uname = req.username
    if not uname and req.random_if_empty:
        uname = "tgx_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    if not uname:
        return {"error": "username missing"}

    steps: list[str] = [profile_actions.open_settings(adb)]
    steps.extend(profile_actions.open_username_editor(adb))
    steps.extend(profile_actions.change_username(adb, uname))
    return {"steps": steps, "username": uname, "state": svc.debug_info()}


@app.post("/actions/name")
def change_name(req: NameReq) -> dict:
    steps = profile_actions.change_name(adb, req.first_name, req.last_name)
    return {"steps": steps, "state": svc.debug_info()}


@app.post("/actions/recover-home")
def action_recover_home() -> dict:
    return {"steps": recover_home(adb), "state": svc.debug_info()}

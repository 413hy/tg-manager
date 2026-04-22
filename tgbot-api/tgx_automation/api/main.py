from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from tgx_automation.actions import login as login_actions
from tgx_automation.actions import navigation as navigation_actions
from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.actions.status_check import SpamBotOpenError, check_spambot_status
from tgx_automation.adb_client import AdbClient
from tgx_automation.config import settings
from tgx_automation.service import AutomationService
from tgx_automation.storage import AccountStore

app = FastAPI(title="tgx-account-login-api")
adb = AdbClient(settings.adb_serial)
svc = AutomationService(adb)
store = AccountStore(settings.db_path)

pending_login_phone: Optional[str] = None
pending_login_data: dict[str, str] = {}


class LoginStartReq(BaseModel):
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


class AutoRouterReq(BaseModel):
    max_steps: int = 6


class AccountRefReq(BaseModel):
    phone_e164: Optional[str] = None
    phone: Optional[str] = None
    index: Optional[int] = None


def _page_name(state: dict) -> str:
    page_obj = state.get("page", "unknown")
    return getattr(page_obj, "value", str(page_obj))


def _login_requirement(state: Optional[dict] = None) -> dict:
    state = state or svc.debug_info()
    page = _page_name(state)
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


def _state_has_error(state: dict) -> bool:
    return bool(state.get("error"))


def _login_state_after_action(delay: float = 1.2) -> dict:
    time.sleep(delay)
    return svc.debug_info()


def _login_state_after_phone_submit() -> dict:
    state = _login_state_after_action(1.2)
    if _login_still_on_same_input("phone", state):
        state = _login_state_after_action(3.0)
    return state


def _login_error_response(message: str, steps: list[str], state: dict) -> dict:
    return {
        "error": message,
        "steps": steps,
        "state": state,
        "login_requirement": _login_requirement(state),
    }


def _login_still_on_same_input(required: str, state: dict) -> bool:
    return _login_requirement(state)["required"] == required


def _is_phone_input_page(state: dict) -> bool:
    return _login_requirement(state)["required"] == "phone"


def _login_active_page(page: str) -> bool:
    return page in {"home_chats"}


def _mark_pending_login(state: dict) -> None:
    global pending_login_phone, pending_login_data
    if not pending_login_phone:
        return
    page = _page_name(state)
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
        return

    if page in {"login_code", "login_email", "login_password", "login_phone", "add_account", "unknown"}:
        return


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


def _existing_active_account(code: str, phone: str) -> Optional[dict]:
    account = store.get_account(AccountStore.normalize_phone(code, phone))
    if account and account.get("status") == "active":
        return account
    return None


def _country_name(country_code: str) -> str:
    return {
        "1": "USA",
        "7": "Russia",
        "44": "United Kingdom",
        "49": "Germany",
        "60": "Malaysia",
        "61": "Australia",
        "65": "Singapore",
        "81": "Japan",
        "86": "China",
        "91": "India",
        "94": "Sri Lanka",
        "234": "Nigeria",
    }.get(country_code, "")


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
    _mark_pending_login(info)
    info["login_requirement"] = _login_requirement(info)
    return info


@app.get("/accounts")
def list_accounts() -> dict:
    return {"accounts": store.list_accounts()}


@app.post("/accounts/sync-telegram")
def sync_telegram_accounts() -> dict:
    steps, centers = navigation_actions.account_switcher_entries(adb)
    visible_count = len(centers)
    synced: list[dict] = []
    missing_slots: list[int] = []
    for index in range(visible_count):
        account, _ = _resolve_account(AccountRefReq(index=index))
        if account:
            if account.get("is_banned"):
                status = "banned"
            elif account.get("has_restrictions"):
                status = "limited"
            else:
                status = "active"
            synced.append(store.upsert_account(phone_e164=account["phone_e164"], status=status, switch_index=index, mark_seen=True))
        else:
            missing_slots.append(index)
    return {
        "steps": steps,
        "visible_accounts": visible_count,
        "synced": synced,
        "missing_slots": missing_slots,
        "message": "只同步 Telegram X 抽屉中可见且数据库已知的账号；未识别槽位不会自动建库。",
    }


@app.post("/actions/account/check-status")
def check_account_status(req: AccountRefReq) -> dict:
    account, error = _resolve_account(req)
    if error:
        return {"error": error}
    if account.get("switch_index") is None:
        return {"error": "account has no switch_index; cannot select it in Telegram X"}

    steps = navigation_actions.switch_account_by_index(adb, int(account["switch_index"]))
    store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
    try:
        with tempfile.TemporaryDirectory(prefix="tgx-status-") as tmp:
            result = check_spambot_status(adb, Path(tmp))
    except SpamBotOpenError as exc:
        return {"error": str(exc), "steps": steps + exc.steps, "state": svc.debug_info()}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}
    result_status = result.get("status_result")
    if result_status == "unknown":
        updated = store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
        return {"account": updated, "result": result, "steps": steps + result["steps"], "state": svc.debug_info()}

    account_status = "banned" if result["is_banned"] else "limited" if result["has_restrictions"] else "active"
    updated = store.upsert_account(
        phone_e164=account["phone_e164"],
        status=account_status,
        is_banned=result["is_banned"],
        has_restrictions=result["has_restrictions"],
        restriction_note=result["restriction_note"],
        mark_status_checked=True,
        mark_seen=True,
    )
    return {"account": updated, "result": result, "steps": steps + result["steps"], "state": svc.debug_info()}


@app.post("/router/step")
def router_step() -> dict:
    rs = svc.step_router()
    _mark_pending_login(svc.debug_info())
    return {"page": rs.page, "actions": rs.actions, "note": rs.note}


@app.post("/router/auto")
def router_auto(req: AutoRouterReq) -> dict:
    result = svc.auto_router(max_steps=req.max_steps)
    _mark_pending_login(svc.debug_info())
    return result


@app.post("/actions/handle-interstitials")
def handle_interstitials() -> dict:
    actions = handle_common_interstitials(adb)
    current = svc.debug_info()
    _mark_pending_login(current)
    return {"actions": actions, "state": current, "login_requirement": _login_requirement(current)}


@app.post("/actions/recover-home")
def action_recover_home() -> dict:
    steps = recover_home(adb)
    current = svc.debug_info()
    _mark_pending_login(current)
    return {"steps": steps, "state": current}


@app.post("/actions/account/switch")
def switch_account(req: AccountRefReq) -> dict:
    account, error = _resolve_account(req)
    if error:
        return {"error": error}
    if account.get("switch_index") is None:
        return {"error": "account has no switch_index; cannot select it in Telegram X"}
    steps = navigation_actions.switch_account_by_index(adb, int(account["switch_index"]))
    store.upsert_account(phone_e164=account["phone_e164"], mark_seen=True)
    return {"account": store.get_account(account["phone_e164"]) or account, "steps": steps, "state": svc.debug_info()}


@app.post("/actions/add-account/open")
def open_add_account() -> dict:
    steps: list[str] = []
    try:
        steps.extend(navigation_actions.open_add_account(adb))
        current = svc.debug_info()
        requirement = _login_requirement(current)
        if not _is_phone_input_page(current):
            return {
                "error": "打开添加账号后未进入手机号输入页；Telegram X 可能正在恢复一个未完成登录流程，请先完成或取消当前登录。",
                "steps": steps,
                "state": current,
                "login_requirement": requirement,
            }
        return {"steps": steps, "state": current, "login_requirement": requirement}
    except Exception as exc:
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/start")
def login_start(req: LoginStartReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    try:
        existing = _existing_active_account(req.code, req.phone)
        if existing:
            return {
                "account": existing,
                "already_logged_in": True,
                "message": "该号码已在系统中且状态为 active，不会重复进入登录流程。",
                "available_actions": ["查看用户", "切换用户"],
                "state": svc.debug_info(),
            }
        state_before = svc.debug_info()
        if _state_has_error(state_before):
            return _login_error_response("ADB/页面快照不可用，已尝试自动修复，请重新点击检测或提交。", steps, state_before)
        requirement = _login_requirement(state_before)
        if requirement["required"] != "phone":
            return _login_error_response("当前页面不是手机号输入页，不能直接提交手机号。请先打开添加账号或按页面提示继续。", steps, state_before)

        phone_e164 = AccountStore.normalize_phone(req.code, req.phone)
        steps.extend(login_actions.fill_phone(adb, "", req.code, req.phone))
        state_after = _login_state_after_phone_submit()
        if _state_has_error(state_after):
            return _login_error_response("手机号提交后无法读取 Telegram X 页面状态。", steps, state_after)
        if _login_still_on_same_input("phone", state_after):
            pending_login_phone = None
            pending_login_data = {}
            return _login_error_response("手机号提交后仍停留在手机号页面，请检查区号/号码是否被 Telegram X 接受。", steps, state_after)
        pending_login_phone = phone_e164
        pending_login_data = {"country": _country_name(req.code), "country_code": req.code, "local_phone": req.phone}
        _mark_pending_login(state_after)
        return {"steps": steps, "state": state_after, "login_requirement": _login_requirement(state_after)}
    except Exception as exc:
        pending_login_phone = None
        pending_login_data = {}
        return {"error": str(exc), "steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/next")
def login_next() -> dict:
    current = svc.debug_info()
    return {"state": current, "login_requirement": _login_requirement(current)}


@app.post("/actions/login/submit-next")
def login_submit_next(req: LoginSubmitNextReq) -> dict:
    global pending_login_phone, pending_login_data
    steps: list[str] = []
    required: Optional[str] = None
    try:
        state_before = svc.debug_info()
        if _state_has_error(state_before):
            return _login_error_response("ADB/页面快照不可用，已尝试自动修复，请重新点击检测或提交。", steps, state_before)
        requirement = _login_requirement(state_before)
        required = requirement["required"]
        if required == "phone":
            if not req.code or not req.phone:
                return _login_error_response("当前页面需要 code 和 phone。", steps, state_before)
            existing = _existing_active_account(req.code, req.phone)
            if existing:
                return {
                    "account": existing,
                    "already_logged_in": True,
                    "message": "该号码已在系统中且状态为 active，不会重复进入登录流程。",
                    "available_actions": ["查看用户", "切换用户"],
                    "state": state_before,
                    "login_requirement": requirement,
                }
            phone_e164 = AccountStore.normalize_phone(req.code, req.phone)
            steps.extend(login_actions.fill_phone(adb, "", req.code, req.phone))
        elif required == "code":
            if not req.value:
                return _login_error_response("当前页面需要验证码 value。", steps, state_before)
            steps.extend(login_actions.submit_code(adb, req.value))
        elif required == "password":
            if not req.value:
                return _login_error_response("当前页面需要 2FA 密码 value。", steps, state_before)
            steps.extend(login_actions.submit_password(adb, req.value))
        elif required == "email_or_email_code":
            if not req.value:
                return _login_error_response("当前页面需要邮箱地址或邮箱验证码 value。", steps, state_before)
            steps.extend(login_actions.submit_current_text(adb, req.value, "email/email code"))
        else:
            return _login_error_response("当前页面未识别为可提交的登录输入页。", steps, state_before)

        state_after = _login_state_after_phone_submit() if required == "phone" else _login_state_after_action()
        if _state_has_error(state_after):
            return _login_error_response("提交后无法读取 Telegram X 页面状态。", steps, state_after)
        if required in {"phone", "code", "password", "email_or_email_code"} and _login_still_on_same_input(required, state_after):
            if required == "phone":
                pending_login_phone = None
                pending_login_data = {}
            return _login_error_response("提交后仍停留在同一个输入页面，请查看页面提示；本次不会记录为登录成功。", steps, state_after)
        if required == "phone":
            pending_login_phone = phone_e164
            pending_login_data = {"country": _country_name(req.code), "country_code": req.code, "local_phone": req.phone}
        _mark_pending_login(state_after)
        return {"steps": steps, "state": state_after, "login_requirement": _login_requirement(state_after)}
    except Exception as exc:
        if required == "phone":
            pending_login_phone = None
            pending_login_data = {}
        elif not pending_login_phone:
            pending_login_data = {}
        current = svc.debug_info()
        return {"error": str(exc), "steps": steps, "state": current, "login_requirement": _login_requirement(current)}


@app.post("/actions/login/submit-code")
def login_submit_code(req: CodeReq) -> dict:
    return login_submit_next(LoginSubmitNextReq(value=req.code))


@app.post("/actions/login/submit-password")
def login_submit_password(req: PasswordReq) -> dict:
    return login_submit_next(LoginSubmitNextReq(value=req.password))

from __future__ import annotations

import random
import string

from fastapi import FastAPI
from pydantic import BaseModel, Field

from tgx_automation.actions import login as login_actions
from tgx_automation.actions import profile as profile_actions
from tgx_automation.actions.interstitial import handle_common_interstitials
from tgx_automation.actions.navigation import recover_home
from tgx_automation.adb_client import AdbClient
from tgx_automation.config import settings
from tgx_automation.service import AutomationService

app = FastAPI(title="tgx-automation-api")
adb = AdbClient(settings.adb_serial)
svc = AutomationService(adb)


class LoginStartReq(BaseModel):
    country: str = "China"
    code: str = "86"
    phone: str


class CodeReq(BaseModel):
    code: str


class PasswordReq(BaseModel):
    password: str


class UsernameReq(BaseModel):
    username: str | None = None
    random_if_empty: bool = True


class NameReq(BaseModel):
    first_name: str
    last_name: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/state")
def state() -> dict:
    return svc.debug_info()


@app.post("/router/step")
def router_step() -> dict:
    rs = svc.step_router()
    return {"page": rs.page, "actions": rs.actions, "note": rs.note}


@app.post("/actions/handle-interstitials")
def handle_interstitials() -> dict:
    return {"actions": handle_common_interstitials(adb)}


@app.post("/actions/login/start")
def login_start(req: LoginStartReq) -> dict:
    steps = login_actions.fill_phone(adb, req.country, req.code, req.phone)
    return {"steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/submit-code")
def login_submit_code(req: CodeReq) -> dict:
    steps = login_actions.submit_code(adb, req.code)
    return {"steps": steps, "state": svc.debug_info()}


@app.post("/actions/login/submit-password")
def login_submit_password(req: PasswordReq) -> dict:
    steps = login_actions.submit_password(adb, req.password)
    return {"steps": steps, "state": svc.debug_info()}


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

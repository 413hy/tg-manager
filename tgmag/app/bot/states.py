from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LoginFlow(StatesGroup):
    phone = State()
    code = State()
    password = State()


class ImportSessionFlow(StatesGroup):
    phone = State()
    session = State()


class ImportSessionsFlow(StatesGroup):
    payload = State()


class ExportSessionFlow(StatesGroup):
    selection = State()


class ProfileEditFlow(StatesGroup):
    value = State()


class TwoFAEditFlow(StatesGroup):
    value = State()
    email_code = State()


class PostLoginSecurityFlow(StatesGroup):
    twofa_email = State()
    twofa_code = State()
    login_email = State()
    login_email_code = State()

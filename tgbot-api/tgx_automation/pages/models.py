from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class PageType(str, Enum):
    START_MESSAGING = "start_messaging"
    LOGIN_PHONE = "login_phone"
    LOGIN_CODE = "login_code"
    LOGIN_PASSWORD = "login_password"
    LOGIN_EMAIL = "login_email"
    ADD_ACCOUNT = "add_account"
    USERNAME_EDIT = "username_edit"
    PROFILE_EDIT = "profile_edit"
    SETTINGS = "settings"
    PRIVACY_SECURITY = "privacy_security"
    DEVICES = "devices"
    TWO_FA = "two_fa"
    LOGIN_EMAIL_SETTINGS = "login_email_settings"
    HOME_CHATS = "home_chats"
    INTERSTITIAL = "interstitial"
    UNKNOWN = "unknown"


class PageSnapshot(BaseModel):
    page: PageType
    xml_excerpt: str
    hints: list[str]

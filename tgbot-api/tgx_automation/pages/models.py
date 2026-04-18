from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class PageType(str, Enum):
    START_MESSAGING = "start_messaging"
    LOGIN_PHONE = "login_phone"
    LOGIN_CODE = "login_code"
    LOGIN_PASSWORD = "login_password"
    LOGIN_EMAIL = "login_email"
    USERNAME_EDIT = "username_edit"
    PROFILE_EDIT = "profile_edit"
    HOME_CHATS = "home_chats"
    INTERSTITIAL = "interstitial"
    UNKNOWN = "unknown"


class PageSnapshot(BaseModel):
    page: PageType
    xml_excerpt: str
    hints: list[str]

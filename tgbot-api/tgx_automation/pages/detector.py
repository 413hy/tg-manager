from __future__ import annotations

from .models import PageSnapshot, PageType


def detect_page(xml: str) -> PageSnapshot:
    x = xml.lower()
    hints: list[str] = []

    if "start messaging" in x and "btn_done" in x:
        hints.append("start messaging CTA")
        return PageSnapshot(page=PageType.START_MESSAGING, xml_excerpt=xml[:1200], hints=hints)

    if "add account" in x and "phone number" in x:
        hints.append("add account phone input page")
        return PageSnapshot(page=PageType.ADD_ACCOUNT, xml_excerpt=xml[:1200], hints=hints)

    if "controller_phone" in x or "login_phone" in x:
        hints.append("phone input page")
        return PageSnapshot(page=PageType.LOGIN_PHONE, xml_excerpt=xml[:1200], hints=hints)

    if "confirmation code" in x or "text=\"code\"" in x:
        hints.append("code input page")
        return PageSnapshot(page=PageType.LOGIN_CODE, xml_excerpt=xml[:1200], hints=hints)

    if "two-step verification" in x or "forgot password" in x:
        hints.append("2fa password page")
        return PageSnapshot(page=PageType.LOGIN_PASSWORD, xml_excerpt=xml[:1200], hints=hints)

    if "change email" in x and "email address will be used" in x:
        hints.append("login email settings")
        return PageSnapshot(page=PageType.LOGIN_EMAIL_SETTINGS, xml_excerpt=xml[:1200], hints=hints)

    if "controller_privacysettings" in x or ("btn_2fa" in x and "btn_loginemail" in x):
        hints.append("privacy/security settings")
        return PageSnapshot(page=PageType.PRIVACY_SECURITY, xml_excerpt=xml[:1200], hints=hints)

    if "email" in x and ("code" in x or "verify" in x):
        hints.append("email verify page")
        return PageSnapshot(page=PageType.LOGIN_EMAIL, xml_excerpt=xml[:1200], hints=hints)

    if "controller_editusername" in x:
        hints.append("username editor")
        return PageSnapshot(page=PageType.USERNAME_EDIT, xml_excerpt=xml[:1200], hints=hints)

    if "active sessions" in x or "btn_terminatesessions" in x or ("this device" in x and "other devices" in x):
        hints.append("devices/sessions")
        return PageSnapshot(page=PageType.DEVICES, xml_excerpt=xml[:1200], hints=hints)

    if "two-step verification" in x and ("change password" in x or "set password" in x or "recovery email" in x):
        hints.append("2fa settings")
        return PageSnapshot(page=PageType.TWO_FA, xml_excerpt=xml[:1200], hints=hints)

    if "login email" in x and ("gmail" in x or "email" in x):
        hints.append("login email settings")
        return PageSnapshot(page=PageType.LOGIN_EMAIL_SETTINGS, xml_excerpt=xml[:1200], hints=hints)

    if "btn_birthdate" in x and "btn_bio" in x and "btn_phone" in x:
        hints.append("profile/settings edit block")
        return PageSnapshot(page=PageType.PROFILE_EDIT, xml_excerpt=xml[:1200], hints=hints)

    if "btn_username" in x and "btn_devices" in x:
        hints.append("settings")
        return PageSnapshot(page=PageType.SETTINGS, xml_excerpt=xml[:1200], hints=hints)

    if "id/chat" in x:
        hints.append("chat list")
        return PageSnapshot(page=PageType.HOME_CHATS, xml_excerpt=xml[:1200], hints=hints)

    interstitial_markers = ["start setting up", "never", "not now", "skip", "later", "folders are here"]
    if any(m in x for m in interstitial_markers):
        hints.append("interstitial/onboarding")
        return PageSnapshot(page=PageType.INTERSTITIAL, xml_excerpt=xml[:1200], hints=hints)

    return PageSnapshot(page=PageType.UNKNOWN, xml_excerpt=xml[:1200], hints=["no known markers"])

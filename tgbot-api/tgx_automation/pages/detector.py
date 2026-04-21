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

    if "email" in x and ("code" in x or "verify" in x):
        hints.append("email verify page")
        return PageSnapshot(page=PageType.LOGIN_EMAIL, xml_excerpt=xml[:1200], hints=hints)

    if "id/chat" in x:
        hints.append("chat list")
        return PageSnapshot(page=PageType.HOME_CHATS, xml_excerpt=xml[:1200], hints=hints)

    interstitial_markers = ["start setting up", "never", "not now", "skip", "later", "folders are here"]
    if any(m in x for m in interstitial_markers):
        hints.append("interstitial/onboarding")
        return PageSnapshot(page=PageType.INTERSTITIAL, xml_excerpt=xml[:1200], hints=hints)

    return PageSnapshot(page=PageType.UNKNOWN, xml_excerpt=xml[:1200], hints=["no known markers"])

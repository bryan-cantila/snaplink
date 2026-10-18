"""Minimal user-agent parsing for click stats (stub — no external deps).

Keyword matching only; good enough to bucket the top browsers / OS families
for the stats endpoint. Unknown agents fall back to "Other".
"""
from __future__ import annotations


def parse_user_agent(ua: str | None) -> dict[str, str]:
    s = (ua or "").lower()
    browser = "Other"
    # order matters: Chrome UAs contain "safari", Edge contains "chrome"
    if "edg" in s:
        browser = "Edge"
    elif "opr" in s or "opera" in s:
        browser = "Opera"
    elif "firefox" in s or "fxios" in s:
        browser = "Firefox"
    elif "crios" in s or "chrome" in s:
        browser = "Chrome"
    elif "safari" in s:
        browser = "Safari"

    os = "Other"
    if "windows" in s:
        os = "Windows"
    elif "android" in s:
        os = "Android"
    elif "iphone" in s or "ipad" in s or "ios" in s:
        os = "iOS"
    elif "mac os" in s or "macintosh" in s:
        os = "macOS"
    elif "linux" in s:
        os = "Linux"

    return {"browser": browser, "os": os}

"""Playwright browser setup with isolated session directory."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import (
    BrowserContext,
    Playwright,
    async_playwright,
)

SESSION_DIR = Path.home() / ".cache" / "rocketmoney-session" / "browser-data"


async def get_browser_context(
    *, headless: bool = False,
) -> tuple[Playwright, BrowserContext]:
    """Launch Chrome with an isolated persistent profile.

    Returns (playwright_instance, context) -- caller must close both.
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(SESSION_DIR),
        headless=headless,
        channel="chrome",
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    return pw, context

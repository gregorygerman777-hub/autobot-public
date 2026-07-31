"""RocketMoney GraphQL client.

RocketMoney's web app authenticates GraphQL via httpOnly auth cookies (auth0)
and sends queries as Automatic Persisted Queries (APQ) — the client only
transmits an operationName + a sha256 hash; the server already has the query
text registered. Introspection is disabled and there is no Bearer token.

Strategy: drive a logged-in persistent Chrome profile, passively learn the
operationName -> sha256Hash mapping from the app's own network traffic (cached
to disk so it self-heals when RocketMoney ships new hashes), then replay any
operation by hash with our own variables via an in-page fetch (so the auth
cookies ride along automatically).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from rocketmoney_cli.browser import get_browser_context

GRAPHQL_URL = "https://client-api.rocketmoney.com/graphql"
APP_URL = "https://app.rocketmoney.com/"
CACHE_DIR = Path.home() / ".cache" / "rocketmoney-session"
HASHES_CACHE = CACHE_DIR / "op_hashes.json"

# Pages to visit while harvesting operation hashes. Visiting more pages exposes
# more operations (transactions, net worth, etc.).
HARVEST_PAGES = [
    "https://app.rocketmoney.com/",
    "https://app.rocketmoney.com/transactions",
    "https://app.rocketmoney.com/net-worth",
]


def _load_cached_hashes() -> dict[str, str]:
    if HASHES_CACHE.exists():
        try:
            return json.loads(HASHES_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_cached_hashes(hashes: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    HASHES_CACHE.write_text(json.dumps(hashes, indent=2))


class RocketSession:
    """A logged-in RocketMoney browser session that can replay GraphQL ops."""

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw: Any = None
        self._context: Any = None
        self._page: Any = None
        self._hashes: dict[str, str] = _load_cached_hashes()

    async def __aenter__(self) -> RocketSession:
        await self._start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _start(self) -> None:
        self._pw, self._context = await get_browser_context(
            headless=self._headless
        )
        self._page = await self._context.new_page()

        # Passively harvest operationName -> hash from outgoing requests.
        def on_request(req: Any) -> None:
            if GRAPHQL_URL not in req.url or not req.post_data:
                return
            try:
                body = json.loads(req.post_data)
            except Exception:
                return
            ops = body if isinstance(body, list) else [body]
            for op in ops:
                name = op.get("operationName")
                h = (
                    (op.get("extensions") or {})
                    .get("persistedQuery", {})
                    .get("sha256Hash")
                )
                if name and h:
                    self._hashes[name] = h

        self._page.on("request", on_request)

        await self._page.goto(APP_URL, wait_until="domcontentloaded")
        await self._page.wait_for_timeout(4000)

        # Log in if we got bounced to the auth domain.
        if "auth.rocketaccount.com" in self._page.url or (
            "/u/login" in self._page.url
        ):
            await self._login()

        # Harvest hashes from a few key pages (best-effort).
        for url in HARVEST_PAGES:
            try:
                await self._page.goto(url, wait_until="domcontentloaded")
                await self._page.wait_for_timeout(2500)
            except Exception:
                pass

        _save_cached_hashes(self._hashes)

    async def _login(self) -> None:
        import os

        email = os.environ.get("ROCKETMONEY_EMAIL", "")
        password = os.environ.get("ROCKETMONEY_PASSWORD", "")
        if not email or not password:
            print(
                "Not logged in and ROCKETMONEY_EMAIL/PASSWORD not set. "
                "Run with a visible browser (headless=False) to log in once.",
                file=sys.stderr,
            )
            sys.exit(1)
        page = self._page
        await page.wait_for_selector("#username", state="visible", timeout=30000)
        await page.fill("#username", email)
        await page.fill("#password", password)
        await page.click('button:has-text("Sign in")')
        await page.wait_for_timeout(5000)
        if "mfa" in page.url:
            await self._handle_mfa()
        # Wait for dashboard
        for _ in range(30):
            await page.wait_for_timeout(1000)
            if "app.rocketmoney.com" in page.url and "auth." not in page.url:
                break

    async def _handle_mfa(self) -> None:
        from rocketmoney_cli.auth import poll_sms_code

        page = self._page
        print("[auth] MFA required, polling SMS...", file=sys.stderr)
        code = await asyncio.to_thread(poll_sms_code, 90, 30)
        if not code:
            mfa_file = CACHE_DIR / "mfa"
            mfa_file.parent.mkdir(parents=True, exist_ok=True)
            mfa_file.unlink(missing_ok=True)
            print(f"[auth] Write 6-digit code to: {mfa_file}", file=sys.stderr)
            deadline = time.time() + 120
            while time.time() < deadline:
                if mfa_file.exists():
                    code = mfa_file.read_text().strip()
                    mfa_file.unlink(missing_ok=True)
                    if code:
                        break
                await asyncio.sleep(3)
        if not code:
            print("[auth] No MFA code provided", file=sys.stderr)
            sys.exit(1)
        inp = page.locator(
            "input:not([disabled])[type='text'], input[type='tel']"
        ).first
        await inp.fill(code)
        await page.click('button:has-text("Continue")')

    async def gql(
        self, operation_name: str, variables: dict | None = None
    ) -> dict:
        """Replay a persisted operation by name with custom variables."""
        h = self._hashes.get(operation_name)
        if not h:
            print(
                f"Unknown operation '{operation_name}'. Known: "
                f"{', '.join(sorted(self._hashes))}",
                file=sys.stderr,
            )
            sys.exit(1)
        payload = {
            "operationName": operation_name,
            "variables": variables or {},
            "extensions": {
                "persistedQuery": {"version": 1, "sha256Hash": h}
            },
        }
        res = await self._page.evaluate(
            """async ({url, payload}) => {
                const r = await fetch(url, {
                    method: 'POST', credentials: 'include',
                    headers: {'content-type':'application/json',
                              'accept':'application/json'},
                    body: JSON.stringify(payload)
                });
                return {status: r.status, body: await r.text()};
            }""",
            {"url": GRAPHQL_URL, "payload": payload},
        )
        if res["status"] != 200:
            print(
                f"HTTP {res['status']}: {res['body'][:300]}", file=sys.stderr
            )
            sys.exit(1)
        data = json.loads(res["body"])
        if "errors" in data:
            print(
                f"GraphQL errors: {json.dumps(data['errors'], indent=2)}",
                file=sys.stderr,
            )
            sys.exit(1)
        return data.get("data", {})

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
        finally:
            if self._pw:
                await self._pw.stop()


def output(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))

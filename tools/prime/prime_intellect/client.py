"""HTTP client for the Prime Intellect API."""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

BASE_URL = "https://api.primeintellect.ai"
API_PREFIX = "/api/v1"


def _get_api_key() -> str:
    key = (
        os.environ.get("PRIME_INTELLECT_API_KEY")
        or os.environ.get("PRIMEINTELLECT_API_KEY")
        or os.environ.get("PRIME_API_KEY")
    )
    if not key:
        print(
            "Error: Set PRIME_INTELLECT_API_KEY or PRIME_API_KEY env var.\n"
            "Generate one at https://app.primeintellect.ai/dashboard/tokens",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=f"{BASE_URL}{API_PREFIX}",
        headers={
            "Authorization": f"Bearer {_get_api_key()}",
            "Content-Type": "application/json",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


def get(path: str, params: dict[str, Any] | None = None) -> Any:
    with _client() as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def post(path: str, json: dict[str, Any] | None = None) -> Any:
    with _client() as c:
        r = c.post(path, json=json)
        r.raise_for_status()
        return r.json()


def delete(path: str) -> None:
    with _client() as c:
        r = c.delete(path)
        r.raise_for_status()

"""MFA helper: poll the macOS iMessage DB for a 6-digit code."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

MFA_CODE_RE = re.compile(r"\b(\d{6})\b")
IMESSAGE_DB = Path.home() / "Library/Messages/chat.db"


def poll_sms_code(timeout: float = 60, lookback: float = 30) -> str | None:
    """Poll iMessage SQLite DB for a recent 6-digit MFA code."""
    deadline = time.time() + timeout
    cd_offset = 978307200
    cd_after = (time.time() - lookback - cd_offset) * 1_000_000_000
    while time.time() < deadline:
        try:
            conn = sqlite3.connect(f"file:{IMESSAGE_DB}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT text FROM message "
                "WHERE date > ? AND is_from_me = 0 "
                "ORDER BY date DESC LIMIT 20",
                (int(cd_after),),
            ).fetchall()
            conn.close()
            for (text,) in rows:
                if not text:
                    continue
                m = MFA_CODE_RE.search(text)
                if m:
                    return m.group(1)
        except Exception:
            pass
        time.sleep(3)
    return None

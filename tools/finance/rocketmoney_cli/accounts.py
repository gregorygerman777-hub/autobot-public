"""Accounts & balances via NetWorthQuery."""

from __future__ import annotations

from datetime import date, timedelta

from rocketmoney_cli.api import RocketSession, output

OP = "NetWorthQuery"


def _vars() -> dict:
    today = date.today()
    six = today.replace(day=1)
    for _ in range(6):
        six = (six.replace(day=1) - timedelta(days=1)).replace(day=1)
    prev_month_end = today.replace(day=1) - timedelta(days=1)
    return {
        "sixMonthsAgo": six.isoformat(),
        "useEquity": False,
        "lastMonth": prev_month_end.isoformat(),
    }


def _collect(net_worth: dict) -> list[dict]:
    out = []
    groups = [
        ("investment", "investments"),
        ("asset", "assetsWithLoan"),
        ("credit_card", "creditCardDebts"),
        ("loan", "longTermDebts"),
        ("asset_backed_loan", "assetBackedLoans"),
        ("other_debt", "otherDebts"),
    ]
    for kind, key in groups:
        for a in net_worth.get(key, []) or []:
            inst = (a.get("institution") or {}).get("name")
            cents = a.get("valueCents")
            if cents is None:
                cents = a.get("balanceCents")
            out.append(
                {
                    "type": kind,
                    "name": a.get("name"),
                    "institution": inst,
                    "balance": (cents or 0) / 100,
                }
            )
    return out


async def run(argv: list[str] | None = None) -> None:
    async with RocketSession() as s:
        data = await s.gql(OP, _vars())
    nw = data.get("viewer", {}).get("netWorth", {})
    accounts = _collect(nw)
    total = sum(a["balance"] for a in accounts)
    output({"accounts": accounts, "net_worth": round(total, 2)})

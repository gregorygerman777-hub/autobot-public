"""List / filter transactions."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from rocketmoney_cli.api import RocketSession, output

OP = "TransactionsPageTransactionTable"


def _flatten(edges: list[dict]) -> list[dict]:
    out = []
    for e in edges:
        n = e.get("node") or {}
        cat = n.get("category") or {}
        acct = n.get("account") or {}
        out.append(
            {
                "date": n.get("date"),
                "amount": (n.get("amount") or 0) / 100,
                "name": n.get("shortName") or n.get("longName"),
                "longName": n.get("longName"),
                "category": cat.get("label"),
                "categoryType": cat.get("categoryType"),
                "isEarnings": cat.get("includeInEarnings"),
                "pending": n.get("pending"),
                "accountSource": acct.get("source"),
            }
        )
    return out


async def fetch(
    session: RocketSession,
    *,
    days: int | None = None,
    gte: str | None = None,
    lt: str | None = None,
    search: str | None = None,
    page_size: int = 200,
) -> list[dict]:
    now = datetime.now(tz=timezone.utc)
    if days is not None and gte is None:
        gte = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    variables = {
        "query": search,
        "order": "reverse:date",
        "accountIds": [],
        "transactionCategoryIds": [],
        "gteDate": gte,
        "ltDate": lt,
        "cursor": None,
        "pageSize": page_size,
        "metaCategory": None,
    }
    data = await session.gql(OP, variables)
    edges = (
        data.get("viewer", {}).get("transactions", {}).get("edges", [])
    )
    return _flatten(edges)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="transactions")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--search", type=str, default=None)
    p.add_argument("--limit", type=int, default=200)
    return p.parse_args(argv)


async def run(argv: list[str] | None = None) -> None:
    args = parse_args(argv or [])
    async with RocketSession() as s:
        txns = await fetch(
            s, days=args.days, search=args.search, page_size=args.limit
        )
    output(txns)

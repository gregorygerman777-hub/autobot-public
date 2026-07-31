"""RocketMoney CLI. Run: python -m rocketmoney_cli <command> [args]

Commands:
  transactions [--days N] [--search TXT] [--limit N]   Recent transactions
  income [--days N]                                     Paychecks + next payday
  accounts                                              Accounts, balances, net worth
  ops                                                   Show discovered GraphQL ops

Auth: drives a logged-in persistent Chrome profile at
~/.cache/rocketmoney-session/browser-data. If not logged in, set
ROCKETMONEY_EMAIL / ROCKETMONEY_PASSWORD and it will log in (MFA via iMessage).
"""

from __future__ import annotations

import asyncio
import json
import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    command, rest = args[0], args[1:]

    if command == "transactions":
        from rocketmoney_cli.transactions import run

        asyncio.run(run(rest))
    elif command == "income":
        from rocketmoney_cli.income import run

        asyncio.run(run(rest))
    elif command in ("accounts", "balances", "networth"):
        from rocketmoney_cli.accounts import run

        asyncio.run(run(rest))
    elif command == "ops":
        from rocketmoney_cli.api import _load_cached_hashes

        print(json.dumps(_load_cached_hashes(), indent=2))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

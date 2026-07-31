#!/usr/bin/env bash
# Periodic inbox poll — run via cron every 5-15 minutes
# Checks all inbound channels, sends Telegram alert only if something urgent
#
# Crontab entry (every 10 min):
#   */10 * * * * /path/to/autobot/scripts/poll.sh >> /tmp/assistant-poll.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_DIR"
autobot -p "Check all inbound channels for urgent items: email (/skill:gws), Slack (/skill:slack), Messages (/skill:messages). If there are any P0 (urgent) items, send a Telegram alert (/skill:telegram). If nothing urgent, do nothing — no output needed."

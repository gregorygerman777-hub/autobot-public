#!/usr/bin/env bash
# Morning briefing — run via cron once daily
# Gathers all channels and sends a summary to Telegram
#
# Crontab entry (8am daily):
#   0 8 * * * /path/to/autobot/scripts/daily-briefing.sh >> /tmp/assistant-briefing.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$PROJECT_DIR"
autobot -p "Generate a morning briefing: check email (/skill:gws), Slack (/skill:slack), and Messages (/skill:messages). Summarize what's urgent, what needs action today, and key updates. Send the briefing to Telegram (/skill:telegram). Check memory for pending items from yesterday."

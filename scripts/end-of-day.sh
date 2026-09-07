#!/usr/bin/env bash
# End-of-day journal writer — run via cron at 10pm
# Summarizes the day and writes a journal entry
#
# Crontab entry (10pm daily):
#   0 22 * * * /path/to/autobot/scripts/end-of-day.sh >> /tmp/assistant-eod.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Unattended: no operator can approve actions in-band. See docs/THREAT-MODEL.md.
export AUTOBOT_MODE=autonomous
TODAY=$(date +%Y-%m-%d)
SESSION_LOG="$PROJECT_DIR/data/sessions/$TODAY.jsonl"
JOURNAL_FILE="$PROJECT_DIR/data/memory/journal/$TODAY.md"

# Skip if journal already written today
if [ -f "$JOURNAL_FILE" ]; then
    echo "Journal for $TODAY already exists, skipping."
    exit 0
fi

# Build prompt
PROMPT="Write today's journal entry at data/memory/journal/$TODAY.md."
if [ -f "$SESSION_LOG" ]; then
    PROMPT="$PROMPT Today's Telegram conversation log is at $SESSION_LOG — read it and summarize. Also check my calendar for what happened today and any pending items."
else
    PROMPT="$PROMPT No Telegram conversations today. Check my calendar for what happened and note any pending items from memory."
fi
PROMPT="$PROMPT Follow the journal format in the memory skill. Keep it concise."

cd "$PROJECT_DIR"
autobot -p "$PROMPT"

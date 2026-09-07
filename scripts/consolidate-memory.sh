#!/usr/bin/env bash
# Memory consolidation — run via cron, nightly after the journal is written.
#
# Reviews episodic entries (journal/) written since the last run and merges
# durable facts into semantic memory (profile.md, preferences.md, people/,
# projects/). Without this, journal entries are written every night and read at
# most once the next morning, so the episodic log grows forever while the
# semantic store goes stale.
#
# This is the reflection step from Generative Agents (Park et al., 2023) and the
# external-to-main-context movement from MemGPT (Packer et al., 2023).
#
# Crontab entry (10:30pm daily, after end-of-day.sh at 10pm):
#   30 22 * * * /path/to/autobot/scripts/consolidate-memory.sh >> /tmp/assistant-consolidate.log 2>&1
#
# SECURITY: consolidation is a laundering path — an attacker's claim in an email
# becomes a journal line becomes a permanent fact in an auto-injected file. The
# extraction below is deterministic Python, not an LLM prompt, and anything
# traceable to untrusted content is written to data/memory/review-queue.md for a
# human instead of being promoted. See docs/THREAT-MODEL.md (A3, R6).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

export AUTOBOT_MODE=autonomous

MEMORY_ROOT="${AUTOBOT_MEMORY_ROOT:-$PROJECT_DIR/data/memory}"

if [ ! -d "$MEMORY_ROOT" ]; then
    echo "No memory directory at $MEMORY_ROOT — nothing to consolidate."
    exit 0
fi

pick_python() {
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        echo "$PROJECT_DIR/.venv/bin/python"
        return
    fi
    for candidate in python3.13 python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
            command -v "$candidate"
            return
        fi
    done
    echo ""
}

PYTHON="$(pick_python)"
if [ -z "$PYTHON" ]; then
    echo "error: no Python >= 3.12 found (see pyproject.toml)" >&2
    exit 1
fi

echo "==> Consolidating memory at $MEMORY_ROOT"
REPORT="$(PYTHONPATH="$PROJECT_DIR" "$PYTHON" -m autobot_core.cli \
    memory-consolidate --root "$MEMORY_ROOT")"
echo "$REPORT"

# Surface anything held for review. These are candidate facts that consolidation
# refused to promote — usually because they trace back to untrusted content.
QUEUED="$(printf '%s' "$REPORT" | "$PYTHON" -c \
    'import json,sys; print(len(json.load(sys.stdin)["queued"]))' 2>/dev/null || echo 0)"

if [ "$QUEUED" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "==> $QUEUED candidate fact(s) held for review."
    echo "    Review them at: $MEMORY_ROOT/review-queue.md"
    echo "    These were NOT promoted. A human should decide."
fi

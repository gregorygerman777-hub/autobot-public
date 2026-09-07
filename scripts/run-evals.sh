#!/usr/bin/env bash
# Evaluation harness — measures accuracy of the triage, conflict, and briefing
# logic against scripted scenarios with known-correct answers.
#
#   ./scripts/run-evals.sh                    # full report
#   ./scripts/run-evals.sh --suite inbox_triage
#   ./scripts/run-evals.sh --fail-under 0.95  # CI gate
#   ./scripts/run-evals.sh --json             # machine-readable
#
# Every run appends to evals/results/history.csv, so accuracy can be compared
# across commits rather than spot-checked by hand. That file is committed on
# purpose: the history is the artifact.
#
# Runs offline — no API keys, no network, no macOS permissions.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

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
    echo "error: no Python >= 3.12 found (repo requires it; see pyproject.toml)" >&2
    exit 1
fi

PYTHONPATH="$PROJECT_DIR" exec "$PYTHON" -m evals.runner "$@"

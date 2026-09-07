#!/usr/bin/env bash
# Test runner for autobot_core.
#
# The repo had no test suite before Checkpoint 1. This runs the security and
# triage tests offline -- no API keys, no network, no macOS permissions -- so it
# is safe to run in CI and on every commit.
#
#   ./scripts/run-tests.sh          # run everything
#   ./scripts/run-tests.sh -v       # verbose

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# The repo requires Python >= 3.12. Prefer a project venv, then a pinned
# interpreter, and fail loudly rather than silently testing on 3.9.
pick_python() {
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        echo "$PROJECT_DIR/.venv/bin/python"
        return
    fi
    for candidate in python3.13 python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then
                command -v "$candidate"
                return
            fi
        fi
    done
    echo "" 
}

PYTHON="$(pick_python)"
if [ -z "$PYTHON" ]; then
    echo "error: no Python >= 3.12 found (repo requires it; see pyproject.toml)" >&2
    echo "       install one, or run: uv sync" >&2
    exit 1
fi

echo "==> Python: $PYTHON ($("$PYTHON" --version 2>&1))"
echo "==> Running autobot_core test suite"
PYTHONPATH="$PROJECT_DIR" "$PYTHON" -m unittest discover -s tests -t "$PROJECT_DIR" "$@"

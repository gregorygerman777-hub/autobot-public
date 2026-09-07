#!/usr/bin/env bash
# Auto-homework — run daily to check for and complete upcoming assignments
#
# Crontab entry (6pm daily):
#   0 18 * * * /path/to/autobot/scripts/auto-homework.sh >> /tmp/assistant-homework.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Unattended: no operator can approve actions in-band. See docs/THREAT-MODEL.md.
export AUTOBOT_MODE=autonomous

cd "$PROJECT_DIR"
autobot -p "Check MyCompass for assignments due in the next 3 days. For each assignment:
1. Check if I've already completed it (look in data/output/schoolwork/ for matching files)
2. If not done, attempt to complete it:
   - For essays/written work: research the topic and write a draft
   - For presentations: create LaTeX beamer slides
   - For study guides: create a comprehensive PDF with key concepts
   - For worksheets: fill them out based on the assignment details
3. Save all output to data/output/schoolwork/<assignment-name>/
4. Skip 'Weekly HW Check' and 'Weekly Research Check' (in-class completions)
5. Skip any Reading-type assignments (excused)
6. Send a Telegram summary of what was completed and what's still pending"

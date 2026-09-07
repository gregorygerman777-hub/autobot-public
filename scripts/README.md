# Scripts

Automation scripts for cron jobs. All scripts use `autobot -p` to run pi in non-interactive (print) mode.

## Available Scripts

| Script | Description | Suggested Cron |
|--------|-------------|----------------|
| `daily-briefing.sh` | Morning summary across all channels (gws, slack, messages), sent to Telegram | `0 8 * * *` |
| `auto-homework.sh` | Checks school portal for upcoming assignments, attempts to complete them | `0 18 * * *` |
| `end-of-day.sh` | Writes a journal entry summarizing the day's conversations and calendar | `0 22 * * *` |
| `poll.sh` | Checks all inbound channels, sends Telegram alert only if something urgent | `*/10 * * * *` |
| `consolidate-memory.sh` | Merges durable facts from journal entries into semantic memory | `30 22 * * *` |
| `run-tests.sh` | Offline unit tests (not a cron job — run manually or in CI) | N/A |
| `run-evals.sh` | Evaluation harness: accuracy vs known-correct scenarios | N/A |
| ~~`telegram-listener.py`~~ | Replaced by `pi-telebridge` extension — run `/telegram` in pi to enable | N/A |

## Setup

1. Make sure `autobot` is in your PATH (run `autobot install` first)
2. Configure your `.env` with the needed API tokens
3. Add cron entries for the scripts you want:

```bash
crontab -e
```

Example crontab:
```
0 8 * * * /path/to/autobot/scripts/daily-briefing.sh >> /tmp/assistant-briefing.log 2>&1
0 22 * * * /path/to/autobot/scripts/end-of-day.sh >> /tmp/assistant-eod.log 2>&1
30 22 * * * /path/to/autobot/scripts/consolidate-memory.sh >> /tmp/assistant-consolidate.log 2>&1
*/10 * * * * /path/to/autobot/scripts/poll.sh >> /tmp/assistant-poll.log 2>&1
```

## Customization

These scripts are starting templates. Customize the prompts, schedules, and which skills they invoke to match your workflow. For example:

- Change `auto-homework.sh` to check a different task system
- Adjust `daily-briefing.sh` to only check the channels you use
- Modify `poll.sh` frequency based on how often you want to be notified

## Security

All cron scripts export `AUTOBOT_MODE=autonomous`, which tells the action guard
that no human is present to approve anything. In that mode, a run that has read
untrusted content (email, messages, web) may only take pre-approved actions:
notifying the operator on their configured Telegram chat, writing a journal
note, and creating reminders. Sending mail, texting a contact, editing contacts,
and submitting coursework are refused by policy.

Ordering matters: `consolidate-memory.sh` runs at 10:30pm, after
`end-of-day.sh` writes the journal at 10pm.

See `docs/THREAT-MODEL.md` and `docs/MEMORY.md`.

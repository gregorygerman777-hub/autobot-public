# Scripts

Automation scripts for cron jobs. All scripts use `autobot -p` to run pi in non-interactive (print) mode.

## Available Scripts

| Script | Description | Suggested Cron |
|--------|-------------|----------------|
| `daily-briefing.sh` | Morning summary across all channels (gws, slack, messages), sent to Telegram | `0 8 * * *` |
| `auto-homework.sh` | Checks school portal for upcoming assignments, attempts to complete them | `0 18 * * *` |
| `end-of-day.sh` | Writes a journal entry summarizing the day's conversations and calendar | `0 22 * * *` |
| `poll.sh` | Checks all inbound channels, sends Telegram alert only if something urgent | `*/10 * * * *` |
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
*/10 * * * * /path/to/autobot/scripts/poll.sh >> /tmp/assistant-poll.log 2>&1
```

## Customization

These scripts are starting templates. Customize the prompts, schedules, and which skills they invoke to match your workflow. For example:

- Change `auto-homework.sh` to check a different task system
- Adjust `daily-briefing.sh` to only check the channels you use
- Modify `poll.sh` frequency based on how often you want to be notified

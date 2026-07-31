# Autobot

Personal AI assistant powered by [pi](https://github.com/badlogic/pi-mono).

## Quick Start

```bash
git clone https://github.com/Wesius/autobot.git
cd autobot
./autobot install
```

That's it. Clones submodules, installs uv if needed, builds pi from source,
installs Python deps, symlinks `autobot` into your PATH, and walks you through
configuring your integrations.

The assistant will guide you through configuring integrations and personalizing your profile.

## What's Inside

- **14 skills** — Slack, Messages, Email, Telegram, Notion, Calendar, Reminders, Contacts, School Portal, Search, Daily Briefing, Triage Inbox, Memory, Setup
- **CLI tools** — Slack reader, Messages reader/sender, Telegram sender, Notion client, School portal, Finance tracker
- **Cron scripts** — Daily briefing, inbox polling, end-of-day journal, auto-homework
- **Persistent memory** — Profile, preferences, people, projects, journal entries
- **Telegram bot** — Two-way messaging via long-polling listener

## Requirements

- [Node.js](https://nodejs.org/) >= 22 (to build pi from source)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- macOS (for Messages, Contacts, Calendar, Reminders integration)
- [gws](https://github.com/AyrisDev/gws-cli) (optional, for Google Workspace)

## License

MIT

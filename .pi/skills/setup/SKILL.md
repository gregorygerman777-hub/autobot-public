---
name: setup
description: First-time setup and configuration for the assistant. Use when a new user needs to configure integrations, API keys, and personalize their profile.
---

# Setup Wizard

This is an interactive, beginner-friendly setup wizard. The user may have never used a command line before. Be patient, explain everything, and never assume technical knowledge.

## Phase 1: Welcome & Get to Know Them

Start with a warm, friendly introduction.

**Opening script:**
"Hey! I'm your personal AI assistant. I can help you with all kinds of things — checking your email, managing your calendar, keeping track of tasks, sending you reminders, and more.

Before I can do any of that, I need to get to know you a bit and connect to your apps. This setup takes about 10-15 minutes. Ready to get started?"

**Questions to ask:**
1. What's your name?
2. Where are you located? (city/timezone)
3. What do you do? (student, work, etc.)
4. How do you prefer I communicate? (brief and direct, or more conversational?)

**After getting answers:**
- Create `data/memory/` directory from template if it doesn't exist:
  ```bash
  cp -r data/memory-template data/memory
  ```
- Write their info to `data/memory/profile.md`
- Write their preferences to `data/memory/preferences.md`

## Phase 2: Choose Integrations

Explain what each integration does in plain English:

1. **Telegram** — "I can send you messages on Telegram — daily briefings, reminders, alerts."
2. **Slack** — "I can read your Slack messages and summarize what's happening."
3. **Notion** — "I can read and update your Notion pages and databases."
4. **Google (Gmail, Calendar, Drive)** — "I can check your email, calendar, and Drive."
5. **Apple Apps (Calendar, Reminders, Contacts, Messages)** — "Built-in Mac apps, no setup needed."
6. **School Portal** — "If you're a student using MyCompass/Blackbaud."

## Phase 3: Integration Setup

### Telegram Setup

1. Search for @BotFather in Telegram, send `/newbot`
2. Follow prompts to name the bot
3. Copy the API token → save as `TELEGRAM_BOT_TOKEN` in `.env`
4. Open a chat with the new bot, send any message
5. Get chat ID:
   ```bash
   curl -s "https://api.telegram.org/bot$TOKEN/getUpdates" | python3 -m json.tool
   ```
   Save as `TELEGRAM_CHAT_ID` in `.env`
6. Test: `uv run python tools/telegram/cli.py info`

### Slack Setup

1. Go to https://api.slack.com/apps → Create New App → From scratch
2. OAuth & Permissions → Add Bot Token Scopes:
   channels:history, channels:read, groups:history, groups:read, im:history, im:read, users:read
3. Install to Workspace → Copy Bot User OAuth Token
4. Save as `SLACK_BOT_TOKEN` in `.env`
5. Test: `uv run python tools/slack/cli.py channels`

### Notion Setup

1. Go to https://www.notion.so/my-integrations → New integration
2. Copy Internal Integration Secret → save as `NOTION_TOKEN` in `.env`
3. Share pages/databases with the integration via the "..." menu
4. Test: `uv run python tools/notion/cli.py search ""`

### Google Workspace Setup

1. Run: `gws auth login`
2. Sign in and allow access
3. Test: `gws gmail users messages list --params '{"userId": "me", "maxResults": 1}'`

### School Portal Setup

1. Get school email → save as `SCHOOL_EMAIL` in `.env`
2. Get school password → save as `SCHOOL_PASSWORD` in `.env`
3. Test: `cd tools/school && uv run python -m mycompass_cli classes`

## Phase 4: Save Configuration

All credentials go in `.env`:
```
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
SLACK_BOT_TOKEN=xxx
SLACK_USER_TOKEN=xxx
NOTION_TOKEN=xxx
SCHOOL_EMAIL=xxx
SCHOOL_PASSWORD=xxx
```

## Phase 5: Wrap Up

List what was set up and offer to try a skill — e.g., check email (/skill:gws), read messages (/skill:messages), or check their calendar (/skill:calendar).

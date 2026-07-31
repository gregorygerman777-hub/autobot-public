---
name: memory
description: Persistent memory system. The agent should use this to recall context about people, projects, and past interactions, and to store new information learned during conversations. Automatically invoked when relevant.
user-invocable: false
---

# Memory System

You have a persistent filesystem-based memory at `data/memory/`. Use it actively — read when you need context, write when you learn something new.

## Structure

```
data/memory/
├── profile.md              # Slim, non-sensitive core facts (auto-injected every session)
├── preferences.md          # Learned preferences (auto-injected every session)
├── pii.md                  # Sensitive PII (SSN, addresses, financial, travel docs) — read on demand, NEVER auto-injected
├── contacts.md             # Phone numbers + emails (user + family) — read on demand, NEVER auto-injected
├── people/                 # One file per person (name-slug.md)
├── projects/
│   ├── school/             # Classes and schoolwork
│   ├── personal/           # Personal projects
│   └── coding/             # Coding / side projects
├── journal/                # Daily summaries (YYYY-MM-DD.md)
├── sessions/               # Raw conversation logs (YYYY-MM-DD.jsonl)
└── scratch/                # Ephemeral working notes
```

## When to READ memory

- Start of session: `profile.md` and `preferences.md` are auto-injected — no need to re-read
- When a task needs a phone number or email: read `contacts.md`
- When a task needs sensitive PII (taxes, bookings, account access, addresses, SSN): read `pii.md`
- **Keep `profile.md` clean:** it is injected into every prompt, so never add raw PII (SSN, addresses, phone/email, account numbers) there — put those in `pii.md` / `contacts.md` instead
- When a person is mentioned: Grep `data/memory/people/` for their name
- When a project/class is mentioned: Grep `data/memory/projects/` for it
- When asked "what happened" or "what did we discuss": read `journal/` entries
- When context seems missing: search across all of `data/memory/`

## When to WRITE memory

- You learn a new fact about the user → update `profile.md` or `preferences.md`
- You learn something about a person → update or create `people/<name>.md`
- A project status changes → update the relevant `projects/` file
- End of a significant conversation → write a `journal/YYYY-MM-DD.md` entry
- A deadline or todo is mentioned → add it to the relevant project file

## File Conventions

### People files (`people/<first>-<last-or-nickname>.md`)
```markdown
# Display Name

- Phone: +1XXXXXXXXXX
- Email: (if known)
- Relationship: friend / classmate / family / colleague
- Context: how the user knows them, shared activities
- Last interaction: YYYY-MM-DD — brief note
```

### Project files (`projects/<category>/<slug>.md`)
```markdown
# Project Name

- Location/repo: path or URL
- Status: active / paused / done
- Key details, deadlines, notes
```

### Journal entries (`journal/YYYY-MM-DD.md`)
```markdown
# YYYY-MM-DD

## Key Events
- What happened today (conversations, tasks, decisions)

## Pending
- Open items, things to follow up on

## Learned
- New facts or preferences discovered
```

## Rules

- Keep files concise — bullet points, not paragraphs
- Update incrementally — don't rewrite whole files, append or edit specific lines
- Use Grep to search before creating duplicates
- Never store sensitive data (passwords, API keys, full message bodies) in memory
- Journal entries should be summaries, not transcripts
- When unsure if something is worth remembering, err on the side of writing it down

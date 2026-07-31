# Memory

This is your personal memory directory. It's gitignored so your data stays private.

## Structure

```
memory/
├── profile.md       # Who you are — name, location, about
├── preferences.md   # How you want the assistant to behave
├── people/          # Files about people you interact with
├── projects/        # Files about ongoing projects, classes, etc.
└── journal/         # Daily journal entries (auto-generated)
```

## How It Works

The memory-loader extension reads `profile.md` and `preferences.md` at the start of every session and injects them into the system prompt. The assistant also reads and writes to `people/`, `projects/`, and `journal/` as needed.

## Setup

This directory is created automatically during `autobot install`. You can also create it manually:

```bash
cp -r data/memory-template data/memory
```

Then edit `profile.md` and `preferences.md` to personalize your assistant.

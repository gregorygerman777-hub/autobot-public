# Autobot

Personal AI assistant powered by [pi](https://github.com/badlogic/pi-mono).

Fork of [Wesius/autobot-public](https://github.com/Wesius/autobot-public), adding
a security and evaluation layer: prompt-injection defenses, an action allowlist,
episodic/semantic memory with consolidation, a reason-act-observe execution loop,
and an accuracy harness with CI.

## Quick Start

```bash
git clone https://github.com/gregorygerman777-hub/autobot-public.git
cd autobot-public
./autobot install
```

Clones submodules, installs uv if needed, builds pi from source, installs Python
deps, symlinks `autobot` into your PATH, and walks you through configuring your
integrations.

## What's Inside

- **12 skills** — Messages, Google Workspace (Gmail/Calendar/Drive), Calendar,
  Reminders, Contacts, School Portal, Search, Browser Tools, Memory,
  Prime Intellect, Claude Subscription, Setup
- **`autobot_core/`** — deterministic security, triage, memory, and loop logic
- **CLI tools** — School portal, Google Classroom, finance tracker, GPU compute
- **Cron scripts** — Daily briefing, inbox polling, end-of-day journal,
  memory consolidation, auto-homework
- **Persistent memory** — Episodic and semantic tiers with nightly consolidation
- **Tests** — 111 unit tests plus a 43-scenario evaluation harness, both in CI

> Upstream's README lists 14 skills including Slack, Telegram, Notion, Daily
> Briefing, and Triage Inbox. Those skill directories are not present in the
> public tree — 12 exist. `poll.sh` and `daily-briefing.sh` still reference
> `/skill:slack` and `/skill:telegram`, which resolve to nothing. Noted rather
> than papered over.

## Why this fork exists

The upstream design has the three properties that make prompt injection a
practical risk rather than a theoretical one: it ingests attacker-controlled
text (email, iMessage, Slack, calendar invites, web pages), it holds sensitive
data (`pii.md`, contacts, a live Gmail token, an authenticated browser profile),
and it can act externally (send mail, send texts, edit contacts, submit
coursework).

`scripts/poll.sh` ran every 10 minutes, read an inbox, and could then send a
message — untrusted input and real-world action in one uninterrupted context,
unattended. The stated security rules ("Sanitize all message content before
passing to LLM") had no implementation.

## What was added

### 1. Prompt injection defenses — [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md)

Untrusted tool output is fenced before the model sees it, with a random 64-bit
nonce in the closing delimiter, so injected text cannot close the region and
re-enter instruction context ([spotlighting](https://arxiv.org/abs/2403.14720),
Hines et al., 2024):

```
<untrusted-data:3ed40fba6b5219c2 source="gmail" trust="untrusted">
  ...attacker-controlled text...
</untrusted-data:3ed40fba6b5219c2>
```

20 capabilities are registered in a closed set with reversibility and external
visibility. Unattended runs that have read untrusted content are restricted to a
three-entry allowlist, none of which is externally visible. The P0-P3 triage
rubric moved out of prose and into deterministic code that scores structural
signals, so a message cannot promote itself by claiming to be urgent.

### 2. Episodic and semantic memory — [`docs/MEMORY.md`](docs/MEMORY.md)

Journal entries were written nightly and read at most once. Durable facts went
stale because nothing reviewed what had happened. Memory now has explicit tiers
([MemGPT](https://arxiv.org/abs/2310.08560), Packer et al., 2023;
[Generative Agents](https://arxiv.org/abs/2304.03442), Park et al., 2023), and a
nightly consolidation job promotes durable facts from episodic entries into the
semantic store.

Consolidation is deterministic Python rather than a prompt, because it is a
laundering path: an attacker's claim in an email becomes a journal line becomes
a permanent fact in an auto-injected file. Untrusted-derived candidates are
queued for a human instead of promoted.

**File paths are unchanged.** Every existing read and write keeps working.

### 3. Reason-act-observe loop — [`docs/EXECUTION-LOOP.md`](docs/EXECUTION-LOOP.md)

The cron scripts were single-shot prompts, so a discovery mid-run had nowhere to
go. Briefing and triage are now ReAct loops
([Yao et al., 2022](https://arxiv.org/abs/2210.03629)) that chain:

```
Thought 2: I should check whether the day actually works before summarizing it.
Action 2: analyze_conflicts
Observation 2: Found 1 conflict, 1 serious: 'Team standup' and '1:1 with Alex'
               are both at 09:00-09:30

Thought 3: That is a real collision. 'Team standup' has 3 attendees and recurs,
           so '1:1 with Alex' is the cheaper one to move. Someone needs to be
           told, so I should draft that message now.
Action 3: draft_conflict_message(target='alex@corp.com', ...)
Observation 3: 'messages.send' not permitted here, recorded as a proposal.
```

Step 3 exists only because of Observation 2. Reasoning is free; acting is not —
a blocked action becomes a proposal carrying its rationale and draft, surfaced
for approval rather than executed or discarded.

### 4. Evaluation harness — [`docs/EVALUATION.md`](docs/EVALUATION.md)

43 scenarios with known-correct answers, run through the same functions the cron
jobs call. Accuracy is appended to `evals/results/history.csv` per run and gated
in CI, so a change that degrades triage quality without throwing fails the build.

It found three real bugs on its first run, all of which had passed the existing
107 unit tests — including a briefing loop that never terminated on ambiguous
calendar conflicts.

## Testing

```bash
./scripts/run-tests.sh     # 111 unit tests
./scripts/run-evals.sh     # 43 scenarios, accuracy vs known answers
```

Both offline: no API keys, no network, no macOS permissions. Both run in CI.

## Known limitations

- **Nothing measures the live model.** Every test exercises the deterministic
  layer. Whether the fence changes model behavior under adversarial pressure is
  unmeasured.
- **`auto-homework.sh` no longer submits coursework.** `school.submit` is denied
  unattended. It was unsafe as designed; re-enabling needs a human approval step.
- **Two defenses rest on prompts, not code** — journal trust marking and
  faithful transcription in the gather phase.
- **`.env` holds plaintext credentials**, unchanged from upstream.

Full residual risk in each doc.

## Requirements

- [Node.js](https://nodejs.org/) >= 22 (to build pi from source)
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- macOS (for Messages, Contacts, Calendar, Reminders integration)
- [gws](https://github.com/AyrisDev/gws-cli) (optional, for Google Workspace)

## License

MIT

# Memory Architecture

**Status:** Checkpoint 2 complete
**Last reviewed:** 2026-09-07

---

## 1. What was wrong

Memory was a flat directory of markdown with no explicit structure. `profile.md`,
`preferences.md`, `people/`, `projects/`, and `journal/` sat side by side, and
the only mechanism was `.pi/extensions/memory-loader.ts` concatenating two of
them plus yesterday's journal into the system prompt.

Two failures followed from that.

**The episodic log was never consumed.** `scripts/end-of-day.sh` wrote a journal
entry every night. The memory-loader read exactly one of them — yesterday's —
the following morning. Every entry older than that was dead weight: written,
read once, then never touched again. After a year the directory holds 365 files
of which one is ever loaded.

**The semantic store went stale.** `profile.md` and `preferences.md` only
changed if the agent happened to notice something mid-conversation and
remembered to write it down. There was no process that reviewed what had
actually happened and updated the durable picture. Facts learned on a Tuesday
stayed buried in `journal/2026-09-08.md` forever.

The two problems are the same problem: nothing connected the tiers, because the
tiers were not distinguished in the first place.

---

## 2. The distinction

Following MemGPT (Packer et al., 2023) and Generative Agents (Park et al.,
2023):

| Tier | Holds | Paths | Lifetime |
|---|---|---|---|
| **Episodic** | Specific dated events | `journal/`, `sessions/` | Append-only, consolidated then retained |
| **Semantic** | Durable facts, preferences, profile | `profile.md`, `preferences.md`, `people/`, `projects/`, `contacts.md`, `pii.md` | Current, small, always loaded |
| **Ephemeral** | Working notes | `scratch/`, `review-queue.md` | No retention guarantee |

MemGPT's framing is a small always-resident *main context* backed by a large
*external context*, with the agent moving information between them. Semantic
memory here is main context — it is injected into every session, so it must stay
small and current. Episodic memory is external context — it can grow, and is
paged in only when relevant.

Park et al. contribute the other half: *reflection*. Their agents periodically
review recent observations and synthesize higher-level statements from them,
rather than only ever accumulating raw events. That is exactly what was missing.

**Physical paths did not change.** `data/memory/profile.md` is still
`data/memory/profile.md`. Any skill that greps `data/memory/people/` works
unchanged. What changed is how memory is organized and maintained, not where it
lives. This is verified by `TestBackwardCompatibility` in `tests/test_memory.py`.

---

## 3. Consolidation

`scripts/consolidate-memory.sh`, nightly at 10:30pm (after `end-of-day.sh` at
10pm). Implemented in `autobot_core/memory/consolidate.py`.

```
journal/*.md written since watermark
        |
        v
  extract candidates      <- only from the "## Learned" section
        |
        v
  score importance        <- durable vs transient language
        |
        v
  safety gates            <- injection scan, trust check
        |
   +----+----+
   |         |
promote   queue for review
   |
   v
semantic tier (+ provenance marker)
```

**Extraction** reads only the `## Learned` section. `## Key Events` is episodic
by definition, and `## Pending` is task state — neither produces durable facts.
This is why the journal format in `memory/SKILL.md` has those headings.

**Importance scoring** (`score_importance`) rates how much a statement deserves
to be durable. Park et al. get this from the model on a 1-10 scale; a
deterministic heuristic is used here so it is testable offline and cannot be
steered by the content being scored. Durable cues ("always", "prefers", "never")
raise it; transient cues ("today", "this morning", "right now") lower it. Below
0.5, the statement stays episodic — "Had coffee at 3pm today" is a real thing
that happened, and it belongs in the journal, not in `preferences.md`.

**Routing** picks a destination: identity language to `profile.md`, preference
language to `preferences.md`, a named person already tracked in `people/` to
that person's file, project language to `projects/`. Unroutable candidates are
not promoted. They stay in the journal, where they already are.

**Corroboration.** A fact seen again is not duplicated; its `seen` count is
incremented. One observation is an anecdote, repeated observation is a pattern,
and the count makes that difference visible.

**Watermark.** `.consolidation-state.json` records the last consolidated date.
Entries are processed exactly once. This is what stops the episodic log growing
forever unconsumed, which was the original complaint.

### Provenance

Every consolidated fact carries a marker:

```markdown
- Greg prefers uv over pip <!-- mem: src=journal/2026-09-05; trust=agent; date=2026-09-05; seen=2 -->
```

An HTML comment, so it is invisible in rendered markdown and ignorable by any
existing reader. Facts written by hand before this existed carry no marker and
are read as `operator` trust, which is the safe interpretation: the user wrote
them.

---

## 4. Why consolidation is not an LLM prompt

Consolidation is a **laundering path**, and this is the main design constraint.

The attack: an attacker sends an email. The agent reads it during the morning
briefing and summarizes it into that night's journal entry. Consolidation reads
the journal and promotes the claim into `preferences.md`. The memory-loader then
injects `preferences.md` into the system prompt of **every future session**.

A one-shot injection has become a permanent standing instruction, and it now
arrives labeled as an established fact about the user. This was residual risk R6
in `docs/THREAT-MODEL.md`, left open by Checkpoint 1.

Three gates close it:

1. **Untrusted-derived content is never auto-promoted.** A journal section
   marked `<!-- mem: trust=external -->` produces candidates with
   `SourceTrust.EXTERNAL`, which is not promotable. They go to
   `data/memory/review-queue.md`.
2. **Every candidate is scanned for injection signals** using the same
   `scan_for_injection` from Checkpoint 1. A hit means quarantine regardless of
   declared trust.
3. **Extraction is deterministic.** The mechanics are Python with 30 tests, not
   a model deciding what to believe. A model asked to "extract facts from this
   journal" can be argued with by the journal's contents.

The review queue is a plain markdown file with checkboxes on purpose. The point
is that a person sees it. `memory-loader.ts` surfaces the pending count at
session start and explicitly states the items are candidates, not facts.

---

## 5. Interfaces

Unchanged. Other skills need no modification.

| Operation | Before | After |
|---|---|---|
| Read profile | `cat data/memory/profile.md` | same |
| Search people | `grep data/memory/people/` | same |
| Write journal | write `journal/YYYY-MM-DD.md` | same |
| Auto-injection | profile + preferences + yesterday's journal | same, now tier-labeled |

New, additive only:

```bash
python -m autobot_core.cli memory-status                    # backlog + watermark
python -m autobot_core.cli memory-consolidate --dry-run     # preview
./scripts/consolidate-memory.sh                             # the cron job
```

`--dry-run` reports every decision without writing anything and without
advancing the watermark.

---

## 6. Verification

```bash
./scripts/run-tests.sh
```

`tests/test_memory.py` (30 tests):

- **Tier classification** — every existing path maps to the right tier.
- **Round-trip** — provenance survives write and read; markers are HTML
  comments; legacy unmarked facts read as operator trust.
- **Consolidation** — promotion from `## Learned`, `## Key Events` explicitly
  *not* promoted, corroboration increments `seen`, watermark prevents
  reprocessing, dry-run writes nothing and does not advance the watermark.
- **Laundering resistance** — external-marked sections never promoted, injection
  payloads quarantined, and an end-state assertion that hostile text never
  reaches the auto-injected files.
- **Backward compatibility** — files are not moved, existing content is
  preserved, journal entries survive consolidation, and output still parses as
  plain markdown for a reader that ignores comments.

---

## 7. Residual risk

**M1 — Trust marking is manual.** A journal section only counts as external if
the writing agent marked it. An agent that summarizes an email into an unmarked
`## Learned` section defeats gate 1. Gates 2 and 3 still apply, but the primary
defense depends on the end-of-day prompt being followed. Automatic taint
propagation from ingest through to journal writing is not implemented.

**M2 — Importance scoring is heuristic.** Deterministic and testable, but
keyword-driven. It will misjudge unusual phrasing in both directions: a durable
fact worded transiently gets skipped, and a transient event worded durably gets
promoted. Promotion is reversible by editing the file, so the cost is low.

**M3 — Routing is coarse.** Four destinations chosen by regex. Facts spanning
categories land in one place. Unroutable facts are silently left episodic and
only visible in the run report.

**M4 — No forgetting.** Semantic memory only grows. Nothing decays, expires, or
resolves contradictions — a superseded preference sits alongside its replacement
until a human removes it. Park et al. use recency-weighted retrieval to
de-emphasize stale memories; that is not implemented here.

**M5 — Nothing rewrites `profile.md` holistically.** Consolidation appends
bullets under a heading. It does not restructure or summarize the file, so
`profile.md` will slowly accumulate rather than staying tight. MemGPT's
recursive summarization would address this.

---

## References

- Packer, C., et al. (2023). *MemGPT: Towards LLMs as Operating Systems.*
- Park, J. S., et al. (2023). *Generative Agents: Interactive Simulacra of Human
  Behavior.*

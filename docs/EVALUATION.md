# Evaluation Harness

**Status:** Checkpoint 4 complete
**Last reviewed:** 2026-09-07

---

## 1. What was wrong

There was no way to know whether a change made the assistant better or worse.

The repo had no tests and no CI. Triage quality lived entirely inside a prompt,
so "did that edit improve things?" could only be answered by running the
briefing and reading it. That is not a measurement — it is a vibe, taken on
whatever handful of emails happened to be in the inbox that morning, with no
record of what the answer was last week.

Checkpoints 1 through 3 moved the decision logic into code
(`autobot_core/triage.py`, `schedule.py`, `loop/flows.py`). This checkpoint
measures it.

---

## 2. Design

Scripted scenarios with known-correct answers, fed through **the actual
functions the cron jobs call**. Not a reimplementation, not a mock: `run-briefing`
in production and the `briefing_flow` suite here both call
`build_briefing_loop`.

```
evals/
├── scenarios/
│   ├── inbox_triage.json        25 messages with known priority labels
│   ├── calendar_conflicts.json  12 calendar situations with known resolutions
│   └── briefing_flow.json        6 end-to-end loop runs
├── runner.py                    loads, runs, scores, records
└── results/history.csv          accuracy per suite per run, committed
```

| Suite | Exercises | Cases |
|---|---|---|
| `inbox_triage` | `autobot_core.triage.triage` | 25 |
| `calendar_conflicts` | `autobot_core.schedule.find_conflicts`, `suggest_resolution` | 12 |
| `briefing_flow` | `autobot_core.loop.flows.build_briefing_loop` | 6 |

The inbox suite is not only happy-path. Eight cases are adversarial: messages
that declare themselves urgent with nothing corroborating it, urgent-sounding
marketing, and five injection payloads that must be quarantined rather than
promoted. One case pairs a genuine deadline with an injection attempt, and
asserts the priority is scored on structure while the quarantine flag still
fires — so the action guard refuses even though the message is legitimately P0.

### Tracking over time

Every run appends to `evals/results/history.csv`:

```csv
timestamp,commit,suite,total,passed,accuracy,failures
2026-09-07T16:24:01,7c0f573,inbox_triage,25,23,0.9200,p0-meeting-moved-today|p1-reschedule-not-today
2026-09-07T16:26:24,7c0f573,inbox_triage,25,25,1.0000,
```

Failing case IDs are recorded, not just the count, so a regression names itself.
The file is committed on purpose — the history *is* the artifact. The runner
reads the previous overall figure and prints the delta, flagging `REGRESSION`
when accuracy drops.

---

## 3. What it caught immediately

The harness found three real bugs on its first run, at 93.0% overall. All three
had passed code review and the existing 107 unit tests.

**`\b` blocked every suffixed form.** `_MEETING_CHANGE` matched on the stem
`reschedul` with a trailing `\b`. No suffixed form can satisfy a word boundary
mid-word, so "rescheduled" — the way people actually write it — never matched.
"Our standup today has been rescheduled to 3pm" scored P2 instead of P0. Same
latent bug for `postpone` and `relocat`.

**An unresolved overlap in the original rubric.** The prose in `gws/SKILL.md`
listed "Direct questions" under P0 and "scheduling asks" under P1, and never
said which wins when a scheduling ask is phrased as a question. "Can we move our
Thursday sync to Friday?" hit both and scored P0. Resolved in favor of the more
specific category, unless it concerns today. This was a genuine ambiguity in the
spec, surfaced only because two scenarios encoded incompatible expectations.

**A non-terminating loop.** The briefing reasoner guarded its conflict branch on
`"draft_conflict_message" not in done`, but the ambiguous path calls
`note_conflict_for_operator` instead. The guard stayed true forever and the run
burned all 12 steps producing nothing. The unit test asserted the right action
was taken but never that the run *ended*, so it passed.

That last one is the argument for this harness existing. Unit tests check the
step you thought about; end-to-end scenarios check that the whole thing
terminates and produces the artifact. All three now have regression tests
(111 unit tests, up from 107).

---

## 4. Running it

```bash
./scripts/run-evals.sh                     # full report
./scripts/run-evals.sh --suite inbox_triage
./scripts/run-evals.sh --json              # machine-readable
./scripts/run-evals.sh --fail-under 0.95   # exit non-zero below threshold
./scripts/run-evals.sh --no-record         # skip the history CSV
```

```
briefing_flow          [############################] 100.0%  (6/6)
calendar_conflicts     [############################] 100.0%  (12/12)
inbox_triage           [############################] 100.0%  (25/25)
--------------------------------------------------------------------
OVERALL                100.0%  (43/43)
vs previous run         93.0%  (+7.0%)
```

Failures print expected, actual, a specific mismatch, and the scenario's note.

### CI

`.github/workflows/tests.yml` runs unit tests, then the harness with
`--fail-under 1.0`, then lint, a CLI smoke check, and a shell parse check. The
accuracy gate matters: a prompt or rule change that degrades triage quality
without throwing an exception fails the build.

### Adding a scenario

Add a case to the relevant JSON file. No code changes needed.

```json
{
  "id": "p0-something-new",
  "expected": {"priority": "P0", "quarantined": false},
  "note": "Why this is the right answer",
  "message": {"source": "gmail", "sender": "...", "subject": "...", "body": "..."}
}
```

Prefer cases where the correct answer is defensible from the rubric. A scenario
encoding a judgment call becomes a constraint on every future change.

---

## 5. Residual risk

**E1 — 100% measures the scenarios, not the world.** 43 cases written alongside
the implementation. They encode what the author thought to test, and share its
blind spots. The figure means "no known regressions", not "triage is correct".

**E2 — Scenarios were written after the code.** Some cases were written to match
observed behavior rather than derived independently. Two were not — they
disagreed with the implementation and the implementation was wrong — but that
was luck, not method. Scenarios written before the logic would be stronger.

**E3 — Nothing measures the live model.** Every suite exercises the
deterministic layer. Whether the fenced prompt actually changes model behavior
under adversarial pressure, and whether phase 1 of the cron scripts transcribes
messages faithfully, are unmeasured. This is the largest gap: the parts of the
system a real attacker interacts with are the parts not covered here. A live
layer would need API credentials, cost money per run, and be non-deterministic,
so it cannot gate CI — it would be a separate opt-in target.

**E4 — The corpus is small and synthetic.** 25 messages is enough for
regressions, not for a meaningful accuracy estimate. No real inbox has been run
through it, and real mail is messier than anything written by hand.

**E5 — The gate is set to 1.0.** Convenient while everything passes, brittle
later: the first legitimately hard scenario forces either lowering the bar or
special-casing. A per-suite threshold would age better.

**E6 — No inter-rater check on labels.** Every expected answer was set by one
author. `p1-reschedule-not-today` shows the risk — its label contradicted the
implementation, and deciding which was right meant resolving an ambiguity in the
original prose rubric by fiat.

---

## 6. Relationship to the unit tests

Both, for different jobs.

`./scripts/run-tests.sh` (111 tests) checks units in isolation: does the fence
neutralize a forged delimiter, does the allowlist deny `gmail.send`, does
consolidation refuse to promote untrusted content.

`./scripts/run-evals.sh` (43 scenarios) checks end-to-end behavior against
known-correct answers, and tracks the number over time.

The non-terminating loop is the case for keeping both: the unit test asserted
the correct action was taken, and passed, while the run never finished.

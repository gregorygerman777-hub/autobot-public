# Execution Loop

**Status:** Checkpoint 3 complete
**Last reviewed:** 2026-09-07

---

## 1. What was wrong

Every cron script was a single-shot prompt. One trigger, one prompt, one pass:

```bash
autobot -p "Generate a morning briefing: check email, Slack, and Messages.
            Summarize what's urgent... Send the briefing to Telegram."
```

There was no cycle. The agent gathered, summarized, sent, and exited. Nothing
carried from one observation to the next decision, because there was no "next
decision" — the run was over.

The cost shows up whenever something is discovered mid-run. If the briefing
noticed that two meetings collided at 9am, there was nowhere for that to go. It
could mention the collision in the summary text, but it could not *act* on it.
Doing something about it would have required a separate trigger, with no memory
of why, no access to which events collided, and no connection to the reasoning
that found the problem. Three unrelated runs, one of which has already
forgotten what the other two saw.

---

## 2. The pattern

ReAct (Yao et al., 2022) interleaves reasoning traces with actions:

```
Thought 1  -> Action 1 -> Observation 1
Thought 2  -> Action 2 -> Observation 2      (Thought 2 conditioned on Observation 1)
...
```

The value is the conditioning. Each thought sees what the last action actually
returned, so the sequence can change course based on what it found rather than
executing a fixed script. Yao et al.'s framing is that reasoning helps the model
decide what to do next, and acting gives the reasoning real information to work
with; neither alone does what the pair does.

Implemented in `autobot_core/loop/`:

| File | Role |
|---|---|
| `types.py` | `ActionCall`, `Observation`, `Step`, `Trace`, `Proposal` |
| `engine.py` | The cycle, the policy gate, termination |
| `flows.py` | Briefing and triage reasoners, tools, assembly |

**The reasoner is pluggable.** `flows.py` supplies deterministic rule-based
reasoners so behavior is testable offline and measurable by the Checkpoint 4
harness. A model-backed reasoner satisfies the same `Reasoner` type and can be
substituted without touching the engine.

---

## 3. Worked example

The chaining case, from an actual run (`--trace`):

```
Thought 1: I need today's schedule before I can say anything about the day.
Action 1: get_calendar
Observation 1: Retrieved 3 calendar event(s) for today.

Thought 2: I have 3 event(s). I should check whether the day actually works
           before summarizing it.
Action 2: analyze_conflicts
Observation 2: Found 1 conflict(s), 1 serious: 'Team standup' and '1:1 with
               Alex' are both at 09:00-09:30

Thought 3: That is a real collision. 'Team standup' has 3 attendee(s) and
           recurs, so '1:1 with Alex' is the cheaper one to move. Someone needs
           to be told, so I should draft that message now rather than leaving it
           for a separate run.
Action 3: draft_conflict_message(target='alex@corp.com', draft="Hi - I have a
          conflict at 09:00 today...")
Observation 3: 'messages.send' not permitted here, recorded as a proposal for
               the operator.

Thought 4: Schedule handled. Now the inbox, so the brief covers what came in.
Action 4: get_inbox
...
```

**Step 3 exists only because of Observation 2.** That is the whole point. With a
clear calendar the loop goes straight from `analyze_conflicts` to `get_inbox`,
which `test_no_conflict_means_no_follow_up` asserts. The follow-up is
conditional, not a script step that always fires.

The loop also declines to overreach: when two colliding events are equally
weighted, `suggest_resolution` returns `ask` and the reasoner routes to
`note_conflict_for_operator` instead of drafting anything
(`test_ambiguous_conflict_defers_to_operator`).

---

## 4. Interaction with the action policy

This is where Checkpoint 3 and Checkpoint 1 meet, and the resolution matters.

A loop that can chain is a loop that can reason its way toward actions nobody
approved. The naive failure mode: the briefing decides a conflict warrants a
text message and sends one, unattended, to a contact — exactly the capability
Checkpoint 1 removed.

**Reasoning is free; acting is not.** Every tool with real-world effects
declares a `gated_action`, and the engine evaluates it against
`autobot_core.actions` before execution. When policy refuses, the run does not
die and the conclusion is not discarded. It becomes a `Proposal` on the trace:

```
Proposals requiring approval:
  - messages.send -> alex@corp.com: Resolve conflict: 'Team standup' and
    '1:1 with Alex' are both at 09:00-09:30
```

The cron scripts surface these under "Proposed (needs your approval)" with the
draft text attached. The operator gets the loop's full reasoning and a ready
message, and makes the call themselves.

So the loop is allowed to conclude *someone should be told*. It is not allowed
to be the one who tells them, unattended. `TestPolicyIsNotEscapable` asserts
this in both modes, including that a blocked action keeps its rationale and
draft rather than being silently dropped.

Ingest also sets taint: `get_inbox` sets `untrusted_in_scope`, and a triage
result flagged as an injection attempt sets `injection_suspected`. Both feed the
policy gate, so reading a hostile message tightens what the rest of that same
run may do.

---

## 5. How the cron scripts use it

Three phases, splitting what each side is good at:

```
PHASE 1  agent gathers   -> messy sources to structured JSON
PHASE 2  loop reasons    -> deterministic scoring, conflict detection, chaining
PHASE 3  agent delivers  -> brief + proposals to Telegram
```

The model pulls data out of Gmail and Messages, which is genuinely hard and
model-shaped work. The decision logic runs in Python, where it is deterministic,
testable, and cannot be talked out of its conclusions by the content it is
reasoning about.

Phase 1 prompts explicitly forbid judging urgency, and forbid setting
`sender_is_known_contact` based on what a message claims about itself — that
comes from `data/memory/contacts.md` and `data/memory/people/`.

```bash
python3 -m autobot_core.cli run-briefing --events e.json --messages m.json --trace
python3 -m autobot_core.cli run-triage --messages m.json --mode autonomous
```

---

## 6. Scope

Applied to **daily briefing** and **inbox triage** only, as the proof of
concept. `end-of-day.sh`, `auto-homework.sh`, and `consolidate-memory.sh` keep
their existing invocation paths, and all 12 skills are unchanged. Rewriting
every invocation path was explicitly not the goal; demonstrating the pattern on
the two flows where chaining actually pays was.

---

## 7. Verification

`tests/test_loop.py` (19 tests):

- **Engine** — terminates on finish, enforces the step limit, survives unknown
  actions and tool exceptions without dying.
- **Chaining** — conflict discovery triggers a follow-up whose position in the
  trace is after the analysis that motivated it; a clear calendar produces no
  follow-up; the drafted message targets the right person; ambiguous conflicts
  defer to the operator.
- **Policy** — blocked sends become proposals with rationale and draft intact,
  in both autonomous and interactive mode.
- **Triage flow** — urgent items notify, quiet inboxes stay quiet, injection
  attempts are reported even when nothing is urgent.

One real bug was caught by these tests during development: the triage reasoner's
terminal branch overwrote `result` with an empty string after a notification had
already been composed, so an injection-only run reported nothing. Fixed by
ordering the notified branch first.

---

## 8. Residual risk

**L1 — The reasoners are rule-based.** They chain correctly and are fully
testable, but they follow written rules, not open-ended reasoning. A situation
the rules do not anticipate produces no interesting behavior. Swapping in a
model-backed reasoner is supported by the type, but then the guarantees in §7
weaken to whatever the model does — which is precisely what Checkpoint 4's live
layer is for measuring.

**L2 — The step limit is a blunt stop.** `MAX_STEPS` prevents runaway loops but
a flow that hits it returns partial results with `stopped_reason` set. Nothing
retries or degrades gracefully.

**L3 — Phase 1 remains a trust boundary.** The loop's determinism only covers
phase 2. If the model transcribes a message body incorrectly, or is talked into
mis-setting `sender_is_known_contact`, the rubric scores wrong input correctly.
The prompt forbids this; nothing enforces it.

**L4 — Proposals have no lifecycle.** They are printed for the operator and
forgotten. There is no queue, no expiry, no way to approve one later without
redoing the work. A conflict found three mornings running produces three
identical proposals.

**L5 — Conflict resolution is heuristic.** `suggest_resolution` weighs attendee
count and recurrence. It does not know which meeting matters, who the user
actually needs to talk to, or that some 1:1s outrank all-hands.

---

## References

- Yao, S., et al. (2022). *ReAct: Synergizing Reasoning and Acting in Language
  Models.*

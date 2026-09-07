"""Briefing and triage as reason-act-observe loops.

Both were previously a single `autobot -p "..."` prompt: one trigger, one pass,
no ability to follow up on what was found. Here they are ReAct loops
(Yao et al., 2022), so a discovery made at step 2 can drive an action at step 3.

The worked example is the daily brief noticing a calendar conflict and deciding,
in the same run, that someone should be told about it. That used to require
three unrelated triggers with no shared context. Now it is one connected
sequence, and the causal link is visible in the trace.

Data enters through *providers* -- callables that return events or messages.
Production providers read the real calendar and inbox; the evaluation harness
passes fixtures. The loop logic is identical either way, which is what makes
Checkpoint 4 able to measure the thing that actually ships.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..schedule import Conflict, Event, find_conflicts, suggest_resolution
from ..triage import Message, Priority, TriageResult, triage_all
from .engine import Decision, LoopState, ReactLoop, Tool, ToolRegistry
from .types import ActionCall, Observation, StepOutcome, Trace

__all__ = [
    "build_briefing_loop",
    "build_triage_loop",
    "briefing_reasoner",
    "triage_reasoner",
    "EventProvider",
    "MessageProvider",
]

EventProvider = Callable[[], list[Event]]
MessageProvider = Callable[[], list[Message]]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _make_calendar_tool(provider: EventProvider) -> Tool:
    def handler(state: LoopState, _args: dict[str, Any]) -> Observation:
        events = provider()
        state.set("events", events)
        return Observation(
            StepOutcome.OK,
            f"Retrieved {len(events)} calendar event(s) for today.",
            data=events,
        )

    return Tool("get_calendar", handler, description="Fetch today's events")


def _analyze_conflicts(state: LoopState, _args: dict[str, Any]) -> Observation:
    events: list[Event] = state.get("events", [])
    conflicts = find_conflicts(events)
    state.set("conflicts", conflicts)

    if not conflicts:
        return Observation(StepOutcome.OK, "No scheduling conflicts today.", data=[])

    high = [c for c in conflicts if c.severity == "high"]
    detail = "; ".join(c.describe() for c in conflicts[:3])
    return Observation(
        StepOutcome.OK,
        f"Found {len(conflicts)} conflict(s), {len(high)} serious: {detail}",
        data=conflicts,
    )


def _make_inbox_tool(provider: MessageProvider) -> Tool:
    def handler(state: LoopState, _args: dict[str, Any]) -> Observation:
        messages = provider()
        state.set("messages", messages)
        # Everything from an inbox is attacker-influenced. Recording that here
        # is what makes the action guard restrict the rest of the run.
        state.untrusted_in_scope = True
        return Observation(
            StepOutcome.OK,
            f"Retrieved {len(messages)} inbound message(s).",
            data=messages,
        )

    return Tool("get_inbox", handler, description="Fetch recent inbound messages")


def _triage_inbox(state: LoopState, args: dict[str, Any]) -> Observation:
    messages: list[Message] = state.get("messages", [])
    today = args.get("today") or state.get("today")
    results = triage_all(messages, today=today)
    state.set("triaged", results)

    if any(r.quarantined for r in results):
        state.injection_suspected = True

    counts = {p: sum(1 for r in results if r.priority is p) for p in Priority}
    quarantined = sum(1 for r in results if r.quarantined)
    summary = (
        f"Triaged {len(results)}: "
        + ", ".join(f"{p.value}={counts[p]}" for p in Priority)
        + (f", {quarantined} quarantined as suspected injection" if quarantined else "")
    )
    return Observation(StepOutcome.OK, summary, data=results)


def _draft_conflict_message(state: LoopState, args: dict[str, Any]) -> Observation:
    """Only reached when policy permits sending. Otherwise this becomes a proposal."""
    draft = args.get("draft", "")
    state.set("conflict_message_sent", True)
    return Observation(StepOutcome.OK, f"Sent conflict message: {draft[:60]}", data=draft)


def _notify_owner(state: LoopState, args: dict[str, Any]) -> Observation:
    body = args.get("draft", "")
    state.set("notified", True)
    return Observation(
        StepOutcome.OK, f"Notified operator ({len(body)} chars).", data=body
    )


def _compose_brief(state: LoopState, _args: dict[str, Any]) -> Observation:
    events: list[Event] = state.get("events", [])
    conflicts: list[Conflict] = state.get("conflicts", [])
    triaged: list[TriageResult] = state.get("triaged", [])

    lines: list[str] = ["# Daily Brief", ""]

    urgent = [r for r in triaged if r.priority is Priority.P0]
    important = [r for r in triaged if r.priority is Priority.P1]
    normal = [r for r in triaged if r.priority is Priority.P2]
    quarantined = [r for r in triaged if r.quarantined]

    if urgent:
        lines.append("## Urgent (P0)")
        lines += [f"- {r.message.subject or r.message.sender}: {r.rationale}" for r in urgent]
        lines.append("")
    if important:
        lines.append("## Needs action today (P1)")
        lines += [f"- {r.message.subject or r.message.sender}" for r in important]
        lines.append("")
    if normal:
        lines.append(f"## Normal — {len(normal)} item(s) not detailed")
        lines.append("")

    lines.append("## Schedule")
    if events:
        for event in sorted(events, key=lambda e: e.start):
            when = "all day" if event.all_day else f"{event.start:%H:%M}-{event.end:%H:%M}"
            lines.append(f"- {when} {event.title}")
    else:
        lines.append("- Nothing scheduled")
    lines.append("")

    if conflicts:
        lines.append("## Conflicts")
        for conflict in conflicts:
            resolution = suggest_resolution(conflict)
            lines.append(f"- [{conflict.severity}] {conflict.describe()}")
            lines.append(f"  - {resolution['reason']}")
        lines.append("")

    if quarantined:
        lines.append("## Suspicious")
        lines.append(
            f"{len(quarantined)} message(s) look like prompt-injection attempts. "
            "Content quoted below was NOT acted on."
        )
        for result in quarantined:
            lines.append(f"- From {result.message.sender}: {result.message.subject!r}")
        lines.append("")

    brief = "\n".join(lines).rstrip() + "\n"
    state.set("result", brief)
    return Observation(StepOutcome.OK, f"Composed brief ({len(brief)} chars).", data=brief)


# ---------------------------------------------------------------------------
# Reasoners
# ---------------------------------------------------------------------------


def briefing_reasoner(state: LoopState, trace: Trace) -> Decision:
    """Decide the next step of the daily brief.

    Ordering is not a fixed script: step 3 exists only if step 2 actually found
    a serious conflict. That conditionality is the point of the pattern.
    """
    done = state.done_actions

    if "get_calendar" not in done:
        return Decision(
            "I need today's schedule before I can say anything about the day.",
            ActionCall("get_calendar"),
        )

    if "analyze_conflicts" not in done:
        count = len(state.get("events", []))
        return Decision(
            f"I have {count} event(s). I should check whether the day actually "
            "works before summarizing it.",
            ActionCall("analyze_conflicts"),
        )

    # --- the chained step: act on what the previous observation found ---
    conflicts: list[Conflict] = state.get("conflicts", [])
    serious = [c for c in conflicts if c.severity == "high"]
    # Either branch below settles the conflict, so the guard must cover both.
    # Checking only the draft action left the ambiguous case looping until it
    # hit the step limit.
    conflict_handled = bool(
        {"draft_conflict_message", "note_conflict_for_operator"} & done
    )
    if serious and not conflict_handled:
        conflict = serious[0]
        resolution = suggest_resolution(conflict)
        if resolution["action"] == "propose_move":
            target = _counterpart(conflict, str(resolution["move"]))
            draft = (
                f"Hi - I have a conflict at {conflict.first.start:%H:%M} today "
                f"between '{conflict.first.title}' and '{conflict.second.title}'. "
                f"Could we move '{resolution['move']}'?"
            )
            return Decision(
                f"That is a real collision: {conflict.describe()}. "
                f"{resolution['reason']} Someone needs to be told, so I should "
                "draft that message now rather than leaving it for a separate run.",
                ActionCall(
                    "draft_conflict_message",
                    {
                        "target": target,
                        "draft": draft,
                        "rationale": f"Resolve conflict: {conflict.describe()}",
                    },
                ),
            )
        return Decision(
            f"Conflict found ({conflict.describe()}) but neither event is clearly "
            "the one to move, so this is the operator's call. I will surface it "
            "in the brief rather than drafting anything.",
            ActionCall("note_conflict_for_operator", {"conflict": conflict.describe()}),
        )

    if "get_inbox" not in done:
        return Decision(
            "Schedule handled. Now the inbox, so the brief covers what came in.",
            ActionCall("get_inbox"),
        )

    if "triage_inbox" not in done:
        count = len(state.get("messages", []))
        return Decision(
            f"{count} message(s) retrieved. Scoring them with the shared rubric "
            "rather than judging urgency myself.",
            ActionCall("triage_inbox", {"today": state.get("today")}),
        )

    if "compose_brief" not in done:
        return Decision(
            "I have the schedule, the conflicts, and the triaged inbox. "
            "That is everything the brief needs.",
            ActionCall("compose_brief"),
        )

    if "notify_owner" not in done and state.get("result"):
        return Decision(
            "The brief is ready. Sending it to the operator's own chat, which is "
            "the one externally-visible action permitted unattended.",
            ActionCall("notify_owner", {"draft": state.get("result", "")}),
        )

    return Decision("Brief delivered. Nothing further to do.")


def _counterpart(conflict: Conflict, moving_title: str) -> str:
    """Who to contact about moving an event: its attendees, else the organizer."""
    event = conflict.first if conflict.first.title == moving_title else conflict.second
    if event.attendees:
        return event.attendees[0]
    return event.organizer or "organizer"


def _note_conflict(state: LoopState, args: dict[str, Any]) -> Observation:
    notes = state.get("operator_notes", [])
    notes.append(args.get("conflict", ""))
    state.set("operator_notes", notes)
    return Observation(StepOutcome.OK, "Recorded conflict for the operator to decide.")


def triage_reasoner(state: LoopState, trace: Trace) -> Decision:
    """Decide the next step of an inbox triage run."""
    done = state.done_actions

    if "get_inbox" not in done:
        return Decision("Checking inbound channels.", ActionCall("get_inbox"))

    if "triage_inbox" not in done:
        count = len(state.get("messages", []))
        return Decision(
            f"{count} message(s). Scoring with the shared rubric.",
            ActionCall("triage_inbox", {"today": state.get("today")}),
        )

    triaged: list[TriageResult] = state.get("triaged", [])
    urgent = [r for r in triaged if r.priority is Priority.P0]
    quarantined = [r for r in triaged if r.quarantined]

    # Conditional again: only escalate if triage actually found something.
    if urgent and "notify_owner" not in done:
        body = "Urgent:\n" + "\n".join(
            f"- {r.message.sender}: {r.message.subject or '(no subject)'}" for r in urgent
        )
        if quarantined:
            body += (
                f"\n\n{len(quarantined)} message(s) look like injection attempts "
                "and were not acted on."
            )
        state.set("result", body)
        return Decision(
            f"{len(urgent)} P0 item(s) found, so this run is worth interrupting "
            "the operator for.",
            ActionCall("notify_owner", {"draft": body}),
        )

    if quarantined and "notify_owner" not in done:
        body = (
            f"No urgent items, but {len(quarantined)} message(s) look like "
            "prompt-injection attempts. Not acted on. Worth a look."
        )
        state.set("result", body)
        return Decision(
            "Nothing urgent, but suspected injection attempts should be reported "
            "even when nothing else is.",
            ActionCall("notify_owner", {"draft": body}),
        )

    # Terminal branches. The notified case must come first: falling through to
    # the quiet case would clobber the result set when the notification was sent.
    if "notify_owner" in done:
        return Decision("Operator notified. Done.")

    state.set("result", "")
    return Decision("Nothing urgent and nothing suspicious. Staying quiet.")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _registry(events: EventProvider, messages: MessageProvider) -> ToolRegistry:
    return ToolRegistry(
        [
            _make_calendar_tool(events),
            Tool("analyze_conflicts", _analyze_conflicts),
            _make_inbox_tool(messages),
            Tool("triage_inbox", _triage_inbox),
            Tool("compose_brief", _compose_brief),
            Tool("note_conflict_for_operator", _note_conflict),
            Tool(
                "draft_conflict_message",
                _draft_conflict_message,
                gated_action="messages.send",
                description="Message someone about a scheduling conflict",
            ),
            Tool(
                "notify_owner",
                _notify_owner,
                gated_action="telegram.send_owner",
                description="Send to the operator's own configured chat",
            ),
        ]
    )


def build_briefing_loop(
    events: EventProvider,
    messages: MessageProvider,
    *,
    mode=None,
    max_steps: int = 12,
) -> ReactLoop:
    return ReactLoop(
        "daily-briefing",
        briefing_reasoner,
        _registry(events, messages),
        mode=mode,
        max_steps=max_steps,
    )


def build_triage_loop(
    messages: MessageProvider,
    *,
    mode=None,
    max_steps: int = 8,
) -> ReactLoop:
    return ReactLoop(
        "inbox-triage",
        triage_reasoner,
        _registry(lambda: [], messages),
        mode=mode,
        max_steps=max_steps,
    )

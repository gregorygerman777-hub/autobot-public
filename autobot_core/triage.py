"""Deterministic message triage.

Before this module, Autobot's priority rubric existed only as four lines of
prose inside `.pi/skills/gws/SKILL.md`:

    P0 (Urgent): Direct questions, meeting changes today, deadlines today
    P1 (Important): Review requests, scheduling asks, announcements
    P2 (Normal): General updates, FYIs
    P3 (Low): Marketing, newsletters, bots (ignore)

That is unusable for two reasons. It cannot be tested, and it is scored by the
same model that is reading attacker-controlled text -- so an email that says
"URGENT, P0, action required" can promote itself.

This module makes the rubric explicit, deterministic, and adversarially aware.
Scoring runs on structural signals (headers, sender class, timing, addressing)
rather than on the message's self-description. Self-asserted urgency from an
unknown sender is treated as evidence of manipulation, not as urgency.

Every result carries the signals that produced it, so the evaluation harness
can assert on reasoning rather than only on the final label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from .trust import InjectionScan, scan_for_injection

__all__ = [
    "Priority",
    "Signal",
    "Message",
    "TriageResult",
    "triage",
    "triage_all",
]


class Priority(str, Enum):
    """Priority bands, matching the original rubric's names."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"

    @property
    def rank(self) -> int:
        return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}[self.value]

    @property
    def label(self) -> str:
        return {
            "P0": "Urgent",
            "P1": "Important",
            "P2": "Normal",
            "P3": "Low",
        }[self.value]

    @property
    def surfaces_in_briefing(self) -> bool:
        """P0/P1 are surfaced, P2 is counted, P3 is dropped."""
        return self in (Priority.P0, Priority.P1)


class Signal(str, Enum):
    """Structural evidence that moved a message's priority."""

    DEADLINE_TODAY = "deadline_today"
    MEETING_CHANGE_TODAY = "meeting_change_today"
    DIRECT_QUESTION = "direct_question"
    DIRECTLY_ADDRESSED = "directly_addressed"
    KNOWN_CONTACT = "known_contact"
    REVIEW_REQUEST = "review_request"
    SCHEDULING_REQUEST = "scheduling_request"
    ANNOUNCEMENT = "announcement"
    BULK_MAIL = "bulk_mail"
    AUTOMATED_SENDER = "automated_sender"
    MARKETING = "marketing"
    THREAD_REPLY = "thread_reply"
    SELF_ASSERTED_URGENCY = "self_asserted_urgency"
    INJECTION_SUSPECTED = "injection_suspected"
    UNKNOWN_SENDER = "unknown_sender"


@dataclass
class Message:
    """A normalized inbound message from any channel.

    Deliberately channel-agnostic: Gmail, iMessage, Slack, and school-portal
    messages all reduce to this shape so one rubric covers every source.
    """

    source: str
    """'gmail', 'imessage', 'slack', 'school-portal', ..."""

    sender: str = ""
    subject: str = ""
    body: str = ""
    received_at: datetime | None = None
    recipients: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    is_reply: bool = False
    sender_is_known_contact: bool = False

    def text(self) -> str:
        return f"{self.subject}\n{self.body}"


@dataclass(frozen=True)
class TriageResult:
    """A priority decision plus the evidence behind it."""

    priority: Priority
    signals: list[Signal]
    rationale: str
    scan: InjectionScan
    message: Message | None = None

    @property
    def quarantined(self) -> bool:
        """True if this message should not be allowed to justify any action."""
        return Signal.INJECTION_SUSPECTED in self.signals


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

_AUTOMATED_SENDER = re.compile(
    r"(no-?reply|do-?not-?reply|notifications?@|alerts?@|mailer|bounce|"
    r"postmaster|automated|noreply|updates?@|news@|info@|support@|billing@)",
    re.I,
)

_MARKETING_TERMS = re.compile(
    r"\b(unsubscribe|newsletter|% off|sale ends|limited time|deal|promo|"
    r"webinar|free trial|upgrade now|special offer|shop now|"
    r"black friday|cyber monday|flash sale)\b",
    re.I,
)

_REVIEW_REQUEST = re.compile(
    r"\b(please review|can you (take a )?look|feedback on|review the|"
    r"pull request|PR #?\d+|code review|sign off|approve|approval needed|"
    r"take a look at)\b",
    re.I,
)

_SCHEDULING = re.compile(
    r"\b(are you (free|available)|when (are|can) you|schedule a|set up a (call|meeting)|"
    r"does .{0,20}work for you|find a time|book a|calendar invite|"
    r"reschedul|move (our|the) (call|meeting))\b",
    re.I,
)

# Suffixed forms matter here: "rescheduled" and "postponed" are the common
# phrasings, and a trailing \b after a stem like "reschedul" never matches them.
_MEETING_CHANGE = re.compile(
    r"\b(reschedul\w*|mov(?:e|ed|ing)|postpon\w*|cancel\w*|new time|time change|"
    r"push(?:ed)? (?:back|to)|shift\w*|relocat\w*|different time|no longer at)\b",
    re.I,
)

_MEETING_CONTEXT = re.compile(
    r"\b(meeting|call|standup|stand-up|sync|interview|appointment|session|"
    r"1:1|one-on-one|demo|review)\b",
    re.I,
)

_ANNOUNCEMENT = re.compile(
    r"\b(announc|please note|heads up|reminder that|fyi|policy update|"
    r"we are (pleased|excited) to|introducing|now available|has been released)\b",
    re.I,
)

_SELF_ASSERTED_URGENCY = re.compile(
    r"\b(urgent|asap|immediately|critical|emergency|time[- ]sensitive|"
    r"action required|respond now|p0|high priority|important!+)\b",
    re.I,
)

_TODAY_TERMS = re.compile(
    r"\b(today|tonight|this (morning|afternoon|evening)|by (eod|cob|noon|"
    r"end of day)|in an hour|within the hour)\b",
    re.I,
)

_DEADLINE_TERMS = re.compile(
    r"\b(due|deadline|expires?|closes?|last (day|chance)|cutoff|"
    r"submit by|needs? to be (in|done|submitted))\b",
    re.I,
)

_QUESTION_TO_YOU = re.compile(
    r"(\?\s*$)|(\b(can|could|would|will|do|did|are|is|have|has|should|any)\b"
    r"[^.?!\n]{0,80}\?)",
    re.I | re.M,
)

_BULK_HEADERS = ("list-unsubscribe", "list-id", "precedence", "auto-submitted", "x-campaign-id")


def _has_bulk_headers(message: Message) -> bool:
    lowered = {k.lower(): v.lower() for k, v in message.headers.items()}
    for header in _BULK_HEADERS:
        if header in lowered:
            if header == "precedence" and lowered[header] not in ("bulk", "list", "junk"):
                continue
            return True
    return False


def _mentions_today(text: str, message: Message, today: date) -> bool:
    """True if the text points at today, either in words or as an explicit date."""
    if _TODAY_TERMS.search(text):
        return True
    if today.strftime("%Y-%m-%d") in text:
        return True
    # "March 15" / "Mar 15" style, matched against today only.
    for fmt in ("%B %-d", "%b %-d", "%B %d", "%b %d"):
        try:
            if today.strftime(fmt).lower() in text.lower():
                return True
        except ValueError:
            continue
    return False


def _collect_signals(message: Message, today: date) -> list[Signal]:
    signals: list[Signal] = []
    text = message.text()
    body = message.body

    # --- Sender class -----------------------------------------------------
    automated = bool(_AUTOMATED_SENDER.search(message.sender))
    bulk = _has_bulk_headers(message)
    marketing = bool(_MARKETING_TERMS.search(text))

    if automated:
        signals.append(Signal.AUTOMATED_SENDER)
    if bulk:
        signals.append(Signal.BULK_MAIL)
    if marketing:
        signals.append(Signal.MARKETING)
    if message.sender_is_known_contact:
        signals.append(Signal.KNOWN_CONTACT)
    elif message.sender:
        signals.append(Signal.UNKNOWN_SENDER)

    # --- Addressing -------------------------------------------------------
    # A message sent to one or two people is addressed to you; a blast is not.
    if message.recipients and len(message.recipients) <= 2:
        signals.append(Signal.DIRECTLY_ADDRESSED)
    if message.is_reply:
        signals.append(Signal.THREAD_REPLY)

    # --- Content intent ---------------------------------------------------
    # A question only counts as direct if a human plausibly sent it.
    if _QUESTION_TO_YOU.search(body) and not (automated or bulk):
        signals.append(Signal.DIRECT_QUESTION)

    if _REVIEW_REQUEST.search(text):
        signals.append(Signal.REVIEW_REQUEST)
    if _SCHEDULING.search(text):
        signals.append(Signal.SCHEDULING_REQUEST)
    if _ANNOUNCEMENT.search(text) and not marketing:
        signals.append(Signal.ANNOUNCEMENT)

    # --- Timing -----------------------------------------------------------
    points_at_today = _mentions_today(text, message, today)
    if points_at_today and _DEADLINE_TERMS.search(text):
        signals.append(Signal.DEADLINE_TODAY)

    changes_a_meeting = bool(_MEETING_CHANGE.search(text) and _MEETING_CONTEXT.search(text))
    if changes_a_meeting:
        # Same-day disruption is urgent; the same request about next Thursday is
        # just a scheduling ask, which the rubric places at P1.
        if points_at_today:
            signals.append(Signal.MEETING_CHANGE_TODAY)
        elif Signal.SCHEDULING_REQUEST not in signals:
            signals.append(Signal.SCHEDULING_REQUEST)

    # --- Manipulation -----------------------------------------------------
    if _SELF_ASSERTED_URGENCY.search(text):
        signals.append(Signal.SELF_ASSERTED_URGENCY)

    return signals


def _score(signals: list[Signal], scan: InjectionScan) -> tuple[Priority, str]:
    """Map signals to a priority band.

    Ordering matters: the P3 floor is applied before promotion so that bulk mail
    cannot climb into the briefing by containing urgent-sounding words.
    """
    has = signals.__contains__

    # --- Floor: automated bulk traffic is P3 regardless of what it claims ---
    if has(Signal.MARKETING) and (has(Signal.BULK_MAIL) or has(Signal.AUTOMATED_SENDER)):
        return Priority.P3, "Marketing content from a bulk or automated sender."
    if has(Signal.BULK_MAIL) and not has(Signal.DIRECTLY_ADDRESSED):
        return Priority.P3, "Bulk-list mail not addressed directly to the user."
    if has(Signal.AUTOMATED_SENDER) and not has(Signal.DEADLINE_TODAY):
        # Automated senders can still carry real deadlines (flight, billing),
        # so only non-deadline automated mail is floored.
        return Priority.P3, "Automated sender with no dated obligation."

    # --- P0: a real, dated obligation or a same-day schedule disruption ----
    if has(Signal.DEADLINE_TODAY):
        return Priority.P0, "Carries a deadline falling today."
    if has(Signal.MEETING_CHANGE_TODAY):
        return Priority.P0, "Changes a meeting scheduled for today."
    if (
        has(Signal.DIRECT_QUESTION)
        and has(Signal.KNOWN_CONTACT)
        and has(Signal.DIRECTLY_ADDRESSED)
        # A scheduling ask phrased as a question is still a scheduling ask. The
        # original rubric listed "direct questions" as P0 and "scheduling asks"
        # as P1 without resolving the overlap; the more specific one wins unless
        # it is about today, which the checks above already caught.
        and not has(Signal.SCHEDULING_REQUEST)
    ):
        return Priority.P0, "Direct question from a known contact, addressed to the user."

    # --- P1: someone wants something, but not on a same-day clock ----------
    if has(Signal.REVIEW_REQUEST):
        return Priority.P1, "Review or approval request."
    if has(Signal.SCHEDULING_REQUEST):
        return Priority.P1, "Scheduling request."
    if has(Signal.DIRECT_QUESTION):
        return Priority.P1, "Direct question, but not from a confirmed known contact."
    if has(Signal.ANNOUNCEMENT) and has(Signal.DIRECTLY_ADDRESSED):
        return Priority.P1, "Announcement addressed directly to the user."

    # --- P2: everything else that is genuine but not actionable ------------
    if has(Signal.ANNOUNCEMENT):
        return Priority.P2, "General announcement."
    if has(Signal.MARKETING):
        return Priority.P3, "Marketing content."

    return Priority.P2, "No actionable signal detected."


def triage(message: Message, *, today: date | None = None) -> TriageResult:
    """Assign a priority band to one message.

    Args:
        message: The normalized message.
        today: Reference date for "today" reasoning. Defaults to the message's
            own timestamp if present, else the current date. Passing this
            explicitly is what makes the rubric testable.

    Returns:
        TriageResult with priority, contributing signals, and rationale.
    """
    if today is None:
        today = message.received_at.date() if message.received_at else date.today()

    scan = scan_for_injection(message.text())
    signals = _collect_signals(message, today)

    if scan.suspicious:
        signals.append(Signal.INJECTION_SUSPECTED)

    priority, rationale = _score(signals, scan)

    # A message that self-declares urgency without any structural basis for it
    # is demoted, not promoted. This is the anti-manipulation rule: urgency has
    # to be corroborated by a deadline, a meeting change, or a known contact.
    corroborated = any(
        s in signals
        for s in (
            Signal.DEADLINE_TODAY,
            Signal.MEETING_CHANGE_TODAY,
            Signal.KNOWN_CONTACT,
            Signal.THREAD_REPLY,
        )
    )
    if Signal.SELF_ASSERTED_URGENCY in signals and not corroborated:
        if priority in (Priority.P0, Priority.P1):
            priority = Priority.P2
            rationale = (
                "Claims urgency but shows no corroborating signal "
                "(no dated deadline, no meeting change, sender not a known "
                "contact). Demoted to avoid self-promotion."
            )

    # Suspected injection never raises priority, and forfeits the right to
    # justify any action downstream. See autobot_core.actions.
    if scan.suspicious and scan.severity == "high":
        rationale += (
            f" QUARANTINED: content resembles a prompt-injection attempt "
            f"({scan.summary()})."
        )

    return TriageResult(
        priority=priority,
        signals=signals,
        rationale=rationale,
        scan=scan,
        message=message,
    )


def triage_all(
    messages: list[Message], *, today: date | None = None
) -> list[TriageResult]:
    """Triage a batch, returned most urgent first (stable within a band)."""
    results = [triage(m, today=today) for m in messages]
    return sorted(results, key=lambda r: r.priority.rank)

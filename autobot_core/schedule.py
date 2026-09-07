"""Calendar conflict detection.

The daily briefing is supposed to notice when the day's schedule does not work.
Doing that required actually modeling the schedule rather than handing raw
`osascript` output to a model and hoping, so this module turns events into a
comparable form and reports conflicts with a suggested resolution.

It is deterministic for the same reason the triage rubric is: the evaluation
harness needs calendar situations with known-correct answers, and a conflict is
either real or it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

__all__ = [
    "Event",
    "ConflictKind",
    "Conflict",
    "find_conflicts",
    "suggest_resolution",
]


@dataclass
class Event:
    """A calendar event, normalized across sources."""

    title: str
    start: datetime
    end: datetime
    calendar: str = ""
    location: str = ""
    attendees: list[str] = field(default_factory=list)
    all_day: bool = False
    organizer: str = ""
    recurring: bool = False

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def overlaps(self, other: Event) -> bool:
        """True if the two occupy the same wall-clock time.

        All-day events are markers, not commitments, so they never conflict.
        Touching boundaries (one ends exactly when the next begins) do not
        overlap either.
        """
        if self.all_day or other.all_day:
            return False
        return self.start < other.end and other.start < self.end

    def overlap_with(self, other: Event) -> timedelta:
        if not self.overlaps(other):
            return timedelta(0)
        return min(self.end, other.end) - max(self.start, other.start)


class ConflictKind(str, Enum):
    DOUBLE_BOOKED = "double_booked"
    """Identical start and end. Someone scheduled straight over the other."""

    OVERLAP = "overlap"
    """Partial overlap."""

    TIGHT_TRANSITION = "tight_transition"
    """Back to back in different physical locations, no travel time."""

    @property
    def severity(self) -> str:
        return {
            "double_booked": "high",
            "overlap": "high",
            "tight_transition": "low",
        }[self.value]


@dataclass
class Conflict:
    """Two events that cannot both work as scheduled."""

    kind: ConflictKind
    first: Event
    second: Event
    overlap: timedelta = timedelta(0)

    @property
    def severity(self) -> str:
        return self.kind.severity

    def describe(self) -> str:
        window = f"{self.first.start:%H:%M}-{self.first.end:%H:%M}"
        other = f"{self.second.start:%H:%M}-{self.second.end:%H:%M}"
        if self.kind is ConflictKind.DOUBLE_BOOKED:
            return f"'{self.first.title}' and '{self.second.title}' are both at {window}"
        if self.kind is ConflictKind.OVERLAP:
            minutes = int(self.overlap.total_seconds() // 60)
            return (
                f"'{self.first.title}' ({window}) overlaps "
                f"'{self.second.title}' ({other}) by {minutes} min"
            )
        gap = int((self.second.start - self.first.end).total_seconds() // 60)
        return (
            f"'{self.first.title}' ends {self.first.end:%H:%M} at "
            f"{self.first.location or 'unknown'}, '{self.second.title}' starts "
            f"{self.second.start:%H:%M} at {self.second.location or 'unknown'} "
            f"({gap} min gap)"
        )


# A transition shorter than this between distinct physical locations is flagged.
TIGHT_TRANSITION_MINUTES = 15

_VIRTUAL_HINTS = ("zoom", "meet.google", "teams", "webex", "http", "phone", "call-in")


def _is_virtual(location: str) -> bool:
    lowered = location.lower()
    return any(hint in lowered for hint in _VIRTUAL_HINTS)


def find_conflicts(events: list[Event]) -> list[Conflict]:
    """Find every scheduling conflict in a set of events.

    Returns conflicts ordered by start time, most severe first within a slot.
    """
    ordered = sorted(events, key=lambda e: (e.start, e.end))
    conflicts: list[Conflict] = []

    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            # Sorted by start, so once we pass the first event's end with a
            # non-overlapping event, later ones cannot overlap it either.
            if second.start >= first.end and not _tight(first, second):
                break

            if first.overlaps(second):
                kind = (
                    ConflictKind.DOUBLE_BOOKED
                    if first.start == second.start and first.end == second.end
                    else ConflictKind.OVERLAP
                )
                conflicts.append(
                    Conflict(kind, first, second, overlap=first.overlap_with(second))
                )
            elif _tight(first, second):
                conflicts.append(Conflict(ConflictKind.TIGHT_TRANSITION, first, second))

    severity_rank = {"high": 0, "low": 1}
    return sorted(
        conflicts, key=lambda c: (c.first.start, severity_rank[c.severity])
    )


def _tight(first: Event, second: Event) -> bool:
    """True if the gap between two events is too short to physically make."""
    if first.all_day or second.all_day:
        return False
    gap = second.start - first.end
    if gap < timedelta(0) or gap >= timedelta(minutes=TIGHT_TRANSITION_MINUTES):
        return False
    if not first.location or not second.location:
        return False
    if first.location.strip().lower() == second.location.strip().lower():
        return False
    # Two virtual meetings need no travel time.
    if _is_virtual(first.location) and _is_virtual(second.location):
        return False
    return True


def suggest_resolution(conflict: Conflict) -> dict[str, object]:
    """Propose which event to move and why.

    The heuristic favors keeping the commitment that is hardest to reschedule:
    more attendees means more calendars to coordinate, and an event the user does
    not organize is not theirs to move unilaterally.
    """
    first, second = conflict.first, conflict.second

    if conflict.kind is ConflictKind.TIGHT_TRANSITION:
        return {
            "action": "flag",
            "move": None,
            "keep": None,
            "reason": (
                f"Only {int((second.start - first.end).total_seconds() // 60)} minutes "
                f"between '{first.title}' and '{second.title}' in different places. "
                "Probably fine if one is remote, tight otherwise."
            ),
        }

    def weight(event: Event) -> tuple[int, int]:
        # Higher is harder to move.
        return (len(event.attendees), 1 if event.recurring else 0)

    keep, move = (first, second) if weight(first) >= weight(second) else (second, first)

    if len(first.attendees) == len(second.attendees) and not (first.recurring or second.recurring):
        reason = (
            f"'{first.title}' and '{second.title}' collide and neither is clearly "
            "more fixed. The user should choose."
        )
        return {"action": "ask", "move": None, "keep": None, "reason": reason}

    reason = (
        f"'{keep.title}' has {len(keep.attendees)} attendee(s)"
        + (" and recurs" if keep.recurring else "")
        + f", so '{move.title}' is the cheaper one to move."
    )
    return {"action": "propose_move", "move": move.title, "keep": keep.title, "reason": reason}

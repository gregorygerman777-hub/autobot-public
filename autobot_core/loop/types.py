"""Types for the reason-act-observe cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

__all__ = [
    "ActionCall",
    "Observation",
    "Step",
    "Trace",
    "Proposal",
    "StepOutcome",
]


class StepOutcome(str, Enum):
    OK = "ok"
    """The action ran and returned a result."""

    BLOCKED = "blocked"
    """Policy refused the action. Recorded as a proposal instead."""

    ERROR = "error"
    """The action failed."""

    FINISHED = "finished"
    """The loop decided no further action is needed."""


@dataclass(frozen=True)
class ActionCall:
    """An action the reasoner decided to take."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if not self.args:
            return self.name
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.args.items()))
        return f"{self.name}({rendered})"


@dataclass
class Observation:
    """What came back from taking an action."""

    outcome: StepOutcome
    summary: str
    """One line, suitable for a trace or a briefing."""

    data: Any = None
    """Structured result, fed back into the next reasoning step."""

    def __bool__(self) -> bool:
        return self.outcome is StepOutcome.OK


@dataclass
class Proposal:
    """An action the loop wanted to take but was not permitted to.

    This is the bridge between Checkpoint 3 and Checkpoint 1. The loop is
    allowed to reason its way to "I should text Alex about the conflict", but in
    an unattended run it may not actually send. Rather than dropping that
    conclusion, it is surfaced to the operator as something to approve.
    """

    action: str
    target: str
    rationale: str
    reason_blocked: str
    draft: str = ""

    def describe(self) -> str:
        head = f"{self.action}" + (f" -> {self.target}" if self.target else "")
        return f"{head}: {self.rationale}"


@dataclass
class Step:
    """One turn of the cycle: thought, action, observation.

    The three-part shape is from ReAct (Yao et al., 2022). The point is that
    reasoning and acting interleave: each thought is conditioned on the previous
    observation, so the loop can change course based on what it actually found
    rather than following a fixed script.
    """

    index: int
    thought: str
    action: ActionCall | None
    observation: Observation

    def render(self) -> str:
        lines = [f"Thought {self.index}: {self.thought}"]
        if self.action:
            lines.append(f"Action {self.index}: {self.action.describe()}")
        lines.append(f"Observation {self.index}: {self.observation.summary}")
        return "\n".join(lines)


@dataclass
class Trace:
    """The full record of a loop run."""

    flow: str
    steps: list[Step] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    result: Any = None
    started_at: datetime = field(default_factory=datetime.now)
    stopped_reason: str = ""

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def actions_taken(self) -> list[str]:
        return [s.action.name for s in self.steps if s.action and s.observation]

    def blocked_actions(self) -> list[str]:
        return [
            s.action.name
            for s in self.steps
            if s.action and s.observation.outcome is StepOutcome.BLOCKED
        ]

    def render(self) -> str:
        body = "\n\n".join(step.render() for step in self.steps)
        header = f"=== {self.flow} ({self.step_count} steps) ==="
        footer = f"Stopped: {self.stopped_reason}"
        if self.proposals:
            footer += "\n\nProposals requiring approval:\n" + "\n".join(
                f"  - {p.describe()}" for p in self.proposals
            )
        return f"{header}\n{body}\n\n{footer}"

    def to_dict(self) -> dict:
        return {
            "flow": self.flow,
            "steps": [
                {
                    "index": s.index,
                    "thought": s.thought,
                    "action": s.action.describe() if s.action else None,
                    "outcome": s.observation.outcome.value,
                    "observation": s.observation.summary,
                }
                for s in self.steps
            ],
            "proposals": [
                {
                    "action": p.action,
                    "target": p.target,
                    "rationale": p.rationale,
                    "blocked_because": p.reason_blocked,
                    "draft": p.draft,
                }
                for p in self.proposals
            ],
            "stopped_reason": self.stopped_reason,
            "step_count": self.step_count,
        }

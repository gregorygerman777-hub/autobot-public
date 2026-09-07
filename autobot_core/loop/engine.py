"""The reason-act-observe loop.

Autobot's cron jobs were single-shot: one trigger, one prompt, one pass. The
briefing gathered channels and wrote a summary; if it noticed a calendar
conflict along the way, there was nowhere for that observation to go. Acting on
it would have been a separate trigger with no memory of why.

This implements the ReAct cycle (Yao et al., 2022): reasoning traces and actions
interleave, so each decision is conditioned on what the previous action actually
returned. The loop can therefore chain -- notice a conflict while building the
brief, decide that warrants telling someone, and draft that message as part of
the same connected sequence.

The reasoner is pluggable. `flows.py` supplies deterministic rule-based
reasoners so the behavior is testable offline and can be measured by the
Checkpoint 4 harness; a model-backed reasoner can be substituted without
changing the engine.

Interaction with Checkpoint 1: the loop reasons freely but does not act freely.
Actions are evaluated against `autobot_core.actions` before execution. A blocked
action does not kill the run and is not silently dropped -- it becomes a
`Proposal` recorded on the trace and surfaced to the operator. The loop is
allowed to conclude "someone should be told"; it is not allowed to be the one
who tells them, unattended.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .. import actions as act
from .types import ActionCall, Observation, Proposal, Step, StepOutcome, Trace

__all__ = ["ReactLoop", "LoopState", "Decision", "ToolRegistry", "Tool"]

MAX_STEPS = 12


class LoopState:
    """Scratch space shared across a run.

    Holds whatever the flow has learned so far. Reasoners read it to decide what
    to do next; tools write to it. Keeping this explicit is what lets a later
    step act on an earlier observation.
    """

    def __init__(self, flow: str, context: dict[str, Any] | None = None):
        self.flow = flow
        self.data: dict[str, Any] = dict(context or {})
        self.done_actions: set[str] = set()
        self.untrusted_in_scope: bool = False
        self.injection_suspected: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def has(self, key: str) -> bool:
        return key in self.data


class Decision:
    """What the reasoner decided to do this turn."""

    def __init__(self, thought: str, action: ActionCall | None = None):
        self.thought = thought
        self.action = action

    @property
    def is_finish(self) -> bool:
        return self.action is None or self.action.name == "finish"


class Tool:
    """A capability the loop can invoke.

    `gated_action` names the entry in `autobot_core.actions.REGISTRY` that this
    tool corresponds to. Read-only tools leave it None and run unconditionally.
    """

    def __init__(
        self,
        name: str,
        handler: Callable[[LoopState, dict[str, Any]], Observation],
        *,
        gated_action: str | None = None,
        description: str = "",
    ):
        self.name = name
        self.handler = handler
        self.gated_action = gated_action
        self.description = description


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {t.name: t for t in (tools or [])}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)


Reasoner = Callable[[LoopState, Trace], Decision]


class ReactLoop:
    """Runs reason -> act -> observe until the reasoner is satisfied."""

    def __init__(
        self,
        flow: str,
        reasoner: Reasoner,
        tools: ToolRegistry,
        *,
        mode: act.ExecutionMode | None = None,
        max_steps: int = MAX_STEPS,
    ):
        self.flow = flow
        self.reasoner = reasoner
        self.tools = tools
        self.mode = mode or act.current_mode()
        self.max_steps = max_steps

    def run(self, context: dict[str, Any] | None = None) -> Trace:
        state = LoopState(self.flow, context)
        trace = Trace(flow=self.flow)

        for index in range(1, self.max_steps + 1):
            decision = self.reasoner(state, trace)

            if decision.is_finish:
                trace.steps.append(
                    Step(
                        index=index,
                        thought=decision.thought,
                        action=None,
                        observation=Observation(
                            StepOutcome.FINISHED, "No further action needed."
                        ),
                    )
                )
                trace.stopped_reason = "reasoner finished"
                trace.result = state.get("result")
                return trace

            action = decision.action
            assert action is not None  # is_finish covers the None case
            observation = self._execute(action, state, trace)

            trace.steps.append(
                Step(
                    index=index,
                    thought=decision.thought,
                    action=action,
                    observation=observation,
                )
            )
            state.done_actions.add(action.name)

        trace.stopped_reason = f"hit step limit ({self.max_steps})"
        trace.result = state.get("result")
        return trace

    def _execute(self, call: ActionCall, state: LoopState, trace: Trace) -> Observation:
        tool = self.tools.get(call.name)
        if tool is None:
            return Observation(
                StepOutcome.ERROR,
                f"No such action '{call.name}'. Available: {', '.join(self.tools.names())}",
            )

        # --- policy gate -------------------------------------------------
        if tool.gated_action:
            verdict = act.evaluate(
                act.ActionRequest(
                    action=tool.gated_action,
                    mode=self.mode,
                    untrusted_in_scope=state.untrusted_in_scope,
                    injection_suspected=state.injection_suspected,
                    target=str(call.args.get("target", "")),
                )
            )
            if verdict.decision is not act.Decision.ALLOW:
                proposal = Proposal(
                    action=tool.gated_action,
                    target=str(call.args.get("target", "")),
                    rationale=str(call.args.get("rationale", "")) or call.describe(),
                    reason_blocked=verdict.reason,
                    draft=str(call.args.get("draft", "")),
                )
                trace.proposals.append(proposal)
                return Observation(
                    StepOutcome.BLOCKED,
                    f"'{tool.gated_action}' not permitted here, recorded as a "
                    f"proposal for the operator. {verdict.reason}",
                    data=proposal,
                )

        try:
            return tool.handler(state, call.args)
        except Exception as exc:  # noqa: BLE001 - a tool failure must not kill the run
            return Observation(StepOutcome.ERROR, f"{call.name} failed: {exc}")

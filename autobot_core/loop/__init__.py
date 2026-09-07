"""Reason-act-observe execution loop (ReAct, Yao et al., 2022).

Replaces the single-shot "one trigger, one prompt, one pass" shape of the cron
scripts with a cycle that can chain: reason about what was observed, act, observe
the result, and decide whether more is needed.

See docs/EXECUTION-LOOP.md.
"""

from .engine import Decision, LoopState, ReactLoop, Tool, ToolRegistry
from .flows import build_briefing_loop, build_triage_loop
from .types import ActionCall, Observation, Proposal, Step, StepOutcome, Trace

__all__ = [
    "ActionCall",
    "Decision",
    "LoopState",
    "Observation",
    "Proposal",
    "ReactLoop",
    "Step",
    "StepOutcome",
    "Tool",
    "ToolRegistry",
    "Trace",
    "build_briefing_loop",
    "build_triage_loop",
]

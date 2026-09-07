"""JSON-on-stdout CLI for autobot_core.

Exists so the pi extensions (TypeScript) and the cron scripts (bash) enforce
exactly the same policy as the Python tests, rather than reimplementing it and
drifting. Follows the repo convention: JSON to stdout, argparse, no side
effects.

Usage:
    python -m autobot_core.cli fence --tool messages --input '{"action":"recent"}'
    python -m autobot_core.cli guard --action gmail.send --untrusted
    python -m autobot_core.cli triage --file inbox.json
    python -m autobot_core.cli registry
    python -m autobot_core.cli memory-consolidate --root data/memory --dry-run
    python -m autobot_core.cli memory-status
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime

from . import actions as act
from . import trust
from .memory import consolidate as memory_consolidate
from .memory.consolidate import status as memory_status
from .triage import Message, triage_all


def _emit(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def _cmd_fence(args: argparse.Namespace) -> int:
    tool_input = json.loads(args.input) if args.input else {}
    content = args.content if args.content is not None else sys.stdin.read()

    provenance = trust.classify_source(args.tool, tool_input)
    if not provenance.needs_fencing:
        _emit(
            {
                "fenced": False,
                "domain": provenance.domain.value,
                "source": provenance.source,
                "content": content,
            }
        )
        return 0

    result = trust.fence(content, provenance)
    _emit(
        {
            "fenced": True,
            "domain": provenance.domain.value,
            "source": provenance.source,
            "content": result.text,
            "nonce": result.nonce,
            "neutralized": result.neutralized,
            "suspicious": result.scan.suspicious,
            "severity": result.scan.severity,
            "signals": [s.value for s in result.scan.signals],
            "excerpts": result.scan.excerpts,
        }
    )
    return 0


def _cmd_guard(args: argparse.Namespace) -> int:
    mode = (
        act.ExecutionMode(args.mode)
        if args.mode
        else act.current_mode()
    )
    request = act.ActionRequest(
        action=args.action,
        mode=mode,
        untrusted_in_scope=args.untrusted,
        injection_suspected=args.injection,
        target=args.target or "",
    )
    result = act.evaluate(request)
    _emit(
        {
            "action": args.action,
            "mode": mode.value,
            "decision": result.decision.value,
            "allowed": result.allowed,
            "reason": result.reason,
            "spec": asdict(result.spec) if result.spec else None,
        }
    )
    return 0 if result.decision != act.Decision.DENY else 3


def _cmd_triage(args: argparse.Namespace) -> int:
    raw = json.load(open(args.file)) if args.file else json.load(sys.stdin)
    if isinstance(raw, dict):
        raw = [raw]

    messages = []
    for item in raw:
        received = item.get("received_at")
        if isinstance(received, str):
            try:
                received = datetime.fromisoformat(received.replace("Z", "+00:00"))
            except ValueError:
                received = None
        messages.append(
            Message(
                source=item.get("source", "unknown"),
                sender=item.get("sender", ""),
                subject=item.get("subject", ""),
                body=item.get("body", ""),
                received_at=received,
                recipients=item.get("recipients", []) or [],
                headers=item.get("headers", {}) or {},
                is_reply=bool(item.get("is_reply", False)),
                sender_is_known_contact=bool(item.get("sender_is_known_contact", False)),
            )
        )

    today = date.fromisoformat(args.today) if args.today else None
    results = triage_all(messages, today=today)

    _emit(
        [
            {
                "priority": r.priority.value,
                "label": r.priority.label,
                "surfaces": r.priority.surfaces_in_briefing,
                "quarantined": r.quarantined,
                "signals": [s.value for s in r.signals],
                "rationale": r.rationale,
                "sender": r.message.sender if r.message else "",
                "subject": r.message.subject if r.message else "",
            }
            for r in results
        ]
    )
    return 0


def _cmd_registry(args: argparse.Namespace) -> int:
    _emit(
        {
            "autonomous_allowlist": sorted(act.AUTONOMOUS_ALLOWLIST),
            "actions": {
                name: asdict(spec) for name, spec in sorted(act.REGISTRY.items())
            },
        }
    )
    return 0


def _default_memory_root() -> str:
    return "data/memory"


def _cmd_memory_consolidate(args: argparse.Namespace) -> int:
    from datetime import date as _date

    since = _date.fromisoformat(args.since) if args.since else None
    report = memory_consolidate(args.root, dry_run=args.dry_run, since=since)
    _emit(report.to_dict())
    return 0


def _cmd_memory_status(args: argparse.Namespace) -> int:
    _emit(memory_status(args.root))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autobot_core.cli",
        description="Trust, triage, and action-policy primitives.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fence = sub.add_parser("fence", help="Wrap tool output in a trust fence")
    p_fence.add_argument("--tool", required=True)
    p_fence.add_argument("--input", default="{}", help="Tool arguments as JSON")
    p_fence.add_argument("--content", default=None, help="Content (default: stdin)")
    p_fence.set_defaults(func=_cmd_fence)

    p_guard = sub.add_parser("guard", help="Evaluate an action against policy")
    p_guard.add_argument("--action", required=True)
    p_guard.add_argument("--mode", choices=["interactive", "autonomous"], default=None)
    p_guard.add_argument("--untrusted", action="store_true")
    p_guard.add_argument("--injection", action="store_true")
    p_guard.add_argument("--target", default="")
    p_guard.set_defaults(func=_cmd_guard)

    p_triage = sub.add_parser("triage", help="Score messages against the rubric")
    p_triage.add_argument("--file", default=None, help="JSON file (default: stdin)")
    p_triage.add_argument("--today", default=None, help="Reference date YYYY-MM-DD")
    p_triage.set_defaults(func=_cmd_triage)

    p_reg = sub.add_parser("registry", help="Dump the action registry")
    p_reg.set_defaults(func=_cmd_registry)

    p_cons = sub.add_parser(
        "memory-consolidate",
        help="Review episodic entries and update semantic memory",
    )
    p_cons.add_argument("--root", default=_default_memory_root())
    p_cons.add_argument("--dry-run", action="store_true")
    p_cons.add_argument("--since", default=None, help="Override watermark, YYYY-MM-DD")
    p_cons.set_defaults(func=_cmd_memory_consolidate)

    p_mstat = sub.add_parser(
        "memory-status", help="Report episodic backlog and consolidation watermark"
    )
    p_mstat.add_argument("--root", default=_default_memory_root())
    p_mstat.set_defaults(func=_cmd_memory_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

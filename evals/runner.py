"""Evaluation harness.

Feeds scripted scenarios through the *actual* triage, conflict, and briefing
logic -- the same functions the cron jobs call -- and reports how often the
output matches the known-correct answer.

The point is regression tracking. Before this, the only way to know whether a
prompt or rule change had made triage worse was to eyeball a few examples.
Results are appended to a CSV per run so accuracy can be compared across
commits.

Runs offline: no API keys, no network, no macOS permissions.

    python -m evals.runner                    # all suites
    python -m evals.runner --suite inbox_triage
    python -m evals.runner --json             # machine-readable
    python -m evals.runner --fail-under 0.95  # CI gate
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autobot_core import actions as act  # noqa: E402
from autobot_core.loop import build_briefing_loop  # noqa: E402
from autobot_core.schedule import Event, find_conflicts, suggest_resolution  # noqa: E402
from autobot_core.triage import Message, triage  # noqa: E402

SCENARIO_DIR = Path(__file__).parent / "scenarios"
RESULTS_DIR = Path(__file__).parent / "results"
HISTORY_CSV = RESULTS_DIR / "history.csv"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    suite: str
    case_id: str
    passed: bool
    expected: str
    actual: str
    detail: str = ""
    note: str = ""


@dataclass
class SuiteResult:
    name: str
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def failures(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.passed]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _message(payload: dict[str, Any]) -> Message:
    return Message(
        source=payload.get("source", "unknown"),
        sender=payload.get("sender", ""),
        subject=payload.get("subject", ""),
        body=payload.get("body", ""),
        recipients=payload.get("recipients", []) or [],
        headers=payload.get("headers", {}) or {},
        is_reply=bool(payload.get("is_reply", False)),
        sender_is_known_contact=bool(payload.get("sender_is_known_contact", False)),
    )


def _event(payload: dict[str, Any]) -> Event:
    return Event(
        title=payload.get("title", ""),
        start=datetime.fromisoformat(payload["start"]),
        end=datetime.fromisoformat(payload["end"]),
        location=payload.get("location", ""),
        attendees=payload.get("attendees", []) or [],
        all_day=bool(payload.get("all_day", False)),
        organizer=payload.get("organizer", ""),
        recurring=bool(payload.get("recurring", False)),
    )


# ---------------------------------------------------------------------------
# Suite runners
# ---------------------------------------------------------------------------


def run_inbox_triage(spec: dict[str, Any]) -> SuiteResult:
    """Score every message and compare to its known label."""
    suite = SuiteResult(spec["suite"])
    today = date.fromisoformat(spec["reference_date"]) if spec.get("reference_date") else None

    for case in spec["cases"]:
        expected = case["expected"]
        result = triage(_message(case["message"]), today=today)

        checks = [
            ("priority", expected["priority"], result.priority.value),
            ("quarantined", expected["quarantined"], result.quarantined),
        ]
        mismatches = [f"{n}: expected {e}, got {a}" for n, e, a in checks if e != a]

        suite.cases.append(
            CaseResult(
                suite=suite.name,
                case_id=case["id"],
                passed=not mismatches,
                expected=f"{expected['priority']}/q={expected['quarantined']}",
                actual=f"{result.priority.value}/q={result.quarantined}",
                detail="; ".join(mismatches) or result.rationale[:80],
                note=case.get("note", ""),
            )
        )
    return suite


def run_calendar_conflicts(spec: dict[str, Any]) -> SuiteResult:
    """Detect conflicts and compare kinds plus the suggested resolution."""
    suite = SuiteResult(spec["suite"])

    for case in spec["cases"]:
        expected = case["expected"]
        conflicts = find_conflicts([_event(e) for e in case["events"]])

        kinds = [c.kind.value for c in conflicts]
        mismatches: list[str] = []

        if len(conflicts) != expected["conflict_count"]:
            mismatches.append(
                f"count: expected {expected['conflict_count']}, got {len(conflicts)}"
            )
        if sorted(kinds) != sorted(expected["kinds"]):
            mismatches.append(f"kinds: expected {expected['kinds']}, got {kinds}")

        actual_resolution = None
        actual_move = None
        if conflicts:
            resolution = suggest_resolution(conflicts[0])
            actual_resolution = resolution["action"]
            actual_move = resolution["move"]

        if expected.get("resolution") != actual_resolution:
            mismatches.append(
                f"resolution: expected {expected.get('resolution')}, got {actual_resolution}"
            )
        if "move" in expected and expected["move"] != actual_move:
            mismatches.append(f"move: expected {expected['move']!r}, got {actual_move!r}")

        suite.cases.append(
            CaseResult(
                suite=suite.name,
                case_id=case["id"],
                passed=not mismatches,
                expected=f"{expected['conflict_count']} conflict(s)/{expected.get('resolution')}",
                actual=f"{len(conflicts)} conflict(s)/{actual_resolution}",
                detail="; ".join(mismatches),
                note=case.get("note", ""),
            )
        )
    return suite


def run_briefing_flow(spec: dict[str, Any]) -> SuiteResult:
    """Run the whole loop and assert on its trace and output."""
    suite = SuiteResult(spec["suite"])
    today = date.fromisoformat(spec["reference_date"]) if spec.get("reference_date") else None

    for case in spec["cases"]:
        expected = case["expected"]
        events = [_event(e) for e in case.get("events", [])]
        messages = [_message(m) for m in case.get("messages", [])]
        mode = act.ExecutionMode(case.get("mode", "autonomous"))

        loop = build_briefing_loop(lambda: events, lambda: messages, mode=mode)
        trace = loop.run({"today": today})

        attempted = [s.action.name for s in trace.steps if s.action]
        brief = trace.result or ""
        mismatches: list[str] = []

        for name in expected.get("actions_include", []):
            if name not in attempted:
                mismatches.append(f"missing action {name}")
        for name in expected.get("actions_exclude", []):
            if name in attempted:
                mismatches.append(f"unexpected action {name}")

        if len(trace.proposals) != expected.get("proposal_count", 0):
            mismatches.append(
                f"proposals: expected {expected.get('proposal_count', 0)}, "
                f"got {len(trace.proposals)}"
            )
        if "proposal_actions" in expected:
            actual = sorted(p.action for p in trace.proposals)
            if actual != sorted(expected["proposal_actions"]):
                mismatches.append(
                    f"proposal actions: expected {expected['proposal_actions']}, got {actual}"
                )
        for fragment in expected.get("brief_contains", []):
            if fragment not in brief:
                mismatches.append(f"brief missing {fragment!r}")
        if expected.get("stopped_reason") and trace.stopped_reason != expected["stopped_reason"]:
            mismatches.append(
                f"stopped: expected {expected['stopped_reason']!r}, got {trace.stopped_reason!r}"
            )

        suite.cases.append(
            CaseResult(
                suite=suite.name,
                case_id=case["id"],
                passed=not mismatches,
                expected=f"{len(expected.get('actions_include', []))} actions/"
                f"{expected.get('proposal_count', 0)} proposals",
                actual=f"{len(attempted)} actions/{len(trace.proposals)} proposals",
                detail="; ".join(mismatches),
                note=case.get("note", ""),
            )
        )
    return suite


RUNNERS = {
    "inbox_triage": run_inbox_triage,
    "calendar_conflicts": run_calendar_conflicts,
    "briefing_flow": run_briefing_flow,
}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def record_history(suites: list[SuiteResult]) -> Path:
    """Append this run to the CSV so accuracy can be tracked across commits."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not HISTORY_CSV.exists()
    timestamp = datetime.now().isoformat(timespec="seconds")
    sha = _git_sha()

    with HISTORY_CSV.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(
                ["timestamp", "commit", "suite", "total", "passed", "accuracy", "failures"]
            )
        for suite in suites:
            writer.writerow(
                [
                    timestamp,
                    sha,
                    suite.name,
                    suite.total,
                    suite.passed,
                    f"{suite.accuracy:.4f}",
                    "|".join(c.case_id for c in suite.failures()),
                ]
            )
        overall_total = sum(s.total for s in suites)
        overall_passed = sum(s.passed for s in suites)
        writer.writerow(
            [
                timestamp,
                sha,
                "OVERALL",
                overall_total,
                overall_passed,
                f"{overall_passed / overall_total:.4f}" if overall_total else "0.0000",
                "",
            ]
        )
    return HISTORY_CSV


def previous_overall() -> float | None:
    """Overall accuracy from the most recent prior run, for regression detection."""
    if not HISTORY_CSV.exists():
        return None
    try:
        with HISTORY_CSV.open(encoding="utf-8") as handle:
            rows = [r for r in csv.DictReader(handle) if r["suite"] == "OVERALL"]
        return float(rows[-1]["accuracy"]) if rows else None
    except (OSError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(suites: list[SuiteResult], baseline: float | None) -> str:
    lines: list[str] = ["", "=" * 68, "AUTOBOT EVALUATION HARNESS", "=" * 68, ""]

    for suite in suites:
        bar_width = 28
        filled = round(suite.accuracy * bar_width)
        bar = "#" * filled + "." * (bar_width - filled)
        lines.append(
            f"{suite.name:<22} [{bar}] "
            f"{suite.accuracy:>6.1%}  ({suite.passed}/{suite.total})"
        )

    total = sum(s.total for s in suites)
    passed = sum(s.passed for s in suites)
    overall = passed / total if total else 0.0

    lines += ["", "-" * 68, f"{'OVERALL':<22} {overall:>6.1%}  ({passed}/{total})"]

    if baseline is not None:
        delta = overall - baseline
        marker = "no change" if abs(delta) < 1e-9 else f"{delta:+.1%}"
        verdict = "REGRESSION" if delta < -1e-9 else ""
        lines.append(f"{'vs previous run':<22} {baseline:>6.1%}  ({marker}) {verdict}")
    lines.append("-" * 68)

    failures = [c for s in suites for c in s.failures()]
    if failures:
        lines += ["", f"FAILURES ({len(failures)}):", ""]
        for case in failures:
            lines.append(f"  [{case.suite}] {case.case_id}")
            lines.append(f"      expected: {case.expected}")
            lines.append(f"      actual:   {case.actual}")
            if case.detail:
                lines.append(f"      detail:   {case.detail}")
            if case.note:
                lines.append(f"      note:     {case.note}")
            lines.append("")
    else:
        lines += ["", "All cases passed.", ""]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Autobot evaluation harness.")
    parser.add_argument("--suite", default=None, help="Run only this suite")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a report")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero if overall accuracy falls below this (0-1). For CI.",
    )
    parser.add_argument(
        "--no-record", action="store_true", help="Do not append to the history CSV"
    )
    args = parser.parse_args(argv)

    suites: list[SuiteResult] = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        name = spec["suite"]
        if args.suite and name != args.suite:
            continue
        runner = RUNNERS.get(name)
        if runner is None:
            print(f"warning: no runner for suite {name!r}, skipping", file=sys.stderr)
            continue
        suites.append(runner(spec))

    if not suites:
        print("No suites ran.", file=sys.stderr)
        return 2

    baseline = previous_overall()
    if not args.no_record:
        record_history(suites)

    total = sum(s.total for s in suites)
    passed = sum(s.passed for s in suites)
    overall = passed / total if total else 0.0

    if args.json:
        json.dump(
            {
                "overall_accuracy": overall,
                "total": total,
                "passed": passed,
                "baseline": baseline,
                "suites": [
                    {
                        "name": s.name,
                        "total": s.total,
                        "passed": s.passed,
                        "accuracy": s.accuracy,
                        "failures": [
                            {
                                "case_id": c.case_id,
                                "expected": c.expected,
                                "actual": c.actual,
                                "detail": c.detail,
                            }
                            for c in s.failures()
                        ],
                    }
                    for s in suites
                ],
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        print(report(suites, baseline))

    if args.fail_under is not None and overall < args.fail_under:
        print(
            f"FAIL: overall accuracy {overall:.1%} is below the "
            f"{args.fail_under:.1%} threshold.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

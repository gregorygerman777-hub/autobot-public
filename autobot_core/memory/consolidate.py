"""Consolidation: episodic entries in, semantic facts out.

Before this, journal entries were written every night by `scripts/end-of-day.sh`
and read at most once, by the memory-loader, the following morning. After that
they were dead weight. Meanwhile `profile.md` and `preferences.md` only changed
if the agent happened to notice something mid-conversation and remembered to
write it down. The episodic log grew forever, unconsumed, while the semantic
store went stale.

Consolidation is the missing link, and it is the same operation as Park et al.'s
(2023) *reflection* step in Generative Agents -- periodically review recent
observations and synthesize higher-level statements from them -- and as MemGPT's
(Packer et al., 2023) movement of information out of external storage into the
small, always-resident main context.

Safety is the reason this is not just an LLM prompt. Consolidation is a
laundering path: an attacker writes something in an email, the agent summarizes
it into a journal entry, consolidation promotes it to `profile.md`, and the
memory-loader then injects it into every session forever. That converts a
one-shot injection into a permanent implant (docs/THREAT-MODEL.md, A3/R6). So
the mechanics here are deterministic and tested, and anything traceable to
untrusted content is queued for a human rather than promoted.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..trust import scan_for_injection
from .store import AUTO_INJECTED, MemoryStore
from .types import Candidate, Fact, SourceTrust

__all__ = [
    "ConsolidationReport",
    "consolidate",
    "extract_candidates",
    "score_importance",
    "STATE_FILE",
]

STATE_FILE = ".consolidation-state.json"

# Journal sections and what they mean. The format comes from
# `.pi/skills/memory/SKILL.md`, which already asks for these headings.
_SECTION_LEARNED = re.compile(r"^#+\s*(learned|new facts?|preferences?)\b", re.I)
_SECTION_PENDING = re.compile(r"^#+\s*(pending|open items?|follow[- ]?ups?|todo)\b", re.I)
_SECTION_EVENTS = re.compile(r"^#+\s*(key events?|what happened|events?)\b", re.I)
_SECTION_ANY = re.compile(r"^#+\s+")

# A journal section can declare that its contents came from outside. The
# end-of-day and briefing prompts are instructed to mark summaries of external
# messages this way.
_EXTERNAL_MARKER = re.compile(
    r"<!--\s*mem:\s*trust=external\s*-->|^#+.*\b(from (external|incoming)|inbox|"
    r"received messages?|email summary)\b",
    re.I,
)

_BULLET = re.compile(r"^\s*[-*+]\s+(?P<text>.+?)\s*$")


# --- routing ---------------------------------------------------------------
# Where a candidate fact belongs in the semantic tier. Unroutable candidates are
# deliberately not promoted: they stay in the journal, where they already are.

_IDENTITY = re.compile(
    r"\b(my name is|lives? in|based in|timezone|works? (at|for)|studies? at|"
    r"attends?|graduat|birthday|is a (student|engineer|developer))\b",
    re.I,
)

_PREFERENCE = re.compile(
    r"\b(prefers?|likes?|dislikes?|hates?|always|never|wants?|avoid|"
    r"favou?rite|instead of|rather than|don'?t (like|want)|should (not )?)\b",
    re.I,
)

_PROJECT = re.compile(
    r"\b(project|repo|repository|class|course|assignment|deadline|building|"
    r"working on|shipping|milestone)\b",
    re.I,
)


def _route(text: str, store: MemoryStore) -> tuple[str, str] | None:
    """Pick a target file and section for a candidate fact."""
    # A named person already tracked in people/ takes precedence.
    people_dir = store.root / "people"
    if people_dir.is_dir():
        for person_file in people_dir.glob("*.md"):
            name = person_file.stem.replace("-", " ")
            first = name.split()[0] if name.split() else ""
            if first and len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", text, re.I):
                return f"people/{person_file.name}", "## Notes"

    if _IDENTITY.search(text):
        return "profile.md", "## About"
    if _PREFERENCE.search(text):
        return "preferences.md", "## Notes"
    if _PROJECT.search(text):
        return "projects/consolidated.md", "## Notes"
    return None


# --- importance ------------------------------------------------------------

_DURABLE_CUES = re.compile(
    r"\b(always|never|prefers?|generally|usually|every|habit|routine|"
    r"policy|rule|standard|by default)\b",
    re.I,
)

_TRANSIENT_CUES = re.compile(
    r"\b(today|tomorrow|yesterday|this (morning|afternoon|evening|week)|"
    r"tonight|right now|currently|at the moment|just now)\b",
    re.I,
)


def score_importance(text: str) -> float:
    """Rate how much a statement deserves to become a durable fact (0-1).

    Park et al. (2023) obtain this from the model on a 1-10 scale. A
    deterministic heuristic is used here so the behavior is testable offline and
    cannot be steered by the content being scored.
    """
    score = 0.4

    if _DURABLE_CUES.search(text):
        score += 0.3
    if _PREFERENCE.search(text):
        score += 0.15
    if _IDENTITY.search(text):
        score += 0.2
    # Statements pinned to a specific moment belong in the episodic log.
    if _TRANSIENT_CUES.search(text):
        score -= 0.35
    # A bare fragment is rarely a durable fact.
    words = len(text.split())
    if words < 4:
        score -= 0.25
    elif words > 30:
        score -= 0.1

    return max(0.0, min(1.0, score))


IMPORTANCE_THRESHOLD = 0.5


# --- extraction ------------------------------------------------------------


def extract_candidates(
    entries: list[tuple[date, str]], store: MemoryStore
) -> list[Candidate]:
    """Pull candidate semantic facts out of episodic journal entries.

    Only the "Learned" section produces semantic candidates. "Key Events" is
    episodic by definition and "Pending" is task state, not durable fact -- both
    stay in the journal.
    """
    candidates: list[Candidate] = []

    for entry_date, text in entries:
        section_kind: str | None = None
        section_external = False
        source = f"journal/{entry_date.isoformat()}"

        for raw_line in text.splitlines():
            if _SECTION_ANY.match(raw_line):
                if _SECTION_LEARNED.match(raw_line):
                    section_kind = "learned"
                elif _SECTION_PENDING.match(raw_line):
                    section_kind = "pending"
                elif _SECTION_EVENTS.match(raw_line):
                    section_kind = "events"
                else:
                    section_kind = "other"
                section_external = bool(_EXTERNAL_MARKER.search(raw_line))
                continue

            if section_kind != "learned":
                continue

            match = _BULLET.match(raw_line)
            if not match:
                continue

            body = match.group("text").strip()
            if not body:
                continue

            line_external = section_external or bool(_EXTERNAL_MARKER.search(raw_line))
            body = _EXTERNAL_MARKER.sub("", body).strip()
            if not body:
                continue

            trust = SourceTrust.EXTERNAL if line_external else SourceTrust.AGENT
            candidate = Candidate(
                fact=Fact(text=body, source=source, trust=trust, observed=entry_date),
                target="",
                importance=score_importance(body),
            )

            # --- safety gates ------------------------------------------
            scan = scan_for_injection(body)
            if scan.suspicious:
                candidate.blocked = True
                candidate.block_reason = (
                    f"content resembles a prompt-injection attempt ({scan.summary()})"
                )
            elif trust == SourceTrust.EXTERNAL:
                candidate.blocked = True
                candidate.block_reason = (
                    "derived from untrusted content; promoting it would make an "
                    "outsider's claim a permanent fact about the user"
                )

            route = _route(body, store)
            if route:
                candidate.target, candidate.section = route
            elif not candidate.blocked:
                candidate.blocked = True
                candidate.block_reason = "no semantic destination matched"
                candidate.reasons.append("unrouted")

            if candidate.importance < IMPORTANCE_THRESHOLD and not candidate.blocked:
                candidate.blocked = True
                candidate.block_reason = (
                    f"importance {candidate.importance:.2f} below threshold "
                    f"{IMPORTANCE_THRESHOLD:.2f}; reads as transient"
                )
                candidate.reasons.append("low-importance")

            candidates.append(candidate)

    return candidates


# --- state -----------------------------------------------------------------


def _load_state(store: MemoryStore) -> dict:
    path = store.path(STATE_FILE)
    if not path.exists():
        return {"last_consolidated": None, "runs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_consolidated": None, "runs": []}


def _save_state(store: MemoryStore, state: dict) -> None:
    path = store.path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


# --- the run ---------------------------------------------------------------


@dataclass
class ConsolidationReport:
    """What one consolidation run did."""

    entries_reviewed: int = 0
    candidates_found: int = 0
    promoted: list[str] = field(default_factory=list)
    corroborated: list[str] = field(default_factory=list)
    queued: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    watermark: date | None = None
    dry_run: bool = False

    def summary(self) -> str:
        return (
            f"reviewed {self.entries_reviewed} episodic entr"
            f"{'y' if self.entries_reviewed == 1 else 'ies'}, "
            f"{self.candidates_found} candidates -> "
            f"{len(self.promoted)} promoted, "
            f"{len(self.corroborated)} corroborated, "
            f"{len(self.queued)} queued for review, "
            f"{len(self.skipped)} skipped"
        )

    def to_dict(self) -> dict:
        return {
            "entries_reviewed": self.entries_reviewed,
            "candidates_found": self.candidates_found,
            "promoted": self.promoted,
            "corroborated": self.corroborated,
            "queued": [{"fact": f, "reason": r} for f, r in self.queued],
            "skipped": [{"fact": f, "reason": r} for f, r in self.skipped],
            "watermark": self.watermark.isoformat() if self.watermark else None,
            "dry_run": self.dry_run,
            "summary": self.summary(),
        }


def consolidate(
    root: str | Path,
    *,
    dry_run: bool = False,
    since: date | None = None,
) -> ConsolidationReport:
    """Review episodic entries since the watermark and update semantic memory.

    Args:
        root: The `data/memory` directory.
        dry_run: Report what would happen without writing anything.
        since: Override the stored watermark. Mainly for backfills and tests.

    Returns:
        A report describing every decision, including the ones that refused to
        promote something and why.
    """
    store = MemoryStore(root)
    state = _load_state(store)

    watermark = since
    if watermark is None and state.get("last_consolidated"):
        try:
            watermark = date.fromisoformat(state["last_consolidated"])
        except (TypeError, ValueError):
            watermark = None

    entries = store.journal_entries(since=watermark)
    report = ConsolidationReport(entries_reviewed=len(entries), dry_run=dry_run)

    if not entries:
        report.watermark = watermark
        return report

    candidates = extract_candidates(entries, store)
    report.candidates_found = len(candidates)

    for candidate in candidates:
        fact = candidate.fact

        if candidate.blocked:
            # Untrusted-derived and injection-flagged candidates go in front of
            # a human. Low-importance and unroutable ones simply stay episodic.
            if fact.trust == SourceTrust.EXTERNAL or "injection" in candidate.block_reason:
                report.queued.append((fact.text, candidate.block_reason))
                if not dry_run:
                    store.queue_for_review(fact.text, candidate.block_reason, fact.source)
            else:
                report.skipped.append((fact.text, candidate.block_reason))
            continue

        if not fact.trust.promotable:  # defense in depth; should be unreachable
            report.queued.append((fact.text, "non-promotable trust level"))
            if not dry_run:
                store.queue_for_review(fact.text, "non-promotable trust level", fact.source)
            continue

        target = candidate.target
        existing = {f.normalized() for f in store.read_facts(target)}

        if fact.normalized() in existing:
            report.corroborated.append(f"{target}: {fact.text}")
            if not dry_run:
                store.bump_seen(target, fact)
            continue

        report.promoted.append(f"{target}: {fact.text}")
        if not dry_run:
            store.append_fact(target, fact, candidate.section)

    newest = max(entry_date for entry_date, _ in entries)
    report.watermark = newest

    if not dry_run:
        state["last_consolidated"] = newest.isoformat()
        state.setdefault("runs", []).append(
            {
                "at": datetime.now().isoformat(timespec="seconds"),
                "entries": report.entries_reviewed,
                "promoted": len(report.promoted),
                "corroborated": len(report.corroborated),
                "queued": len(report.queued),
                "skipped": len(report.skipped),
            }
        )
        state["runs"] = state["runs"][-50:]  # keep the tail bounded
        _save_state(store, state)

    return report


def status(root: str | Path) -> dict:
    """Report whether the episodic log is actually being consumed."""
    store = MemoryStore(root)
    state = _load_state(store)
    watermark = state.get("last_consolidated")
    parsed = date.fromisoformat(watermark) if watermark else None
    unconsumed = store.journal_entries(since=parsed)

    return {
        "last_consolidated": watermark,
        "unconsumed_entries": len(unconsumed),
        "oldest_unconsumed": unconsumed[0][0].isoformat() if unconsumed else None,
        "volume": store.episodic_volume(),
        "auto_injected_files": sorted(AUTO_INJECTED),
        "runs_recorded": len(state.get("runs", [])),
    }

"""Tier-aware view over the existing memory directory.

Physical layout is unchanged. `data/memory/profile.md` is still
`data/memory/profile.md`, and any skill that greps `data/memory/people/`
keeps working exactly as before. This module adds a classification layer and
provenance-aware read/write helpers on top of the files that are already there.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .types import PROVENANCE_RE, Fact, MemoryTier, SourceTrust

__all__ = ["MemoryStore", "classify_path"]


# Maps the existing directory layout onto tiers. Order matters: the first
# matching prefix wins, so the more specific patterns come first.
_TIER_RULES: list[tuple[re.Pattern[str], MemoryTier]] = [
    (re.compile(r"^journal/"), MemoryTier.EPISODIC),
    (re.compile(r"^sessions/"), MemoryTier.EPISODIC),
    (re.compile(r"^scratch/"), MemoryTier.EPHEMERAL),
    (re.compile(r"^review-queue\.md$"), MemoryTier.EPHEMERAL),
    (re.compile(r"^profile\.md$"), MemoryTier.SEMANTIC),
    (re.compile(r"^preferences\.md$"), MemoryTier.SEMANTIC),
    (re.compile(r"^contacts\.md$"), MemoryTier.SEMANTIC),
    (re.compile(r"^pii\.md$"), MemoryTier.SEMANTIC),
    (re.compile(r"^people/"), MemoryTier.SEMANTIC),
    (re.compile(r"^projects/"), MemoryTier.SEMANTIC),
]

# Files auto-injected into every session by .pi/extensions/memory-loader.ts.
# Writes here are the persistence vector described in docs/THREAT-MODEL.md A3,
# so they are held to the strictest promotion rules.
AUTO_INJECTED = frozenset({"profile.md", "preferences.md"})


def classify_path(relative: str) -> MemoryTier:
    """Classify a path relative to data/memory/ into a tier."""
    rel = relative.lstrip("./").replace("\\", "/")
    for pattern, tier in _TIER_RULES:
        if pattern.match(rel):
            return tier
    # Unrecognized paths are treated as ephemeral: they are not consolidated
    # from, and not promoted into.
    return MemoryTier.EPHEMERAL


class MemoryStore:
    """Read and write memory with tier awareness and per-fact provenance."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- paths -----------------------------------------------------------
    def path(self, relative: str) -> Path:
        return self.root / relative

    def exists(self, relative: str) -> bool:
        return self.path(relative).exists()

    def tier(self, relative: str) -> MemoryTier:
        return classify_path(relative)

    def is_auto_injected(self, relative: str) -> bool:
        return relative.lstrip("./") in AUTO_INJECTED

    # -- episodic --------------------------------------------------------
    def journal_entries(self, since: date | None = None) -> list[tuple[date, str]]:
        """Return (date, text) for journal entries, oldest first.

        Args:
            since: If given, only entries strictly after this date.
        """
        journal_dir = self.root / "journal"
        if not journal_dir.is_dir():
            return []

        entries: list[tuple[date, str]] = []
        for path in sorted(journal_dir.glob("*.md")):
            try:
                entry_date = datetime.strptime(path.stem, "%Y-%m-%d").date()
            except ValueError:
                continue  # not a dated entry; skip rather than guess
            if since and entry_date <= since:
                continue
            try:
                entries.append((entry_date, path.read_text(encoding="utf-8")))
            except OSError:
                continue
        return entries

    def episodic_volume(self) -> dict[str, int]:
        """Counts used to show whether the episodic log is being consumed."""
        journal = self.root / "journal"
        sessions = self.root / "sessions"
        return {
            "journal_entries": len(list(journal.glob("*.md"))) if journal.is_dir() else 0,
            "session_logs": len(list(sessions.glob("*.jsonl"))) if sessions.is_dir() else 0,
        }

    # -- semantic --------------------------------------------------------
    def read_facts(self, relative: str) -> list[Fact]:
        """Parse a semantic file into facts, recovering provenance where present."""
        path = self.path(relative)
        if not path.exists():
            return []

        facts: list[Fact] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("-", "*", "+")):
                continue
            match = PROVENANCE_RE.search(stripped)
            text = PROVENANCE_RE.sub("", stripped).strip()
            text = re.sub(r"^[\s\-*+]+", "", text).strip()
            if not text:
                continue
            if match:
                facts.append(
                    Fact(
                        text=text,
                        source=match.group("src"),
                        trust=SourceTrust(match.group("trust")),
                        observed=datetime.strptime(match.group("date"), "%Y-%m-%d").date(),
                        seen=int(match.group("seen") or 1),
                    )
                )
            else:
                # Pre-existing hand-written facts carry no marker. They are
                # treated as operator-authored, which is the safe reading: the
                # user wrote them, so they are already trusted.
                facts.append(Fact(text=text, source="manual", trust=SourceTrust.OPERATOR))
        return facts

    def append_fact(self, relative: str, fact: Fact, section: str = "") -> bool:
        """Append a fact under a heading, creating the file or heading if needed.

        Returns False if an equivalent fact is already present.
        """
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = {f.normalized() for f in self.read_facts(relative)}
        if fact.normalized() in existing:
            return False

        text = path.read_text(encoding="utf-8") if path.exists() else ""
        line = fact.render()

        if section:
            lines = text.splitlines()
            heading = section.strip()
            idx = next(
                (i for i, ln in enumerate(lines) if ln.strip().lower() == heading.lower()),
                None,
            )
            if idx is None:
                # Append a new section at the end.
                if text and not text.endswith("\n"):
                    text += "\n"
                text += f"\n{heading}\n{line}\n"
            else:
                # Insert at the end of the existing section's bullet list.
                insert_at = len(lines)
                for j in range(idx + 1, len(lines)):
                    if lines[j].startswith("#"):
                        insert_at = j
                        break
                while insert_at > idx + 1 and not lines[insert_at - 1].strip():
                    insert_at -= 1
                lines.insert(insert_at, line)
                text = "\n".join(lines) + "\n"
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += line + "\n"

        path.write_text(text, encoding="utf-8")
        return True

    def bump_seen(self, relative: str, fact: Fact) -> bool:
        """Increment the corroboration count on an existing fact.

        Repeated observation is what distinguishes a durable fact from a
        one-off remark, so the count is the signal consolidation uses to decide
        whether something belongs in the always-injected files.
        """
        path = self.path(relative)
        if not path.exists():
            return False

        target = fact.normalized()
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith(("-", "*", "+")):
                continue
            bare = re.sub(r"^[\s\-*+]+", "", PROVENANCE_RE.sub("", stripped)).strip()
            if Fact(text=bare).normalized() != target:
                continue

            match = PROVENANCE_RE.search(stripped)
            if match:
                updated = Fact(
                    text=bare,
                    source=match.group("src"),
                    trust=SourceTrust(match.group("trust")),
                    observed=datetime.strptime(match.group("date"), "%Y-%m-%d").date(),
                    seen=int(match.group("seen") or 1) + 1,
                )
            else:
                updated = Fact(
                    text=bare,
                    source=fact.source,
                    trust=SourceTrust.OPERATOR,
                    observed=fact.observed or date.today(),
                    seen=2,
                )
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = indent + updated.render()
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
        return False

    def queue_for_review(self, candidate_text: str, reason: str, source: str) -> None:
        """Park an untrusted-derived candidate where a human can adjudicate it.

        Deliberately a plain markdown file rather than a hidden queue: the point
        is that a person sees it.
        """
        path = self.path("review-queue.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "" if path.exists() else (
            "# Review Queue\n\n"
            "Candidate facts that consolidation refused to promote automatically.\n"
            "Each was derived from untrusted content or failed a safety check.\n"
            "Move an entry into the semantic store yourself if it is legitimate.\n"
            "See docs/MEMORY.md.\n"
        )
        with path.open("a", encoding="utf-8") as handle:
            if header:
                handle.write(header)
            handle.write(
                f"\n- [ ] {candidate_text}\n"
                f"      - source: `{source}`\n"
                f"      - held because: {reason}\n"
            )

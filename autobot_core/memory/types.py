"""Core types for the memory tiers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

__all__ = [
    "MemoryTier",
    "SourceTrust",
    "Fact",
    "Candidate",
    "PROVENANCE_RE",
    "format_provenance",
]


class MemoryTier(str, Enum):
    """Which kind of memory a path holds."""

    EPISODIC = "episodic"
    """Dated records of what happened. Journal entries, session logs."""

    SEMANTIC = "semantic"
    """Durable facts that remain true across sessions."""

    EPHEMERAL = "ephemeral"
    """Working notes with no retention guarantee. Never consolidated."""


class SourceTrust(str, Enum):
    """How much authority the origin of a fact carries.

    This is the Checkpoint 1 trust model applied to memory. It exists because
    consolidation is otherwise a laundering path: an attacker says something
    once in an email, the agent journals it, consolidation promotes it to
    `profile.md`, and the memory-loader then injects it into every future
    session forever.
    """

    OPERATOR = "operator"
    """The user said it directly. Promotable."""

    AGENT = "agent"
    """The agent observed or derived it from trusted context. Promotable."""

    EXTERNAL = "external"
    """Derived from untrusted content. NEVER auto-promoted; queued for review."""

    @property
    def promotable(self) -> bool:
        return self in (SourceTrust.OPERATOR, SourceTrust.AGENT)


# Provenance rides along inside an HTML comment so it is invisible in rendered
# markdown, harmless to any existing reader, and still machine-parseable. This
# is what makes per-fact provenance possible without changing the file format
# that other skills already read.
PROVENANCE_RE = re.compile(
    r"<!--\s*mem:\s*"
    r"src=(?P<src>[^\s;]+)\s*;\s*"
    r"trust=(?P<trust>operator|agent|external)\s*;\s*"
    r"date=(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:\s*;\s*seen=(?P<seen>\d+))?"
    r"\s*-->"
)


def format_provenance(
    source: str, trust: SourceTrust, observed: date, seen: int = 1
) -> str:
    """Render a provenance marker for appending to a fact line."""
    return (
        f"<!-- mem: src={source}; trust={trust.value}; "
        f"date={observed.isoformat()}; seen={seen} -->"
    )


@dataclass
class Fact:
    """A single durable statement living in the semantic tier."""

    text: str
    source: str = ""
    trust: SourceTrust = SourceTrust.AGENT
    observed: date | None = None
    seen: int = 1
    """How many distinct episodic entries corroborated this fact."""

    def normalized(self) -> str:
        """Comparison key: lowercase, punctuation-insensitive, bullet-stripped."""
        text = re.sub(r"^[\s\-*+]+", "", self.text)
        text = re.sub(r"[^\w\s]", " ", text.lower())
        return re.sub(r"\s+", " ", text).strip()

    def render(self) -> str:
        """Render as a markdown bullet with a provenance marker."""
        body = self.text.strip()
        body = re.sub(r"^[\s\-*+]+", "", body)
        marker = ""
        if self.observed:
            marker = " " + format_provenance(
                self.source or "unknown", self.trust, self.observed, self.seen
            )
        return f"- {body}{marker}"


@dataclass
class Candidate:
    """A fact proposed by consolidation but not yet committed."""

    fact: Fact
    target: str
    """Relative path in the semantic tier, e.g. 'preferences.md'."""

    section: str = ""
    """Heading to file it under, e.g. '## Communication Style'."""

    importance: float = 0.0
    """0-1. Park et al. (2023) score importance to decide what is worth keeping."""

    reasons: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""

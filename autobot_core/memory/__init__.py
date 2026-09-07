"""Episodic and semantic memory.

Autobot's memory was a flat directory of markdown with no explicit structure:
`profile.md`, `preferences.md`, `people/`, `projects/`, and `journal/` all sat
side by side, and the only mechanism was an extension that concatenated two of
them plus yesterday's journal into the system prompt. Journal entries were
written every night and read at most once, the next morning. Nothing ever
consumed them, so the log grew without bound while the durable facts went stale.

This package introduces the distinction the architecture was missing, following
MemGPT (Packer et al., 2023) and Generative Agents (Park et al., 2023):

  * **Episodic memory** -- specific dated events. Journal entries, session logs.
    Append-only, timestamped, and eventually consolidated.
  * **Semantic memory** -- durable facts. Profile, preferences, people,
    projects. Small, current, and cheap enough to keep in context.

Consolidation is the process that connects them: it reads episodic entries
written since the last run, extracts candidate facts, and merges them into the
semantic store. This is Park et al.'s "reflection" step and MemGPT's movement of
information between external and main context.

Physical paths are unchanged on purpose. Every existing read and write keeps
working byte-for-byte; what changed is how memory is organized and maintained,
not where it lives.
"""

from .consolidate import ConsolidationReport, consolidate
from .store import MemoryStore
from .types import Candidate, Fact, MemoryTier, SourceTrust

__all__ = [
    "Candidate",
    "ConsolidationReport",
    "Fact",
    "MemoryStore",
    "MemoryTier",
    "SourceTrust",
    "consolidate",
]

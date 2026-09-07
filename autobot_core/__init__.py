"""Autobot core: security, triage, and memory primitives.

This package holds the parts of Autobot that must behave deterministically and
be testable offline. Skills (`.pi/skills/*/SKILL.md`) remain prose instructions
for the model; this package holds the logic those instructions must not be
free to reinterpret -- trust boundaries, priority scoring, and the action
allowlist.

See docs/THREAT-MODEL.md for the reasoning behind the trust module.
"""

__all__ = ["actions", "triage", "trust"]

__version__ = "0.1.0"

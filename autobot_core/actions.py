"""Action capability registry and allowlist.

The original design had no notion of an action at all. Any skill could do
anything the model decided to do, and a cron job that read an inbox could send
mail as a direct consequence of what it read. `scripts/poll.sh` is exactly that
shape: read email/Slack/iMessage, then send a Telegram message, in one
uninterrupted context.

This module makes capability explicit. Every side-effecting operation is
registered with:

  * whether it is reversible,
  * whether it is externally visible (does a third party observe it?),
  * what it costs to get wrong.

Policy is then a function of three inputs: the action, the execution mode
(is a human present?), and whether untrusted content is in scope. The default
for an autonomous run that has touched untrusted data is DENY for anything
externally visible, with a narrow allowlist of pre-approved exceptions --
notifying the operator on their own configured Telegram chat, and writing to
the journal.

This is the "restricted to a small set of pre-approved action types" property:
the allowlist is a closed set defined here in code, not something a skill can
extend by deciding to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "Decision",
    "ExecutionMode",
    "Reversibility",
    "ActionSpec",
    "ActionRequest",
    "PolicyResult",
    "REGISTRY",
    "lookup",
    "evaluate",
    "current_mode",
]


class Decision(str, Enum):
    ALLOW = "allow"
    """Proceed without asking."""

    CONFIRM = "confirm"
    """Requires explicit human approval before proceeding."""

    DENY = "deny"
    """Refuse. Not offerable as a confirmation prompt in this context."""


class ExecutionMode(str, Enum):
    INTERACTIVE = "interactive"
    """A human is at the keyboard and can answer a confirmation prompt."""

    AUTONOMOUS = "autonomous"
    """Cron / `autobot -p`. Nobody can approve anything in-band."""


class Reversibility(str, Enum):
    REVERSIBLE = "reversible"
    PARTIAL = "partial"
    IRREVERSIBLE = "irreversible"


@dataclass(frozen=True)
class ActionSpec:
    """A registered capability."""

    name: str
    description: str
    reversibility: Reversibility
    externally_visible: bool
    """True if a third party observes the effect. Governs exfiltration risk."""

    interactive_default: Decision
    autonomous_default: Decision
    skill: str = ""
    notes: str = ""

    @property
    def is_high_risk(self) -> bool:
        return self.externally_visible or self.reversibility == Reversibility.IRREVERSIBLE


def _spec(
    name: str,
    description: str,
    *,
    reversibility: Reversibility,
    external: bool,
    interactive: Decision,
    autonomous: Decision,
    skill: str = "",
    notes: str = "",
) -> ActionSpec:
    return ActionSpec(
        name=name,
        description=description,
        reversibility=reversibility,
        externally_visible=external,
        interactive_default=interactive,
        autonomous_default=autonomous,
        skill=skill,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------
# Derived from the audit in docs/THREAT-MODEL.md. Every entry corresponds to a
# concrete capability documented in one of the 12 SKILL.md files.

REGISTRY: dict[str, ActionSpec] = {
    s.name: s
    for s in [
        # --- Egress: third parties see these -------------------------------
        _spec(
            "gmail.send",
            "Send email to arbitrary recipients via gws or the Gmail API",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="gws",
            notes="Highest-risk egress. Skill documents decrypting the stored "
            "OAuth refresh token, so this path carries full account authority.",
        ),
        _spec(
            "messages.send",
            "Send an iMessage/SMS to a contact or group chat",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="messages",
        ),
        _spec(
            "telegram.send_owner",
            "Send a notification to the operator's own pre-configured chat ID",
            reversibility=Reversibility.IRREVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.ALLOW,
            skill="telegram",
            notes="Pre-approved for autonomous use: this is how cron reports "
            "back. Destination is pinned to TELEGRAM_CHAT_ID and is not "
            "selectable from message content.",
        ),
        _spec(
            "telegram.send_other",
            "Send a Telegram message to any other chat ID",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="telegram",
        ),
        _spec(
            "school.submit",
            "Submit files to a school assignment dropbox",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="school-portal",
            notes="scripts/auto-homework.sh currently does this unattended.",
        ),
        _spec(
            "notion.write",
            "Create or update a Notion page",
            reversibility=Reversibility.PARTIAL,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="notion",
        ),
        _spec(
            "browser.submit",
            "Submit a web form or click an irreversible control",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="browser-tools",
        ),
        _spec(
            "browser.eval",
            "Execute arbitrary JavaScript in the authenticated browser profile",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="browser-tools",
            notes="Runs against a profile holding live logins. Equivalent to "
            "session-riding any site the user is signed into.",
        ),
        # --- Local mutation: reversible-ish, but destructive ---------------
        _spec(
            "contacts.create",
            "Create a macOS contact (syncs to iCloud)",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.DENY,
            skill="contacts",
        ),
        _spec(
            "contacts.update",
            "Modify an existing contact",
            reversibility=Reversibility.PARTIAL,
            external=False,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="contacts",
            notes="Rewriting a phone number redirects future messages. This is "
            "an egress attack disguised as a local edit.",
        ),
        _spec(
            "contacts.delete",
            "Delete a contact",
            reversibility=Reversibility.IRREVERSIBLE,
            external=False,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="contacts",
        ),
        _spec(
            "calendar.create",
            "Create a calendar event",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.CONFIRM,
            skill="calendar",
            notes="Invitees see events with attendees, so this can become "
            "externally visible.",
        ),
        _spec(
            "calendar.delete",
            "Delete a calendar event",
            reversibility=Reversibility.IRREVERSIBLE,
            external=False,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="calendar",
        ),
        _spec(
            "reminders.create",
            "Create a reminder",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.ALLOW,
            skill="reminders",
        ),
        _spec(
            "reminders.delete",
            "Delete a reminder",
            reversibility=Reversibility.IRREVERSIBLE,
            external=False,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="reminders",
        ),
        # --- Compute / spend ------------------------------------------------
        _spec(
            "prime.create_pod",
            "Provision a GPU pod (costs money)",
            reversibility=Reversibility.PARTIAL,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="prime-intellect",
        ),
        _spec(
            "prime.terminate_pod",
            "Terminate a GPU pod (destroys running work)",
            reversibility=Reversibility.IRREVERSIBLE,
            external=True,
            interactive=Decision.CONFIRM,
            autonomous=Decision.DENY,
            skill="prime-intellect",
        ),
        # --- Memory ----------------------------------------------------------
        # Memory is where a one-shot injection becomes permanent: profile.md and
        # preferences.md are auto-injected into every future session by
        # .pi/extensions/memory-loader.ts.
        _spec(
            "memory.write_journal",
            "Append to data/memory/journal/ or scratch/",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.ALLOW,
            skill="memory",
        ),
        _spec(
            "memory.write_semantic",
            "Write to profile.md, preferences.md, people/, or projects/",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.CONFIRM,
            skill="memory",
            notes="Auto-injected into every future session. Content written "
            "here becomes a persistent implant, so untrusted-derived writes "
            "are held for review.",
        ),
        _spec(
            "memory.read_pii",
            "Read data/memory/pii.md or contacts.md",
            reversibility=Reversibility.REVERSIBLE,
            external=False,
            interactive=Decision.ALLOW,
            autonomous=Decision.CONFIRM,
            skill="memory",
            notes="Reading is not itself harmful, but pulling PII into a "
            "context that also holds untrusted content sets up exfiltration.",
        ),
    ]
}


# Actions pre-approved for autonomous execution even when untrusted content is
# in scope. Deliberately tiny, and deliberately not extensible at runtime.
AUTONOMOUS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "telegram.send_owner",
        "memory.write_journal",
        "reminders.create",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    """A proposed action, with the provenance of its justification."""

    action: str
    mode: ExecutionMode
    untrusted_in_scope: bool = False
    """True if untrusted content was ingested earlier in this session."""

    injection_suspected: bool = False
    """True if that content tripped a high-severity injection signal."""

    target: str = ""
    """Recipient / object of the action, for logging."""

    justification_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str
    spec: ActionSpec | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


def lookup(action: str) -> ActionSpec | None:
    return REGISTRY.get(action)


def current_mode(env: dict[str, str] | None = None) -> ExecutionMode:
    """Infer execution mode from the environment.

    `scripts/*.sh` set AUTOBOT_MODE=autonomous. Absent that, an unattended run
    is still assumed whenever stdin is not a TTY, so a forgotten export fails
    closed rather than open.
    """
    env = env if env is not None else dict(os.environ)
    declared = env.get("AUTOBOT_MODE", "").strip().lower()
    if declared == "autonomous":
        return ExecutionMode.AUTONOMOUS
    if declared == "interactive":
        return ExecutionMode.INTERACTIVE
    try:
        import sys

        if not sys.stdin.isatty():
            return ExecutionMode.AUTONOMOUS
    except (AttributeError, ValueError):
        return ExecutionMode.AUTONOMOUS
    return ExecutionMode.INTERACTIVE


def evaluate(request: ActionRequest) -> PolicyResult:
    """Decide whether an action may proceed.

    Rules, in precedence order:

    1. Unregistered actions are denied. The registry is a closed set.
    2. High-severity injection in scope denies every non-allowlisted action,
       in both modes. The agent may still report what it saw.
    3. In autonomous mode with untrusted content in scope, only the
       AUTONOMOUS_ALLOWLIST may run.
    4. Otherwise the action's per-mode default applies.
    """
    spec = lookup(request.action)
    if spec is None:
        return PolicyResult(
            Decision.DENY,
            f"'{request.action}' is not a registered action. The registry is a "
            "closed set; unknown capabilities are refused rather than assumed safe.",
            None,
        )

    allowlisted = request.action in AUTONOMOUS_ALLOWLIST

    # Rule 2 -- suspected injection revokes everything outside the allowlist.
    if request.injection_suspected and not allowlisted:
        return PolicyResult(
            Decision.DENY,
            "Content resembling a prompt-injection attempt is in scope. "
            f"'{spec.name}' is not on the pre-approved allowlist, so it is "
            "refused regardless of mode. Report the content instead.",
            spec,
        )

    # Rule 3 -- unattended runs that have read untrusted data are restricted.
    if request.mode == ExecutionMode.AUTONOMOUS and request.untrusted_in_scope:
        if not allowlisted:
            return PolicyResult(
                Decision.DENY,
                f"Autonomous run with untrusted content in scope. '{spec.name}' "
                "is not on the pre-approved allowlist "
                f"({', '.join(sorted(AUTONOMOUS_ALLOWLIST))}). No human can "
                "approve it in-band, so it is refused.",
                spec,
            )
        return PolicyResult(
            Decision.ALLOW,
            f"'{spec.name}' is pre-approved for autonomous execution.",
            spec,
        )

    # Rule 4 -- per-mode defaults.
    default = (
        spec.autonomous_default
        if request.mode == ExecutionMode.AUTONOMOUS
        else spec.interactive_default
    )
    reason = {
        Decision.ALLOW: f"'{spec.name}' is permitted in {request.mode.value} mode.",
        Decision.CONFIRM: (
            f"'{spec.name}' is {spec.reversibility.value}"
            + (" and externally visible" if spec.externally_visible else "")
            + "; explicit approval required."
        ),
        Decision.DENY: (
            f"'{spec.name}' is not permitted in {request.mode.value} mode."
        ),
    }[default]

    # A CONFIRM that nobody can answer is a DENY.
    if default == Decision.CONFIRM and request.mode == ExecutionMode.AUTONOMOUS:
        return PolicyResult(
            Decision.DENY,
            reason + " No operator is present in an autonomous run, so it is refused.",
            spec,
        )

    return PolicyResult(default, reason, spec)

"""Tests for the action allowlist.

The property under test is the one the threat model depends on: an unattended
run that has read attacker-controlled text cannot produce an externally visible
side effect unless that specific action was pre-approved.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from autobot_core.actions import (
    AUTONOMOUS_ALLOWLIST,
    REGISTRY,
    ActionRequest,
    Decision,
    ExecutionMode,
    Reversibility,
    current_mode,
    evaluate,
    lookup,
)


def decide(action: str, mode: ExecutionMode, *, untrusted=False, injection=False) -> Decision:
    return evaluate(
        ActionRequest(
            action=action,
            mode=mode,
            untrusted_in_scope=untrusted,
            injection_suspected=injection,
        )
    ).decision


class TestRegistry(unittest.TestCase):
    def test_every_spec_is_self_consistent(self):
        for name, spec in REGISTRY.items():
            self.assertEqual(name, spec.name)
            if spec.externally_visible:
                self.assertNotEqual(
                    spec.autonomous_default,
                    Decision.ALLOW,
                    f"{name} is externally visible and must not auto-run unattended",
                )

    def test_allowlist_entries_are_registered(self):
        for name in AUTONOMOUS_ALLOWLIST:
            self.assertIsNotNone(lookup(name), f"{name} missing from registry")

    def test_allowlist_is_small_and_not_externally_visible(self):
        self.assertLessEqual(len(AUTONOMOUS_ALLOWLIST), 5)
        for name in AUTONOMOUS_ALLOWLIST:
            self.assertFalse(
                REGISTRY[name].externally_visible,
                f"{name} reaches a third party and must not be pre-approved",
            )

    def test_irreversible_actions_never_auto_allow_interactively(self):
        for name, spec in REGISTRY.items():
            if spec.reversibility == Reversibility.IRREVERSIBLE and spec.externally_visible:
                self.assertNotEqual(spec.interactive_default, Decision.ALLOW, name)


class TestClosedSet(unittest.TestCase):
    def test_unknown_action_denied(self):
        self.assertEqual(decide("totally.made.up", ExecutionMode.INTERACTIVE), Decision.DENY)

    def test_unknown_action_denied_even_when_clean(self):
        self.assertEqual(
            decide("gmail.send_quietly", ExecutionMode.INTERACTIVE, untrusted=False),
            Decision.DENY,
        )


class TestAutonomousRestriction(unittest.TestCase):
    """The poll.sh scenario: cron reads an inbox, then wants to act."""

    def test_email_send_blocked_after_reading_untrusted(self):
        self.assertEqual(
            decide("gmail.send", ExecutionMode.AUTONOMOUS, untrusted=True), Decision.DENY
        )

    def test_imessage_send_blocked_after_reading_untrusted(self):
        self.assertEqual(
            decide("messages.send", ExecutionMode.AUTONOMOUS, untrusted=True), Decision.DENY
        )

    def test_contact_rewrite_blocked(self):
        # Rewriting a contact's number redirects future messages to an attacker.
        self.assertEqual(
            decide("contacts.update", ExecutionMode.AUTONOMOUS, untrusted=True), Decision.DENY
        )

    def test_school_submit_blocked(self):
        self.assertEqual(
            decide("school.submit", ExecutionMode.AUTONOMOUS, untrusted=True), Decision.DENY
        )

    def test_owner_notification_still_allowed(self):
        # The whole point of the cron job must keep working.
        self.assertEqual(
            decide("telegram.send_owner", ExecutionMode.AUTONOMOUS, untrusted=True),
            Decision.ALLOW,
        )

    def test_journal_write_still_allowed(self):
        self.assertEqual(
            decide("memory.write_journal", ExecutionMode.AUTONOMOUS, untrusted=True),
            Decision.ALLOW,
        )

    def test_semantic_memory_write_blocked_unattended(self):
        # profile.md is auto-injected forever; this is the implant vector.
        self.assertEqual(
            decide("memory.write_semantic", ExecutionMode.AUTONOMOUS, untrusted=True),
            Decision.DENY,
        )

    def test_confirm_becomes_deny_when_nobody_can_confirm(self):
        self.assertEqual(
            decide("calendar.create", ExecutionMode.AUTONOMOUS, untrusted=False),
            Decision.DENY,
        )


class TestInjectionRevokesAuthority(unittest.TestCase):
    def test_injection_denies_even_interactively(self):
        for action in ("gmail.send", "messages.send", "contacts.delete", "browser.eval"):
            self.assertEqual(
                decide(action, ExecutionMode.INTERACTIVE, untrusted=True, injection=True),
                Decision.DENY,
                action,
            )

    def test_allowlisted_reporting_survives_injection(self):
        # The agent must still be able to tell the operator what it found.
        self.assertEqual(
            decide(
                "telegram.send_owner",
                ExecutionMode.AUTONOMOUS,
                untrusted=True,
                injection=True,
            ),
            Decision.ALLOW,
        )


class TestInteractiveDefaults(unittest.TestCase):
    def test_send_requires_confirmation_when_clean(self):
        self.assertEqual(
            decide("gmail.send", ExecutionMode.INTERACTIVE, untrusted=False), Decision.CONFIRM
        )

    def test_reminders_create_is_frictionless(self):
        self.assertEqual(
            decide("reminders.create", ExecutionMode.INTERACTIVE), Decision.ALLOW
        )


class TestModeInference(unittest.TestCase):
    def test_explicit_autonomous(self):
        self.assertEqual(
            current_mode({"AUTOBOT_MODE": "autonomous"}), ExecutionMode.AUTONOMOUS
        )

    def test_explicit_interactive(self):
        self.assertEqual(
            current_mode({"AUTOBOT_MODE": "interactive"}), ExecutionMode.INTERACTIVE
        )

    def test_unset_fails_closed_without_tty(self):
        # Under a test runner stdin is not a TTY, so this must not be interactive.
        self.assertEqual(current_mode({}), ExecutionMode.AUTONOMOUS)


if __name__ == "__main__":
    unittest.main()

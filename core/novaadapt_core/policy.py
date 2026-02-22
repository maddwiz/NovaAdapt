from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DANGEROUS_TYPES = {
    "delete",
    "remove",
    "rm",
    "format",
    "shutdown",
    "reboot",
    "kill",
    "terminate",
    "run_shell",
    "shell",
    "terminal",
}

DANGEROUS_KEYWORDS = {
    "rm -rf",
    "format",
    "factory reset",
    "delete",
    "drop table",
    "shutdown",
    "reboot",
    "killall",
    "poweroff",
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    dangerous: bool
    reason: str


class ActionPolicy:
    """Guards desktop action execution with minimal but explicit risk checks."""

    def evaluate(self, action: dict[str, Any], allow_dangerous: bool) -> PolicyDecision:
        action_type = str(action.get("type", "")).strip().lower()
        target = str(action.get("target", "")).strip().lower()
        value = str(action.get("value", "")).strip().lower()
        haystack = f"{action_type} {target} {value}"

        dangerous = action_type in DANGEROUS_TYPES or any(
            keyword in haystack for keyword in DANGEROUS_KEYWORDS
        )
        if dangerous and not allow_dangerous:
            return PolicyDecision(
                allowed=False,
                dangerous=True,
                reason=(
                    "Blocked potentially destructive action. "
                    "Re-run with --allow-dangerous after reviewing the plan."
                ),
            )

        return PolicyDecision(allowed=True, dangerous=dangerous, reason="allowed")

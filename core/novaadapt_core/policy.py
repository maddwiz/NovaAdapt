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
    "ha_service",
    "mqtt_publish",
    "run_adb",
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
    "delete account",
    "factory reset",
}

MOBILE_FINANCIAL_KEYWORDS = {
    "bank",
    "banking",
    "payment",
    "pay bill",
    "pay",
    "transfer",
    "wire",
    "withdraw",
    "deposit",
    "venmo",
    "cash app",
    "zelle",
    "paypal",
    "credit card",
    "debit card",
    "wallet",
}

PHYSICAL_ACTUATION_KEYWORDS = {
    "garage",
    "door",
    "gate",
    "unlock",
    "lock",
    "alarm",
    "vacuum",
    "robot",
    "thermostat",
    "heater",
    "sprinkler",
    "printer",
    "3d printer",
    "light",
    "actuator",
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
        platform = str(action.get("platform", "")).strip().lower()
        domain = str(action.get("domain", "")).strip().lower()
        service = str(action.get("service", "")).strip().lower()
        entity_id = str(action.get("entity_id", "")).strip().lower()
        topic = str(action.get("topic", "")).strip().lower()
        command = str(action.get("command", "")).strip().lower()
        haystack = " ".join(
            part
            for part in (action_type, platform, target, value, domain, service, entity_id, topic, command)
            if part
        )

        dangerous = action_type in DANGEROUS_TYPES or any(
            keyword in haystack for keyword in DANGEROUS_KEYWORDS
        )
        if platform in {"android", "ios"} and any(keyword in haystack for keyword in MOBILE_FINANCIAL_KEYWORDS):
            dangerous = True
        if action_type in {"ha_service", "mqtt_publish"}:
            dangerous = True
        if any(keyword in haystack for keyword in PHYSICAL_ACTUATION_KEYWORDS):
            dangerous = True
        if dangerous and not allow_dangerous:
            return PolicyDecision(
                allowed=False,
                dangerous=True,
                reason=(
                    "Blocked potentially destructive or sensitive action. "
                    "Re-run with --allow-dangerous after reviewing the plan."
                ),
            )

        return PolicyDecision(allowed=True, dangerous=dangerous, reason="allowed")

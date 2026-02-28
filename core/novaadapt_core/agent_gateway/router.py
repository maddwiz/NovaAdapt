from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RoutingDecision:
    workspace_id: str
    profile_name: str


class GatewayRouter:
    def __init__(
        self,
        *,
        default_workspace: str = "default",
        default_profile: str = "unleashed_local",
        channel_workspace_map: dict[str, str] | None = None,
        channel_profile_map: dict[str, str] | None = None,
    ) -> None:
        self.default_workspace = str(default_workspace or "default")
        self.default_profile = str(default_profile or "unleashed_local")
        self.channel_workspace_map = {
            str(k).strip().lower(): str(v).strip()
            for k, v in (channel_workspace_map or {}).items()
            if str(k).strip() and str(v).strip()
        }
        self.channel_profile_map = {
            str(k).strip().lower(): str(v).strip()
            for k, v in (channel_profile_map or {}).items()
            if str(k).strip() and str(v).strip()
        }

    def route(self, message: dict[str, Any]) -> RoutingDecision:
        row = message if isinstance(message, dict) else {}
        channel = str(row.get("channel") or row.get("connector") or "").strip().lower()
        metadata = row.get("metadata")
        metadata_obj = metadata if isinstance(metadata, dict) else {}

        workspace = str(metadata_obj.get("workspace_id") or "").strip()
        if not workspace and channel:
            workspace = str(self.channel_workspace_map.get(channel, "")).strip()
        workspace = workspace or self.default_workspace

        profile = str(metadata_obj.get("profile_name") or metadata_obj.get("policy_profile") or "").strip()
        if not profile and channel:
            profile = str(self.channel_profile_map.get(channel, "")).strip()
        profile = profile or self.default_profile

        return RoutingDecision(workspace_id=workspace, profile_name=profile)

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from novaadapt_shared import ModelRouter, UndoQueue

from .adapt import AdaptBondCache, AdaptPersonaEngine, AdaptToggleStore
from .audit_store import AuditStore
from .agent import NovaAdaptAgent
from .browser_executor import BrowserExecutor
from .channels import ChannelRegistry, build_channel_registry
from .canvas import CanvasRenderResult, CanvasRenderer, CanvasSessionStore, canvas_enabled
from .control_artifacts import ControlArtifactStore
from .directshell import DirectShellClient
from .flags import coerce_bool
from .homeassistant_executor import HomeAssistantExecutor
from .memory import MemoryBackend, build_memory_backend
from .mobile_executor import AndroidMaestroExecutor, IOSAppiumExecutor, IOSVisionExecutor, UnifiedMobileExecutor
from .novaprime import (
    NovaPrimeBackend,
    build_novaprime_client,
    kernel_required,
    run_with_kernel,
    should_use_kernel,
)
from .plan_store import PlanStore
from .policy import ActionPolicy
from .plugins import PluginRegistry, SIBBridge, build_plugin_registry
from .runtime_governance import RuntimeGovernance, _UNSET as _RUNTIME_UNSET
from .voice import build_stt_backend, build_tts_backend
from .vision_grounding import VisionGroundingExecutor
from .workflows import WorkflowCheckpointStore, WorkflowEngine, WorkflowRecord, WorkflowStore, workflows_enabled


def _result_payload(status: str, output: str, action: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": str(status),
        "output": str(output),
        "action": dict(action),
    }
    if data is not None:
        payload["data"] = dict(data)
    return payload

class NovaAdaptService:
    """Shared application service used by CLI and HTTP server."""

    def __init__(
        self,
        default_config: Path,
        db_path: Path | None = None,
        plans_db_path: Path | None = None,
        audit_db_path: Path | None = None,
        router_loader: Callable[[Path], ModelRouter] | None = None,
        directshell_factory: Callable[[], DirectShellClient] | None = None,
        browser_executor_factory: Callable[[], BrowserExecutor] | None = None,
        vision_executor_factory: Callable[[], VisionGroundingExecutor] | None = None,
        mobile_executor_factory: Callable[[], UnifiedMobileExecutor] | None = None,
        homeassistant_executor_factory: Callable[[], HomeAssistantExecutor] | None = None,
        memory_backend: MemoryBackend | None = None,
        novaprime_client: NovaPrimeBackend | None = None,
        adapt_toggle_store: AdaptToggleStore | None = None,
        adapt_bond_cache: AdaptBondCache | None = None,
        adapt_persona: AdaptPersonaEngine | None = None,
        channel_registry: ChannelRegistry | None = None,
        plugin_registry: PluginRegistry | None = None,
        runtime_governance: RuntimeGovernance | None = None,
    ) -> None:
        self.default_config = default_config
        self.db_path = db_path
        self.plans_db_path = plans_db_path
        self.audit_db_path = audit_db_path
        self.router_loader = router_loader or ModelRouter.from_config_file
        self.directshell_factory = directshell_factory or DirectShellClient
        self.browser_executor_factory = browser_executor_factory or BrowserExecutor
        self.vision_executor_factory = vision_executor_factory
        self.mobile_executor_factory = mobile_executor_factory
        self.homeassistant_executor_factory = homeassistant_executor_factory or HomeAssistantExecutor
        self.memory_backend = memory_backend or build_memory_backend()
        self.novaprime_client = novaprime_client or build_novaprime_client()
        self.adapt_toggle_store = adapt_toggle_store or AdaptToggleStore()
        self.adapt_bond_cache = adapt_bond_cache or AdaptBondCache()
        self.adapt_persona = adapt_persona or AdaptPersonaEngine()
        self.channel_registry = channel_registry or build_channel_registry()
        self.plugin_registry = plugin_registry or build_plugin_registry()
        self.runtime_governance = runtime_governance or RuntimeGovernance(self._runtime_governance_state_path())
        self._plan_store: PlanStore | None = None
        self._audit_store: AuditStore | None = None
        self._browser_executor: BrowserExecutor | None = None
        self._vision_executor: VisionGroundingExecutor | None = None
        self._mobile_executor: UnifiedMobileExecutor | None = None
        self._homeassistant_executor: HomeAssistantExecutor | None = None
        self._sib_bridge: SIBBridge | None = None
        self._canvas_renderer: CanvasRenderer | None = None
        self._canvas_sessions: CanvasSessionStore | None = None
        self._workflow_store: WorkflowStore | None = None
        self._workflow_checkpoints: WorkflowCheckpointStore | None = None
        self._workflow_engine: WorkflowEngine | None = None
        self._control_artifact_store: ControlArtifactStore | None = None

    def close(self) -> None:
        browser = self._browser_executor
        self._browser_executor = None
        vision = self._vision_executor
        self._vision_executor = None
        mobile = self._mobile_executor
        self._mobile_executor = None
        homeassistant = self._homeassistant_executor
        self._homeassistant_executor = None
        if browser is None:
            browser = None
        for runtime in (browser, vision, mobile, homeassistant):
            close_fn = getattr(runtime, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass

    def models(self, config_path: Path | None = None) -> list[dict[str, Any]]:
        router = self.router_loader(config_path or self.default_config)
        return [
            {
                "name": item.name,
                "model": item.model,
                "provider": item.provider,
                "base_url": item.base_url,
            }
            for item in router.list_models()
        ]

    def check(
        self,
        config_path: Path | None = None,
        model_names: list[str] | None = None,
        probe_prompt: str = "Reply with: OK",
    ) -> list[dict[str, object]]:
        router = self.router_loader(config_path or self.default_config)
        return router.health_check(model_names=model_names, probe_prompt=probe_prompt)

    def directshell_probe(self) -> dict[str, Any]:
        client = self.directshell_factory()
        probe_fn = getattr(client, "probe", None)
        if not callable(probe_fn):
            return {
                "ok": False,
                "error": "DirectShell probe is not implemented by current directshell_factory",
            }
        result = probe_fn()
        if isinstance(result, dict):
            return result
        return {
            "ok": False,
            "error": "DirectShell probe returned invalid payload",
        }

    def browser_status(self) -> dict[str, Any]:
        result = self._browser().probe()
        if isinstance(result, dict):
            return result
        return {
            "ok": False,
            "transport": "browser",
            "error": "Browser probe returned invalid payload",
        }

    def browser_pages(self) -> dict[str, Any]:
        result = self._browser().execute_action({"type": "list_pages"})
        out: dict[str, Any] = {
            "status": str(result.status),
            "output": str(result.output),
        }
        if isinstance(result.data, dict):
            out.update(result.data)
        return out

    def browser_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_action = payload.get("action")
        action: dict[str, Any]
        if isinstance(raw_action, dict):
            action = dict(raw_action)
        elif isinstance(payload, dict) and payload.get("type") is not None:
            action = dict(payload)
        else:
            raise ValueError("'action' must be an object or provide a top-level 'type'")

        result = self._browser().execute_action(action)
        out: dict[str, Any] = {
            "status": str(result.status),
            "output": str(result.output),
            "action": action,
        }
        if isinstance(result.data, dict):
            out["data"] = result.data
        return out

    def browser_close(self) -> dict[str, Any]:
        result = self._browser().close()
        return {
            "status": str(result.status),
            "output": str(result.output),
        }

    def vision_execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        config_path = Path(payload.get("config") or self.default_config)
        goal = str(payload.get("goal") or payload.get("objective") or "").strip()
        if not goal:
            raise ValueError("'goal' or 'objective' is required")

        strategy = str(payload.get("strategy", "single") or "single")
        model_name = str(payload.get("model") or "").strip() or None
        candidate_models = self._as_name_list(payload.get("candidates"))
        fallback_models = self._as_name_list(payload.get("fallbacks"))
        execute = coerce_bool(payload.get("execute"), default=False)
        allow_dangerous = coerce_bool(payload.get("allow_dangerous"), default=False)
        screenshot_png = self._decode_base64_image(payload.get("screenshot_base64"))
        app_name = str(payload.get("app_name") or "").strip()
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        grounded = self._vision().ground(
            goal=goal,
            config_path=config_path,
            screenshot_png=screenshot_png,
            app_name=app_name,
            model_name=model_name,
            strategy=strategy,
            candidate_models=candidate_models or None,
            fallback_models=fallback_models or None,
            context=context,
            ocr_text=str(payload.get("ocr_text") or ""),
            accessibility_tree=str(payload.get("accessibility_tree") or ""),
        )
        policy = ActionPolicy()
        decision = policy.evaluate(grounded.action, allow_dangerous=allow_dangerous)
        runtime_result = self._execute_routed_action(
            grounded.action,
            execute=(execute and decision.allowed),
            config_path=config_path,
        )
        out: dict[str, Any] = {
            "goal": goal,
            "status": "blocked" if execute and not decision.allowed else runtime_result["status"],
            "output": decision.reason if execute and not decision.allowed else runtime_result["output"],
            "action": runtime_result["action"],
            "dangerous": decision.dangerous,
            "vision": {
                "confidence": grounded.confidence,
                "reason": grounded.reason,
                "model": grounded.model_name,
                "model_id": grounded.model_id,
                "strategy": grounded.strategy,
                "vote_summary": grounded.vote_summary,
                "attempted_models": grounded.attempted_models,
                "model_errors": grounded.model_errors,
                "ocr_text": grounded.ocr_text,
                "accessibility_tree": grounded.accessibility_tree,
                "screenshot_base64": grounded.screenshot_base64,
            },
        }
        if runtime_result.get("data") is not None:
            out["data"] = runtime_result.get("data")
        artifact = self._store_control_artifact(
            control_type="vision",
            result=out,
            goal=goal,
            transport="vision-grounding",
            preview_png=self._decode_base64_image(grounded.screenshot_base64),
            model=grounded.model_name,
            model_id=grounded.model_id,
            metadata={
                "app_name": app_name,
                "context": context,
                "vision": self._vision_metadata_without_screenshot(out.get("vision")),
            },
        )
        if artifact is not None:
            out["artifact"] = artifact
        self._ingest_control_memory(
            control_type="vision",
            payload={
                "goal": goal,
                "result": out,
                "context": context,
            },
            event_names=["control.vision", f"control.vision.{out['status']}"],
        )
        return out

    def mobile_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        platform_name = str(payload.get("platform") or "").strip().lower()
        if platform_name not in {"android", "ios"}:
            raise ValueError("'platform' must be 'android' or 'ios'")
        execute = coerce_bool(payload.get("execute"), default=False)
        allow_dangerous = coerce_bool(payload.get("allow_dangerous"), default=False)
        config_path = Path(payload.get("config") or self.default_config)
        strategy = str(payload.get("strategy", "single") or "single")
        model_name = str(payload.get("model") or "").strip() or None
        candidate_models = self._as_name_list(payload.get("candidates"))
        fallback_models = self._as_name_list(payload.get("fallbacks"))

        raw_action = payload.get("action")
        has_direct_mobile_action = isinstance(raw_action, dict) or payload.get("type") is not None
        prefer_appium = coerce_bool(payload.get("prefer_appium"), default=False)

        if platform_name == "ios" and prefer_appium and has_direct_mobile_action and self._mobile().ios_appium_executor.available():
            if isinstance(raw_action, dict):
                action = dict(raw_action)
            else:
                action = {key: value for key, value in payload.items() if key not in {"action", "config"}}
            action["platform"] = "ios"
            policy = ActionPolicy()
            decision = policy.evaluate(action, allow_dangerous=allow_dangerous)
            runtime_result = self._mobile().execute_action(
                action,
                dry_run=not (execute and decision.allowed),
            )
            out = {
                "platform": "ios",
                "transport": "appium",
                "status": "blocked" if execute and not decision.allowed else runtime_result.status,
                "output": decision.reason if execute and not decision.allowed else runtime_result.output,
                "action": runtime_result.action,
                "dangerous": decision.dangerous,
            }
            if runtime_result.data is not None:
                out["data"] = runtime_result.data
            artifact = self._store_control_artifact(
                control_type="mobile",
                result=out,
                goal=str(payload.get("goal") or payload.get("objective") or ""),
                platform="ios",
                transport="appium",
                preview_png=self._decode_base64_image(payload.get("screenshot_base64")),
                metadata={
                    "prefer_appium": True,
                    "executor": "ios-appium",
                },
            )
            if artifact is not None:
                out["artifact"] = artifact
        elif platform_name == "ios":
            grounded, routed_action = self._mobile().ios_executor.execute(
                payload,
                config_path=config_path,
                execute=execute,
                strategy=strategy,
                model_name=model_name,
                candidate_models=candidate_models or None,
                fallback_models=fallback_models or None,
            )
            policy = ActionPolicy()
            decision = policy.evaluate(routed_action, allow_dangerous=allow_dangerous)
            runtime_result = self._execute_routed_action(
                routed_action,
                execute=(execute and decision.allowed),
                config_path=config_path,
            )
            out: dict[str, Any] = {
                "platform": "ios",
                "goal": str(payload.get("goal") or payload.get("objective") or ""),
                "status": "blocked" if execute and not decision.allowed else runtime_result["status"],
                "output": decision.reason if execute and not decision.allowed else runtime_result["output"],
                "action": runtime_result["action"],
                "dangerous": decision.dangerous,
                "vision": {
                    "confidence": grounded.confidence,
                    "reason": grounded.reason,
                    "model": grounded.model_name,
                    "model_id": grounded.model_id,
                    "screenshot_base64": grounded.screenshot_base64,
                },
            }
            if runtime_result.get("data") is not None:
                out["data"] = runtime_result.get("data")
            artifact = self._store_control_artifact(
                control_type="mobile",
                result=out,
                goal=str(payload.get("goal") or payload.get("objective") or ""),
                platform="ios",
                transport="vision",
                preview_png=self._decode_base64_image(grounded.screenshot_base64),
                model=grounded.model_name,
                model_id=grounded.model_id,
                metadata={
                    "app_name": str(payload.get("app_name") or "iPhone").strip(),
                    "vision": self._vision_metadata_without_screenshot(out.get("vision")),
                },
            )
            if artifact is not None:
                out["artifact"] = artifact
        else:
            raw_action = payload.get("action")
            if isinstance(raw_action, dict):
                action = dict(raw_action)
            else:
                action = {key: value for key, value in payload.items() if key not in {"action", "config"}}
            action["platform"] = "android"
            policy = ActionPolicy()
            decision = policy.evaluate(action, allow_dangerous=allow_dangerous)
            runtime_result = self._execute_routed_action(
                action,
                execute=(execute and decision.allowed),
                config_path=config_path,
            )
            out = {
                "platform": "android",
                "status": "blocked" if execute and not decision.allowed else runtime_result["status"],
                "output": decision.reason if execute and not decision.allowed else runtime_result["output"],
                "action": runtime_result["action"],
                "dangerous": decision.dangerous,
            }
            if runtime_result.get("data") is not None:
                out["data"] = runtime_result.get("data")
            artifact = self._store_control_artifact(
                control_type="mobile",
                result=out,
                goal=str(payload.get("goal") or payload.get("objective") or ""),
                platform="android",
                transport="android-maestro",
                preview_png=self._decode_base64_image(payload.get("screenshot_base64")),
                metadata={
                    "executor": "android-maestro",
                },
            )
            if artifact is not None:
                out["artifact"] = artifact

        self._ingest_control_memory(
            control_type="mobile",
            payload=out,
            event_names=["control.mobile", f"control.mobile.{platform_name}", f"control.mobile.{out['status']}"],
        )
        return out

    def mobile_status(self) -> dict[str, Any]:
        return self._mobile().status()

    def list_control_artifacts(self, *, limit: int = 10, control_type: str | None = None) -> list[dict[str, Any]]:
        return self._control_artifact_store_obj().list(limit=max(1, int(limit)), control_type=control_type)

    def get_control_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return self._control_artifact_store_obj().get(artifact_id)

    def control_artifact_preview(self, artifact_id: str) -> tuple[bytes, str] | None:
        return self._control_artifact_store_obj().read_preview(artifact_id)

    def runtime_governance_status(self, *, job_stats: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.runtime_governance.snapshot(job_stats=job_stats)

    def runtime_governance_preflight(self) -> str | None:
        return self.runtime_governance.preflight_error()

    def runtime_governance_update(
        self,
        *,
        paused: bool | None = None,
        pause_reason: str | None = None,
        budget_limit_usd: float | None | object = _RUNTIME_UNSET,
        max_active_runs: int | None | object = _RUNTIME_UNSET,
        reset_usage: bool = False,
        job_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        budget_value = (
            budget_limit_usd
            if budget_limit_usd is _RUNTIME_UNSET or budget_limit_usd is None or isinstance(budget_limit_usd, (int, float))
            else _RUNTIME_UNSET
        )
        max_active_value = (
            max_active_runs
            if max_active_runs is _RUNTIME_UNSET or max_active_runs is None or isinstance(max_active_runs, int)
            else _RUNTIME_UNSET
        )
        state = self.runtime_governance.update(
            paused=paused,
            pause_reason=pause_reason,
            budget_limit_usd=budget_value,
            max_active_runs=max_active_value,
        )
        if reset_usage:
            state = self.runtime_governance.reset_usage()
        if isinstance(job_stats, dict):
            state["jobs"] = job_stats
        return state

    def homeassistant_status(self) -> dict[str, Any]:
        return self._homeassistant().status()

    def mqtt_status(self) -> dict[str, Any]:
        status = self._homeassistant().status()
        mqtt_status = status.get("mqtt_direct") if isinstance(status, dict) else None
        if isinstance(mqtt_status, dict):
            return mqtt_status
        return {
            "ok": False,
            "configured": False,
            "transport": "mqtt-direct",
            "error": "MQTT status unavailable",
        }

    def homeassistant_discover(
        self,
        *,
        domain: str = "",
        entity_id_prefix: str = "",
        limit: int = 250,
    ) -> dict[str, Any]:
        return self._homeassistant().discover(
            domain=domain,
            entity_id_prefix=entity_id_prefix,
            limit=max(1, int(limit)),
        )

    def mqtt_subscribe(
        self,
        *,
        topic: str,
        timeout_seconds: float = 3.0,
        max_messages: int = 10,
        qos: int = 0,
    ) -> dict[str, Any]:
        out = self.homeassistant_action(
            {
                "action": {
                    "type": "mqtt_subscribe",
                    "topic": str(topic or ""),
                    "timeout_seconds": float(timeout_seconds),
                    "max_messages": max(1, int(max_messages)),
                    "qos": int(qos),
                    "transport": "mqtt-direct",
                },
                "execute": True,
                "allow_dangerous": False,
            }
        )
        return out

    def homeassistant_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_action = payload.get("action")
        if isinstance(raw_action, dict):
            action = dict(raw_action)
        else:
            action = {key: value for key, value in payload.items() if key != "action"}
        execute = coerce_bool(payload.get("execute"), default=False)
        allow_dangerous = coerce_bool(payload.get("allow_dangerous"), default=False)
        policy = ActionPolicy()
        decision = policy.evaluate(action, allow_dangerous=allow_dangerous)
        runtime_result = self._execute_routed_action(action, execute=(execute and decision.allowed))
        out: dict[str, Any] = {
            "status": "blocked" if execute and not decision.allowed else runtime_result["status"],
            "output": decision.reason if execute and not decision.allowed else runtime_result["output"],
            "action": runtime_result["action"],
            "dangerous": decision.dangerous,
        }
        if runtime_result.get("data") is not None:
            out["data"] = runtime_result.get("data")
        runtime_transport = ""
        if isinstance(runtime_result.get("data"), dict):
            runtime_transport = str(runtime_result["data"].get("transport") or "").strip()
        artifact = self._store_control_artifact(
            control_type="iot",
            result=out,
            goal=str(payload.get("goal") or payload.get("objective") or ""),
            transport=runtime_transport or "homeassistant",
            metadata={
                "executor": "homeassistant",
            },
        )
        if artifact is not None:
            out["artifact"] = artifact
        self._ingest_control_memory(
            control_type="iot",
            payload=out,
            event_names=["control.iot", f"control.iot.{out['status']}"],
        )
        return out

    def memory_status(self) -> dict[str, Any]:
        status = self.memory_backend.status()
        if isinstance(status, dict):
            return status
        return {
            "ok": False,
            "enabled": True,
            "backend": "unknown",
            "error": "Memory backend returned invalid status payload",
        }

    def novaprime_status(self) -> dict[str, Any]:
        status = self.novaprime_client.status()
        if isinstance(status, dict):
            return status
        return {
            "ok": False,
            "enabled": True,
            "backend": "unknown",
            "error": "NovaPrime client returned invalid status payload",
        }

    def capabilities(self) -> dict[str, Any]:
        try:
            novaprime = self.novaprime_status()
        except Exception as exc:
            novaprime = {
                "ok": False,
                "enabled": False,
                "backend": "unknown",
                "error": str(exc),
            }
        novaprime_enabled = bool(novaprime.get("enabled", False))
        novaprime_required = bool(novaprime.get("required", False))
        return {
            "standalone_ready": True,
            "open_source_mode": {
                "requires_novaprime": False,
                "requires_mesh": False,
                "requires_game": False,
            },
            "integrations": {
                "novaprime": {
                    "optional": True,
                    "enabled": novaprime_enabled,
                    "required": novaprime_required,
                    "backend": str(novaprime.get("backend") or ""),
                    "ok": bool(novaprime.get("ok", False)),
                },
                "mesh_perks": {"available": novaprime_enabled},
                "sib_perks": {"available": novaprime_enabled},
                "aetherion_perks": {"available": novaprime_enabled},
            },
        }

    def novaprime_reason_dual(self, task: str) -> dict[str, Any]:
        normalized_task = str(task or "").strip()
        if not normalized_task:
            raise ValueError("'task' is required")
        result = self.novaprime_client.reason_dual(normalized_task)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime reason response"}

    def novaprime_emotion_get(self) -> dict[str, Any]:
        result = self.novaprime_client.emotion_get()
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime emotion response"}

    def novaprime_emotion_set(self, chemicals: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = chemicals if isinstance(chemicals, dict) else {}
        normalized: dict[str, float] = {}
        for key, value in payload.items():
            name = str(key or "").strip()
            if not name:
                continue
            try:
                normalized[name] = float(value)
            except Exception:
                continue
        result = self.novaprime_client.emotion_set(normalized)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime emotion update response"}

    def novaprime_mesh_balance(self, node_id: str) -> dict[str, Any]:
        normalized_node = str(node_id or "").strip()
        if not normalized_node:
            raise ValueError("'node_id' is required")
        balance = float(self.novaprime_client.mesh_balance(normalized_node))
        return {
            "ok": True,
            "node_id": normalized_node,
            "balance": balance,
        }

    def novaprime_mesh_reputation(self, node_id: str) -> dict[str, Any]:
        normalized_node = str(node_id or "").strip()
        if not normalized_node:
            raise ValueError("'node_id' is required")
        reputation = float(self.novaprime_client.mesh_reputation(normalized_node))
        return {
            "ok": True,
            "node_id": normalized_node,
            "reputation": reputation,
        }

    def novaprime_mesh_peers(self) -> dict[str, Any]:
        peers = self.novaprime_client.mesh_peers()
        if not isinstance(peers, list):
            return {"ok": False, "error": "invalid novaprime mesh peers response", "count": 0, "peers": []}
        return {"ok": True, "count": len(peers), "peers": peers}

    def novaprime_mesh_peer_register(
        self,
        node_id: str,
        url: str,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_node = str(node_id or "").strip()
        normalized_url = str(url or "").strip()
        if not normalized_node:
            raise ValueError("'node_id' is required")
        if not normalized_url:
            raise ValueError("'url' is required")
        caps = capabilities if isinstance(capabilities, list) else []
        normalized_caps = [str(item).strip() for item in caps if str(item).strip()]
        result = self.novaprime_client.mesh_peer_register(
            normalized_node,
            normalized_url,
            normalized_caps,
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime mesh peer register response"}

    def novaprime_mesh_credit(self, node_id: str, amount: float) -> dict[str, Any]:
        normalized_node = str(node_id or "").strip()
        normalized_amount = float(amount)
        if not normalized_node:
            raise ValueError("'node_id' is required")
        if normalized_amount <= 0:
            raise ValueError("'amount' must be > 0")
        result = self.novaprime_client.mesh_credit(normalized_node, normalized_amount)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime mesh credit response"}

    def novaprime_mesh_transfer(self, from_node: str, to_node: str, amount: float) -> dict[str, Any]:
        normalized_from = str(from_node or "").strip()
        normalized_to = str(to_node or "").strip()
        normalized_amount = float(amount)
        if not normalized_from:
            raise ValueError("'from_node' is required")
        if not normalized_to:
            raise ValueError("'to_node' is required")
        if normalized_amount <= 0:
            raise ValueError("'amount' must be > 0")
        result = self.novaprime_client.mesh_transfer(normalized_from, normalized_to, normalized_amount)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime mesh transfer response"}

    def novaprime_mesh_compute_request(
        self,
        requester: str,
        provider: str,
        units: float,
        unit_price: float,
    ) -> dict[str, Any]:
        normalized_requester = str(requester or "").strip()
        normalized_provider = str(provider or "").strip()
        normalized_units = float(units)
        normalized_unit_price = float(unit_price)
        if not normalized_requester:
            raise ValueError("'requester' is required")
        if not normalized_provider:
            raise ValueError("'provider' is required")
        if normalized_units <= 0:
            raise ValueError("'units' must be > 0")
        if normalized_unit_price <= 0:
            raise ValueError("'unit_price' must be > 0")
        result = self.novaprime_client.mesh_compute_request(
            normalized_requester,
            normalized_provider,
            normalized_units,
            normalized_unit_price,
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime mesh compute request response"}

    def novaprime_mesh_compute_settle(
        self,
        *,
        request_id: str = "",
        requester: str,
        provider: str,
        units: float,
        unit_price: float,
        status: str = "requested",
        ts: str = "",
    ) -> dict[str, Any]:
        normalized_requester = str(requester or "").strip()
        normalized_provider = str(provider or "").strip()
        normalized_units = float(units)
        normalized_unit_price = float(unit_price)
        normalized_request_id = str(request_id or "").strip()
        normalized_status = str(status or "requested").strip() or "requested"
        normalized_ts = str(ts or "").strip()
        if not normalized_requester:
            raise ValueError("'requester' is required")
        if not normalized_provider:
            raise ValueError("'provider' is required")
        if normalized_units <= 0:
            raise ValueError("'units' must be > 0")
        if normalized_unit_price <= 0:
            raise ValueError("'unit_price' must be > 0")
        result = self.novaprime_client.mesh_compute_settle(
            request_id=normalized_request_id,
            requester=normalized_requester,
            provider=normalized_provider,
            units=normalized_units,
            unit_price=normalized_unit_price,
            status=normalized_status,
            ts=normalized_ts,
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime mesh compute settle response"}

    def novaprime_marketplace_listings(self) -> dict[str, Any]:
        listings = self.novaprime_client.marketplace_listings()
        if isinstance(listings, list):
            return {"ok": True, "listings": listings}
        return {"ok": False, "listings": [], "error": "invalid novaprime marketplace listings response"}

    def novaprime_marketplace_list(
        self,
        capsule_id: str,
        seller: str,
        price: float,
        title: str,
    ) -> dict[str, Any]:
        normalized_capsule = str(capsule_id or "").strip()
        normalized_seller = str(seller or "").strip()
        normalized_title = str(title or "").strip()
        normalized_price = float(price)
        if not normalized_capsule:
            raise ValueError("'capsule_id' is required")
        if not normalized_seller:
            raise ValueError("'seller' is required")
        if not normalized_title:
            raise ValueError("'title' is required")
        if normalized_price < 0:
            raise ValueError("'price' must be >= 0")
        result = self.novaprime_client.marketplace_list(
            normalized_capsule,
            normalized_seller,
            normalized_price,
            normalized_title,
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime marketplace list response"}

    def novaprime_marketplace_buy(self, listing_id: str, buyer: str) -> dict[str, Any]:
        normalized_listing = str(listing_id or "").strip()
        normalized_buyer = str(buyer or "").strip()
        if not normalized_listing:
            raise ValueError("'listing_id' is required")
        if not normalized_buyer:
            raise ValueError("'buyer' is required")
        result = self.novaprime_client.marketplace_buy(normalized_listing, normalized_buyer)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime marketplace buy response"}

    def novaprime_identity_bond(
        self,
        adapt_id: str,
        player_id: str,
        *,
        element: str = "",
        subclass: str = "",
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self.novaprime_client.identity_bond(
            normalized_adapt,
            normalized_player,
            element=str(element or ""),
            subclass=str(subclass or ""),
        )
        if isinstance(result, dict):
            out = dict(result)
            cached = self._cache_bond_from_novaprime_result(
                result=out,
                adapt_id_hint=normalized_adapt,
                player_id_hint=normalized_player,
                source="novaprime_identity_bond",
            )
            if isinstance(cached, dict):
                out["cached_bond"] = cached
            return out
        return {"ok": False, "error": "invalid novaprime identity bond response"}

    def novaprime_identity_verify(self, adapt_id: str, player_id: str) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")
        out: dict[str, Any] = {
            "ok": True,
            "adapt_id": normalized_adapt,
            "player_id": normalized_player,
            "verified": False,
        }
        verified = False
        verify_error = ""
        try:
            verified = bool(self.novaprime_client.identity_verify(normalized_adapt, normalized_player))
            if verified:
                out["verified_source"] = "novaprime"
        except Exception as exc:
            verify_error = str(exc)
            out["novaprime_error"] = verify_error

        if verified:
            profile: dict[str, Any] | None = None
            try:
                loaded_profile = self.novaprime_client.identity_profile(normalized_adapt)
                if isinstance(loaded_profile, dict):
                    profile = loaded_profile
                    out["profile"] = profile
            except Exception as exc:
                out["profile_error"] = str(exc)
            try:
                cached = self.adapt_bond_cache.remember(
                    normalized_adapt,
                    normalized_player,
                    verified=True,
                    profile=profile if isinstance(profile, dict) else {},
                    source="novaprime_identity_verify",
                )
                out["cached_bond"] = cached
            except Exception as exc:
                out["ok"] = False
                out["error"] = str(exc)
                out["verified"] = False
                return out
        else:
            cache_verified = self.adapt_bond_cache.verify_cached(normalized_adapt, normalized_player)
            out["cache_verified"] = cache_verified
            if cache_verified:
                verified = True
                out["verified_source"] = "cache_fallback"
                cached = self.adapt_bond_cache.get(normalized_adapt)
                if isinstance(cached, dict):
                    out["cached_bond"] = cached
            elif verify_error:
                out["ok"] = False

        out["verified"] = verified
        return out

    def novaprime_identity_profile(self, adapt_id: str) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        profile = self.novaprime_client.identity_profile(normalized_adapt)
        return {
            "ok": True,
            "adapt_id": normalized_adapt,
            "profile": profile if isinstance(profile, dict) else None,
            "found": isinstance(profile, dict),
        }

    def novaprime_identity_evolve(
        self,
        adapt_id: str,
        *,
        xp_gain: float = 0.0,
        new_skill: str = "",
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        result = self.novaprime_client.identity_evolve(
            normalized_adapt,
            xp_gain=float(xp_gain),
            new_skill=str(new_skill or ""),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime identity evolve response"}

    def novaprime_presence_get(self, adapt_id: str) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        presence = self.novaprime_client.presence_get(normalized_adapt)
        normalized_presence: dict[str, Any]
        if isinstance(presence, dict):
            normalized_presence = presence
        else:
            normalized_presence = {
                "adapt_id": normalized_adapt,
                "realm": "aetherion",
                "activity": "idle",
            }
        return {
            "ok": True,
            "adapt_id": normalized_adapt,
            "presence": normalized_presence,
        }

    def novaprime_presence_update(
        self,
        adapt_id: str,
        *,
        realm: str = "",
        activity: str = "",
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        result = self.novaprime_client.presence_update(
            normalized_adapt,
            realm=str(realm or ""),
            activity=str(activity or ""),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime presence update response"}

    def novaprime_resonance_score(self, player_profile: dict[str, Any]) -> dict[str, Any]:
        result = self.novaprime_client.resonance_score(player_profile if isinstance(player_profile, dict) else {})
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime resonance score response"}

    def novaprime_resonance_bond(
        self,
        player_id: str,
        player_profile: dict[str, Any] | None = None,
        *,
        adapt_id: str = "",
    ) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self.novaprime_client.resonance_bond(
            normalized_player,
            player_profile if isinstance(player_profile, dict) else {},
            adapt_id=str(adapt_id or ""),
        )
        if isinstance(result, dict):
            out = dict(result)
            cached = self._cache_bond_from_novaprime_result(
                result=out,
                adapt_id_hint=str(adapt_id or ""),
                player_id_hint=normalized_player,
                source="novaprime_resonance_bond",
            )
            if isinstance(cached, dict):
                out["cached_bond"] = cached
            return out
        return {"ok": False, "error": "invalid novaprime resonance bond response"}

    def novaprime_mesh_aetherion_state(self, *, refresh: bool = True) -> dict[str, Any]:
        result = self.novaprime_client.mesh_aetherion_state(refresh=bool(refresh))
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime aetherion state response"}

    def novaprime_imprinting_start(
        self,
        player_id: str,
        player_profile: dict[str, Any] | None = None,
        *,
        ttl_sec: float = 1800.0,
    ) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self.novaprime_client.imprinting_start(
            normalized_player,
            player_profile if isinstance(player_profile, dict) else {},
            ttl_sec=float(ttl_sec),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime imprinting start response"}

    def novaprime_imprinting_session(self, session_id: str) -> dict[str, Any]:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("'session_id' is required")
        result = self.novaprime_client.imprinting_session(normalized_session)
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime imprinting session response"}

    def novaprime_imprinting_resolve(
        self,
        session_id: str,
        *,
        accepted: bool,
        adapt_id: str = "",
    ) -> dict[str, Any]:
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("'session_id' is required")
        result = self.novaprime_client.imprinting_resolve(
            normalized_session,
            accepted=bool(accepted),
            adapt_id=str(adapt_id or ""),
        )
        if isinstance(result, dict):
            out = dict(result)
            cached = self._cache_bond_from_novaprime_result(
                result=out,
                adapt_id_hint=str(adapt_id or ""),
                source="novaprime_imprinting_resolve",
            )
            if isinstance(cached, dict):
                out["cached_bond"] = cached
            return out
        return {"ok": False, "error": "invalid novaprime imprinting resolve response"}

    def novaprime_phase_evaluate(
        self,
        player_state: dict[str, Any] | None = None,
        *,
        narrative_state: dict[str, Any] | None = None,
        environment_state: dict[str, Any] | None = None,
        adapt_id: str = "",
        auto_presence_update: bool = False,
    ) -> dict[str, Any]:
        result = self.novaprime_client.phase_evaluate(
            player_state if isinstance(player_state, dict) else {},
            narrative_state=narrative_state if isinstance(narrative_state, dict) else {},
            environment_state=environment_state if isinstance(environment_state, dict) else {},
            adapt_id=str(adapt_id or ""),
            auto_presence_update=bool(auto_presence_update),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime phase evaluate response"}

    def novaprime_void_create(
        self,
        player_id: str,
        *,
        player_profile: dict[str, Any] | None = None,
        seed: str = "",
    ) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self.novaprime_client.void_create(
            normalized_player,
            player_profile=player_profile if isinstance(player_profile, dict) else {},
            seed=str(seed or ""),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime void create response"}

    def novaprime_void_tick(
        self,
        state: dict[str, Any] | None = None,
        *,
        stimulus: dict[str, Any] | None = None,
        tick: int = 1,
    ) -> dict[str, Any]:
        result = self.novaprime_client.void_tick(
            state if isinstance(state, dict) else {},
            stimulus=stimulus if isinstance(stimulus, dict) else {},
            tick=int(tick),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime void tick response"}

    def novaprime_narrative_bond_history(
        self,
        adapt_id: str,
        player_id: str,
        *,
        top_k: int = 120,
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self.novaprime_client.narrative_bond_history(
            normalized_adapt,
            normalized_player,
            top_k=max(1, int(top_k)),
        )
        if isinstance(result, dict):
            return result
        return {"ok": False, "error": "invalid novaprime bond history response"}

    def adapt_toggle_get(self, adapt_id: str) -> dict[str, Any]:
        return self.adapt_toggle_store.get(adapt_id)

    def adapt_toggle_set(self, adapt_id: str, mode: str, *, source: str = "api") -> dict[str, Any]:
        updated = self.adapt_toggle_store.set(adapt_id, mode, source=source)
        out = dict(updated)
        try:
            presence = self.novaprime_client.presence_update(
                str(adapt_id or "").strip(),
                activity=f"toggle_mode:{out.get('mode', '')}",
            )
            if isinstance(presence, dict):
                out["novaprime_presence"] = presence
        except Exception as exc:
            out["novaprime_presence_error"] = str(exc)
        return out

    def adapt_bond_get(self, adapt_id: str) -> dict[str, Any] | None:
        return self.adapt_bond_cache.get(adapt_id)

    def adapt_bond_verify(
        self,
        adapt_id: str,
        player_id: str,
        *,
        refresh_profile: bool = True,
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")

        cached = self.adapt_bond_cache.get(normalized_adapt)
        cache_verified = self.adapt_bond_cache.verify_cached(normalized_adapt, normalized_player)
        out: dict[str, Any] = {
            "adapt_id": normalized_adapt,
            "player_id": normalized_player,
            "verified": False,
            "cache_verified": cache_verified,
            "cached": cached if isinstance(cached, dict) else None,
            "source": "none",
        }

        remote_error = ""
        remote_verified = False
        try:
            remote_verified = bool(self.novaprime_client.identity_verify(normalized_adapt, normalized_player))
        except Exception as exc:
            remote_error = str(exc)
            out["novaprime_error"] = remote_error

        if remote_verified:
            profile: dict[str, Any] | None = None
            if bool(refresh_profile):
                try:
                    loaded = self.novaprime_client.identity_profile(normalized_adapt)
                    if isinstance(loaded, dict):
                        profile = loaded
                        out["profile"] = profile
                except Exception as exc:
                    out["profile_error"] = str(exc)
            remembered_profile: dict[str, Any]
            if isinstance(profile, dict):
                remembered_profile = profile
            elif isinstance(cached, dict) and isinstance(cached.get("profile"), dict):
                remembered_profile = dict(cached.get("profile"))
            else:
                remembered_profile = {}
            remembered = self.adapt_bond_cache.remember(
                normalized_adapt,
                normalized_player,
                verified=True,
                profile=remembered_profile,
                source="novaprime_verify",
            )
            out["verified"] = True
            out["source"] = "novaprime"
            out["cached"] = remembered
            out["ok"] = True
            return out

        if cache_verified:
            out["verified"] = True
            out["source"] = "cache_fallback"
            out["ok"] = True
            return out

        out["ok"] = not bool(remote_error)
        return out

    def adapt_persona_get(
        self,
        adapt_id: str,
        *,
        player_id: str = "",
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")

        toggle_state = self.adapt_toggle_store.get(normalized_adapt)
        cached_bond = self.adapt_bond_cache.get(normalized_adapt)
        identity_profile: dict[str, Any] | None = None
        bond_verified: bool | None = None

        verify_result: dict[str, Any] | None = None
        if normalized_player:
            verify_result = self.adapt_bond_verify(
                normalized_adapt,
                normalized_player,
                refresh_profile=False,
            )
            bond_verified = bool(verify_result.get("verified", False))
            cached_value = verify_result.get("cached")
            if isinstance(cached_value, dict):
                cached_bond = cached_value

        try:
            loaded_profile = self.novaprime_client.identity_profile(normalized_adapt)
            if isinstance(loaded_profile, dict):
                identity_profile = loaded_profile
        except Exception as exc:
            identity_profile = None
            profile_error = str(exc)
        else:
            profile_error = ""

        if bond_verified is None:
            bond_verified = bool(cached_bond.get("verified", False)) if isinstance(cached_bond, dict) else False

        persona = self.adapt_persona.build_context(
            adapt_id=normalized_adapt,
            toggle_mode=str(toggle_state.get("mode", "")) if isinstance(toggle_state, dict) else "",
            bond_verified=bond_verified,
            identity_profile=identity_profile,
            cached_bond=cached_bond,
        )

        out: dict[str, Any] = {
            "ok": True,
            "adapt_id": normalized_adapt,
            "player_id": normalized_player or None,
            "toggle": toggle_state,
            "cached_bond": cached_bond if isinstance(cached_bond, dict) else None,
            "bond_verified": bool(bond_verified),
            "profile": identity_profile if isinstance(identity_profile, dict) else None,
            "persona": persona,
        }
        if verify_result is not None:
            out["verify"] = verify_result
        if profile_error:
            out["profile_error"] = profile_error
        return out

    def _voice_enabled(self, *, context: str = "api") -> bool:
        normalized_context = str(context or "api").strip().upper() or "API"
        global_enabled = coerce_bool(os.getenv("NOVAADAPT_ENABLE_VOICE"), default=False)
        context_enabled = coerce_bool(os.getenv(f"NOVAADAPT_ENABLE_VOICE_{normalized_context}"), default=False)
        return bool(global_enabled or context_enabled)

    def voice_status(self, *, context: str = "api") -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        enabled = self._voice_enabled(context=normalized_context)
        configured_stt = str(os.getenv("NOVAADAPT_STT_BACKEND", "noop")).strip().lower() or "noop"
        configured_tts = str(os.getenv("NOVAADAPT_TTS_BACKEND", "noop")).strip().lower() or "noop"
        out: dict[str, Any] = {
            "ok": True,
            "enabled": enabled,
            "context": normalized_context,
            "configured": {
                "stt_backend": configured_stt,
                "tts_backend": configured_tts,
            },
            "flag_hint": {
                "global": "NOVAADAPT_ENABLE_VOICE=1",
                "context": f"NOVAADAPT_ENABLE_VOICE_{normalized_context.upper()}=1",
            },
        }
        if not enabled:
            return out
        try:
            out["stt_backend"] = build_stt_backend().name
        except Exception as exc:
            out["stt_error"] = str(exc)
        try:
            out["tts_backend"] = build_tts_backend().name
        except Exception as exc:
            out["tts_error"] = str(exc)
        return out

    def voice_transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        backend: str = "",
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._voice_enabled(context=normalized_context):
            raise ValueError(
                "voice feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_VOICE=1 or NOVAADAPT_ENABLE_VOICE_{normalized_context.upper()}=1"
            )
        backend_name = str(backend or "").strip()
        stt = build_stt_backend(backend_name or None)
        result = stt.transcribe(
            str(audio_path or "").strip(),
            hints=list(hints or []),
            metadata=metadata if isinstance(metadata, dict) else {},
        )
        return {
            "ok": bool(result.ok),
            "backend": str(result.backend or stt.name),
            "text": str(result.text or ""),
            "confidence": result.confidence,
            "error": result.error,
            "metadata": dict(result.metadata or {}),
        }

    def voice_synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
        backend: str = "",
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._voice_enabled(context=normalized_context):
            raise ValueError(
                "voice feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_VOICE=1 or NOVAADAPT_ENABLE_VOICE_{normalized_context.upper()}=1"
            )
        backend_name = str(backend or "").strip()
        tts = build_tts_backend(backend_name or None)
        result = tts.synthesize(
            str(text or ""),
            output_path=str(output_path or ""),
            voice=str(voice or ""),
            metadata=metadata if isinstance(metadata, dict) else {},
        )
        return {
            "ok": bool(result.ok),
            "backend": str(result.backend or tts.name),
            "output_path": str(result.output_path or ""),
            "error": result.error,
            "metadata": dict(result.metadata or {}),
        }

    def _canvas_enabled(self, *, context: str = "api") -> bool:
        return canvas_enabled(context=str(context or "api"))

    def canvas_status(self, *, context: str = "api") -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        enabled = self._canvas_enabled(context=normalized_context)
        out: dict[str, Any] = {
            "ok": True,
            "enabled": enabled,
            "context": normalized_context,
            "flag_hint": {
                "global": "NOVAADAPT_ENABLE_CANVAS=1",
                "context": f"NOVAADAPT_ENABLE_CANVAS_{normalized_context.upper()}=1",
            },
        }
        if enabled and self._canvas_sessions is not None:
            out["loaded_sessions"] = len(getattr(self._canvas_sessions, "_sessions", {}))
        return out

    def canvas_render(
        self,
        title: str,
        *,
        session_id: str = "default",
        sections: list[dict[str, Any]] | None = None,
        footer: str = "",
        metadata: dict[str, Any] | None = None,
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._canvas_enabled(context=normalized_context):
            raise ValueError(
                "canvas feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_CANVAS=1 or NOVAADAPT_ENABLE_CANVAS_{normalized_context.upper()}=1"
            )
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("'title' is required")
        normalized_session = str(session_id or "default").strip() or "default"
        frame = self._canvas_renderer_obj().render(
            normalized_title,
            sections=list(sections or []),
            footer=str(footer or ""),
            metadata=metadata if isinstance(metadata, dict) else {},
        )
        self._canvas_store().push(normalized_session, frame)
        out = self._canvas_frame_payload(frame)
        out.update({"ok": True, "session_id": normalized_session, "context": normalized_context})
        return out

    def canvas_frames(
        self,
        session_id: str,
        *,
        limit: int = 20,
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._canvas_enabled(context=normalized_context):
            raise ValueError(
                "canvas feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_CANVAS=1 or NOVAADAPT_ENABLE_CANVAS_{normalized_context.upper()}=1"
            )
        normalized_session = str(session_id or "").strip()
        if not normalized_session:
            raise ValueError("'session_id' is required")
        frames = self._canvas_store().list(normalized_session, limit=max(1, min(200, int(limit))))
        return {
            "ok": True,
            "context": normalized_context,
            "session_id": normalized_session,
            "count": len(frames),
            "frames": [self._canvas_frame_payload(item) for item in frames],
        }

    def _workflows_enabled(self, *, context: str = "api") -> bool:
        return workflows_enabled(context=str(context or "api"))

    def workflows_status(self, *, context: str = "api") -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        enabled = self._workflows_enabled(context=normalized_context)
        out: dict[str, Any] = {
            "ok": True,
            "enabled": enabled,
            "context": normalized_context,
            "flag_hint": {
                "global": "NOVAADAPT_ENABLE_WORKFLOWS=1",
                "context": f"NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1",
            },
            "db_path": str(self._workflow_db_path()),
        }
        if enabled and self._workflow_store is not None:
            out["count"] = len(self._workflow_store.list(limit=500))
        return out

    def workflows_start(
        self,
        objective: str,
        *,
        steps: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        workflow_id: str = "",
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._workflows_enabled(context=normalized_context):
            raise ValueError(
                "workflow feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_WORKFLOWS=1 or NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1"
            )
        ctx = dict(metadata or {})
        ctx.setdefault("surface", normalized_context)
        record = self._workflow_engine_obj().start(
            str(objective or ""),
            steps=[dict(step) for step in (steps or [])],
            context=ctx,
            workflow_id=str(workflow_id or ""),
        )
        out = self._workflow_payload(record)
        out["ok"] = True
        return out

    def workflows_advance(
        self,
        workflow_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str = "",
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._workflows_enabled(context=normalized_context):
            raise ValueError(
                "workflow feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_WORKFLOWS=1 or NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1"
            )
        normalized_id = str(workflow_id or "").strip()
        if not normalized_id:
            raise ValueError("'workflow_id' is required")
        record = self._workflow_engine_obj().advance(normalized_id, result=result, error=str(error or ""))
        if record is None:
            return {"ok": False, "error": "workflow not found", "workflow_id": normalized_id}
        out = self._workflow_payload(record)
        out["ok"] = True
        return out

    def workflows_resume(
        self,
        workflow_id: str,
        *,
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._workflows_enabled(context=normalized_context):
            raise ValueError(
                "workflow feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_WORKFLOWS=1 or NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1"
            )
        normalized_id = str(workflow_id or "").strip()
        if not normalized_id:
            raise ValueError("'workflow_id' is required")
        record = self._workflow_engine_obj().resume(normalized_id)
        if record is None:
            return {"ok": False, "error": "workflow not found", "workflow_id": normalized_id}
        out = self._workflow_payload(record)
        out["ok"] = True
        return out

    def workflows_get(self, workflow_id: str, *, context: str = "api") -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._workflows_enabled(context=normalized_context):
            raise ValueError(
                "workflow feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_WORKFLOWS=1 or NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1"
            )
        normalized_id = str(workflow_id or "").strip()
        if not normalized_id:
            raise ValueError("'workflow_id' is required")
        record = self._workflow_store_obj().get(normalized_id)
        if record is None:
            return {"ok": False, "error": "workflow not found", "workflow_id": normalized_id}
        out = self._workflow_payload(record)
        out["ok"] = True
        return out

    def workflows_list(
        self,
        *,
        limit: int = 50,
        status: str = "",
        context: str = "api",
    ) -> dict[str, Any]:
        normalized_context = str(context or "api").strip().lower() or "api"
        if not self._workflows_enabled(context=normalized_context):
            raise ValueError(
                "workflow feature disabled for this surface. "
                f"Set NOVAADAPT_ENABLE_WORKFLOWS=1 or NOVAADAPT_ENABLE_WORKFLOWS_{normalized_context.upper()}=1"
            )
        rows = self._workflow_store_obj().list(
            limit=max(1, min(500, int(limit))),
            status=str(status or "").strip(),
        )
        return {
            "ok": True,
            "count": len(rows),
            "workflows": [self._workflow_payload(item) for item in rows],
            "context": normalized_context,
        }

    def channels(self) -> list[dict[str, Any]]:
        return self.channel_registry.list_channels()

    def channel_health(self, channel: str) -> dict[str, Any]:
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_channel:
            raise ValueError("'channel' is required")
        return self.channel_registry.health(normalized_channel)

    def channel_send(
        self,
        channel: str,
        to: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requested_channel = str(channel or "").strip().lower()
        normalized_channel = (
            self.channel_registry.resolve_name(requested_channel)
            if hasattr(self.channel_registry, "resolve_name")
            else requested_channel
        )
        normalized_to = str(to or "").strip()
        normalized_text = str(text or "").strip()
        if not requested_channel:
            raise ValueError("'channel' is required")
        if not normalized_to:
            raise ValueError("'to' is required")
        if not normalized_text:
            raise ValueError("'text' is required")

        adapter = self.channel_registry.get(normalized_channel)
        if adapter is None:
            raise ValueError(
                f"unknown channel: {normalized_channel}. Available: {', '.join(self.channel_registry.names())}"
            )

        normalized_metadata = metadata if isinstance(metadata, dict) else {}
        result = adapter.send_text(normalized_to, normalized_text, metadata=normalized_metadata)
        out = result if isinstance(result, dict) else {}
        payload = dict(out)
        payload.setdefault("channel", normalized_channel)
        if requested_channel != normalized_channel:
            payload.setdefault("requested_channel", requested_channel)
        payload.setdefault("to", normalized_to)
        payload.setdefault("text", normalized_text)

        try:
            message_id = str(payload.get("message_id") or "").strip()
            source_id = f"channel:{normalized_channel}:outbound:{message_id or uuid.uuid4().hex}"
            self.memory_backend.ingest(
                text=json.dumps(
                    {
                        "type": "channel_outbound",
                        "channel": normalized_channel,
                        "to": normalized_to,
                        "text": normalized_text,
                        "message_id": message_id,
                        "metadata": normalized_metadata,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=True,
                ),
                source_id=source_id,
                metadata={
                    "type": "channel_outbound",
                    "channel": normalized_channel,
                    "to": normalized_to,
                },
            )
            payload["memory_ingested"] = True
            payload["memory_source_id"] = source_id
        except Exception as exc:
            payload["memory_ingested"] = False
            payload["memory_error"] = str(exc)

        return payload

    def channel_inbound(
        self,
        channel: str,
        payload: dict[str, Any],
        *,
        adapt_id: str = "",
        auto_run: bool = False,
        execute: bool = False,
        request_headers: dict[str, str] | None = None,
        request_body_text: str | None = None,
    ) -> dict[str, Any]:
        requested_channel = str(channel or "").strip().lower()
        normalized_channel = (
            self.channel_registry.resolve_name(requested_channel)
            if hasattr(self.channel_registry, "resolve_name")
            else requested_channel
        )
        if not requested_channel:
            raise ValueError("'channel' is required")
        if not isinstance(payload, dict):
            raise ValueError("'payload' must be an object")

        adapter = self.channel_registry.get(normalized_channel)
        if adapter is None:
            raise ValueError(
                f"unknown channel: {normalized_channel}. Available: {', '.join(self.channel_registry.names())}"
            )

        verify_headers = request_headers if isinstance(request_headers, dict) else None
        try:
            auth = adapter.verify_inbound(
                payload,
                headers=verify_headers,
                raw_body=request_body_text,
            )
        except TypeError:
            # Backward compatibility for adapters/tests that still implement the old signature.
            auth = adapter.verify_inbound(payload, headers=verify_headers)
        if not bool(auth.get("ok", False)):
            return {
                "ok": False,
                "channel": normalized_channel,
                "status_code": int(auth.get("status_code") or 401),
                "error": str(auth.get("error") or "unauthorized inbound payload"),
                "auth": auth,
            }

        # Slack Events API URL verification challenge.
        if normalized_channel == "slack":
            event_type = str(payload.get("type") or "").strip().lower()
            challenge = str(payload.get("challenge") or "").strip()
            if event_type == "url_verification" and challenge:
                return {
                    "ok": True,
                    "channel": normalized_channel,
                    "verification": True,
                    "challenge": challenge,
                    "status_code": 200,
                    "auth": auth,
                }

        normalized_adapt = str(adapt_id or "").strip()
        message = adapter.normalize_inbound(payload)
        message_payload = message.to_dict()
        if normalized_adapt:
            message_payload.setdefault("metadata", {})
            if isinstance(message_payload["metadata"], dict):
                message_payload["metadata"]["adapt_id"] = normalized_adapt

        source_id = f"channel:{normalized_channel}:inbound:{message_payload.get('message_id') or uuid.uuid4().hex}"
        memory_result: dict[str, Any]
        try:
            stored = self.memory_backend.ingest(
                text=json.dumps(
                    {
                        "type": "channel_inbound",
                        "message": message_payload,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=True,
                ),
                source_id=source_id,
                metadata={
                    "type": "channel_inbound",
                    "channel": normalized_channel,
                    "sender": str(message_payload.get("sender") or ""),
                },
            )
            memory_result = {
                "ok": True,
                "source_id": source_id,
                "result": stored if isinstance(stored, dict) else {},
            }
        except Exception as exc:
            memory_result = {"ok": False, "source_id": source_id, "error": str(exc)}

        out: dict[str, Any] = {
            "ok": True,
            "channel": normalized_channel,
            "message": message_payload,
            "memory": memory_result,
            "auto_run": bool(auto_run),
        }
        if requested_channel != normalized_channel:
            out["requested_channel"] = requested_channel

        if auto_run:
            body_text = str(message_payload.get("text") or "").strip()
            if not body_text:
                out["run"] = {"ok": False, "error": "inbound message text is empty"}
                return out
            objective = (
                f"Respond to inbound {normalized_channel} message from "
                f"{str(message_payload.get('sender') or 'user')}: {body_text}"
            )
            run_payload: dict[str, Any] = {
                "objective": objective,
                "execute": bool(execute),
            }
            if normalized_adapt:
                run_payload["adapt_id"] = normalized_adapt
            out["run"] = self.run(run_payload)

        return out

    def memory_recall(self, query: str, *, top_k: int = 10) -> dict[str, Any]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise ValueError("'query' is required")
        normalized_top_k = max(1, min(100, int(top_k)))
        rows = self.memory_backend.recall(normalized_query, top_k=normalized_top_k)
        if not isinstance(rows, list):
            rows = []
        return {
            "query": normalized_query,
            "top_k": normalized_top_k,
            "count": len(rows),
            "memories": rows,
        }

    def memory_ingest(
        self,
        text: str,
        *,
        source_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise ValueError("'text' is required")
        normalized_source = str(source_id or "").strip()
        normalized_metadata = metadata if isinstance(metadata, dict) else {}
        response = self.memory_backend.ingest(
            normalized_text,
            source_id=normalized_source,
            metadata=normalized_metadata,
        )
        return {
            "ok": True,
            "source_id": normalized_source,
            "metadata": normalized_metadata,
            "result": response if isinstance(response, dict) else {},
        }

    def plugins(self) -> list[dict[str, Any]]:
        return self.plugin_registry.list_plugins()

    def plugin_health(self, plugin_name: str) -> dict[str, Any]:
        return self.plugin_registry.health(plugin_name)

    def plugin_call(self, plugin_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        route = str(payload.get("route", "")).strip()
        if not route:
            raise ValueError("'route' is required")
        method = str(payload.get("method", "POST")).strip().upper() or "POST"
        raw_request_payload = payload.get("payload")
        request_payload: dict[str, Any] | None = None
        if raw_request_payload is not None:
            if not isinstance(raw_request_payload, dict):
                raise ValueError("'payload' must be an object when provided")
            request_payload = raw_request_payload
        return self.plugin_registry.call(
            plugin_name=plugin_name,
            route=route,
            payload=request_payload,
            method=method,
        )

    def sib_status(self) -> dict[str, Any]:
        return self._sib().health()

    def sib_realm(self, player_id: str, realm: str) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        normalized_realm = str(realm or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        if not normalized_realm:
            raise ValueError("'realm' is required")
        return self._sib().realm(normalized_player, normalized_realm)

    def sib_companion_state(self, adapt_id: str, state: dict[str, Any]) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not isinstance(state, dict):
            raise ValueError("'state' must be an object")
        return self._sib().companion_state(normalized_adapt, state)

    def sib_companion_speak(self, adapt_id: str, text: str, channel: str = "in_game") -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_text = str(text or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_text:
            raise ValueError("'text' is required")
        return self._sib().companion_speak(normalized_adapt, normalized_text, channel=str(channel or "in_game"))

    def sib_phase_event(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_event = str(event_type or "").strip()
        if not normalized_event:
            raise ValueError("'event_type' is required")
        return self._sib().phase_event(normalized_event, payload if isinstance(payload, dict) else None)

    def sib_resonance_start(self, player_id: str, player_profile: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        result = self._sib().resonance_start(
            normalized_player,
            profile=player_profile if isinstance(player_profile, dict) else None,
        )
        if isinstance(result, dict):
            try:
                resonance = self.novaprime_client.resonance_score(
                    player_profile if isinstance(player_profile, dict) else {}
                )
                if isinstance(resonance, dict):
                    result["novaprime_resonance"] = resonance
            except Exception as exc:
                result["novaprime_resonance_error"] = str(exc)
        return result

    def sib_resonance_result(
        self,
        player_id: str,
        adapt_id: str,
        accepted: bool,
        player_profile: dict[str, Any] | None = None,
        toggle_mode: str | None = None,
    ) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        result = self._sib().resonance_result(normalized_player, normalized_adapt, bool(accepted))
        if bool(accepted) and isinstance(result, dict):
            resolved_adapt = normalized_adapt
            cached_bond: dict[str, Any] | None = None
            identity_profile: dict[str, Any] | None = None
            try:
                bond = self.novaprime_client.resonance_bond(
                    normalized_player,
                    player_profile if isinstance(player_profile, dict) else {},
                    adapt_id=normalized_adapt,
                )
                if isinstance(bond, dict):
                    result["novaprime_bond"] = bond
                    cached_bond = self._cache_bond_from_novaprime_result(
                        result=bond,
                        adapt_id_hint=normalized_adapt,
                        player_id_hint=normalized_player,
                        source="sib_resonance_result",
                    )
                    if isinstance(cached_bond, dict):
                        result["adapt_bond_cache"] = cached_bond
                        resolved_adapt = str(cached_bond.get("adapt_id") or resolved_adapt).strip() or resolved_adapt
            except Exception as exc:
                result["novaprime_bond_error"] = str(exc)
            try:
                if toggle_mode is not None and str(toggle_mode).strip():
                    result["adapt_toggle"] = self.adapt_toggle_store.set(
                        resolved_adapt,
                        str(toggle_mode),
                        source="sib_resonance_result",
                    )
                else:
                    result["adapt_toggle"] = self.adapt_toggle_store.get(resolved_adapt)
            except Exception as exc:
                result["adapt_toggle_error"] = str(exc)
            try:
                profile = self.novaprime_client.identity_profile(resolved_adapt)
                if isinstance(profile, dict):
                    identity_profile = profile
                    result["novaprime_profile"] = profile
            except Exception as exc:
                result["novaprime_profile_error"] = str(exc)
            try:
                presence = self.novaprime_client.presence_update(
                    resolved_adapt,
                    realm="game_world",
                    activity="bonded",
                )
                if isinstance(presence, dict):
                    result["novaprime_presence"] = presence
            except Exception as exc:
                result["novaprime_presence_error"] = str(exc)
            persona_profile = identity_profile
            if persona_profile is None and isinstance(cached_bond, dict):
                cached_profile = cached_bond.get("profile")
                if isinstance(cached_profile, dict):
                    persona_profile = cached_profile
            try:
                toggle_state = result.get("adapt_toggle")
                result["adapt_persona"] = self.adapt_persona.build_context(
                    adapt_id=resolved_adapt,
                    toggle_mode=toggle_state.get("mode") if isinstance(toggle_state, dict) else None,
                    bond_verified=True,
                    identity_profile=persona_profile,
                    cached_bond=cached_bond,
                )
            except Exception as exc:
                result["adapt_persona_error"] = str(exc)
        return result

    def _cache_bond_from_novaprime_result(
        self,
        *,
        result: dict[str, Any],
        adapt_id_hint: str = "",
        player_id_hint: str = "",
        source: str = "novaprime",
    ) -> dict[str, Any] | None:
        if not bool(result.get("ok", False)):
            return None
        bond = result.get("bond")
        profile = result.get("profile")
        resonance = result.get("resonance")
        bond_payload = bond if isinstance(bond, dict) else {}
        profile_payload = profile if isinstance(profile, dict) else {}

        resolved_adapt = str(
            bond_payload.get("adapt_id")
            or result.get("adapt_id")
            or adapt_id_hint
            or ""
        ).strip()
        resolved_player = str(
            bond_payload.get("player_id")
            or result.get("player_id")
            or player_id_hint
            or ""
        ).strip()
        if not resolved_adapt or not resolved_player:
            return None

        merged_profile: dict[str, Any] = {}
        if bond_payload:
            merged_profile.update(bond_payload)
        if profile_payload:
            merged_profile.update(profile_payload)
        if isinstance(resonance, dict):
            element = str(resonance.get("element") or "").strip()
            subclass = str(resonance.get("subclass") or "").strip()
            if element and "element" not in merged_profile:
                merged_profile["element"] = element
            if subclass and "subclass" not in merged_profile:
                merged_profile["subclass"] = subclass
            merged_profile["resonance"] = dict(resonance)

        return self.adapt_bond_cache.remember(
            resolved_adapt,
            resolved_player,
            verified=True,
            profile=merged_profile,
            source=source,
        )

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = str(payload.get("objective") or "").strip()
        notes = str(payload.get("notes") or "").strip()
        metadata = payload.get("metadata")
        context = payload.get("context")

        raw_rating = payload.get("rating")
        if raw_rating is None:
            raise ValueError("'rating' is required")
        try:
            rating = int(raw_rating)
        except (TypeError, ValueError) as exc:
            raise ValueError("'rating' must be an integer between 1 and 10") from exc
        if rating < 1 or rating > 10:
            raise ValueError("'rating' must be between 1 and 10")

        feedback_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()

        memory_payload = {
            "type": "novaadapt_feedback",
            "id": feedback_id,
            "created_at": created_at,
            "rating": rating,
            "objective": objective,
            "notes": notes,
            "context": context if isinstance(context, dict) else {},
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        self.memory_backend.ingest(
            text=json.dumps(memory_payload, ensure_ascii=True),
            source_id=f"novaadapt:feedback:{feedback_id}",
            metadata={
                "type": "novaadapt_feedback",
                "rating": rating,
                "objective": objective[:240],
            },
        )
        return {
            "ok": True,
            "id": feedback_id,
            "created_at": created_at,
            "rating": rating,
            "objective": objective,
            "notes": notes,
        }

    def _execute_runtime_mesh_ops(
        self,
        *,
        adapt_id: str,
        mesh_node_id: str,
        mesh_probe: bool,
        mesh_probe_marketplace: bool,
        mesh_credit_amount: object,
        mesh_transfer_to: str,
        mesh_transfer_amount: object,
        mesh_marketplace_list: object,
        mesh_marketplace_buy: object,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        node_id = str(mesh_node_id or "").strip() or str(adapt_id or "").strip()
        if node_id:
            context["node_id"] = node_id
            try:
                context["balance_before"] = float(self.novaprime_client.mesh_balance(node_id))
            except Exception as exc:
                context["balance_before_error"] = str(exc)
            try:
                context["reputation"] = float(self.novaprime_client.mesh_reputation(node_id))
            except Exception as exc:
                context["reputation_error"] = str(exc)
        elif mesh_probe:
            context["probe_error"] = "'mesh_node_id' or 'adapt_id' is required for mesh probe"

        if mesh_probe_marketplace:
            try:
                listings = self.novaprime_client.marketplace_listings()
                if isinstance(listings, list):
                    context["listings_count"] = len(listings)
                    context["listings_preview"] = listings[:5]
                else:
                    context["listings_error"] = "invalid novaprime marketplace listings response"
            except Exception as exc:
                context["listings_error"] = str(exc)

        if mesh_credit_amount is not None:
            if not node_id:
                context["credit_error"] = "'mesh_node_id' or 'adapt_id' is required for mesh credit"
            else:
                try:
                    amount = float(mesh_credit_amount)
                    if amount <= 0:
                        context["credit_error"] = "'mesh_credit_amount' must be > 0"
                    else:
                        credit_result = self.novaprime_client.mesh_credit(node_id, amount)
                        if isinstance(credit_result, dict):
                            context["credit"] = credit_result
                            if not bool(credit_result.get("ok", False)):
                                context["credit_error"] = str(
                                    credit_result.get("error") or "novaprime mesh credit failed"
                                )
                        else:
                            context["credit_error"] = "invalid novaprime mesh credit response"
                except Exception as exc:
                    context["credit_error"] = str(exc)

        if mesh_transfer_amount is not None or mesh_transfer_to:
            from_node = node_id
            to_node = str(mesh_transfer_to or "").strip()
            if not from_node or not to_node:
                context["transfer_error"] = "'mesh_node_id'/'adapt_id' and 'mesh_transfer_to' are required"
            else:
                try:
                    amount = float(mesh_transfer_amount if mesh_transfer_amount is not None else 0.0)
                    if amount <= 0:
                        context["transfer_error"] = "'mesh_transfer_amount' must be > 0"
                    else:
                        transfer_result = self.novaprime_client.mesh_transfer(from_node, to_node, amount)
                        if isinstance(transfer_result, dict):
                            context["transfer"] = transfer_result
                            if not bool(transfer_result.get("ok", False)):
                                context["transfer_error"] = str(
                                    transfer_result.get("error") or "novaprime mesh transfer failed"
                                )
                        else:
                            context["transfer_error"] = "invalid novaprime mesh transfer response"
                except Exception as exc:
                    context["transfer_error"] = str(exc)

        if mesh_marketplace_list is not None:
            if not isinstance(mesh_marketplace_list, dict):
                context["marketplace_list_error"] = "'mesh_marketplace_list' must be an object"
            else:
                capsule_id = str(mesh_marketplace_list.get("capsule_id") or "").strip()
                seller = str(mesh_marketplace_list.get("seller") or node_id).strip()
                title = str(mesh_marketplace_list.get("title") or "").strip()
                try:
                    price = float(mesh_marketplace_list.get("price", 0.0))
                except Exception:
                    price = -1.0
                if not capsule_id or not seller or not title:
                    context["marketplace_list_error"] = "'capsule_id', 'seller', and 'title' are required"
                elif price < 0:
                    context["marketplace_list_error"] = "'price' must be >= 0"
                else:
                    try:
                        list_result = self.novaprime_client.marketplace_list(capsule_id, seller, price, title)
                        if isinstance(list_result, dict):
                            context["marketplace_list"] = list_result
                            if not bool(list_result.get("ok", False)):
                                context["marketplace_list_error"] = str(
                                    list_result.get("error") or "novaprime marketplace list failed"
                                )
                        else:
                            context["marketplace_list_error"] = "invalid novaprime marketplace list response"
                    except Exception as exc:
                        context["marketplace_list_error"] = str(exc)

        if mesh_marketplace_buy is not None:
            if not isinstance(mesh_marketplace_buy, dict):
                context["marketplace_buy_error"] = "'mesh_marketplace_buy' must be an object"
            else:
                listing_id = str(mesh_marketplace_buy.get("listing_id") or "").strip()
                buyer = str(mesh_marketplace_buy.get("buyer") or node_id).strip()
                if not listing_id or not buyer:
                    context["marketplace_buy_error"] = "'listing_id' and 'buyer' are required"
                else:
                    try:
                        buy_result = self.novaprime_client.marketplace_buy(listing_id, buyer)
                        if isinstance(buy_result, dict):
                            context["marketplace_buy"] = buy_result
                            if not bool(buy_result.get("ok", False)):
                                context["marketplace_buy_error"] = str(
                                    buy_result.get("error") or "novaprime marketplace buy failed"
                                )
                        else:
                            context["marketplace_buy_error"] = "invalid novaprime marketplace buy response"
                    except Exception as exc:
                        context["marketplace_buy_error"] = str(exc)

        if node_id:
            try:
                context["balance_after"] = float(self.novaprime_client.mesh_balance(node_id))
            except Exception as exc:
                context["balance_after_error"] = str(exc)

        errors = [key for key in context if key.endswith("_error")]
        context["ok"] = len(errors) == 0
        if errors:
            context["errors"] = sorted(errors)
        return context

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        config_path = Path(payload.get("config") or self.default_config)
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("'objective' is required")

        strategy = str(payload.get("strategy", "single"))
        model_name = payload.get("model")
        candidate_models = self._as_name_list(payload.get("candidates"))
        fallback_models = self._as_name_list(payload.get("fallbacks"))
        execute = coerce_bool(payload.get("execute"), default=False)
        record_history = coerce_bool(payload.get("record_history"), default=True)
        allow_dangerous = coerce_bool(payload.get("allow_dangerous"), default=False)
        max_actions = int(payload.get("max_actions", 25))
        adapt_id = str(payload.get("adapt_id") or "").strip()
        player_id = str(payload.get("player_id") or "").strip()
        realm = str(payload.get("realm") or "").strip()
        activity = str(payload.get("activity") or "").strip()
        post_realm = str(payload.get("post_realm") or "").strip()
        post_activity = str(payload.get("post_activity") or "").strip()
        mesh_node_id = str(payload.get("mesh_node_id") or "").strip()
        mesh_credit_amount = payload.get("mesh_credit_amount")
        mesh_transfer_to = str(payload.get("mesh_transfer_to") or "").strip()
        mesh_transfer_amount = payload.get("mesh_transfer_amount")
        mesh_probe = coerce_bool(payload.get("mesh_probe"), default=False)
        mesh_probe_marketplace = coerce_bool(payload.get("mesh_probe_marketplace"), default=False)
        mesh_marketplace_list = payload.get("mesh_marketplace_list")
        mesh_marketplace_buy = payload.get("mesh_marketplace_buy")
        has_mesh_context = bool(
            mesh_probe
            or mesh_probe_marketplace
            or mesh_node_id
            or mesh_credit_amount is not None
            or mesh_transfer_to
            or mesh_transfer_amount is not None
            or mesh_marketplace_list is not None
            or mesh_marketplace_buy is not None
        )
        toggle_mode_input = payload.get("toggle_mode")
        toggle_mode = ""
        if adapt_id:
            if toggle_mode_input is not None:
                _ = self.adapt_toggle_store.set(adapt_id, str(toggle_mode_input), source="run_payload")
            toggle_mode = self.adapt_toggle_store.get_mode(adapt_id)

        novaprime_context: dict[str, Any] = {"enabled": bool(adapt_id or has_mesh_context)}
        adapt_context: dict[str, Any] = {}
        identity_profile: dict[str, Any] | None = None
        bond_verified: bool | None = None
        cached_bond: dict[str, Any] | None = None
        if adapt_id:
            adapt_context = {"adapt_id": adapt_id, "toggle_mode": toggle_mode}
            cached_bond = self.adapt_bond_cache.get(adapt_id)
            if isinstance(cached_bond, dict):
                adapt_context["bond_cache"] = cached_bond
        if adapt_id:
            try:
                if player_id:
                    bond_verified = bool(self.novaprime_client.identity_verify(adapt_id, player_id))
                    if not bond_verified and self.adapt_bond_cache.verify_cached(adapt_id, player_id):
                        bond_verified = True
                        novaprime_context["bond_verified_source"] = "cache_fallback"
                    novaprime_context["bond_verified"] = bond_verified
                identity_profile = self.novaprime_client.identity_profile(adapt_id)
                if isinstance(identity_profile, dict):
                    novaprime_context["profile"] = identity_profile
                if player_id and bond_verified is not None:
                    cached_bond = self.adapt_bond_cache.remember(
                        adapt_id,
                        player_id,
                        verified=bool(bond_verified),
                        profile=identity_profile if isinstance(identity_profile, dict) else {},
                    )
                    if isinstance(cached_bond, dict):
                        adapt_context["bond_cache"] = cached_bond
                if realm or activity:
                    presence_before = self.novaprime_client.presence_update(
                        adapt_id,
                        realm=realm,
                        activity=activity or ("executing_objective" if execute else "planning_objective"),
                    )
                else:
                    presence_before = self.novaprime_client.presence_get(adapt_id)
                if isinstance(presence_before, dict):
                    novaprime_context["presence_before"] = presence_before
            except Exception as exc:
                novaprime_context["error"] = str(exc)
                if player_id and self.adapt_bond_cache.verify_cached(adapt_id, player_id):
                    bond_verified = True
                    novaprime_context["bond_verified"] = True
                    novaprime_context["bond_verified_source"] = "cache_fallback"

        planning_identity_profile: dict[str, Any] | None = identity_profile
        if adapt_id:
            persona_context = self.adapt_persona.build_context(
                adapt_id=adapt_id,
                toggle_mode=toggle_mode,
                bond_verified=bond_verified,
                identity_profile=identity_profile,
                cached_bond=cached_bond,
            )
            novaprime_context["persona"] = persona_context
            adapt_context["persona"] = persona_context
            if isinstance(identity_profile, dict):
                planning_identity_profile = dict(identity_profile)
                planning_identity_profile["persona"] = persona_context
            else:
                planning_identity_profile = {"persona": persona_context}

        with self.runtime_governance.run_guard():
            router = self.router_loader(config_path)
            queue = UndoQueue(db_path=self.db_path)
            agent = NovaAdaptAgent(
                router=router,
                directshell=self.directshell_factory(),
                undo_queue=queue,
                memory_backend=self.memory_backend,
            )
            kernel_context: dict[str, Any] | None = None
            if should_use_kernel(payload):
                novaprime_context["enabled"] = True
                kernel_response = run_with_kernel(
                    payload=payload,
                    objective=objective,
                    strategy=strategy,
                    model_name=str(model_name or "").strip() or None,
                    router=router,
                    agent=agent,
                    execute=execute,
                    record_history=record_history,
                    allow_dangerous=allow_dangerous,
                    max_actions=max(1, max_actions),
                    adapt_id=adapt_id,
                    player_id=player_id,
                    identity_profile=planning_identity_profile,
                )
                raw_kernel_context = kernel_response.get("kernel")
                if isinstance(raw_kernel_context, dict):
                    kernel_context = dict(raw_kernel_context)
                if bool(kernel_response.get("ok", False)) and isinstance(kernel_response.get("result"), dict):
                    result = dict(kernel_response.get("result", {}))
                else:
                    kernel_error = str(kernel_response.get("error") or "novaprime kernel execution failed")
                    if kernel_context is None:
                        kernel_context = {"ok": False, "error": kernel_error}
                    else:
                        kernel_context.setdefault("ok", False)
                        kernel_context.setdefault("error", kernel_error)
                    if kernel_required(payload):
                        raise RuntimeError(kernel_error)
                    kernel_context["fallback"] = "legacy_agent"
                    result = agent.run_objective(
                        objective=objective,
                        strategy=strategy,
                        model_name=model_name,
                        candidate_models=candidate_models or None,
                        fallback_models=fallback_models or None,
                        dry_run=not execute,
                        record_history=record_history,
                        allow_dangerous=allow_dangerous,
                        max_actions=max(1, max_actions),
                        identity_profile=planning_identity_profile,
                        bond_verified=bond_verified,
                    )
            else:
                result = agent.run_objective(
                    objective=objective,
                    strategy=strategy,
                    model_name=model_name,
                    candidate_models=candidate_models or None,
                    fallback_models=fallback_models or None,
                    dry_run=not execute,
                    record_history=record_history,
                    allow_dangerous=allow_dangerous,
                    max_actions=max(1, max_actions),
                    identity_profile=planning_identity_profile,
                    bond_verified=bond_verified,
                )
            self.runtime_governance.record_model_usage(
                usage=result.get("model_usage") if isinstance(result, dict) else None,
                strategy=strategy,
                objective=objective,
            )
        if isinstance(kernel_context, dict):
            novaprime_context["kernel"] = kernel_context
        if adapt_id:
            try:
                presence_after = self.novaprime_client.presence_update(
                    adapt_id,
                    realm=post_realm or realm,
                    activity=post_activity or ("objective_executed" if execute else "objective_planned"),
                )
                if isinstance(presence_after, dict):
                    novaprime_context["presence_after"] = presence_after
            except Exception as exc:
                if "error" not in novaprime_context:
                    novaprime_context["error"] = str(exc)
        if has_mesh_context:
            try:
                novaprime_context["mesh"] = self._execute_runtime_mesh_ops(
                    adapt_id=adapt_id,
                    mesh_node_id=mesh_node_id,
                    mesh_probe=mesh_probe,
                    mesh_probe_marketplace=mesh_probe_marketplace,
                    mesh_credit_amount=mesh_credit_amount,
                    mesh_transfer_to=mesh_transfer_to,
                    mesh_transfer_amount=mesh_transfer_amount,
                    mesh_marketplace_list=mesh_marketplace_list,
                    mesh_marketplace_buy=mesh_marketplace_buy,
                )
            except Exception as exc:
                novaprime_context["mesh"] = {"ok": False, "error": str(exc)}
                if "error" not in novaprime_context:
                    novaprime_context["error"] = str(exc)
        if novaprime_context.get("enabled"):
            result["novaprime"] = novaprime_context
        if adapt_context:
            result["adapt"] = adapt_context
        return result

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan_preview = self.run(
            {
                **payload,
                "execute": False,
                "record_history": False,
            }
        )
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("'objective' is required")
        stored = self._plans().create(
            {
                "objective": objective,
                "strategy": str(payload.get("strategy", "single")),
                "model": plan_preview.get("model"),
                "model_id": plan_preview.get("model_id"),
                "actions": plan_preview.get("actions", []),
                "votes": plan_preview.get("votes", {}),
                "model_errors": plan_preview.get("model_errors", {}),
                "attempted_models": plan_preview.get("attempted_models", []),
                "status": "pending",
            }
        )
        stored["preview_results"] = plan_preview.get("results", [])
        return stored

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._plans().list(limit=max(1, int(limit)))

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._plans().get(plan_id)

    def approve_plan(
        self,
        plan_id: str,
        payload: dict[str, Any],
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        if plan["status"] == "rejected":
            raise ValueError("Plan already rejected")
        if plan["status"] == "executing":
            raise ValueError("Plan is already executing")

        execute = coerce_bool(payload.get("execute"), default=True)
        allow_dangerous = coerce_bool(payload.get("allow_dangerous"), default=False)
        max_actions = int(payload.get("max_actions", len(plan.get("actions", [])) or 1))
        action_retry_attempts = max(0, int(payload.get("action_retry_attempts", 0)))
        action_retry_backoff_seconds = max(0.0, float(payload.get("action_retry_backoff_seconds", 0.25)))
        retry_failed_only = coerce_bool(payload.get("retry_failed_only"), default=False)

        if plan["status"] == "executed":
            if retry_failed_only:
                raise ValueError("Plan is already executed and has no failed actions to retry")
            return plan
        if retry_failed_only and plan["status"] != "failed":
            raise ValueError("Plan must be failed to retry failed actions")

        if retry_failed_only and not execute:
            raise ValueError("'retry_failed_only' requires execute=true")

        if not execute:
            approved = self._plans().approve(plan_id=plan_id, status="approved")
            if approved is None:
                raise ValueError("Plan not found")
            return approved

        actions = [item for item in plan.get("actions", []) if isinstance(item, dict)]
        if retry_failed_only:
            prior_results = plan.get("execution_results")
            if not isinstance(prior_results, list):
                raise ValueError("Plan has no prior execution results to retry")
            retry_indexes = []
            for idx, result in enumerate(prior_results):
                if idx >= len(actions):
                    break
                if not isinstance(result, dict):
                    continue
                status = str(result.get("status", "")).strip().lower()
                if status in {"failed", "blocked"}:
                    retry_indexes.append(idx)
            if not retry_indexes:
                raise ValueError("No failed or blocked actions available for retry")
            actions = [actions[idx] for idx in retry_indexes]
        actions = actions[: max(1, max_actions)]

        existing_action_log_ids = plan.get("action_log_ids")
        preserved_action_log_ids: list[int] = []
        if isinstance(existing_action_log_ids, list):
            for value in existing_action_log_ids:
                try:
                    preserved_action_log_ids.append(int(value))
                except (TypeError, ValueError):
                    continue

        policy = ActionPolicy()
        queue = UndoQueue(db_path=self.db_path)
        self._plans().mark_executing(plan_id=plan_id, total_actions=len(actions))

        execution_results: list[dict[str, Any]] = []
        action_log_ids: list[int] = list(preserved_action_log_ids)
        try:
            for idx, action in enumerate(actions, start=1):
                if callable(cancel_requested) and bool(cancel_requested()):
                    raise RuntimeError("execution canceled by operator")

                decision = policy.evaluate(action, allow_dangerous=allow_dangerous)
                undo_action = action.get("undo") if isinstance(action.get("undo"), dict) else None
                if not decision.allowed:
                    execution_results.append(
                        {
                            "status": "blocked",
                            "output": decision.reason,
                            "action": action,
                            "dangerous": decision.dangerous,
                        }
                    )
                    action_log_ids.append(
                        queue.record(
                            action=action,
                            status="blocked",
                            undo_action=undo_action,
                        )
                    )
                    self._plans().update_execution_progress(
                        plan_id=plan_id,
                        execution_results=execution_results,
                        action_log_ids=action_log_ids,
                        progress_completed=idx,
                        progress_total=len(actions),
                    )
                    continue

                routed = self._execute_routed_action(action, execute=True)
                attempts = 1
                while str(routed["status"]).lower() != "ok" and attempts <= action_retry_attempts:
                    if callable(cancel_requested) and bool(cancel_requested()):
                        raise RuntimeError("execution canceled by operator")
                    if action_retry_backoff_seconds > 0:
                        time.sleep(action_retry_backoff_seconds * (2 ** (attempts - 1)))
                    routed = self._execute_routed_action(action, execute=True)
                    attempts += 1
                execution_results.append(
                    {
                        "status": routed["status"],
                        "output": routed["output"],
                        "action": routed["action"],
                        "dangerous": decision.dangerous,
                        "attempts": attempts,
                        "data": routed.get("data"),
                    }
                )
                action_log_ids.append(
                    queue.record(
                        action=routed["action"],
                        status=routed["status"],
                        undo_action=undo_action,
                    )
                )
                self._plans().update_execution_progress(
                    plan_id=plan_id,
                    execution_results=execution_results,
                    action_log_ids=action_log_ids,
                    progress_completed=idx,
                    progress_total=len(actions),
                )
        except Exception as exc:  # pragma: no cover - defensive execution boundary
            self._plans().fail_execution(
                plan_id=plan_id,
                error=str(exc),
                execution_results=execution_results,
                action_log_ids=action_log_ids,
                progress_completed=len(execution_results),
                progress_total=len(actions),
            )
            self._persist_plan_memory(
                plan_id=plan_id,
                objective=str(plan.get("objective", "")),
                status="failed",
                actions=actions,
                execution_results=execution_results,
                execution_error=str(exc),
            )
            raise

        failed_actions = [
            item
            for item in execution_results
            if str(item.get("status", "")).lower() in {"failed", "blocked"}
        ]
        if failed_actions:
            failed = self._plans().fail_execution(
                plan_id=plan_id,
                error=f"{len(failed_actions)} actions failed or were blocked",
                execution_results=execution_results,
                action_log_ids=action_log_ids,
                progress_completed=len(execution_results),
                progress_total=len(actions),
            )
            if failed is None:
                raise ValueError("Plan not found")
            self._persist_plan_memory(
                plan_id=plan_id,
                objective=str(plan.get("objective", "")),
                status="failed",
                actions=actions,
                execution_results=execution_results,
                execution_error=str(failed.get("execution_error", "")),
            )
            self._track_memory_events(["plan.failed", "plan.failed_actions"])
            return failed

        approved = self._plans().approve(
            plan_id=plan_id,
            execution_results=execution_results,
            action_log_ids=action_log_ids,
            status="executed",
        )
        if approved is None:
            raise ValueError("Plan not found")
        self._persist_plan_memory(
            plan_id=plan_id,
            objective=str(plan.get("objective", "")),
            status="executed",
            actions=actions,
            execution_results=execution_results,
            execution_error="",
        )
        self._track_memory_events(["plan.executed"])
        return approved

    def reject_plan(self, plan_id: str, reason: str | None = None) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        if plan["status"] == "executed":
            raise ValueError("Plan already executed")
        rejected = self._plans().reject(plan_id, reason=reason)
        if rejected is None:
            raise ValueError("Plan not found")
        self._ingest_control_memory(
            control_type="plan_reject",
            payload={"plan_id": plan_id, "reason": str(reason or ""), "status": "rejected"},
            event_names=["plan.reject"],
        )
        return rejected

    def undo_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        action_log_ids = plan.get("action_log_ids") or []
        if not isinstance(action_log_ids, list) or not action_log_ids:
            raise ValueError("Plan has no recorded action logs to undo")

        execute = coerce_bool(payload.get("execute"), default=False)
        mark_only = coerce_bool(payload.get("mark_only"), default=False)
        results: list[dict[str, Any]] = []
        for action_id in reversed(action_log_ids):
            try:
                result = self.undo(
                    {
                        "id": int(action_id),
                        "execute": execute,
                        "mark_only": mark_only,
                    }
                )
                results.append({"id": int(action_id), "ok": True, "result": result})
            except ValueError as exc:
                results.append({"id": int(action_id), "ok": False, "error": str(exc)})

        payload = {
            "plan_id": plan_id,
            "executed": execute,
            "mark_only": mark_only,
            "results": results,
        }
        self._ingest_control_memory(
            control_type="plan_undo",
            payload=payload,
            event_names=["plan.undo"],
        )
        return payload

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        queue = UndoQueue(db_path=self.db_path)
        return queue.recent(limit=max(1, int(limit)))

    def undo(self, payload: dict[str, Any]) -> dict[str, Any]:
        queue = UndoQueue(db_path=self.db_path)
        action_id = payload.get("id")
        mark_only = coerce_bool(payload.get("mark_only"), default=False)
        execute = coerce_bool(payload.get("execute"), default=False)

        item = queue.get(int(action_id)) if action_id is not None else queue.latest_pending()
        if item is None:
            raise ValueError("No matching action found in log")

        if item["undone"]:
            raise ValueError(f"Action {item['id']} is already marked undone")

        undo_action = item.get("undo_action")
        if undo_action is None and not mark_only:
            raise ValueError(
                "No undo action stored for this record. Set 'mark_only': true to mark it manually."
            )

        if mark_only:
            queue.mark_undone(item["id"])
            return {"id": item["id"], "status": "marked_undone", "mode": "mark_only"}

        result = self._execute_routed_action(undo_action, execute=execute)
        marked = bool(execute and result["status"] == "ok")
        if marked:
            queue.mark_undone(item["id"])
        payload = {
            "id": item["id"],
            "executed": execute,
            "undo_result": {
                "status": result["status"],
                "output": result["output"],
                "action": result["action"],
            },
            "marked_undone": marked,
        }
        self._ingest_control_memory(
            control_type="undo",
            payload=payload,
            event_names=["undo.executed" if marked else "undo.preview"],
        )
        return payload

    def events(
        self,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._audits().list(
            limit=max(1, int(limit)),
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            since_id=(int(since_id) if since_id is not None else None),
        )

    def events_wait(
        self,
        *,
        timeout_seconds: float = 30.0,
        interval_seconds: float = 0.25,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        timeout = min(300.0, max(0.1, float(timeout_seconds)))
        interval = min(5.0, max(0.01, float(interval_seconds)))
        deadline = time.monotonic() + timeout
        marker = int(since_id) if since_id is not None else None

        while True:
            rows = self.events(
                limit=max(1, int(limit)),
                category=category,
                entity_type=entity_type,
                entity_id=entity_id,
                since_id=marker,
            )
            if rows:
                # events() returns descending; watchers generally want oldest-first.
                return list(reversed(rows))
            if time.monotonic() >= deadline:
                return []
            time.sleep(interval)

    def _execute_routed_action(
        self,
        action: dict[str, Any],
        *,
        execute: bool,
        config_path: Path | None = None,
    ) -> dict[str, Any]:
        normalized_action = self._normalize_routed_action(action)
        action_type = str(normalized_action.get("type") or "").strip().lower()
        executor_name = str(normalized_action.get("executor") or "").strip().lower()
        platform_name = str(normalized_action.get("platform") or "").strip().lower()

        if executor_name == "vision" or action_type == "vision_goal":
            goal = str(normalized_action.get("goal") or normalized_action.get("target") or normalized_action.get("value") or "").strip()
            grounded = self._vision().ground(
                goal=goal,
                config_path=config_path or self.default_config,
                screenshot_png=self._decode_base64_image(normalized_action.get("screenshot_base64")),
                app_name=str(normalized_action.get("app_name") or "").strip(),
                model_name=str(normalized_action.get("model") or "").strip() or None,
                strategy=str(normalized_action.get("strategy") or "single"),
                candidate_models=self._as_name_list(normalized_action.get("candidates")) or None,
                fallback_models=self._as_name_list(normalized_action.get("fallbacks")) or None,
                context=normalized_action.get("context") if isinstance(normalized_action.get("context"), dict) else None,
                ocr_text=str(normalized_action.get("ocr_text") or ""),
                accessibility_tree=str(normalized_action.get("accessibility_tree") or ""),
            )
            inner_action = dict(grounded.action)
            result = self._execute_routed_action(inner_action, execute=execute, config_path=config_path)
            result.setdefault("data", {})
            if isinstance(result["data"], dict):
                result["data"]["vision"] = {
                    "confidence": grounded.confidence,
                    "reason": grounded.reason,
                    "model": grounded.model_name,
                    "model_id": grounded.model_id,
                }
            return result

        if platform_name == "android" or executor_name == "mobile" or action_type.startswith("android_"):
            if action_type.startswith("android_"):
                normalized_action["type"] = action_type.removeprefix("android_")
            normalized_action["platform"] = "android"
            result = self._mobile().execute_action(normalized_action, dry_run=not execute)
            return _result_payload(result.status, result.output, result.action, result.data)

        if action_type in {"ha_service", "mqtt_publish", "mqtt_subscribe", "discover", "discover_entities", "list_entities"} or executor_name in {"homeassistant", "iot"}:
            result = self._homeassistant().execute_action(normalized_action, dry_run=not execute)
            return _result_payload(result.status, result.output, result.action, result.data)

        browser_types = set(BrowserExecutor.capabilities())
        if action_type in browser_types or executor_name == "browser":
            if not execute:
                return _result_payload(
                    "preview",
                    f"Preview only: browser {action_type}",
                    normalized_action,
                    {"transport": "browser"},
                )
            result = self._browser().execute_action(normalized_action)
            return _result_payload(
                str(result.status),
                str(result.output),
                normalized_action,
                result.data if isinstance(result.data, dict) else None,
            )

        result = self.directshell_factory().execute_action(action=normalized_action, dry_run=not execute)
        return _result_payload(result.status, result.output, result.action, None)

    @staticmethod
    def _normalize_routed_action(action: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(action or {})
        action_type = str(normalized.get("type") or "").strip().lower()
        if action_type in {"click", "right_click", "double_click"} and not normalized.get("target"):
            x = normalized.get("x")
            y = normalized.get("y")
            if x is not None and y is not None:
                try:
                    normalized["target"] = f"{int(x)},{int(y)}"
                except Exception:
                    pass
        if action_type in {"type", "text", "input"} and not normalized.get("value") and normalized.get("text") is not None:
            normalized["value"] = str(normalized.get("text") or "")
        if action_type == "hotkey" and not normalized.get("target"):
            keys = normalized.get("keys")
            if isinstance(keys, list):
                normalized["target"] = "+".join(str(item).strip() for item in keys if str(item).strip())
        return normalized

    def _ingest_control_memory(
        self,
        *,
        control_type: str,
        payload: dict[str, Any],
        event_names: list[str] | None = None,
    ) -> None:
        normalized_type = str(control_type or "").strip().lower() or "control"
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            self.memory_backend.ingest(
                text=json.dumps(
                    {
                        "type": f"novaadapt_{normalized_type}",
                        "created_at": created_at,
                        "payload": payload,
                    },
                    ensure_ascii=True,
                ),
                source_id=f"novaadapt:{normalized_type}:{uuid.uuid4().hex}",
                metadata={"type": f"novaadapt_{normalized_type}"},
            )
        except Exception:
            pass
        self._track_memory_events(event_names or [])

    def _track_memory_events(self, event_names: list[str]) -> None:
        cleaned = [str(item).strip() for item in event_names if str(item).strip()]
        if not cleaned:
            return
        track_batch = getattr(self.memory_backend, "track_events_batch", None)
        if callable(track_batch):
            try:
                track_batch(cleaned)
                return
            except Exception:
                return
        track_single = getattr(self.memory_backend, "track_event", None)
        if callable(track_single):
            for item in cleaned:
                try:
                    track_single(item)
                except Exception:
                    return

    @staticmethod
    def _decode_base64_image(value: object) -> bytes | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if "," in raw and raw.lower().startswith("data:image"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise ValueError("invalid screenshot_base64 payload") from exc

    @staticmethod
    def _as_name_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _persist_plan_memory(
        self,
        *,
        plan_id: str,
        objective: str,
        status: str,
        actions: list[dict[str, Any]],
        execution_results: list[dict[str, Any]],
        execution_error: str,
    ) -> None:
        try:
            payload = {
                "type": "novaadapt_plan_execution",
                "plan_id": plan_id,
                "objective": objective,
                "status": status,
                "execution_error": execution_error,
                "actions": [
                    {
                        "type": str(item.get("type", "")),
                        "target": str(item.get("target", "")),
                        "value": str(item.get("value", "")) if item.get("value") is not None else "",
                    }
                    for item in actions
                ],
                "results": [
                    {
                        "status": str(item.get("status", "")),
                        "output": str(item.get("output", "")),
                        "dangerous": bool(item.get("dangerous", False)),
                    }
                    for item in execution_results
                ],
            }
            self.memory_backend.ingest(
                text=json.dumps(payload, ensure_ascii=True),
                source_id=f"novaadapt:plan:{plan_id}",
                metadata={
                    "type": "novaadapt_plan_execution",
                    "plan_id": plan_id,
                    "status": status,
                    "objective": objective[:240],
                },
            )
        except Exception:
            return

    def _canvas_renderer_obj(self) -> CanvasRenderer:
        if self._canvas_renderer is None:
            self._canvas_renderer = CanvasRenderer()
        return self._canvas_renderer

    def _canvas_store(self) -> CanvasSessionStore:
        if self._canvas_sessions is None:
            self._canvas_sessions = CanvasSessionStore()
        return self._canvas_sessions

    def _workflow_db_path(self) -> Path:
        if isinstance(self.db_path, Path):
            return self.db_path.with_name("novaadapt_workflows.sqlite3")
        base_dir = self.default_config.parent if isinstance(self.default_config, Path) else Path(".")
        return base_dir / ".novaadapt_workflows.sqlite3"

    def _workflow_store_obj(self) -> WorkflowStore:
        if self._workflow_store is None:
            db_path = self._workflow_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._workflow_store = WorkflowStore(str(db_path))
        return self._workflow_store

    def _workflow_checkpoints_obj(self) -> WorkflowCheckpointStore:
        if self._workflow_checkpoints is None:
            db_path = self._workflow_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._workflow_checkpoints = WorkflowCheckpointStore(str(db_path))
        return self._workflow_checkpoints

    def _workflow_engine_obj(self) -> WorkflowEngine:
        if self._workflow_engine is None:
            self._workflow_engine = WorkflowEngine(
                self._workflow_store_obj(),
                checkpoints=self._workflow_checkpoints_obj(),
            )
        return self._workflow_engine

    def _control_artifact_dir(self) -> Path:
        if isinstance(self.db_path, Path):
            return self.db_path.with_name("novaadapt_control_artifacts")
        base_dir = self.default_config.parent if isinstance(self.default_config, Path) else Path(".")
        return base_dir / ".novaadapt_control_artifacts"

    def _runtime_governance_state_path(self) -> Path:
        if isinstance(self.db_path, Path):
            return self.db_path.with_name("novaadapt_runtime_governance.json")
        base_dir = self.default_config.parent if isinstance(self.default_config, Path) else Path(".")
        return base_dir / ".novaadapt_runtime_governance.json"

    def _control_artifact_store_obj(self) -> ControlArtifactStore:
        if self._control_artifact_store is None:
            root_dir = self._control_artifact_dir()
            root_dir.mkdir(parents=True, exist_ok=True)
            self._control_artifact_store = ControlArtifactStore(root_dir)
        return self._control_artifact_store

    @staticmethod
    def _canvas_frame_payload(frame: CanvasRenderResult) -> dict[str, Any]:
        return {
            "frame_id": str(frame.frame_id),
            "html": str(frame.html),
            "created_at": str(frame.created_at),
            "metadata": dict(frame.metadata),
        }

    @staticmethod
    def _workflow_payload(record: WorkflowRecord) -> dict[str, Any]:
        return {
            "workflow_id": str(record.workflow_id),
            "status": str(record.status),
            "objective": str(record.objective),
            "steps": [dict(item) for item in record.steps],
            "context": dict(record.context),
            "created_at": str(record.created_at),
            "updated_at": str(record.updated_at),
            "last_error": str(record.last_error),
        }

    def _plans(self) -> PlanStore:
        if self._plan_store is None:
            self._plan_store = PlanStore(self.plans_db_path)
        return self._plan_store

    def _audits(self) -> AuditStore:
        if self._audit_store is None:
            self._audit_store = AuditStore(self.audit_db_path)
        return self._audit_store

    def _store_control_artifact(
        self,
        *,
        control_type: str,
        result: dict[str, Any],
        goal: str = "",
        platform: str = "",
        transport: str = "",
        preview_png: bytes | None = None,
        model: str | None = None,
        model_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            action = result.get("action") if isinstance(result.get("action"), dict) else {}
            return self._control_artifact_store_obj().create(
                control_type=control_type,
                status=str(result.get("status") or ""),
                output=str(result.get("output") or ""),
                action=action,
                dangerous=bool(result.get("dangerous", False)),
                goal=goal,
                platform=platform or str(result.get("platform") or ""),
                transport=transport,
                model=model or str((result.get("vision") or {}).get("model") or ""),
                model_id=model_id or str((result.get("vision") or {}).get("model_id") or ""),
                preview_png=preview_png,
                data=result.get("data") if isinstance(result.get("data"), dict) else None,
                metadata=metadata,
            )
        except Exception:
            return None

    @staticmethod
    def _vision_metadata_without_screenshot(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key): item
            for key, item in value.items()
            if str(key) != "screenshot_base64"
        }

    def _browser(self) -> BrowserExecutor:
        if self._browser_executor is None:
            self._browser_executor = self.browser_executor_factory()
        return self._browser_executor

    def _vision(self) -> VisionGroundingExecutor:
        if self._vision_executor is None:
            if self.vision_executor_factory is not None:
                self._vision_executor = self.vision_executor_factory()
            else:
                self._vision_executor = VisionGroundingExecutor(
                    router_loader=self.router_loader,
                    default_config=self.default_config,
                )
        return self._vision_executor

    def _mobile(self) -> UnifiedMobileExecutor:
        if self._mobile_executor is None:
            if self.mobile_executor_factory is not None:
                self._mobile_executor = self.mobile_executor_factory()
            else:
                self._mobile_executor = UnifiedMobileExecutor(
                    android_executor=AndroidMaestroExecutor(),
                    ios_executor=IOSVisionExecutor(self._vision()),
                    ios_appium_executor=IOSAppiumExecutor(),
                )
        return self._mobile_executor

    def _homeassistant(self) -> HomeAssistantExecutor:
        if self._homeassistant_executor is None:
            self._homeassistant_executor = self.homeassistant_executor_factory()
        return self._homeassistant_executor

    def _sib(self) -> SIBBridge:
        if self._sib_bridge is None:
            self._sib_bridge = SIBBridge(self.plugin_registry)
        return self._sib_bridge

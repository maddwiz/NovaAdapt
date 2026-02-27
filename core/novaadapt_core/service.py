from __future__ import annotations

import json
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
from .directshell import DirectShellClient
from .memory import MemoryBackend, build_memory_backend
from .novaprime import NovaPrimeBackend, build_novaprime_client
from .plan_store import PlanStore
from .policy import ActionPolicy
from .plugins import PluginRegistry, SIBBridge, build_plugin_registry


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
        memory_backend: MemoryBackend | None = None,
        novaprime_client: NovaPrimeBackend | None = None,
        adapt_toggle_store: AdaptToggleStore | None = None,
        adapt_bond_cache: AdaptBondCache | None = None,
        adapt_persona: AdaptPersonaEngine | None = None,
        plugin_registry: PluginRegistry | None = None,
    ) -> None:
        self.default_config = default_config
        self.db_path = db_path
        self.plans_db_path = plans_db_path
        self.audit_db_path = audit_db_path
        self.router_loader = router_loader or ModelRouter.from_config_file
        self.directshell_factory = directshell_factory or DirectShellClient
        self.browser_executor_factory = browser_executor_factory or BrowserExecutor
        self.memory_backend = memory_backend or build_memory_backend()
        self.novaprime_client = novaprime_client or build_novaprime_client()
        self.adapt_toggle_store = adapt_toggle_store or AdaptToggleStore()
        self.adapt_bond_cache = adapt_bond_cache or AdaptBondCache()
        self.adapt_persona = adapt_persona or AdaptPersonaEngine()
        self.plugin_registry = plugin_registry or build_plugin_registry()
        self._plan_store: PlanStore | None = None
        self._audit_store: AuditStore | None = None
        self._browser_executor: BrowserExecutor | None = None
        self._sib_bridge: SIBBridge | None = None

    def close(self) -> None:
        browser = self._browser_executor
        self._browser_executor = None
        if browser is None:
            return
        close_fn = getattr(browser, "close", None)
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
            return result
        return {"ok": False, "error": "invalid novaprime identity bond response"}

    def novaprime_identity_verify(self, adapt_id: str, player_id: str) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")
        verified = bool(self.novaprime_client.identity_verify(normalized_adapt, normalized_player))
        return {"ok": True, "adapt_id": normalized_adapt, "player_id": normalized_player, "verified": verified}

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
            return result
        return {"ok": False, "error": "invalid novaprime resonance bond response"}

    def adapt_toggle_get(self, adapt_id: str) -> dict[str, Any]:
        return self.adapt_toggle_store.get(adapt_id)

    def adapt_toggle_set(self, adapt_id: str, mode: str, *, source: str = "api") -> dict[str, Any]:
        return self.adapt_toggle_store.set(adapt_id, mode, source=source)

    def adapt_bond_get(self, adapt_id: str) -> dict[str, Any] | None:
        return self.adapt_bond_cache.get(adapt_id)

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
        return self._sib().resonance_start(
            normalized_player,
            profile=player_profile if isinstance(player_profile, dict) else None,
        )

    def sib_resonance_result(self, player_id: str, adapt_id: str, accepted: bool) -> dict[str, Any]:
        normalized_player = str(player_id or "").strip()
        normalized_adapt = str(adapt_id or "").strip()
        if not normalized_player:
            raise ValueError("'player_id' is required")
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        return self._sib().resonance_result(normalized_player, normalized_adapt, bool(accepted))

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
                        context["credit"] = (
                            credit_result
                            if isinstance(credit_result, dict)
                            else {"ok": False, "error": "invalid novaprime mesh credit response"}
                        )
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
                        context["transfer"] = (
                            transfer_result
                            if isinstance(transfer_result, dict)
                            else {"ok": False, "error": "invalid novaprime mesh transfer response"}
                        )
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
                        context["marketplace_list"] = (
                            list_result
                            if isinstance(list_result, dict)
                            else {"ok": False, "error": "invalid novaprime marketplace list response"}
                        )
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
                        context["marketplace_buy"] = (
                            buy_result
                            if isinstance(buy_result, dict)
                            else {"ok": False, "error": "invalid novaprime marketplace buy response"}
                        )
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
        execute = bool(payload.get("execute", False))
        record_history = bool(payload.get("record_history", True))
        allow_dangerous = bool(payload.get("allow_dangerous", False))
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
        mesh_marketplace_list = payload.get("mesh_marketplace_list")
        mesh_marketplace_buy = payload.get("mesh_marketplace_buy")
        has_mesh_ops = bool(
            mesh_node_id
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

        novaprime_context: dict[str, Any] = {"enabled": bool(adapt_id or has_mesh_ops)}
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

        router = self.router_loader(config_path)
        queue = UndoQueue(db_path=self.db_path)
        agent = NovaAdaptAgent(
            router=router,
            directshell=self.directshell_factory(),
            undo_queue=queue,
            memory_backend=self.memory_backend,
        )
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
        if has_mesh_ops:
            try:
                novaprime_context["mesh"] = self._execute_runtime_mesh_ops(
                    adapt_id=adapt_id,
                    mesh_node_id=mesh_node_id,
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

        execute = bool(payload.get("execute", True))
        allow_dangerous = bool(payload.get("allow_dangerous", False))
        max_actions = int(payload.get("max_actions", len(plan.get("actions", [])) or 1))
        action_retry_attempts = max(0, int(payload.get("action_retry_attempts", 0)))
        action_retry_backoff_seconds = max(0.0, float(payload.get("action_retry_backoff_seconds", 0.25)))
        retry_failed_only = bool(payload.get("retry_failed_only", False))

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
        directshell = self.directshell_factory()
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

                run_result = directshell.execute_action(action=action, dry_run=False)
                attempts = 1
                while str(run_result.status).lower() != "ok" and attempts <= action_retry_attempts:
                    if callable(cancel_requested) and bool(cancel_requested()):
                        raise RuntimeError("execution canceled by operator")
                    if action_retry_backoff_seconds > 0:
                        time.sleep(action_retry_backoff_seconds * (2 ** (attempts - 1)))
                    run_result = directshell.execute_action(action=action, dry_run=False)
                    attempts += 1
                execution_results.append(
                    {
                        "status": run_result.status,
                        "output": run_result.output,
                        "action": run_result.action,
                        "dangerous": decision.dangerous,
                        "attempts": attempts,
                    }
                )
                action_log_ids.append(
                    queue.record(
                        action=run_result.action,
                        status=run_result.status,
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
        return rejected

    def undo_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        action_log_ids = plan.get("action_log_ids") or []
        if not isinstance(action_log_ids, list) or not action_log_ids:
            raise ValueError("Plan has no recorded action logs to undo")

        execute = bool(payload.get("execute", False))
        mark_only = bool(payload.get("mark_only", False))
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

        return {
            "plan_id": plan_id,
            "executed": execute,
            "mark_only": mark_only,
            "results": results,
        }

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        queue = UndoQueue(db_path=self.db_path)
        return queue.recent(limit=max(1, int(limit)))

    def undo(self, payload: dict[str, Any]) -> dict[str, Any]:
        queue = UndoQueue(db_path=self.db_path)
        action_id = payload.get("id")
        mark_only = bool(payload.get("mark_only", False))
        execute = bool(payload.get("execute", False))

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

        directshell = self.directshell_factory()
        result = directshell.execute_action(action=undo_action, dry_run=not execute)
        marked = bool(execute and result.status == "ok")
        if marked:
            queue.mark_undone(item["id"])
        return {
            "id": item["id"],
            "executed": execute,
            "undo_result": {
                "status": result.status,
                "output": result.output,
                "action": result.action,
            },
            "marked_undone": marked,
        }

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

    def _plans(self) -> PlanStore:
        if self._plan_store is None:
            self._plan_store = PlanStore(self.plans_db_path)
        return self._plan_store

    def _audits(self) -> AuditStore:
        if self._audit_store is None:
            self._audit_store = AuditStore(self.audit_db_path)
        return self._audit_store

    def _browser(self) -> BrowserExecutor:
        if self._browser_executor is None:
            self._browser_executor = self.browser_executor_factory()
        return self._browser_executor

    def _sib(self) -> SIBBridge:
        if self._sib_bridge is None:
            self._sib_bridge = SIBBridge(self.plugin_registry)
        return self._sib_bridge

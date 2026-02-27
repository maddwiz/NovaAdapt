from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import quote


class APIClientError(RuntimeError):
    pass


@dataclass
class NovaAdaptAPIClient:
    base_url: str
    token: str | None = None
    timeout_seconds: int = 30
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25

    def health(self, deep: bool = False) -> dict[str, Any]:
        suffix = "/health?deep=1" if deep else "/health"
        return self._get_json(suffix)

    def openapi(self) -> dict[str, Any]:
        return self._get_json("/openapi.json")

    def dashboard_data(
        self,
        plans_limit: int = 25,
        jobs_limit: int = 25,
        events_limit: int = 25,
        config: str | None = None,
    ) -> dict[str, Any]:
        query = (
            f"plans_limit={max(1, int(plans_limit))}"
            f"&jobs_limit={max(1, int(jobs_limit))}"
            f"&events_limit={max(1, int(events_limit))}"
        )
        if config:
            query = f"{query}&config={config}"
        payload = self._get_json(f"/dashboard/data?{query}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /dashboard/data")

    def models(self) -> list[dict[str, Any]]:
        payload = self._get_json("/models")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /models")

    def check(self, models: list[str] | None = None, probe: str = "Reply with: OK") -> Any:
        body = {"models": models or [], "probe": probe}
        return self._post_json("/check", body)

    def plugins(self) -> list[dict[str, Any]]:
        payload = self._get_json("/plugins")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /plugins")

    def plugin_health(self, plugin_name: str) -> dict[str, Any]:
        payload = self._get_json(f"/plugins/{plugin_name}/health")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plugins/{name}/health")

    def plugin_call(
        self,
        plugin_name: str,
        *,
        route: str,
        payload: dict[str, Any] | None = None,
        method: str = "POST",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "route": route,
            "method": str(method or "POST").upper(),
        }
        if payload is not None:
            body["payload"] = payload
        result = self._post_json(
            f"/plugins/{plugin_name}/call",
            body,
            idempotency_key=idempotency_key,
        )
        if isinstance(result, dict):
            return result
        raise APIClientError("Expected object payload from /plugins/{name}/call")

    def submit_feedback(
        self,
        *,
        rating: int,
        objective: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"rating": int(rating)}
        if objective:
            body["objective"] = objective
        if notes:
            body["notes"] = notes
        if metadata is not None:
            body["metadata"] = metadata
        if context is not None:
            body["context"] = context
        payload = self._post_json("/feedback", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /feedback")

    def memory_status(self) -> dict[str, Any]:
        payload = self._get_json("/memory/status")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /memory/status")

    def novaprime_status(self) -> dict[str, Any]:
        payload = self._get_json("/novaprime/status")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/status")

    def novaprime_reason_dual(self, task: str, *, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/reason/dual",
            {"task": str(task or "")},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/reason/dual")

    def novaprime_emotion_get(self) -> dict[str, Any]:
        payload = self._get_json("/novaprime/reason/emotion")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/reason/emotion")

    def novaprime_emotion_set(
        self,
        chemicals: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/reason/emotion",
            {"chemicals": chemicals if isinstance(chemicals, dict) else {}},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/reason/emotion")

    def novaprime_mesh_balance(self, node_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/novaprime/mesh/balance?node_id={quote(str(node_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/mesh/balance")

    def novaprime_mesh_reputation(self, node_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/novaprime/mesh/reputation?node_id={quote(str(node_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/mesh/reputation")

    def novaprime_marketplace_listings(self) -> dict[str, Any]:
        payload = self._get_json("/novaprime/marketplace/listings")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/marketplace/listings")

    def novaprime_identity_profile(self, adapt_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/novaprime/identity/profile?adapt_id={quote(str(adapt_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/identity/profile")

    def novaprime_presence(self, adapt_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/novaprime/presence?adapt_id={quote(str(adapt_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/presence")

    def novaprime_identity_bond(
        self,
        adapt_id: str,
        player_id: str,
        *,
        element: str = "",
        subclass: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/identity/bond",
            {
                "adapt_id": str(adapt_id or ""),
                "player_id": str(player_id or ""),
                "element": str(element or ""),
                "subclass": str(subclass or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/identity/bond")

    def novaprime_mesh_credit(
        self,
        node_id: str,
        amount: float,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/mesh/credit",
            {"node_id": str(node_id or ""), "amount": float(amount)},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/mesh/credit")

    def novaprime_mesh_transfer(
        self,
        from_node: str,
        to_node: str,
        amount: float,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/mesh/transfer",
            {
                "from_node": str(from_node or ""),
                "to_node": str(to_node or ""),
                "amount": float(amount),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/mesh/transfer")

    def novaprime_marketplace_list(
        self,
        capsule_id: str,
        seller: str,
        price: float,
        title: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/marketplace/list",
            {
                "capsule_id": str(capsule_id or ""),
                "seller": str(seller or ""),
                "price": float(price),
                "title": str(title or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/marketplace/list")

    def novaprime_marketplace_buy(
        self,
        listing_id: str,
        buyer: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/marketplace/buy",
            {
                "listing_id": str(listing_id or ""),
                "buyer": str(buyer or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/marketplace/buy")

    def novaprime_identity_verify(
        self,
        adapt_id: str,
        player_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/identity/verify",
            {
                "adapt_id": str(adapt_id or ""),
                "player_id": str(player_id or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/identity/verify")

    def novaprime_identity_evolve(
        self,
        adapt_id: str,
        *,
        xp_gain: float = 0.0,
        new_skill: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/identity/evolve",
            {
                "adapt_id": str(adapt_id or ""),
                "xp_gain": float(xp_gain),
                "new_skill": str(new_skill or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/identity/evolve")

    def novaprime_presence_update(
        self,
        adapt_id: str,
        *,
        realm: str = "",
        activity: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/presence/update",
            {
                "adapt_id": str(adapt_id or ""),
                "realm": str(realm or ""),
                "activity": str(activity or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/presence/update")

    def novaprime_resonance_score(
        self,
        player_profile: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/resonance/score",
            {"player_profile": player_profile if isinstance(player_profile, dict) else {}},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/resonance/score")

    def novaprime_resonance_bond(
        self,
        player_id: str,
        player_profile: dict[str, Any] | None = None,
        *,
        adapt_id: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/novaprime/resonance/bond",
            {
                "player_id": str(player_id or ""),
                "player_profile": player_profile if isinstance(player_profile, dict) else {},
                "adapt_id": str(adapt_id or ""),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /novaprime/resonance/bond")

    def sib_status(self) -> dict[str, Any]:
        payload = self._get_json("/sib/status")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /sib/status")

    def sib_realm(self, player_id: str, realm: str, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            "/sib/realm",
            {"player_id": str(player_id or ""), "realm": str(realm or "")},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /sib/realm")

    def sib_companion_state(
        self,
        adapt_id: str,
        state: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/sib/companion/state",
            {"adapt_id": str(adapt_id or ""), "state": state if isinstance(state, dict) else {}},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /sib/companion/state")

    def sib_companion_speak(
        self,
        adapt_id: str,
        text: str,
        *,
        channel: str = "in_game",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/sib/companion/speak",
            {
                "adapt_id": str(adapt_id or ""),
                "text": str(text or ""),
                "channel": str(channel or "in_game"),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /sib/companion/speak")

    def sib_phase_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"event_type": str(event_type or "")}
        if isinstance(payload, dict):
            body["payload"] = payload
        resp = self._post_json("/sib/phase-event", body, idempotency_key=idempotency_key)
        if isinstance(resp, dict):
            return resp
        raise APIClientError("Expected object payload from /sib/phase-event")

    def sib_resonance_start(
        self,
        player_id: str,
        player_profile: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"player_id": str(player_id or "")}
        if isinstance(player_profile, dict):
            body["player_profile"] = player_profile
        resp = self._post_json("/sib/resonance/start", body, idempotency_key=idempotency_key)
        if isinstance(resp, dict):
            return resp
        raise APIClientError("Expected object payload from /sib/resonance/start")

    def sib_resonance_result(
        self,
        player_id: str,
        adapt_id: str,
        accepted: bool,
        player_profile: dict[str, Any] | None = None,
        *,
        toggle_mode: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "player_id": str(player_id or ""),
            "adapt_id": str(adapt_id or ""),
            "accepted": bool(accepted),
        }
        if isinstance(player_profile, dict):
            body["player_profile"] = player_profile
        if toggle_mode is not None:
            body["toggle_mode"] = str(toggle_mode or "")
        resp = self._post_json("/sib/resonance/result", body, idempotency_key=idempotency_key)
        if isinstance(resp, dict):
            return resp
        raise APIClientError("Expected object payload from /sib/resonance/result")

    def adapt_toggle(self, adapt_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/adapt/toggle?adapt_id={quote(str(adapt_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /adapt/toggle")

    def set_adapt_toggle(
        self,
        adapt_id: str,
        mode: str,
        *,
        source: str = "api_client",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/adapt/toggle",
            {
                "adapt_id": str(adapt_id or ""),
                "mode": str(mode or ""),
                "source": str(source or "api_client"),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /adapt/toggle")

    def adapt_bond(self, adapt_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/adapt/bond?adapt_id={quote(str(adapt_id), safe='')}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /adapt/bond")

    def memory_recall(self, query: str, top_k: int = 10) -> dict[str, Any]:
        payload = self._post_json(
            "/memory/recall",
            {"query": str(query), "top_k": max(1, int(top_k))},
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /memory/recall")

    def memory_ingest(
        self,
        text: str,
        *,
        source_id: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "text": str(text),
            "source_id": str(source_id or ""),
        }
        if metadata is not None:
            body["metadata"] = metadata
        payload = self._post_json("/memory/ingest", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /memory/ingest")

    def browser_status(self) -> dict[str, Any]:
        payload = self._get_json("/browser/status")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/status")

    def browser_pages(self) -> dict[str, Any]:
        payload = self._get_json("/browser/pages")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/pages")

    def browser_action(self, action: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            "/browser/action",
            {"action": action},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/action")

    def browser_navigate(self, url: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            "/browser/navigate",
            {"url": str(url), **kwargs},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/navigate")

    def browser_click(self, selector: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            "/browser/click",
            {"selector": str(selector), **kwargs},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/click")

    def browser_fill(
        self,
        selector: str,
        value: str,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._post_json(
            "/browser/fill",
            {"selector": str(selector), "value": str(value), **kwargs},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/fill")

    def browser_extract_text(
        self,
        selector: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = dict(kwargs)
        if selector is not None:
            body["selector"] = str(selector)
        payload = self._post_json(
            "/browser/extract_text",
            body,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/extract_text")

    def browser_screenshot(
        self,
        *,
        path: str | None = None,
        full_page: bool = True,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"full_page": bool(full_page), **kwargs}
        if path is not None:
            body["path"] = str(path)
        payload = self._post_json(
            "/browser/screenshot",
            body,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/screenshot")

    def browser_wait_for_selector(
        self,
        selector: str,
        *,
        state: str = "visible",
        timeout_ms: int | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"selector": str(selector), "state": str(state), **kwargs}
        if timeout_ms is not None:
            body["timeout_ms"] = int(timeout_ms)
        payload = self._post_json(
            "/browser/wait_for_selector",
            body,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/wait_for_selector")

    def browser_evaluate_js(
        self,
        script: str,
        *,
        arg: Any = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"script": str(script), **kwargs}
        if arg is not None:
            body["arg"] = arg
        payload = self._post_json(
            "/browser/evaluate_js",
            body,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/evaluate_js")

    def browser_close(self, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            "/browser/close",
            {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /browser/close")

    def terminal_sessions(self) -> list[dict[str, Any]]:
        payload = self._get_json("/terminal/sessions")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /terminal/sessions")

    def terminal_session(self, session_id: str) -> dict[str, Any]:
        session = quote(str(session_id), safe="")
        payload = self._get_json(f"/terminal/sessions/{session}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /terminal/sessions/{id}")

    def terminal_output(self, session_id: str, *, since_seq: int = 0, limit: int = 200) -> dict[str, Any]:
        session = quote(str(session_id), safe="")
        payload = self._get_json(
            f"/terminal/sessions/{session}/output?since_seq={max(0, int(since_seq))}&limit={max(1, int(limit))}"
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /terminal/sessions/{id}/output")

    def start_terminal_session(
        self,
        *,
        command: str | None = None,
        cwd: str | None = None,
        shell: str | None = None,
        max_chunks: int = 4000,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"max_chunks": max(200, int(max_chunks))}
        if command is not None:
            body["command"] = str(command)
        if cwd is not None:
            body["cwd"] = str(cwd)
        if shell is not None:
            body["shell"] = str(shell)
        payload = self._post_json("/terminal/sessions", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /terminal/sessions")

    def terminal_input(self, session_id: str, text: str) -> dict[str, Any]:
        session = quote(str(session_id), safe="")
        payload = self._post_json(
            f"/terminal/sessions/{session}/input",
            {"input": str(text)},
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /terminal/sessions/{id}/input")

    def terminal_close(self, session_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        session = quote(str(session_id), safe="")
        payload = self._post_json(
            f"/terminal/sessions/{session}/close",
            {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /terminal/sessions/{id}/close")

    def run(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run")

    def run_async(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run_async", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run_async")

    def run_swarm(
        self,
        objectives: list[str],
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body = {"objectives": objectives, **kwargs}
        payload = self._post_json("/swarm/run", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /swarm/run")

    def create_plan(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/plans", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans")

    def plans(self, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._get_json(f"/plans?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /plans")

    def plan(self, plan_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/plans/{plan_id}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}")

    def approve_plan(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/approve",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/approve")

    def retry_failed_plan(
        self,
        plan_id: str,
        *,
        allow_dangerous: bool = True,
        action_retry_attempts: int = 2,
        action_retry_backoff_seconds: float = 0.2,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/retry_failed",
            {
                "allow_dangerous": bool(allow_dangerous),
                "action_retry_attempts": max(0, int(action_retry_attempts)),
                "action_retry_backoff_seconds": max(0.0, float(action_retry_backoff_seconds)),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from retry_failed_plan")

    def retry_failed_plan_async(
        self,
        plan_id: str,
        *,
        allow_dangerous: bool = True,
        action_retry_attempts: int = 2,
        action_retry_backoff_seconds: float = 0.2,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/retry_failed_async",
            {
                "allow_dangerous": bool(allow_dangerous),
                "action_retry_attempts": max(0, int(action_retry_attempts)),
                "action_retry_backoff_seconds": max(0.0, float(action_retry_backoff_seconds)),
            },
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from retry_failed_plan_async")

    def approve_plan_async(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/approve_async",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/approve_async")

    def reject_plan(
        self,
        plan_id: str,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/reject",
            {"reason": reason} if reason is not None else {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/reject")

    def undo_plan(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/undo",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/undo")

    def jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._get_json(f"/jobs?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /jobs")

    def job(self, job_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/jobs/{job_id}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /jobs/{id}")

    def job_stream(
        self,
        job_id: str,
        timeout_seconds: int = 30,
        interval_seconds: float = 0.25,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        interval = min(5.0, max(0.05, float(interval_seconds)))
        text = self._request_text(
            "GET",
            f"/jobs/{job_id}/stream?timeout={timeout}&interval={interval}",
        )
        return self._parse_sse_events(text)

    def plan_stream(
        self,
        plan_id: str,
        timeout_seconds: int = 30,
        interval_seconds: float = 0.25,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        interval = min(5.0, max(0.05, float(interval_seconds)))
        text = self._request_text(
            "GET",
            f"/plans/{plan_id}/stream?timeout={timeout}&interval={interval}",
        )
        return self._parse_sse_events(text)

    def cancel_job(self, job_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            f"/jobs/{job_id}/cancel",
            {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /jobs/{id}/cancel")

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._get_json(f"/history?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /history")

    def events(
        self,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        query = [f"limit={max(1, int(limit))}"]
        if category:
            query.append(f"category={category}")
        if entity_type:
            query.append(f"entity_type={entity_type}")
        if entity_id:
            query.append(f"entity_id={entity_id}")
        if since_id is not None:
            query.append(f"since_id={int(since_id)}")
        payload = self._get_json(f"/events?{'&'.join(query)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /events")

    def events_stream(
        self,
        timeout_seconds: int = 30,
        interval_seconds: float = 0.25,
        since_id: int = 0,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        interval = min(5.0, max(0.05, float(interval_seconds)))
        text = self._request_text(
            "GET",
            f"/events/stream?timeout={timeout}&interval={interval}&since_id={max(0, int(since_id))}",
        )
        return self._parse_sse_events(text)

    def undo(self, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json("/undo", kwargs, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /undo")

    def issue_session_token(
        self,
        scopes: list[str] | None = None,
        subject: str | None = None,
        device_id: str | None = None,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if scopes:
            body["scopes"] = scopes
        if subject:
            body["subject"] = subject
        if device_id:
            body["device_id"] = device_id
        if ttl_seconds is not None:
            body["ttl_seconds"] = max(1, int(ttl_seconds))
        payload = self._post_json("/auth/session", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/session")

    def revoke_session_token(self, token: str) -> dict[str, Any]:
        return self.revoke_session(session_token=token)

    def revoke_session(
        self,
        session_token: str | None = None,
        session_id: str | None = None,
        expires_at: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if session_token:
            body["token"] = session_token
        if session_id:
            body["session_id"] = session_id
        if expires_at is not None:
            body["expires_at"] = int(expires_at)
        if not body:
            raise APIClientError("session_token or session_id is required")
        payload = self._post_json("/auth/session/revoke", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/session/revoke")

    def revoke_session_id(self, session_id: str, expires_at: int | None = None) -> dict[str, Any]:
        payload = self.revoke_session(session_id=session_id, expires_at=expires_at)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/session/revoke")

    def allowed_devices(self) -> dict[str, Any]:
        payload = self._get_json("/auth/devices")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/devices")

    def add_allowed_device(self, device_id: str) -> dict[str, Any]:
        body = {"device_id": (device_id or "").strip()}
        payload = self._post_json("/auth/devices", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/devices")

    def remove_allowed_device(self, device_id: str) -> dict[str, Any]:
        body = {"device_id": (device_id or "").strip()}
        payload = self._post_json("/auth/devices/remove", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /auth/devices/remove")

    def metrics_text(self) -> str:
        return self._request_text("GET", "/metrics")

    def _get_json(self, path: str) -> Any:
        return self._request_json("GET", path, None)

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> Any:
        return self._request_json("POST", path, body, idempotency_key=idempotency_key)

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        idempotency_key: str | None = None,
    ) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        raw = self._perform_request_with_retries(
            method=method,
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
        )

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise APIClientError("Expected JSON response") from exc

    def _request_text(self, method: str, path: str) -> str:
        return self._perform_request_with_retries(method=method, path=path, payload=None)

    @staticmethod
    def _parse_sse_events(text: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        current_event = "message"
        for line in text.splitlines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip() or "message"
                continue
            if line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"raw": raw}
                events.append({"event": current_event, "data": data})
                current_event = "message"
        return events

    def _perform_request_with_retries(
        self,
        method: str,
        path: str,
        payload: bytes | None,
        idempotency_key: str | None = None,
    ) -> str:
        attempts = max(0, int(self.max_retries)) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            req = self._build_request(
                method=method,
                path=path,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8")
            except error.HTTPError as exc:
                try:
                    body_text = exc.read().decode("utf-8", errors="ignore")
                finally:
                    try:
                        exc.close()
                    except Exception:
                        pass
                last_error = APIClientError(f"HTTP {exc.code}: {body_text}")
                if not self._should_retry_http(exc.code) or attempt >= attempts - 1:
                    raise last_error from exc
            except error.URLError as exc:
                reason = exc.reason
                close_fn = getattr(reason, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
                last_error = APIClientError(f"Request failed: {exc.reason}")
                if attempt >= attempts - 1:
                    raise last_error from exc

            if attempt < attempts - 1:
                backoff = max(0.0, float(self.retry_backoff_seconds)) * (2**attempt)
                if backoff:
                    time.sleep(backoff)

        raise APIClientError(str(last_error) if last_error else "Request failed")

    def _build_request(
        self,
        method: str,
        path: str,
        payload: bytes | None,
        idempotency_key: str | None = None,
    ) -> request.Request:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": secrets.token_hex(12),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return request.Request(url=url, data=payload, headers=headers, method=method)

    @staticmethod
    def _should_retry_http(status_code: int) -> bool:
        return status_code in {408, 425, 429, 500, 502, 503, 504}

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol
from urllib import error, parse, request


class NovaPrimeBackend(Protocol):
    def status(self) -> dict[str, Any]:
        ...


class NoopNovaPrimeClient:
    def __init__(self, reason: str = "novaprime backend disabled") -> None:
        self.reason = str(reason or "").strip() or "novaprime backend disabled"

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": False,
            "backend": "noop",
            "reason": self.reason,
        }

    def _disabled(self) -> dict[str, Any]:
        return {"ok": False, "error": self.reason}

    def reason_dual(self, task: str) -> dict[str, Any]:
        _ = task
        return self._disabled()

    def emotion_get(self) -> dict[str, Any]:
        return self._disabled()

    def emotion_set(self, chemicals: dict[str, float]) -> dict[str, Any]:
        _ = chemicals
        return self._disabled()

    def mesh_balance(self, node_id: str) -> float:
        _ = node_id
        return 0.0

    def mesh_credit(self, node_id: str, amount: float) -> dict[str, Any]:
        _ = (node_id, amount)
        return self._disabled()

    def mesh_transfer(self, from_node: str, to_node: str, amount: float) -> dict[str, Any]:
        _ = (from_node, to_node, amount)
        return self._disabled()

    def marketplace_listings(self) -> list[dict[str, Any]]:
        return []

    def marketplace_list(self, capsule_id: str, seller: str, price: float, title: str) -> dict[str, Any]:
        _ = (capsule_id, seller, price, title)
        return self._disabled()

    def marketplace_buy(self, listing_id: str, buyer: str) -> dict[str, Any]:
        _ = (listing_id, buyer)
        return self._disabled()

    def identity_bond(
        self,
        adapt_id: str,
        player_id: str,
        element: str = "",
        subclass: str = "",
    ) -> dict[str, Any]:
        _ = (adapt_id, player_id, element, subclass)
        return self._disabled()

    def identity_verify(self, adapt_id: str, player_id: str) -> bool:
        _ = (adapt_id, player_id)
        return False

    def identity_profile(self, adapt_id: str) -> dict[str, Any] | None:
        _ = adapt_id
        return None

    def identity_evolve(
        self,
        adapt_id: str,
        xp_gain: float = 0,
        new_skill: str = "",
    ) -> dict[str, Any]:
        _ = (adapt_id, xp_gain, new_skill)
        return self._disabled()

    def presence_get(self, adapt_id: str) -> dict[str, Any]:
        return {"adapt_id": adapt_id, "realm": "aetherion", "activity": "idle"}

    def presence_update(self, adapt_id: str, realm: str = "", activity: str = "") -> dict[str, Any]:
        _ = (adapt_id, realm, activity)
        return self._disabled()

    def resonance_score(self, player_profile: dict[str, Any]) -> dict[str, Any]:
        _ = player_profile
        return self._disabled()

    def resonance_bond(
        self,
        player_id: str,
        player_profile: dict[str, Any],
        adapt_id: str = "",
    ) -> dict[str, Any]:
        _ = (player_id, player_profile, adapt_id)
        return self._disabled()


class NovaPrimeClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float = 10.0,
        retry_after_seconds: float = 30.0,
    ) -> None:
        raw_url = base_url or os.getenv("NOVAADAPT_NOVAPRIME_URL", "http://127.0.0.1:8400")
        self.base_url = str(raw_url).rstrip("/")
        raw_token = token if token is not None else os.getenv("NOVAADAPT_NOVAPRIME_TOKEN", "")
        self.token = str(raw_token).strip() or None
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.retry_after_seconds = max(1.0, float(retry_after_seconds))
        self.required = str(os.getenv("NOVAADAPT_NOVAPRIME_REQUIRED", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._available: bool | None = None
        self._last_error: str = ""
        self._next_probe_after = 0.0

    def status(self) -> dict[str, Any]:
        available = self._ensure_available()
        status: dict[str, Any] = {
            "ok": bool(available) if self.required else True,
            "enabled": bool(available),
            "backend": "novaprime-http",
            "base_url": self.base_url,
            "reachable": bool(available),
        }
        if self.required:
            status["required"] = True
        if self.token:
            status["token_configured"] = True
        if self._last_error:
            status["error"] = self._last_error
        return status

    # ------------------------------------------------------------------
    # Reasoning channel
    # ------------------------------------------------------------------

    def reason_dual(self, task: str) -> dict[str, Any]:
        return self._post("/api/v1/reason/dual", {"task": str(task or "")})

    def emotion_get(self) -> dict[str, Any]:
        return self._post("/api/v1/reason/emotion", {"action": "get"})

    def emotion_set(self, chemicals: dict[str, float]) -> dict[str, Any]:
        payload = chemicals if isinstance(chemicals, dict) else {}
        return self._post("/api/v1/reason/emotion", {"action": "set", "chemicals": payload})

    # ------------------------------------------------------------------
    # Mesh / economy channel
    # ------------------------------------------------------------------

    def mesh_balance(self, node_id: str) -> float:
        payload = self._get("/api/v1/mesh/credits/balance", {"node_id": str(node_id or "")})
        try:
            return float(payload.get("balance", 0.0))
        except Exception:
            return 0.0

    def mesh_credit(self, node_id: str, amount: float) -> dict[str, Any]:
        return self._post(
            "/api/v1/mesh/credits/credit",
            {"node_id": str(node_id or ""), "amount": float(amount)},
        )

    def mesh_transfer(self, from_node: str, to_node: str, amount: float) -> dict[str, Any]:
        return self._post(
            "/api/v1/mesh/credits/transfer",
            {
                "from_node": str(from_node or ""),
                "to_node": str(to_node or ""),
                "amount": float(amount),
            },
        )

    def marketplace_listings(self) -> list[dict[str, Any]]:
        payload = self._get("/api/v1/mesh/marketplace/listings")
        rows = payload.get("listings")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
        return []

    def marketplace_list(
        self,
        capsule_id: str,
        seller: str,
        price: float,
        title: str,
    ) -> dict[str, Any]:
        return self._post(
            "/api/v1/mesh/marketplace/list",
            {
                "capsule_id": str(capsule_id or ""),
                "seller": str(seller or ""),
                "price": float(price),
                "title": str(title or ""),
            },
        )

    def marketplace_buy(self, listing_id: str, buyer: str) -> dict[str, Any]:
        return self._post(
            "/api/v1/mesh/marketplace/buy",
            {
                "listing_id": str(listing_id or ""),
                "buyer": str(buyer or ""),
            },
        )

    # ------------------------------------------------------------------
    # Identity channel
    # ------------------------------------------------------------------

    def identity_bond(
        self,
        adapt_id: str,
        player_id: str,
        element: str = "",
        subclass: str = "",
    ) -> dict[str, Any]:
        return self._post(
            "/api/v1/identity/bond",
            {
                "adapt_id": str(adapt_id or ""),
                "player_id": str(player_id or ""),
                "element": str(element or ""),
                "subclass": str(subclass or ""),
            },
        )

    def identity_verify(self, adapt_id: str, player_id: str) -> bool:
        payload = self._post(
            "/api/v1/identity/verify",
            {
                "adapt_id": str(adapt_id or ""),
                "player_id": str(player_id or ""),
            },
        )
        return bool(payload.get("verified", False))

    def identity_profile(self, adapt_id: str) -> dict[str, Any] | None:
        payload = self._get("/api/v1/identity/profile", {"adapt_id": str(adapt_id or "")})
        profile = payload.get("profile")
        if isinstance(profile, dict):
            return profile
        return None

    def identity_evolve(
        self,
        adapt_id: str,
        xp_gain: float = 0,
        new_skill: str = "",
    ) -> dict[str, Any]:
        return self._post(
            "/api/v1/identity/evolve",
            {
                "adapt_id": str(adapt_id or ""),
                "xp_gain": float(xp_gain),
                "new_skill": str(new_skill or ""),
            },
        )

    def presence_get(self, adapt_id: str) -> dict[str, Any]:
        payload = self._get("/api/v1/identity/presence", {"adapt_id": str(adapt_id or "")})
        presence = payload.get("presence")
        if isinstance(presence, dict):
            return presence
        return {"adapt_id": str(adapt_id or ""), "realm": "aetherion", "activity": "idle"}

    def presence_update(self, adapt_id: str, realm: str = "", activity: str = "") -> dict[str, Any]:
        return self._post(
            "/api/v1/identity/presence/update",
            {
                "adapt_id": str(adapt_id or ""),
                "realm": str(realm or ""),
                "activity": str(activity or ""),
            },
        )

    # ------------------------------------------------------------------
    # SIB channel
    # ------------------------------------------------------------------

    def resonance_score(self, player_profile: dict[str, Any]) -> dict[str, Any]:
        payload = player_profile if isinstance(player_profile, dict) else {}
        return self._post("/api/v1/sib/resonance/score", {"player_profile": payload})

    def resonance_bond(
        self,
        player_id: str,
        player_profile: dict[str, Any],
        adapt_id: str = "",
    ) -> dict[str, Any]:
        payload = player_profile if isinstance(player_profile, dict) else {}
        return self._post(
            "/api/v1/sib/resonance/bond",
            {
                "player_id": str(player_id or ""),
                "player_profile": payload,
                "adapt_id": str(adapt_id or ""),
            },
        )

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _get(self, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
        if not self._ensure_available():
            return {"ok": False, "error": "novaprime unavailable"}
        try:
            return self._request_json("GET", path, None, query=query)
        except Exception as exc:
            self._mark_unavailable(exc)
            if self.required:
                raise
            return {"ok": False, "error": str(exc)}

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._ensure_available():
            return {"ok": False, "error": "novaprime unavailable"}
        try:
            return self._request_json("POST", path, payload, query=None)
        except Exception as exc:
            self._mark_unavailable(exc)
            if self.required:
                raise
            return {"ok": False, "error": str(exc)}

    def _ensure_available(self) -> bool:
        now = time.monotonic()
        if self._available is True:
            return True
        if self._available is False and now < self._next_probe_after:
            return False
        try:
            _ = self._request_json("GET", "/api/v1/health", None, query=None)
            self._available = True
            self._last_error = ""
            self._next_probe_after = 0.0
            return True
        except Exception as exc:
            self._mark_unavailable(exc)
            return False

    def _mark_unavailable(self, exc: Exception) -> None:
        self._available = False
        self._last_error = str(exc)
        self._next_probe_after = time.monotonic() + self.retry_after_seconds

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        query: dict[str, str] | None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            encoded = parse.urlencode(query)
            if encoded:
                url = f"{url}?{encoded}"

        headers = {"Accept": "application/json"}
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            raw = None

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(url=url, data=raw, method=method.upper(), headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
            code = int(exc.code)
            try:
                detail = exc.read().decode("utf-8", errors="ignore")
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
                try:
                    exc.fp = None
                    exc.file = None
                except Exception:
                    pass
            raise RuntimeError(f"NovaPrime HTTP {code}: {detail}") from None
        except error.URLError as exc:
            reason = exc.reason
            close_fn = getattr(reason, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            try:
                setattr(reason, "fp", None)
                setattr(reason, "file", None)
            except Exception:
                pass
            raise RuntimeError(f"NovaPrime transport error: {reason}") from None

        if not body.strip():
            return {}

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("NovaPrime returned non-JSON payload") from exc
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


def build_novaprime_client() -> NovaPrimeBackend:
    mode = str(os.getenv("NOVAADAPT_NOVAPRIME_BACKEND", "novaprime-http")).strip().lower()
    if mode in {"", "off", "none", "noop", "disabled"}:
        return NoopNovaPrimeClient(reason="disabled by NOVAADAPT_NOVAPRIME_BACKEND")
    if mode in {"novaprime-http", "http", "auto"}:
        return NovaPrimeClient()
    return NoopNovaPrimeClient(reason=f"unsupported novaprime backend mode: {mode}")

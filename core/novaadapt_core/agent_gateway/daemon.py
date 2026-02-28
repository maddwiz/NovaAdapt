from __future__ import annotations

import json
import time
from typing import Any

from .delivery import DeliveryManager
from .guards import assert_no_llm_env
from .router import GatewayRouter
from .worker import GatewayWorker, WorkerOutcome


class NovaAgentDaemon:
    def __init__(
        self,
        *,
        worker: GatewayWorker,
        delivery: DeliveryManager,
        router: GatewayRouter | None = None,
        connectors: dict[str, Any] | None = None,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        self.worker = worker
        self.delivery = delivery
        self.router = router or GatewayRouter()
        self.connectors = {
            str(name).strip().lower(): connector
            for name, connector in (connectors or {}).items()
            if str(name).strip()
        }
        self.poll_interval_seconds = max(0.05, float(poll_interval_seconds))

    def run_once(self) -> WorkerOutcome:
        self._drain_connectors()
        outcome = self.worker.process_once()
        if not outcome.processed or not outcome.job_id:
            return outcome
        if outcome.error:
            self.delivery.deliver(
                job_id=outcome.job_id,
                content=f"Job {outcome.job_id} failed: {outcome.error}",
            )
            return outcome
        content = self._extract_result_text(outcome.result)
        self.delivery.deliver(job_id=outcome.job_id, content=content)
        return outcome

    def run_forever(self) -> None:
        assert_no_llm_env()
        while True:
            self.run_once()
            time.sleep(self.poll_interval_seconds)

    def _drain_connectors(self) -> None:
        for name, connector in self.connectors.items():
            listen = getattr(connector, "listen", None)
            if not callable(listen):
                continue
            for message in listen():
                payload = message.to_dict() if hasattr(message, "to_dict") else {}
                if not isinstance(payload, dict):
                    continue
                decision = self.router.route(payload)
                text = str(payload.get("text") or "").strip()
                if not text:
                    continue
                job_payload = {
                    "objective": text,
                    "source": f"connector:{name}",
                    "session_id": str(payload.get("message_id") or ""),
                    "meta": {"connector_message": payload},
                }
                job_id = self.worker.queue.enqueue(
                    payload=job_payload,
                    workspace_id=decision.workspace_id,
                    profile_name=decision.profile_name,
                    reply_to=payload.get("reply_to") if isinstance(payload.get("reply_to"), dict) else {},
                )
                reply_to = payload.get("reply_to") if isinstance(payload.get("reply_to"), dict) else {}
                address = str(reply_to.get("to") or payload.get("sender") or "").strip()
                token = str(reply_to.get("token") or "").strip()
                if address:
                    self.delivery.register_reply_target(
                        job_id=job_id,
                        connector=name,
                        address=address,
                        token=token,
                    )

    @staticmethod
    def _extract_result_text(result: dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return ""
        for key in ("output_text", "final_text", "content", "output"):
            value = result.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        return json.dumps(result, ensure_ascii=True, default=str)

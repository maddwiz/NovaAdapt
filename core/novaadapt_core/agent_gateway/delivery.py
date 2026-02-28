from __future__ import annotations

from typing import Any, Callable

from .job_queue import GatewayJobQueue


class DeliveryManager:
    def __init__(
        self,
        *,
        queue: GatewayJobQueue,
        connector_resolver: Callable[[str], Any],
    ) -> None:
        self.queue = queue
        self.connector_resolver = connector_resolver

    def register_reply_target(
        self,
        *,
        job_id: str,
        connector: str,
        address: str,
        token: str = "",
    ) -> None:
        self.queue.upsert_delivery(
            job_id=str(job_id),
            connector=str(connector),
            address=str(address),
            token=str(token or ""),
            status="pending",
        )

    def deliver(
        self,
        *,
        job_id: str,
        content: str,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows = self.queue.list_pending_deliveries(job_id)
        sent = 0
        failed = 0
        for row in rows:
            connector_name = str(row.get("connector", "")).strip().lower()
            address = str(row.get("address", "")).strip()
            connector = self.connector_resolver(connector_name)
            if connector is None:
                failed += 1
                self.queue.mark_delivery(
                    job_id=str(job_id),
                    connector=connector_name,
                    address=address,
                    status="dead_letter",
                    last_error=f"missing connector: {connector_name}",
                )
                continue
            try:
                connector.send(
                    {"connector": connector_name, "to": address, "token": str(row.get("token", ""))},
                    str(content or ""),
                    attachments,
                )
                sent += 1
                self.queue.mark_delivery(
                    job_id=str(job_id),
                    connector=connector_name,
                    address=address,
                    status="sent",
                )
            except Exception as exc:
                failed += 1
                self.queue.mark_delivery(
                    job_id=str(job_id),
                    connector=connector_name,
                    address=address,
                    status="failed",
                    last_error=str(exc),
                )
        return {
            "ok": failed == 0,
            "job_id": str(job_id),
            "attempted": len(rows),
            "sent": sent,
            "failed": failed,
        }

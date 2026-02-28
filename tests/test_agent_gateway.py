import importlib
import inspect
import os
import tempfile
import unittest
from pathlib import Path

from novaadapt_core.agent_gateway.connectors import (
    ChannelAdapterConnector,
    XRealConnector,
    build_gateway_connectors,
)
from novaadapt_core.agent_gateway.daemon import NovaAgentDaemon
from novaadapt_core.agent_gateway.delivery import DeliveryManager
from novaadapt_core.agent_gateway.guards import assert_no_llm_env
from novaadapt_core.agent_gateway.job_queue import GatewayJobQueue
from novaadapt_core.agent_gateway.router import GatewayRouter
from novaadapt_core.agent_gateway.worker import GatewayWorker
from novaadapt_core.channels.base import ChannelMessage


class _StubConnector:
    def __init__(self, name: str, inbound: list[dict] | None = None):
        self.name = name
        self._inbound = list(inbound or [])
        self.sent: list[dict] = []

    def listen(self):
        while self._inbound:
            row = self._inbound.pop(0)
            yield _StubInbound(self.name, row)

    def send(self, reply_to: dict, content: str, attachments=None):
        self.sent.append(
            {
                "reply_to": dict(reply_to or {}),
                "content": str(content),
                "attachments": list(attachments or []),
            }
        )

    def health(self):
        return {"ok": True, "channel": self.name, "enabled": True}


class _StubInbound:
    def __init__(self, connector: str, row: dict):
        self.connector = connector
        self.row = dict(row)

    def to_dict(self):
        return {
            "connector": self.connector,
            "sender": str(self.row.get("sender") or "user"),
            "text": str(self.row.get("text") or ""),
            "reply_to": self.row.get("reply_to") if isinstance(self.row.get("reply_to"), dict) else {},
            "metadata": self.row.get("metadata") if isinstance(self.row.get("metadata"), dict) else {},
            "message_id": str(self.row.get("message_id") or ""),
        }


class _StubChannelAdapter:
    name = "stubchannel"

    def __init__(self):
        self.sent: list[dict] = []

    def verify_inbound(self, payload: dict, *, headers: dict | None = None):
        _ = headers
        if str(payload.get("auth_token") or "") == "deny":
            return {"ok": False, "error": "unauthorized", "status_code": 401}
        return {"ok": True}

    def normalize_inbound(self, payload: dict):
        return ChannelMessage(
            channel=self.name,
            sender=str(payload.get("sender") or "stub-user"),
            text=str(payload.get("text") or ""),
            message_id=str(payload.get("id") or ""),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )

    def send_text(self, to: str, text: str, *, metadata=None):
        self.sent.append({"to": to, "text": text, "metadata": dict(metadata or {})})
        return {"ok": True}

    def health(self):
        return {"ok": True, "channel": self.name, "enabled": True}


class AgentGatewayTests(unittest.TestCase):
    def test_guard_rejects_llm_env_keys(self):
        with tempfile.TemporaryDirectory() as _tmp:
            original = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "x"
            try:
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    assert_no_llm_env()
            finally:
                if original is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = original

    def test_queue_claim_retry_and_done_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = GatewayJobQueue(Path(tmp) / "gateway_jobs.db")
            job_id = queue.enqueue(
                {"objective": "patrol"},
                workspace_id="alpha",
                profile_name="developer",
                reply_to={"connector": "cli", "to": "operator"},
            )
            claimed = queue.claim_next()
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.job_id, job_id)
            self.assertEqual(claimed.status, "running")
            retry_status = queue.mark_failed(job_id, retry_delay_seconds=1.0, max_attempts=3)
            self.assertEqual(retry_status, "retry_wait")
            queued = queue.get_job(job_id)
            self.assertIsNotNone(queued)
            assert queued is not None
            self.assertEqual(queued.status, "retry_wait")
            next_claim = queue.claim_next()
            self.assertIsNone(next_claim)
            queue.mark_done(job_id)
            done = queue.get_job(job_id)
            self.assertIsNotNone(done)
            assert done is not None
            self.assertEqual(done.status, "done")

    def test_delivery_manager_marks_sent_and_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = GatewayJobQueue(Path(tmp) / "gateway_jobs.db")
            job_id = queue.enqueue({"objective": "reply"})
            ok_connector = _StubConnector("cli")
            resolver = lambda name: ok_connector if name == "cli" else None
            delivery = DeliveryManager(queue=queue, connector_resolver=resolver)
            delivery.register_reply_target(job_id=job_id, connector="cli", address="operator")
            delivery.register_reply_target(job_id=job_id, connector="missing", address="void")
            report = delivery.deliver(job_id=job_id, content="done")
            self.assertEqual(report["attempted"], 2)
            self.assertEqual(report["sent"], 1)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(len(ok_connector.sent), 1)

    def test_daemon_drains_connector_processes_and_delivers(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = GatewayJobQueue(Path(tmp) / "gateway_jobs.db")
            outbound = _StubConnector("cli")
            inbound = _StubConnector(
                "cli",
                inbound=[
                    {
                        "sender": "operator",
                        "text": "scan area",
                        "reply_to": {"connector": "cli", "to": "operator"},
                        "metadata": {"workspace_id": "ops", "profile_name": "developer"},
                        "message_id": "m1",
                    }
                ],
            )

            def resolver(name: str):
                if name == "cli":
                    return outbound
                return None

            worker = GatewayWorker(
                queue=queue,
                runner=lambda job: {"ok": True, "output_text": f"executed:{job.payload.get('objective', '')}"},
            )
            daemon = NovaAgentDaemon(
                worker=worker,
                delivery=DeliveryManager(queue=queue, connector_resolver=resolver),
                router=GatewayRouter(),
                connectors={"cli": inbound},
            )
            outcome = daemon.run_once()
            self.assertTrue(outcome.processed)
            self.assertEqual(len(outbound.sent), 1)
            self.assertIn("executed:scan area", outbound.sent[0]["content"])

    def test_gateway_never_imports_model_router(self):
        gateway_modules = [
            "novaadapt_core.agent_gateway.daemon",
            "novaadapt_core.agent_gateway.job_queue",
            "novaadapt_core.agent_gateway.worker",
            "novaadapt_core.agent_gateway.router",
            "novaadapt_core.agent_gateway.delivery",
        ]
        for mod_name in gateway_modules:
            mod = importlib.import_module(mod_name)
            source = inspect.getsource(mod)
            self.assertNotIn("ModelRouter", source)
            self.assertNotIn("model_router", source)

    def test_build_gateway_connectors_includes_common_channels_and_wearables(self):
        connectors = build_gateway_connectors()
        expected = {
            "http",
            "mcp",
            "cli",
            "webchat",
            "imessage",
            "whatsapp",
            "telegram",
            "discord",
            "slack",
            "signal",
            "teams",
            "googlechat",
            "matrix",
            "xreal",
            "halo",
        }
        self.assertTrue(expected.issubset(set(connectors.keys())))

    def test_channel_adapter_connector_normalizes_and_routes_reply_target(self):
        adapter = _StubChannelAdapter()
        connector = ChannelAdapterConnector(adapter, target_metadata_keys=["chat_id"], fallback_to_sender=True)
        auth = connector.push_inbound(
            {
                "sender": "user-a",
                "text": "hello",
                "id": "m1",
                "metadata": {"chat_id": "chat-1"},
            }
        )
        self.assertTrue(auth["ok"])
        messages = list(connector.listen())
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].reply_to["to"], "chat-1")
        connector.send({"to": "chat-1"}, "ack")
        self.assertEqual(adapter.sent[0]["to"], "chat-1")
        self.assertEqual(adapter.sent[0]["text"], "ack")

    def test_channel_adapter_connector_rejects_unauthorized_payload(self):
        connector = ChannelAdapterConnector(_StubChannelAdapter(), target_metadata_keys=[], fallback_to_sender=True)
        auth = connector.push_inbound({"auth_token": "deny", "sender": "user-a", "text": "hello"})
        self.assertFalse(auth["ok"])
        self.assertEqual(list(connector.listen()), [])

    def test_xreal_connector_pushes_intent_with_x1_metadata(self):
        connector = XRealConnector()
        connector.push_intent(
            sender="xreal-user",
            transcript="open Aetherion map",
            source="xreal_x1",
            device_model="xreal-x1",
            display_mode="air_cast",
            hand_tracking=True,
        )
        rows = list(connector.listen())
        self.assertEqual(len(rows), 1)
        msg = rows[0]
        self.assertEqual(msg.connector, "xreal")
        self.assertEqual(msg.sender, "xreal-user")
        self.assertEqual(msg.metadata.get("device_model"), "xreal-x1")
        self.assertEqual(msg.metadata.get("display_mode"), "air_cast")
        self.assertTrue(msg.metadata.get("hand_tracking"))


if __name__ == "__main__":
    unittest.main()

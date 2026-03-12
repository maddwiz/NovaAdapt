from __future__ import annotations

import json
import os
from concurrent import futures
from typing import Any

from .native_executor import NativeDesktopExecutor


_GRPC_SERVICE_NAME = "novaadapt.runtime.NativeExecutor"
_EXECUTE_RPC_PATH = f"/{_GRPC_SERVICE_NAME}/Execute"
_HEALTH_RPC_PATH = f"/{_GRPC_SERVICE_NAME}/Health"


def _require_grpc():
    try:
        import grpc  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in callers without grpcio
        raise RuntimeError(
            "gRPC support requires 'grpcio'. Install with 'pip install -e \".[grpc]\"' or 'pip install grpcio'."
        ) from exc
    return grpc


def _json_request_deserializer(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    decoded = json.loads(raw.decode("utf-8"))
    if isinstance(decoded, dict):
        return decoded
    raise ValueError("gRPC payload must decode to a JSON object")


def _json_response_serializer(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class NativeExecutionGRPCServer:
    """Optional DirectShell-compatible gRPC endpoint backed by NativeDesktopExecutor.

    The service intentionally uses generic JSON request/response payloads so NovaAdapt
    can ship a gRPC backend without requiring generated protobuf code in the default
    runtime path. Method contracts:

    - Execute: {"action": {...}} -> {"status": "ok|failed", "output": "..."}
    - Health: {} -> {"ok": true, "transport": "grpc", "capabilities": [...]}
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8767,
        grpc_token: str | None = None,
        timeout_seconds: int = 30,
        max_workers: int = 8,
        executor: NativeDesktopExecutor | None = None,
    ) -> None:
        raw_token = os.getenv("DIRECTSHELL_GRPC_TOKEN", "") if grpc_token is None else str(grpc_token)
        self.grpc_token = raw_token.strip() or None
        self.host = str(host or "127.0.0.1")
        self.port = max(0, int(port))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_workers = max(1, int(max_workers))
        self.executor = executor or NativeDesktopExecutor(timeout_seconds=self.timeout_seconds)
        self._server = None
        self._pool: futures.ThreadPoolExecutor | None = None
        self._grpc = None

    def bind(self) -> int:
        grpc = _require_grpc()
        server = self._server
        if server is None:
            pool = futures.ThreadPoolExecutor(max_workers=self.max_workers)
            server = grpc.server(pool)
            handler = grpc.method_handlers_generic_handler(
                _GRPC_SERVICE_NAME,
                {
                    "Execute": grpc.unary_unary_rpc_method_handler(
                        self._handle_execute,
                        request_deserializer=_json_request_deserializer,
                        response_serializer=_json_response_serializer,
                    ),
                    "Health": grpc.unary_unary_rpc_method_handler(
                        self._handle_health,
                        request_deserializer=_json_request_deserializer,
                        response_serializer=_json_response_serializer,
                    ),
                },
            )
            server.add_generic_rpc_handlers((handler,))
            bound_port = server.add_insecure_port(f"{self.host}:{self.port}")
            if bound_port <= 0:
                pool.shutdown(wait=False, cancel_futures=True)
                raise RuntimeError(f"failed to bind native gRPC runtime on {self.host}:{self.port}")
            self.port = int(bound_port)
            self._server = server
            self._pool = pool
            self._grpc = grpc
        return int(self.port)

    def start(self) -> int:
        self.bind()
        server = self._server
        if server is None:
            raise RuntimeError("native gRPC server failed to initialize")
        server.start()
        return int(self.port)

    def serve_forever(self) -> None:
        self.start()
        server = self._server
        if server is None:
            raise RuntimeError("native gRPC server failed to initialize")
        try:
            server.wait_for_termination()
        finally:
            self.shutdown()

    def shutdown(self, grace_seconds: float = 1.0) -> None:
        server = self._server
        pool = self._pool
        self._server = None
        self._pool = None
        if server is not None:
            stop_future = server.stop(max(0.0, float(grace_seconds)))
            if stop_future is not None:
                stop_future.wait(timeout=max(1.0, float(grace_seconds) + 2.0))
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    def _authorized(self, context) -> bool:
        expected_token = self.grpc_token
        if not expected_token:
            return True
        metadata = {str(k).lower(): str(v) for k, v in context.invocation_metadata()}
        if metadata.get("x-directshell-token", "") == expected_token:
            return True
        self._grpc_status(context, "UNAUTHENTICATED", "unauthorized")
        return False

    def _grpc_status(self, context, status_name: str, detail: str) -> None:
        grpc = self._grpc or _require_grpc()
        code = getattr(grpc.StatusCode, status_name)
        context.set_code(code)
        context.set_details(detail)

    def _handle_execute(self, payload: dict[str, Any], context) -> dict[str, Any]:
        if not self._authorized(context):
            return {"status": "failed", "output": "unauthorized"}
        action = payload.get("action") if isinstance(payload, dict) else None
        if not isinstance(action, dict):
            self._grpc_status(context, "INVALID_ARGUMENT", "payload must include object field 'action'")
            return {"status": "failed", "output": "payload must include object field 'action'"}
        result = self.executor.execute_action(action)
        return {"status": str(result.status), "output": str(result.output)}

    def _handle_health(self, payload: dict[str, Any], context) -> dict[str, Any]:
        if not self._authorized(context):
            return {"ok": False, "error": "unauthorized", "transport": "grpc"}
        deep = bool(payload.get("deep", True)) if isinstance(payload, dict) else True
        out: dict[str, Any] = {
            "ok": True,
            "service": "novaadapt-native-grpc",
            "transport": "grpc",
            "host": self.host,
            "port": int(self.port),
        }
        if deep:
            out["capabilities"] = self.executor.capabilities()
        return out


__all__ = [
    "NativeExecutionGRPCServer",
    "_EXECUTE_RPC_PATH",
    "_GRPC_SERVICE_NAME",
    "_HEALTH_RPC_PATH",
]

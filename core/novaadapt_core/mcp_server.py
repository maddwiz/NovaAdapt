from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from .service import NovaAdaptService


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]


class NovaAdaptMCPServer:
    """Minimal JSON-RPC MCP-compatible server over stdio."""

    def __init__(self, service: NovaAdaptService) -> None:
        self.service = service
        self._tools = [
            MCPTool(
                name="novaadapt_run",
                description="Run objective through NovaAdapt core",
                input_schema={
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "strategy": {"type": "string", "enum": ["single", "vote"]},
                        "model": {"type": "string"},
                        "candidates": {"type": "array", "items": {"type": "string"}},
                        "fallbacks": {"type": "array", "items": {"type": "string"}},
                        "execute": {"type": "boolean"},
                        "allow_dangerous": {"type": "boolean"},
                        "max_actions": {"type": "integer"},
                    },
                    "required": ["objective"],
                },
            ),
            MCPTool(
                name="novaadapt_models",
                description="List available model endpoints",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_check",
                description="Check model endpoint health",
                input_schema={
                    "type": "object",
                    "properties": {
                        "models": {"type": "array", "items": {"type": "string"}},
                        "probe": {"type": "string"},
                    },
                },
            ),
            MCPTool(
                name="novaadapt_history",
                description="Get recent action history",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            ),
            MCPTool(
                name="novaadapt_plan_create",
                description="Create a pending approval plan from objective",
                input_schema={
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string"},
                        "strategy": {"type": "string", "enum": ["single", "vote"]},
                        "model": {"type": "string"},
                        "candidates": {"type": "array", "items": {"type": "string"}},
                        "fallbacks": {"type": "array", "items": {"type": "string"}},
                        "max_actions": {"type": "integer"},
                    },
                    "required": ["objective"],
                },
            ),
            MCPTool(
                name="novaadapt_plans",
                description="List recent approval plans",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            ),
            MCPTool(
                name="novaadapt_plan_get",
                description="Fetch approval plan by id",
                input_schema={
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            ),
            MCPTool(
                name="novaadapt_plan_approve",
                description="Approve plan and optionally execute",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "execute": {"type": "boolean"},
                        "allow_dangerous": {"type": "boolean"},
                        "max_actions": {"type": "integer"},
                    },
                    "required": ["id"],
                },
            ),
            MCPTool(
                name="novaadapt_plan_reject",
                description="Reject plan with optional reason",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id"],
                },
            ),
        ]

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            if method in {"initialize", "mcp.initialize"}:
                return self._ok(
                    req_id,
                    {
                        "serverInfo": {"name": "NovaAdapt MCP", "version": "0.1.0"},
                        "capabilities": {"tools": {}},
                    },
                )

            if method in {"tools/list", "mcp.tools/list"}:
                return self._ok(req_id, {"tools": [self._tool_to_dict(tool) for tool in self._tools]})

            if method in {"tools/call", "mcp.tools/call"}:
                tool_name = params.get("name")
                arguments = params.get("arguments") or {}
                result = self._call_tool(tool_name=tool_name, arguments=arguments)
                return self._ok(req_id, {"content": [{"type": "json", "json": result}]})

            return self._err(req_id, code=-32601, message=f"Method not found: {method}")
        except Exception as exc:
            return self._err(req_id, code=-32000, message=str(exc))

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                response = self._err(None, code=-32700, message="Parse error")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            if not isinstance(request, dict):
                response = self._err(None, code=-32600, message="Invalid Request")
            else:
                response = self.handle_request(request)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "novaadapt_run":
            return self.service.run(arguments)
        if tool_name == "novaadapt_models":
            return self.service.models()
        if tool_name == "novaadapt_check":
            models = arguments.get("models")
            probe = arguments.get("probe", "Reply with: OK")
            if isinstance(models, list):
                models = [str(item) for item in models]
            else:
                models = None
            return self.service.check(model_names=models, probe_prompt=str(probe))
        if tool_name == "novaadapt_history":
            limit = int(arguments.get("limit", 20))
            return self.service.history(limit=limit)
        if tool_name == "novaadapt_plan_create":
            return self.service.create_plan(arguments)
        if tool_name == "novaadapt_plans":
            limit = int(arguments.get("limit", 50))
            return self.service.list_plans(limit=limit)
        if tool_name == "novaadapt_plan_get":
            plan_id = str(arguments.get("id", "")).strip()
            if not plan_id:
                raise ValueError("'id' is required")
            item = self.service.get_plan(plan_id)
            if item is None:
                raise ValueError("Plan not found")
            return item
        if tool_name == "novaadapt_plan_approve":
            plan_id = str(arguments.get("id", "")).strip()
            if not plan_id:
                raise ValueError("'id' is required")
            payload = {
                "execute": bool(arguments.get("execute", True)),
                "allow_dangerous": bool(arguments.get("allow_dangerous", False)),
                "max_actions": int(arguments.get("max_actions", 25)),
            }
            return self.service.approve_plan(plan_id, payload)
        if tool_name == "novaadapt_plan_reject":
            plan_id = str(arguments.get("id", "")).strip()
            if not plan_id:
                raise ValueError("'id' is required")
            reason = arguments.get("reason")
            return self.service.reject_plan(plan_id, reason=str(reason) if reason is not None else None)
        raise ValueError(f"Unknown tool: {tool_name}")

    @staticmethod
    def _tool_to_dict(tool: MCPTool) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
        }

    @staticmethod
    def _ok(req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

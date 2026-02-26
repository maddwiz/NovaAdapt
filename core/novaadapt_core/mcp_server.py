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
                        "adapt_id": {"type": "string"},
                        "player_id": {"type": "string"},
                        "realm": {"type": "string"},
                        "activity": {"type": "string"},
                        "post_realm": {"type": "string"},
                        "post_activity": {"type": "string"},
                    },
                    "required": ["objective"],
                },
            ),
            MCPTool(
                name="novaadapt_swarm_run",
                description="Queue multiple objectives as parallel NovaAdapt async jobs",
                input_schema={
                    "type": "object",
                    "properties": {
                        "objectives": {"type": "array", "items": {"type": "string"}},
                        "strategy": {"type": "string", "enum": ["single", "vote"]},
                        "model": {"type": "string"},
                        "candidates": {"type": "array", "items": {"type": "string"}},
                        "fallbacks": {"type": "array", "items": {"type": "string"}},
                        "execute": {"type": "boolean"},
                        "allow_dangerous": {"type": "boolean"},
                        "max_actions": {"type": "integer"},
                        "max_agents": {"type": "integer"},
                        "adapt_id": {"type": "string"},
                        "player_id": {"type": "string"},
                        "realm": {"type": "string"},
                        "activity": {"type": "string"},
                        "post_realm": {"type": "string"},
                        "post_activity": {"type": "string"},
                    },
                    "required": ["objectives"],
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
                name="novaadapt_plugins",
                description="List first-party plugin targets",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_plugin_health",
                description="Check plugin target health",
                input_schema={
                    "type": "object",
                    "properties": {"plugin": {"type": "string"}},
                    "required": ["plugin"],
                },
            ),
            MCPTool(
                name="novaadapt_plugin_call",
                description="Call plugin route via NovaAdapt plugin adapter",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin": {"type": "string"},
                        "route": {"type": "string"},
                        "method": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                    "required": ["plugin", "route"],
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
                name="novaadapt_events",
                description="List recent audit events",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "category": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "entity_id": {"type": "string"},
                        "since_id": {"type": "integer"},
                    },
                },
            ),
            MCPTool(
                name="novaadapt_events_wait",
                description="Wait for new audit events and return when available or timeout",
                input_schema={
                    "type": "object",
                    "properties": {
                        "timeout_seconds": {"type": "number"},
                        "interval_seconds": {"type": "number"},
                        "limit": {"type": "integer"},
                        "category": {"type": "string"},
                        "entity_type": {"type": "string"},
                        "entity_id": {"type": "string"},
                        "since_id": {"type": "integer"},
                    },
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
            MCPTool(
                name="novaadapt_plan_undo",
                description="Undo executed plan actions in reverse order",
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "execute": {"type": "boolean"},
                        "mark_only": {"type": "boolean"},
                    },
                    "required": ["id"],
                },
            ),
            MCPTool(
                name="novaadapt_feedback",
                description="Record operator rating/feedback for self-improvement memory",
                input_schema={
                    "type": "object",
                    "properties": {
                        "rating": {"type": "integer", "minimum": 1, "maximum": 10},
                        "objective": {"type": "string"},
                        "notes": {"type": "string"},
                        "metadata": {"type": "object"},
                        "context": {"type": "object"},
                    },
                    "required": ["rating"],
                },
            ),
            MCPTool(
                name="novaadapt_memory_status",
                description="Get NovaSpine memory backend readiness/status",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_novaprime_status",
                description="Get NovaPrime integration backend readiness/status",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_memory_recall",
                description="Recall relevant long-term memory entries",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "minimum": 1},
                    },
                    "required": ["query"],
                },
            ),
            MCPTool(
                name="novaadapt_memory_ingest",
                description="Ingest text into long-term memory backend",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "source_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_status",
                description="Get browser automation runtime status/capabilities",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_browser_pages",
                description="List active browser pages and current selection",
                input_schema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="novaadapt_browser_action",
                description="Execute a raw browser automation action payload",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "object"},
                    },
                    "required": ["action"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_navigate",
                description="Navigate browser to a URL",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "wait_until": {"type": "string"},
                        "timeout_ms": {"type": "integer"},
                    },
                    "required": ["url"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_click",
                description="Click a browser selector",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "button": {"type": "string"},
                        "force": {"type": "boolean"},
                        "timeout_ms": {"type": "integer"},
                    },
                    "required": ["selector"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_fill",
                description="Fill a browser selector with text/value",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "value": {"type": "string"},
                        "allow_sensitive_fill": {"type": "boolean"},
                        "timeout_ms": {"type": "integer"},
                    },
                    "required": ["selector", "value"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_extract_text",
                description="Extract text from selector or body",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "timeout_ms": {"type": "integer"},
                    },
                },
            ),
            MCPTool(
                name="novaadapt_browser_screenshot",
                description="Capture browser screenshot",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "full_page": {"type": "boolean"},
                    },
                },
            ),
            MCPTool(
                name="novaadapt_browser_wait_for_selector",
                description="Wait for selector state in browser",
                input_schema={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "state": {"type": "string"},
                        "timeout_ms": {"type": "integer"},
                    },
                    "required": ["selector"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_evaluate_js",
                description="Evaluate JavaScript in browser page context",
                input_schema={
                    "type": "object",
                    "properties": {
                        "script": {"type": "string"},
                        "arg": {},
                    },
                    "required": ["script"],
                },
            ),
            MCPTool(
                name="novaadapt_browser_close",
                description="Close browser automation session",
                input_schema={"type": "object", "properties": {}},
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
        if tool_name == "novaadapt_swarm_run":
            objectives = arguments.get("objectives")
            if not isinstance(objectives, list):
                raise ValueError("'objectives' is required and must be an array")
            normalized = [str(item).strip() for item in objectives if str(item).strip()]
            if not normalized:
                raise ValueError("'objectives' must contain at least one non-empty value")
            max_agents = max(1, min(32, int(arguments.get("max_agents", len(normalized)))))
            selected = normalized[:max_agents]
            jobs: list[dict[str, Any]] = []
            for idx, objective in enumerate(selected, start=1):
                run_payload = {
                    "objective": objective,
                    "strategy": str(arguments.get("strategy", "single")),
                    "model": arguments.get("model"),
                    "candidates": arguments.get("candidates"),
                    "fallbacks": arguments.get("fallbacks"),
                    "execute": bool(arguments.get("execute", False)),
                    "allow_dangerous": bool(arguments.get("allow_dangerous", False)),
                    "max_actions": int(arguments.get("max_actions", 25)),
                    "adapt_id": arguments.get("adapt_id"),
                    "player_id": arguments.get("player_id"),
                    "realm": arguments.get("realm"),
                    "activity": arguments.get("activity"),
                    "post_realm": arguments.get("post_realm"),
                    "post_activity": arguments.get("post_activity"),
                }
                jobs.append({"index": idx, "objective": objective, "result": self.service.run(run_payload)})
            return {
                "status": "completed",
                "kind": "swarm",
                "submitted_jobs": len(jobs),
                "jobs": jobs,
            }
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
        if tool_name == "novaadapt_plugins":
            return self.service.plugins()
        if tool_name == "novaadapt_plugin_health":
            plugin_name = str(arguments.get("plugin", "")).strip()
            if not plugin_name:
                raise ValueError("'plugin' is required")
            return self.service.plugin_health(plugin_name)
        if tool_name == "novaadapt_plugin_call":
            plugin_name = str(arguments.get("plugin", "")).strip()
            if not plugin_name:
                raise ValueError("'plugin' is required")
            route = str(arguments.get("route", "")).strip()
            if not route:
                raise ValueError("'route' is required")
            payload = arguments.get("payload")
            call_payload: dict[str, Any] = {
                "route": route,
                "method": str(arguments.get("method", "POST")).strip().upper(),
            }
            if payload is not None:
                if not isinstance(payload, dict):
                    raise ValueError("'payload' must be an object when provided")
                call_payload["payload"] = payload
            return self.service.plugin_call(plugin_name, call_payload)
        if tool_name == "novaadapt_history":
            limit = int(arguments.get("limit", 20))
            return self.service.history(limit=limit)
        if tool_name == "novaadapt_events":
            return self.service.events(
                limit=int(arguments.get("limit", 100)),
                category=str(arguments.get("category")).strip() if arguments.get("category") else None,
                entity_type=str(arguments.get("entity_type")).strip() if arguments.get("entity_type") else None,
                entity_id=str(arguments.get("entity_id")).strip() if arguments.get("entity_id") else None,
                since_id=int(arguments.get("since_id")) if arguments.get("since_id") is not None else None,
            )
        if tool_name == "novaadapt_events_wait":
            return self.service.events_wait(
                timeout_seconds=float(arguments.get("timeout_seconds", 30.0)),
                interval_seconds=float(arguments.get("interval_seconds", 0.25)),
                limit=int(arguments.get("limit", 100)),
                category=str(arguments.get("category")).strip() if arguments.get("category") else None,
                entity_type=str(arguments.get("entity_type")).strip() if arguments.get("entity_type") else None,
                entity_id=str(arguments.get("entity_id")).strip() if arguments.get("entity_id") else None,
                since_id=int(arguments.get("since_id")) if arguments.get("since_id") is not None else None,
            )
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
        if tool_name == "novaadapt_plan_undo":
            plan_id = str(arguments.get("id", "")).strip()
            if not plan_id:
                raise ValueError("'id' is required")
            payload = {
                "execute": bool(arguments.get("execute", False)),
                "mark_only": bool(arguments.get("mark_only", False)),
            }
            return self.service.undo_plan(plan_id, payload)
        if tool_name == "novaadapt_feedback":
            return self.service.record_feedback(
                {
                    "rating": int(arguments.get("rating")),
                    "objective": (
                        str(arguments.get("objective")).strip()
                        if arguments.get("objective") is not None
                        else None
                    ),
                    "notes": (
                        str(arguments.get("notes")).strip()
                        if arguments.get("notes") is not None
                        else None
                    ),
                    "metadata": arguments.get("metadata"),
                    "context": arguments.get("context"),
                }
            )
        if tool_name == "novaadapt_memory_status":
            return self.service.memory_status()
        if tool_name == "novaadapt_novaprime_status":
            return self.service.novaprime_status()
        if tool_name == "novaadapt_memory_recall":
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("'query' is required")
            top_k = int(arguments.get("top_k", 10))
            return self.service.memory_recall(query, top_k=max(1, min(100, top_k)))
        if tool_name == "novaadapt_memory_ingest":
            text = str(arguments.get("text", "")).strip()
            if not text:
                raise ValueError("'text' is required")
            source_id = str(arguments.get("source_id", "")).strip()
            metadata = arguments.get("metadata")
            return self.service.memory_ingest(
                text,
                source_id=source_id,
                metadata=metadata if isinstance(metadata, dict) else None,
            )
        if tool_name == "novaadapt_browser_status":
            return self.service.browser_status()
        if tool_name == "novaadapt_browser_pages":
            return self.service.browser_pages()
        if tool_name == "novaadapt_browser_action":
            action = arguments.get("action")
            if not isinstance(action, dict):
                raise ValueError("'action' is required and must be an object")
            return self.service.browser_action({"action": action})
        if tool_name == "novaadapt_browser_navigate":
            url = str(arguments.get("url", "")).strip()
            if not url:
                raise ValueError("'url' is required")
            payload: dict[str, Any] = {
                "type": "navigate",
                "target": url,
            }
            if arguments.get("wait_until") is not None:
                payload["wait_until"] = str(arguments.get("wait_until"))
            if arguments.get("timeout_ms") is not None:
                payload["timeout_ms"] = int(arguments.get("timeout_ms"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_click":
            selector = str(arguments.get("selector", "")).strip()
            if not selector:
                raise ValueError("'selector' is required")
            payload = {
                "type": "click_selector",
                "selector": selector,
                "button": str(arguments.get("button", "left")),
                "force": bool(arguments.get("force", False)),
            }
            if arguments.get("timeout_ms") is not None:
                payload["timeout_ms"] = int(arguments.get("timeout_ms"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_fill":
            selector = str(arguments.get("selector", "")).strip()
            if not selector:
                raise ValueError("'selector' is required")
            if arguments.get("value") is None:
                raise ValueError("'value' is required")
            payload = {
                "type": "fill",
                "selector": selector,
                "value": str(arguments.get("value")),
                "allow_sensitive_fill": bool(arguments.get("allow_sensitive_fill", False)),
            }
            if arguments.get("timeout_ms") is not None:
                payload["timeout_ms"] = int(arguments.get("timeout_ms"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_extract_text":
            payload: dict[str, Any] = {"type": "extract_text"}
            if arguments.get("selector") is not None:
                payload["selector"] = str(arguments.get("selector"))
            if arguments.get("timeout_ms") is not None:
                payload["timeout_ms"] = int(arguments.get("timeout_ms"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_screenshot":
            payload: dict[str, Any] = {
                "type": "screenshot",
                "full_page": bool(arguments.get("full_page", True)),
            }
            if arguments.get("path") is not None:
                payload["path"] = str(arguments.get("path"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_wait_for_selector":
            selector = str(arguments.get("selector", "")).strip()
            if not selector:
                raise ValueError("'selector' is required")
            payload = {
                "type": "wait_for_selector",
                "selector": selector,
                "state": str(arguments.get("state", "visible")),
            }
            if arguments.get("timeout_ms") is not None:
                payload["timeout_ms"] = int(arguments.get("timeout_ms"))
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_evaluate_js":
            script = str(arguments.get("script", "")).strip()
            if not script:
                raise ValueError("'script' is required")
            payload: dict[str, Any] = {
                "type": "evaluate_js",
                "script": script,
            }
            if "arg" in arguments:
                payload["arg"] = arguments.get("arg")
            return self.service.browser_action(payload)
        if tool_name == "novaadapt_browser_close":
            return self.service.browser_close()
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

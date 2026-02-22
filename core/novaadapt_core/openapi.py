from __future__ import annotations


def build_openapi_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "NovaAdapt Core API",
            "version": "0.1.0",
            "description": "Desktop orchestration API for NovaAdapt.",
        },
        "paths": {
            "/health": {
                "get": {
                    "summary": "Service health",
                    "responses": {"200": {"description": "Healthy"}},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "OpenAPI schema",
                    "responses": {"200": {"description": "Schema"}},
                }
            },
            "/models": {
                "get": {
                    "summary": "List configured model endpoints",
                    "responses": {"200": {"description": "Model list"}},
                }
            },
            "/check": {
                "post": {
                    "summary": "Probe model endpoint health",
                    "responses": {"200": {"description": "Health report"}},
                }
            },
            "/run": {
                "post": {
                    "summary": "Execute objective synchronously",
                    "responses": {"200": {"description": "Execution result"}},
                }
            },
            "/run_async": {
                "post": {
                    "summary": "Queue objective for async execution",
                    "responses": {"202": {"description": "Queued"}},
                }
            },
            "/jobs": {
                "get": {
                    "summary": "List recent async jobs",
                    "responses": {"200": {"description": "Job list"}},
                }
            },
            "/jobs/{id}": {
                "get": {
                    "summary": "Fetch async job status",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Job status"}, "404": {"description": "Not found"}},
                }
            },
            "/history": {
                "get": {
                    "summary": "Fetch action history",
                    "responses": {"200": {"description": "History entries"}},
                }
            },
            "/undo": {
                "post": {
                    "summary": "Undo an action or mark as undone",
                    "responses": {"200": {"description": "Undo result"}},
                }
            },
            "/metrics": {
                "get": {
                    "summary": "Prometheus metrics",
                    "responses": {"200": {"description": "Metrics text"}},
                }
            },
        },
    }

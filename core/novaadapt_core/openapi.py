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
            "/dashboard": {
                "get": {
                    "summary": "Operational dashboard HTML",
                    "responses": {"200": {"description": "Dashboard"}},
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
            "/jobs/{id}/stream": {
                "get": {
                    "summary": "Stream async job status updates as SSE",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "timeout",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "number"},
                        },
                        {
                            "name": "interval",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "number"},
                        },
                    ],
                    "responses": {"200": {"description": "SSE stream"}, "404": {"description": "Not found"}},
                }
            },
            "/jobs/{id}/cancel": {
                "post": {
                    "summary": "Request cancellation for queued/running async job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Cancellation status"}, "404": {"description": "Not found"}},
                }
            },
            "/plans": {
                "get": {
                    "summary": "List recent approval plans",
                    "responses": {"200": {"description": "Plan list"}},
                },
                "post": {
                    "summary": "Create a pending plan from objective",
                    "responses": {"201": {"description": "Plan created"}},
                },
            },
            "/plans/{id}": {
                "get": {
                    "summary": "Fetch plan status/details",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Plan"}, "404": {"description": "Not found"}},
                }
            },
            "/plans/{id}/approve": {
                "post": {
                    "summary": "Approve plan and optionally execute actions",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Approved plan"}, "404": {"description": "Not found"}},
                }
            },
            "/plans/{id}/reject": {
                "post": {
                    "summary": "Reject plan with optional reason",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Rejected plan"}, "404": {"description": "Not found"}},
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

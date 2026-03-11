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
                    "parameters": [
                        {
                            "name": "deep",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "enum": [0, 1]},
                            "description": "Set to 1 for readiness checks (models + stores + metrics).",
                        }
                    ],
                    "responses": {
                        "200": {"description": "Healthy"},
                        "503": {"description": "Unhealthy readiness check"},
                    },
                }
            },
            "/dashboard": {
                "get": {
                    "summary": "Operational dashboard HTML",
                    "responses": {"200": {"description": "Dashboard"}},
                }
            },
            "/dashboard/canvas-workflows": {
                "get": {
                    "summary": "Optional Canvas + Workflows inspector dashboard HTML",
                    "responses": {"200": {"description": "Canvas/workflows dashboard"}, "404": {"description": "Disabled"}},
                }
            },
            "/dashboard/data": {
                "get": {
                    "summary": "Dashboard JSON data (health/metrics/jobs/plans)",
                    "responses": {"200": {"description": "Dashboard data"}},
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
            "/plugins": {
                "get": {
                    "summary": "List first-party plugin targets",
                    "responses": {"200": {"description": "Plugin targets"}},
                }
            },
            "/plugins/{name}/health": {
                "get": {
                    "summary": "Probe a plugin target health endpoint",
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Plugin health"}, "404": {"description": "Not found"}},
                }
            },
            "/plugins/{name}/call": {
                "post": {
                    "summary": "Call a plugin route through the configured adapter",
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Plugin response"}, "404": {"description": "Not found"}},
                }
            },
            "/channels": {
                "get": {
                    "summary": "List configured messaging channel adapters",
                    "responses": {"200": {"description": "Channel adapter list"}},
                }
            },
            "/channels/{name}/health": {
                "get": {
                    "summary": "Get channel adapter health/configuration",
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Channel health"}, "404": {"description": "Not found"}},
                }
            },
            "/channels/{name}/send": {
                "post": {
                    "summary": "Send outbound message through a channel adapter",
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Channel send response"}, "404": {"description": "Not found"}},
                }
            },
            "/channels/{name}/inbound": {
                "post": {
                    "summary": "Normalize and ingest inbound channel payload (optional auth_token)",
                    "parameters": [
                        {
                            "name": "name",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Inbound message normalized"},
                        "401": {"description": "Inbound payload authentication failed"},
                        "404": {"description": "Not found"},
                    },
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
            "/swarm/run": {
                "post": {
                    "summary": "Queue multiple objectives as parallel async jobs",
                    "responses": {"202": {"description": "Swarm queued"}},
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
            "/plans/{id}/stream": {
                "get": {
                    "summary": "Stream plan status updates as SSE",
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
            "/plans/{id}/approve_async": {
                "post": {
                    "summary": "Queue plan approval/execution as async job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"202": {"description": "Approval queued"}, "404": {"description": "Not found"}},
                }
            },
            "/plans/{id}/retry_failed": {
                "post": {
                    "summary": "Retry only previously failed/blocked plan actions",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Retried plan"}, "404": {"description": "Not found"}},
                }
            },
            "/plans/{id}/retry_failed_async": {
                "post": {
                    "summary": "Queue retry for failed/blocked plan actions as async job",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"202": {"description": "Retry queued"}, "404": {"description": "Not found"}},
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
            "/plans/{id}/undo": {
                "post": {
                    "summary": "Undo executed plan actions in reverse order",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Undo results"}, "404": {"description": "Not found"}},
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
            "/feedback": {
                "post": {
                    "summary": "Record operator feedback for self-improvement memory",
                    "responses": {"200": {"description": "Feedback recorded"}},
                }
            },
            "/memory/status": {
                "get": {
                    "summary": "Get long-term memory backend readiness and configuration",
                    "responses": {"200": {"description": "Memory backend status"}},
                }
            },
            "/novaprime/status": {
                "get": {
                    "summary": "Get NovaPrime integration backend readiness and configuration",
                    "responses": {"200": {"description": "NovaPrime backend status"}},
                }
            },
            "/novaprime/reason/emotion": {
                "get": {
                    "summary": "Get NovaPrime emotion state",
                    "responses": {"200": {"description": "Emotion state response"}},
                },
                "post": {
                    "summary": "Set NovaPrime emotion state chemicals",
                    "responses": {"200": {"description": "Emotion update response"}},
                },
            },
            "/novaprime/reason/dual": {
                "post": {
                    "summary": "Run a task through NovaPrime dual-brain reasoning",
                    "responses": {"200": {"description": "Dual-brain reasoning response"}},
                }
            },
            "/novaprime/mesh/balance": {
                "get": {
                    "summary": "Get NovaPrime mesh credit balance by node_id",
                    "parameters": [
                        {
                            "name": "node_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Mesh balance response"}},
                }
            },
            "/novaprime/mesh/reputation": {
                "get": {
                    "summary": "Get NovaPrime mesh reputation by node_id",
                    "parameters": [
                        {
                            "name": "node_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Mesh reputation response"}},
                }
            },
            "/novaprime/mesh/peers": {
                "get": {
                    "summary": "List known NovaPrime mesh peers",
                    "responses": {"200": {"description": "Mesh peers response"}},
                }
            },
            "/novaprime/mesh/aetherion/state": {
                "get": {
                    "summary": "Get NovaPrime Aetherion aggregate world state",
                    "parameters": [
                        {
                            "name": "refresh",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "boolean"},
                        }
                    ],
                    "responses": {"200": {"description": "Aetherion world state response"}},
                }
            },
            "/novaprime/marketplace/listings": {
                "get": {
                    "summary": "Get NovaPrime marketplace listings",
                    "responses": {"200": {"description": "Marketplace listings response"}},
                }
            },
            "/novaprime/identity/profile": {
                "get": {
                    "summary": "Get Adapt identity profile from NovaPrime",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Identity profile response"}},
                }
            },
            "/novaprime/presence": {
                "get": {
                    "summary": "Get Adapt realm/activity presence from NovaPrime",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Presence response"}},
                }
            },
            "/novaprime/sib/imprinting/session": {
                "get": {
                    "summary": "Get NovaPrime SIB imprinting session details",
                    "parameters": [
                        {
                            "name": "session_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Imprinting session response"}},
                }
            },
            "/novaprime/narrative/bond/history": {
                "get": {
                    "summary": "Generate NovaPrime narrative bond history timeline",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "player_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "top_k",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        },
                    ],
                    "responses": {"200": {"description": "Narrative bond history response"}},
                }
            },
            "/novaprime/identity/bond": {
                "post": {
                    "summary": "Create a soulbound Adapt-player bond via NovaPrime",
                    "responses": {"200": {"description": "Bond result"}},
                }
            },
            "/novaprime/mesh/credit": {
                "post": {
                    "summary": "Credit mesh balance for a node via NovaPrime",
                    "responses": {"200": {"description": "Mesh credit response"}},
                }
            },
            "/novaprime/mesh/transfer": {
                "post": {
                    "summary": "Transfer mesh balance between nodes via NovaPrime",
                    "responses": {"200": {"description": "Mesh transfer response"}},
                }
            },
            "/novaprime/mesh/peers/register": {
                "post": {
                    "summary": "Register or update a NovaPrime mesh peer",
                    "responses": {"200": {"description": "Mesh peer registration response"}},
                }
            },
            "/novaprime/mesh/compute/request": {
                "post": {
                    "summary": "Submit a community compute burst request via NovaPrime",
                    "responses": {"200": {"description": "Compute request response"}},
                }
            },
            "/novaprime/mesh/compute/settle": {
                "post": {
                    "summary": "Settle a community compute burst request via NovaPrime",
                    "responses": {"200": {"description": "Compute settlement response"}},
                }
            },
            "/novaprime/marketplace/list": {
                "post": {
                    "summary": "List an item on NovaPrime marketplace",
                    "responses": {"200": {"description": "Marketplace list response"}},
                }
            },
            "/novaprime/marketplace/buy": {
                "post": {
                    "summary": "Buy an item from NovaPrime marketplace",
                    "responses": {"200": {"description": "Marketplace buy response"}},
                }
            },
            "/novaprime/identity/verify": {
                "post": {
                    "summary": "Verify an Adapt-player bond via NovaPrime",
                    "responses": {"200": {"description": "Bond verification"}},
                }
            },
            "/novaprime/identity/evolve": {
                "post": {
                    "summary": "Apply Adapt progression updates via NovaPrime",
                    "responses": {"200": {"description": "Identity evolution result"}},
                }
            },
            "/novaprime/presence/update": {
                "post": {
                    "summary": "Update Adapt realm/activity presence via NovaPrime",
                    "responses": {"200": {"description": "Presence update result"}},
                }
            },
            "/novaprime/resonance/score": {
                "post": {
                    "summary": "Score player resonance profile via NovaPrime",
                    "responses": {"200": {"description": "Resonance score result"}},
                }
            },
            "/novaprime/resonance/bond": {
                "post": {
                    "summary": "Run resonance bonding flow via NovaPrime",
                    "responses": {"200": {"description": "Resonance bond result"}},
                }
            },
            "/novaprime/sib/imprinting/start": {
                "post": {
                    "summary": "Start NovaPrime SIB imprinting ceremony session",
                    "responses": {"200": {"description": "Imprinting session start response"}},
                }
            },
            "/novaprime/sib/imprinting/resolve": {
                "post": {
                    "summary": "Resolve NovaPrime SIB imprinting ceremony acceptance",
                    "responses": {"200": {"description": "Imprinting resolve response"}},
                }
            },
            "/novaprime/sib/phase/evaluate": {
                "post": {
                    "summary": "Evaluate NovaPrime SIB phase transition trigger",
                    "responses": {"200": {"description": "Phase evaluation response"}},
                }
            },
            "/novaprime/sib/void/create": {
                "post": {
                    "summary": "Create NovaPrime SIB pre-form void state",
                    "responses": {"200": {"description": "Void create response"}},
                }
            },
            "/novaprime/sib/void/tick": {
                "post": {
                    "summary": "Advance NovaPrime SIB pre-form void state",
                    "responses": {"200": {"description": "Void tick response"}},
                }
            },
            "/sib/status": {
                "get": {
                    "summary": "Get SIB bridge status",
                    "responses": {"200": {"description": "SIB bridge status"}},
                }
            },
            "/sib/realm": {
                "post": {
                    "summary": "Set player realm in SIB bridge",
                    "responses": {"200": {"description": "Realm sync response"}},
                }
            },
            "/sib/companion/state": {
                "post": {
                    "summary": "Sync Adapt companion state to SIB bridge",
                    "responses": {"200": {"description": "Companion state response"}},
                }
            },
            "/sib/companion/speak": {
                "post": {
                    "summary": "Send Adapt companion speech to SIB bridge",
                    "responses": {"200": {"description": "Companion speech response"}},
                }
            },
            "/sib/phase-event": {
                "post": {
                    "summary": "Trigger SIB phase event route",
                    "responses": {"200": {"description": "Phase event response"}},
                }
            },
            "/sib/resonance/start": {
                "post": {
                    "summary": "Start SIB resonance ceremony",
                    "responses": {"200": {"description": "Resonance start response"}},
                }
            },
            "/sib/resonance/result": {
                "post": {
                    "summary": "Finalize SIB resonance result",
                    "responses": {"200": {"description": "Resonance result response"}},
                }
            },
            "/adapt/toggle": {
                "get": {
                    "summary": "Get Adapt communication toggle mode by adapt_id",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Adapt toggle state"}},
                },
                "post": {
                    "summary": "Set Adapt communication toggle mode",
                    "responses": {"200": {"description": "Updated Adapt toggle state"}},
                },
            },
            "/adapt/bond": {
                "get": {
                    "summary": "Get cached local bond state by adapt_id",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Adapt bond cache record"}},
                }
            },
            "/adapt/bond/verify": {
                "post": {
                    "summary": "Verify Adapt soulbond against NovaPrime with cache fallback",
                    "responses": {"200": {"description": "Bond verification result"}},
                }
            },
            "/adapt/persona": {
                "get": {
                    "summary": "Get Adapt persona context by adapt_id",
                    "parameters": [
                        {
                            "name": "adapt_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "player_id",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {"200": {"description": "Adapt persona context"}},
                }
            },
            "/voice/status": {
                "get": {
                    "summary": "Get optional voice feature status and configured backends",
                    "parameters": [
                        {
                            "name": "context",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["api", "cli"]},
                        }
                    ],
                    "responses": {"200": {"description": "Voice feature status"}},
                }
            },
            "/voice/transcribe": {
                "post": {
                    "summary": "Transcribe audio with configured optional STT backend",
                    "responses": {"200": {"description": "Transcription result"}},
                }
            },
            "/voice/synthesize": {
                "post": {
                    "summary": "Synthesize speech with configured optional TTS backend",
                    "responses": {"200": {"description": "Synthesis result"}},
                }
            },
            "/canvas/status": {
                "get": {
                    "summary": "Get optional canvas feature status",
                    "parameters": [
                        {
                            "name": "context",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["api", "cli", "mcp"]},
                        }
                    ],
                    "responses": {"200": {"description": "Canvas feature status"}},
                }
            },
            "/canvas/frames": {
                "get": {
                    "summary": "List rendered canvas frames for a session",
                    "parameters": [
                        {"name": "session_id", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                        {"name": "context", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Canvas frames"}},
                }
            },
            "/canvas/render": {
                "post": {
                    "summary": "Render and persist a canvas frame",
                    "responses": {"200": {"description": "Rendered canvas frame"}},
                }
            },
            "/workflows/status": {
                "get": {
                    "summary": "Get optional workflows feature status",
                    "parameters": [
                        {"name": "context", "in": "query", "required": False, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Workflows feature status"}},
                }
            },
            "/workflows/list": {
                "get": {
                    "summary": "List workflow records",
                    "parameters": [
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                        {"name": "status", "in": "query", "required": False, "schema": {"type": "string"}},
                        {"name": "context", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Workflow list"}},
                }
            },
            "/workflows/item": {
                "get": {
                    "summary": "Get workflow by workflow_id",
                    "parameters": [
                        {"name": "workflow_id", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "context", "in": "query", "required": False, "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "Workflow record"}},
                }
            },
            "/workflows/start": {
                "post": {
                    "summary": "Start a workflow",
                    "responses": {"200": {"description": "Started workflow"}},
                }
            },
            "/workflows/advance": {
                "post": {
                    "summary": "Advance workflow by one step",
                    "responses": {"200": {"description": "Advanced workflow"}},
                }
            },
            "/workflows/resume": {
                "post": {
                    "summary": "Resume a paused/failed workflow",
                    "responses": {"200": {"description": "Resumed workflow"}},
                }
            },
            "/memory/recall": {
                "post": {
                    "summary": "Recall memory entries relevant to a query",
                    "responses": {"200": {"description": "Memory recall results"}},
                }
            },
            "/memory/ingest": {
                "post": {
                    "summary": "Ingest text into long-term memory store",
                    "responses": {"200": {"description": "Memory ingest result"}},
                }
            },
            "/execute/vision": {
                "post": {
                    "summary": "Ground and optionally execute the next desktop action from a screenshot and goal",
                    "responses": {"200": {"description": "Vision grounding and execution result"}},
                }
            },
            "/mobile/action": {
                "post": {
                    "summary": "Execute or preview a unified Android or iOS mobile action",
                    "responses": {"200": {"description": "Mobile action result"}},
                }
            },
            "/mobile/status": {
                "get": {
                    "summary": "Get mobile executor status and platform readiness",
                    "responses": {"200": {"description": "Mobile status"}},
                }
            },
            "/iot/homeassistant/entities": {
                "get": {
                    "summary": "Discover Home Assistant entities with optional domain or prefix filters",
                    "responses": {"200": {"description": "Entity discovery results"}},
                }
            },
            "/control/artifacts": {
                "get": {
                    "summary": "List recent persisted control artifacts for vision, mobile, and IoT actions",
                    "responses": {"200": {"description": "Control artifact summaries"}},
                }
            },
            "/control/artifacts/{artifact_id}": {
                "get": {
                    "summary": "Get a persisted control artifact record",
                    "responses": {"200": {"description": "Control artifact detail"}, "404": {"description": "Not found"}},
                }
            },
            "/control/artifacts/{artifact_id}/preview": {
                "get": {
                    "summary": "Fetch the stored preview image for a control artifact when available",
                    "responses": {"200": {"description": "Artifact preview image"}, "404": {"description": "Not found"}},
                }
            },
            "/iot/homeassistant/status": {
                "get": {
                    "summary": "Get Home Assistant integration status",
                    "responses": {"200": {"description": "Home Assistant status"}},
                }
            },
            "/iot/mqtt/status": {
                "get": {
                    "summary": "Get direct MQTT broker connectivity status",
                    "responses": {"200": {"description": "MQTT status"}},
                }
            },
            "/iot/homeassistant/action": {
                "post": {
                    "summary": "Preview or execute a Home Assistant or MQTT action",
                    "responses": {"200": {"description": "IoT action result"}},
                }
            },
            "/iot/mqtt/publish": {
                "post": {
                    "summary": "Preview or publish a direct MQTT broker message",
                    "responses": {"200": {"description": "MQTT publish result"}},
                }
            },
            "/browser/status": {
                "get": {
                    "summary": "Get browser automation runtime status and capabilities",
                    "responses": {"200": {"description": "Browser runtime status"}},
                }
            },
            "/browser/pages": {
                "get": {
                    "summary": "List active browser pages and current page selection",
                    "responses": {"200": {"description": "Browser pages"}},
                }
            },
            "/browser/action": {
                "post": {
                    "summary": "Execute a raw browser action payload",
                    "responses": {"200": {"description": "Browser action result"}},
                }
            },
            "/browser/navigate": {
                "post": {
                    "summary": "Navigate browser page to URL",
                    "responses": {"200": {"description": "Navigate result"}},
                }
            },
            "/browser/click": {
                "post": {
                    "summary": "Click browser element by selector",
                    "responses": {"200": {"description": "Click result"}},
                }
            },
            "/browser/fill": {
                "post": {
                    "summary": "Fill browser input by selector",
                    "responses": {"200": {"description": "Fill result"}},
                }
            },
            "/browser/extract_text": {
                "post": {
                    "summary": "Extract text from browser page/selector",
                    "responses": {"200": {"description": "Extract result"}},
                }
            },
            "/browser/screenshot": {
                "post": {
                    "summary": "Capture browser screenshot",
                    "responses": {"200": {"description": "Screenshot result"}},
                }
            },
            "/browser/wait_for_selector": {
                "post": {
                    "summary": "Wait for selector state in browser page",
                    "responses": {"200": {"description": "Wait result"}},
                }
            },
            "/browser/evaluate_js": {
                "post": {
                    "summary": "Evaluate JavaScript in browser context",
                    "responses": {"200": {"description": "Script evaluation result"}},
                }
            },
            "/browser/close": {
                "post": {
                    "summary": "Close browser session",
                    "responses": {"200": {"description": "Browser closed"}},
                }
            },
            "/terminal/sessions": {
                "get": {
                    "summary": "List terminal sessions",
                    "responses": {"200": {"description": "Terminal sessions"}},
                },
                "post": {
                    "summary": "Start a terminal session",
                    "responses": {"201": {"description": "Session created"}},
                },
            },
            "/terminal/sessions/{id}": {
                "get": {
                    "summary": "Get terminal session metadata",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Session details"}, "404": {"description": "Not found"}},
                }
            },
            "/terminal/sessions/{id}/output": {
                "get": {
                    "summary": "Read terminal output chunks",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "since_seq",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 0},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 1},
                        },
                    ],
                    "responses": {"200": {"description": "Terminal output"}, "404": {"description": "Not found"}},
                }
            },
            "/terminal/sessions/{id}/input": {
                "post": {
                    "summary": "Write input to terminal session stdin",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Input accepted"}, "404": {"description": "Not found"}},
                }
            },
            "/terminal/sessions/{id}/close": {
                "post": {
                    "summary": "Close a terminal session",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Session closed"}, "404": {"description": "Not found"}},
                }
            },
            "/metrics": {
                "get": {
                    "summary": "Prometheus metrics",
                    "responses": {"200": {"description": "Metrics text"}},
                }
            },
            "/events": {
                "get": {
                    "summary": "List recent audit events",
                    "responses": {"200": {"description": "Audit events"}},
                }
            },
            "/events/stream": {
                "get": {
                    "summary": "Stream audit events as SSE",
                    "responses": {"200": {"description": "SSE stream"}},
                }
            },
        },
    }

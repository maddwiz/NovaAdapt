from __future__ import annotations

import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from urllib import error, request


@dataclass(frozen=True)
class ModelEndpoint:
    name: str
    model: str
    base_url: str
    provider: str = "openai-compatible"
    api_key_env: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    estimated_cost_per_call_usd: float = 0.0


@dataclass(frozen=True)
class RouterResult:
    model_name: str
    model_id: str
    content: str
    strategy: str
    votes: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    attempted_models: list[str] = field(default_factory=list)
    vote_summary: dict[str, object] = field(default_factory=dict)
    usage: dict[str, dict[str, object]] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    collaboration: dict[str, object] = field(default_factory=dict)


class ModelRouter:
    """Routes chat requests to configured model endpoints.

    Supports OpenAI-compatible APIs by default, with optional LiteLLM fallback.
    """

    def __init__(
        self,
        endpoints: list[ModelEndpoint],
        default_model: str,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout_seconds: int = 90,
        default_vote_candidates: int = 3,
        min_vote_agreement: int = 1,
        decompose_max_subtasks: int = 4,
        decompose_parallel_workers: int = 4,
        decompose_review_retries: int = 1,
        transport: Callable[[ModelEndpoint, list[dict[str, str]], float, int, int], str] | None = None,
    ) -> None:
        if not endpoints:
            raise ValueError("ModelRouter requires at least one endpoint")

        self._endpoints = {endpoint.name: endpoint for endpoint in endpoints}
        if default_model not in self._endpoints:
            raise ValueError(f"Default model '{default_model}' not found in endpoints")

        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.default_vote_candidates = max(1, int(default_vote_candidates))
        self.min_vote_agreement = max(1, int(min_vote_agreement))
        self.decompose_max_subtasks = max(1, int(decompose_max_subtasks))
        self.decompose_parallel_workers = max(1, int(decompose_parallel_workers))
        self.decompose_review_retries = max(0, int(decompose_review_retries))
        self._transport = transport

    @classmethod
    def from_config_file(cls, config_path: str | Path) -> "ModelRouter":
        path = Path(config_path)
        raw = json.loads(path.read_text())

        endpoints = [
            ModelEndpoint(
                name=item["name"],
                model=item["model"],
                base_url=item["base_url"],
                provider=item.get("provider", "openai-compatible"),
                api_key_env=item.get("api_key_env"),
                headers=item.get("headers", {}),
                estimated_cost_per_call_usd=float(item.get("estimated_cost_per_call_usd", 0.0) or 0.0),
            )
            for item in raw["models"]
        ]

        routing = raw.get("routing", {})
        return cls(
            endpoints=endpoints,
            default_model=raw["default_model"],
            temperature=float(routing.get("temperature", 0.2)),
            max_tokens=int(routing.get("max_tokens", 800)),
            timeout_seconds=int(routing.get("timeout_seconds", 90)),
            default_vote_candidates=int(routing.get("default_vote_candidates", 3)),
            min_vote_agreement=int(routing.get("min_vote_agreement", 1)),
            decompose_max_subtasks=int(routing.get("decompose_max_subtasks", 4)),
            decompose_parallel_workers=int(routing.get("decompose_parallel_workers", 4)),
            decompose_review_retries=int(routing.get("decompose_review_retries", 1)),
        )

    def list_models(self) -> list[ModelEndpoint]:
        return list(self._endpoints.values())

    def chat(
        self,
        messages: list[dict[str, str]],
        model_name: str | None = None,
        strategy: str = "single",
        candidate_models: Iterable[str] | None = None,
        fallback_models: Iterable[str] | None = None,
    ) -> RouterResult:
        if strategy not in {"single", "vote", "decompose"}:
            raise ValueError("strategy must be 'single', 'vote', or 'decompose'")

        if strategy == "single":
            return self._chat_single(
                messages=messages,
                model_name=model_name,
                fallback_models=fallback_models,
            )
        if strategy == "vote":
            return self._chat_vote(
                messages=messages,
                candidate_models=candidate_models,
            )
        return self._chat_decompose(
            messages=messages,
            model_name=model_name,
            candidate_models=candidate_models,
            fallback_models=fallback_models,
        )

    def health_check(
        self,
        model_names: Iterable[str] | None = None,
        probe_prompt: str = "Reply with: OK",
    ) -> list[dict[str, object]]:
        names = self._dedupe_names(list(model_names or self._endpoints.keys()))
        messages = [{"role": "user", "content": probe_prompt}]
        report: list[dict[str, object]] = []
        for name in names:
            endpoint = self._resolve_model(name)
            start = time.perf_counter()
            try:
                content = self._invoke(endpoint, messages)
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                report.append(
                    {
                        "name": endpoint.name,
                        "model": endpoint.model,
                        "provider": endpoint.provider,
                        "ok": True,
                        "latency_ms": elapsed_ms,
                        "preview": content[:120],
                    }
                )
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                report.append(
                    {
                        "name": endpoint.name,
                        "model": endpoint.model,
                        "provider": endpoint.provider,
                        "ok": False,
                        "latency_ms": elapsed_ms,
                        "error": str(exc),
                    }
                )
        return report

    def _resolve_model(self, model_name: str | None) -> ModelEndpoint:
        name = model_name or self.default_model
        try:
            return self._endpoints[name]
        except KeyError as exc:
            raise ValueError(f"Unknown model endpoint '{name}'") from exc

    def _chat_single(
        self,
        *,
        messages: list[dict[str, str]],
        model_name: str | None,
        fallback_models: Iterable[str] | None,
    ) -> RouterResult:
        primary_name = model_name or self.default_model
        fallback_names = list(fallback_models or [])
        ordered_names = self._dedupe_names([primary_name, *fallback_names])
        errors: dict[str, str] = {}
        endpoint = self._resolve_model(ordered_names[0])
        content = ""
        attempted: list[str] = []
        for name in ordered_names:
            endpoint = self._resolve_model(name)
            attempted.append(name)
            try:
                content = self._invoke(endpoint, messages)
                break
            except Exception as exc:
                errors[name] = str(exc)
        else:
            joined = "; ".join(f"{k}: {v}" for k, v in errors.items())
            raise RuntimeError(f"All model attempts failed: {joined}")

        return RouterResult(
            model_name=endpoint.name,
            model_id=endpoint.model,
            content=content,
            strategy="single",
            errors=errors,
            attempted_models=attempted,
            usage=self._usage_for_attempts(attempted),
            estimated_cost_usd=self._usage_total(self._usage_for_attempts(attempted)),
        )

    def _chat_vote(
        self,
        *,
        messages: list[dict[str, str]],
        candidate_models: Iterable[str] | None,
    ) -> RouterResult:
        names = self._dedupe_names(list(candidate_models or self._default_vote_models()))
        if not names:
            raise ValueError("candidate_models must not be empty when strategy='vote'")
        if self.min_vote_agreement > len(names):
            raise ValueError(
                f"min_vote_agreement={self.min_vote_agreement} exceeds vote candidates={len(names)}"
            )

        endpoints = [self._resolve_model(name) for name in names]
        votes: dict[str, str] = {}
        outputs: list[str] = []
        errors: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=min(4, len(endpoints))) as executor:
            futures = {
                executor.submit(self._invoke, endpoint, messages): endpoint for endpoint in endpoints
            }
            for future in as_completed(futures):
                endpoint = futures[future]
                try:
                    value = future.result()
                    votes[endpoint.name] = value
                    outputs.append(value)
                except Exception as exc:
                    errors[endpoint.name] = str(exc)

        if not outputs:
            joined = "; ".join(f"{k}: {v}" for k, v in errors.items())
            raise RuntimeError(f"All vote candidates failed: {joined}")

        chosen, winner_count = self._majority_vote(outputs)
        if winner_count < self.min_vote_agreement:
            raise RuntimeError(
                f"Vote quorum not met: winner_votes={winner_count}, required_votes={self.min_vote_agreement}"
            )
        winner = next(
            (
                name
                for name in names
                if name in votes and self._normalize(votes[name]) == self._normalize(chosen)
            ),
            names[0],
        )

        return RouterResult(
            model_name=winner,
            model_id=self._endpoints[winner].model,
            content=chosen,
            strategy="vote",
            votes=votes,
            errors=errors,
            attempted_models=names,
            vote_summary={
                "winner_votes": winner_count,
                "required_votes": self.min_vote_agreement,
                "total_votes": len(outputs),
                "quorum_met": True,
            },
            usage=self._usage_for_attempts(names),
            estimated_cost_usd=self._usage_total(self._usage_for_attempts(names)),
        )

    def _chat_decompose(
        self,
        *,
        messages: list[dict[str, str]],
        model_name: str | None,
        candidate_models: Iterable[str] | None,
        fallback_models: Iterable[str] | None,
    ) -> RouterResult:
        planner_name = model_name or self.default_model
        planner_endpoint = self._resolve_model(planner_name)
        execution_pool = self._dedupe_names(list(candidate_models or self._endpoints.keys()))
        if not execution_pool:
            execution_pool = [planner_name]
        objective = self._extract_user_objective(messages)

        planner_messages = [
            {
                "role": "system",
                "content": (
                    "Build a concise JSON plan for decomposed execution. "
                    "Return JSON only using schema: "
                    "{\"subtasks\":[{\"id\":\"s1\",\"objective\":\"...\",\"model\":\"optional-model-name\","
                    "\"agent\":\"optional-agent-role\",\"depends_on\":[\"optional-subtask-id\"],"
                    "\"review_with\":\"optional-reviewer-model\"}]}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Primary objective:\n{objective}\n\n"
                    f"Available models: {', '.join(execution_pool)}\n"
                    f"Return at most {self.decompose_max_subtasks} subtasks."
                ),
            },
        ]

        attempted_models: list[str] = [planner_name]
        errors: dict[str, str] = {}
        usage: dict[str, dict[str, object]] = self._usage_for_attempts([planner_name])
        collaboration: dict[str, object] = {
            "mode": "decompose",
            "planner_model": planner_name,
            "transcript": [],
            "agents": [],
            "parallel_batches": [],
        }

        def _fallback(reason: str, planner_error: str, *, subtasks_total: int, subtasks_succeeded: int) -> RouterResult:
            errors["decompose.planner"] = planner_error
            try:
                fallback = self._chat_single(
                    messages=messages,
                    model_name=planner_name,
                    fallback_models=fallback_models,
                )
            except Exception as exc:
                errors["decompose.fallback"] = str(exc)
                joined = "; ".join(f"{k}: {v}" for k, v in errors.items())
                raise RuntimeError(f"decompose fallback failed: {joined}") from exc
            return RouterResult(
                model_name=fallback.model_name,
                model_id=fallback.model_id,
                content=fallback.content,
                strategy="decompose",
                errors={**fallback.errors, **errors},
                attempted_models=self._dedupe_names([*attempted_models, *fallback.attempted_models]),
                vote_summary={
                    "fallback": "single",
                    "reason": reason,
                    "subtasks_total": subtasks_total,
                    "subtasks_succeeded": subtasks_succeeded,
                    "subtasks_failed": max(0, subtasks_total - subtasks_succeeded),
                },
                usage=self._merge_usage(usage, fallback.usage),
                estimated_cost_usd=self._usage_total(self._merge_usage(usage, fallback.usage)),
                collaboration=collaboration,
            )

        try:
            raw_plan = self._invoke(planner_endpoint, planner_messages)
            subtasks = self._parse_subtasks(raw_plan, max_items=self.decompose_max_subtasks)
        except Exception as exc:
            return _fallback("planner_failed", str(exc), subtasks_total=0, subtasks_succeeded=0)

        if not subtasks:
            return _fallback(
                "invalid_plan",
                "planner returned no usable subtasks",
                subtasks_total=0,
                subtasks_succeeded=0,
            )

        collaboration["subtasks"] = [dict(item) for item in subtasks]
        agent_roles = []
        for item in subtasks:
            role = str(item.get("agent") or item.get("model") or "agent").strip()
            if role and role not in agent_roles:
                agent_roles.append(role)
        collaboration["agents"] = agent_roles

        subtask_outputs: list[dict[str, str]] = []
        subtask_votes: dict[str, str] = {}
        completed_outputs: dict[str, dict[str, str]] = {}
        pending: list[dict[str, object]] = [dict(item) for item in subtasks]
        processed: set[str] = set()

        while pending:
            ready = []
            for item in pending:
                deps = [str(dep).strip() for dep in item.get("depends_on", []) if str(dep).strip()]
                if all(dep in completed_outputs for dep in deps):
                    ready.append(item)
            if not ready:
                unresolved = [str(item.get("id") or "").strip() for item in pending]
                return _fallback(
                    "invalid_plan",
                    f"planner returned unresolved dependency cycle: {', '.join(unresolved)}",
                    subtasks_total=len(subtasks),
                    subtasks_succeeded=len(subtask_outputs),
                )

            batch = ready[: self.decompose_parallel_workers]
            collaboration["parallel_batches"].append([str(item.get("id") or "") for item in batch])

            with ThreadPoolExecutor(max_workers=min(self.decompose_parallel_workers, len(batch))) as executor:
                futures = {
                    executor.submit(
                        self._execute_decompose_subtask,
                        objective=objective,
                        subtask=subtask,
                        execution_pool=execution_pool,
                        fallback_models=fallback_models,
                        completed_outputs=completed_outputs,
                    ): subtask
                    for subtask in batch
                }
                for future in as_completed(futures):
                    subtask = futures[future]
                    subtask_id = str(subtask.get("id") or "").strip() or f"s{len(processed) + 1}"
                    try:
                        outcome = future.result()
                        attempted_models.extend(outcome["attempted_models"])
                        usage = self._merge_usage(usage, outcome["usage"])
                        for key, value in outcome["errors"].items():
                            errors[f"decompose.{subtask_id}.{key}"] = value
                        subtask_votes[subtask_id] = outcome["output"]
                        output_item = {
                            "id": subtask_id,
                            "objective": str(outcome["objective"]),
                            "model": str(outcome["model"]),
                            "agent": str(outcome.get("agent") or ""),
                            "depends_on": list(outcome.get("depends_on", [])),
                            "output": str(outcome["output"]),
                        }
                        subtask_outputs.append(output_item)
                        completed_outputs[subtask_id] = output_item
                        transcript = outcome.get("transcript")
                        if isinstance(transcript, list):
                            collaboration["transcript"].extend(transcript)
                    except Exception as exc:
                        errors[f"decompose.{subtask_id}"] = str(exc)
                        collaboration["transcript"].append(
                            {
                                "type": "subtask_failed",
                                "subtask_id": subtask_id,
                                "error": str(exc),
                            }
                        )
                    processed.add(subtask_id)
            pending = [item for item in pending if str(item.get("id") or "").strip() not in processed]

        if not subtask_outputs:
            return _fallback(
                "subtasks_failed",
                "all subtasks failed",
                subtasks_total=len(subtasks),
                subtasks_succeeded=0,
            )

        synthesis_messages = [
            {
                "role": "system",
                "content": "Synthesize final answer from subtask outputs. Keep it clear and complete.",
            },
            {
                "role": "user",
                "content": (
                    f"Primary objective:\n{objective}\n\n"
                    "Subtask outputs (JSON):\n"
                    f"{json.dumps(subtask_outputs, ensure_ascii=True)}"
                ),
            },
        ]
        synthesis = self._chat_single(
            messages=synthesis_messages,
            model_name=planner_name,
            fallback_models=fallback_models,
        )
        attempted_models.extend(synthesis.attempted_models)
        usage = self._merge_usage(usage, synthesis.usage)
        for key, value in synthesis.errors.items():
            errors[f"decompose.synthesis.{key}"] = value
        collaboration["transcript"].append(
            {
                "type": "synthesis",
                "model": synthesis.model_name,
                "subtasks_used": [item["id"] for item in subtask_outputs],
            }
        )
        collaboration["synthesis_model"] = synthesis.model_name

        return RouterResult(
            model_name=synthesis.model_name,
            model_id=synthesis.model_id,
            content=synthesis.content,
            strategy="decompose",
            votes=subtask_votes,
            errors=errors,
            attempted_models=self._dedupe_names(attempted_models),
            vote_summary={
                "subtasks_total": len(subtasks),
                "subtasks_succeeded": len(subtask_outputs),
                "subtasks_failed": max(0, len(subtasks) - len(subtask_outputs)),
                "quorum_met": len(subtask_outputs) > 0,
                "dependency_edges": sum(len(item.get("depends_on", [])) for item in subtasks),
                "reviewed_subtasks": sum(1 for item in subtasks if str(item.get("review_with") or "").strip()),
                "parallel_batches": len(collaboration["parallel_batches"]),
            },
            usage=usage,
            estimated_cost_usd=self._usage_total(usage),
            collaboration=collaboration,
        )

    def _execute_decompose_subtask(
        self,
        *,
        objective: str,
        subtask: dict[str, object],
        execution_pool: list[str],
        fallback_models: Iterable[str] | None,
        completed_outputs: dict[str, dict[str, str]],
    ) -> dict[str, object]:
        subtask_id = str(subtask.get("id") or "").strip() or "subtask"
        subtask_objective = str(subtask.get("objective") or "").strip()
        if not subtask_objective:
            raise ValueError("missing objective")
        agent_role = str(subtask.get("agent") or subtask.get("model") or subtask_id).strip()
        depends_on = [str(dep).strip() for dep in subtask.get("depends_on", []) if str(dep).strip()]
        requested_model = str(subtask.get("model") or "").strip()
        chosen_model = requested_model if requested_model in execution_pool else execution_pool[0]

        dependency_payload = [
            {
                "id": dep,
                "objective": str(completed_outputs[dep].get("objective") or ""),
                "output": str(completed_outputs[dep].get("output") or ""),
            }
            for dep in depends_on
            if dep in completed_outputs
        ]
        user_content = (
            f"Primary objective:\n{objective}\n\n"
            f"Subtask {subtask_id} ({agent_role}):\n{subtask_objective}"
        )
        if dependency_payload:
            user_content += "\n\nDependency outputs (JSON):\n" + json.dumps(dependency_payload, ensure_ascii=True)

        attempt = 0
        attempted_models: list[str] = []
        merged_usage: dict[str, dict[str, object]] = {}
        merged_errors: dict[str, str] = {}
        transcript: list[dict[str, object]] = [
            {
                "type": "subtask_started",
                "subtask_id": subtask_id,
                "agent": agent_role,
                "model": chosen_model,
                "depends_on": depends_on,
            }
        ]
        reviewer_model = str(subtask.get("review_with") or "").strip()
        reviewer_model = reviewer_model if reviewer_model in execution_pool else ""

        feedback = ""
        while True:
            attempt += 1
            sub_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are solving one subtask in a decomposed workflow. "
                        f"Your agent role is '{agent_role}'. Return concise actionable output."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        user_content
                        + (
                            "\n\nReviewer feedback to incorporate:\n" + feedback
                            if feedback
                            else ""
                        )
                    ),
                },
            ]
            sub_result = self._chat_single(
                messages=sub_messages,
                model_name=chosen_model,
                fallback_models=fallback_models,
            )
            attempted_models.extend(sub_result.attempted_models)
            merged_usage = self._merge_usage(merged_usage, sub_result.usage)
            merged_errors.update(sub_result.errors)
            output = sub_result.content
            review_payload: dict[str, object] | None = None
            transcript.append(
                {
                    "type": "subtask_output",
                    "subtask_id": subtask_id,
                    "agent": agent_role,
                    "model": sub_result.model_name,
                    "attempt": attempt,
                }
            )

            if reviewer_model:
                review_result = self._chat_single(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Review a collaborator output. Return JSON only using schema: "
                                "{\"approved\":true|false,\"feedback\":\"...\"}"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Primary objective:\n{objective}\n\n"
                                f"Subtask {subtask_id} ({agent_role}):\n{subtask_objective}\n\n"
                                f"Candidate output:\n{output}"
                            ),
                        },
                    ],
                    model_name=reviewer_model,
                    fallback_models=fallback_models,
                )
                attempted_models.extend(review_result.attempted_models)
                merged_usage = self._merge_usage(merged_usage, review_result.usage)
                merged_errors.update({f"review.{k}": v for k, v in review_result.errors.items()})
                review_payload = self._parse_review(review_result.content)
                transcript.append(
                    {
                        "type": "subtask_review",
                        "subtask_id": subtask_id,
                        "reviewer_model": review_result.model_name,
                        "approved": bool(review_payload.get("approved", False)),
                        "attempt": attempt,
                    }
                )
                if not bool(review_payload.get("approved", False)) and attempt <= self.decompose_review_retries:
                    feedback = str(review_payload.get("feedback") or "").strip() or "Tighten the answer."
                    continue

            return {
                "id": subtask_id,
                "objective": subtask_objective,
                "model": sub_result.model_name,
                "agent": agent_role,
                "depends_on": depends_on,
                "output": output,
                "review": review_payload,
                "attempted_models": self._dedupe_names(attempted_models),
                "usage": merged_usage,
                "errors": merged_errors,
                "transcript": transcript,
            }

    def _invoke(self, endpoint: ModelEndpoint, messages: list[dict[str, str]]) -> str:
        if self._transport is not None:
            return self._transport(
                endpoint,
                messages,
                self.temperature,
                self.max_tokens,
                self.timeout_seconds,
            )

        if endpoint.provider.lower() == "litellm":
            return self._call_with_litellm(endpoint, messages)

        return self._call_openai_compatible(endpoint, messages)

    def _call_with_litellm(self, endpoint: ModelEndpoint, messages: list[dict[str, str]]) -> str:
        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError(
                "Endpoint provider='litellm' requires optional dependency: pip install 'novaadapt[litellm]'"
            ) from exc

        kwargs = {
            "model": endpoint.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "api_base": endpoint.base_url,
        }

        if endpoint.api_key_env:
            api_key = os.getenv(endpoint.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Missing API key env var '{endpoint.api_key_env}' for endpoint '{endpoint.name}'"
                )
            kwargs["api_key"] = api_key

        response = completion(**kwargs)
        content = response["choices"][0]["message"]["content"]
        return str(content).strip()

    def _call_openai_compatible(self, endpoint: ModelEndpoint, messages: list[dict[str, str]]) -> str:
        base = endpoint.base_url.rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"

        headers = {"Content-Type": "application/json", **endpoint.headers}

        if endpoint.api_key_env:
            api_key = os.getenv(endpoint.api_key_env)
            if not api_key:
                raise RuntimeError(
                    f"Missing API key env var '{endpoint.api_key_env}' for endpoint '{endpoint.name}'"
                )
            headers["Authorization"] = f"Bearer {api_key}"

        payload = json.dumps(
            {
                "model": endpoint.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
            }
        ).encode("utf-8")

        req = request.Request(url=url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="ignore")
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
            raise RuntimeError(f"Model endpoint '{endpoint.name}' failed ({exc.code}): {body}") from exc
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
            raise RuntimeError(f"Model endpoint '{endpoint.name}' unreachable: {exc.reason}") from exc

        choices = raw.get("choices") or []
        if not choices:
            raise RuntimeError(f"Model endpoint '{endpoint.name}' returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
            return text.strip()

        return str(content).strip()

    def _majority_vote(self, outputs: list[str]) -> tuple[str, int]:
        normalized = [self._normalize(item) for item in outputs]
        counts = Counter(normalized)
        winner_norm, winner_count = counts.most_common(1)[0]
        for item in outputs:
            if self._normalize(item) == winner_norm:
                return item, winner_count
        return outputs[0], winner_count

    def _usage_for_attempts(self, attempts: Iterable[str]) -> dict[str, dict[str, object]]:
        counts = Counter(str(name) for name in attempts if str(name))
        usage: dict[str, dict[str, object]] = {}
        for name, count in counts.items():
            endpoint = self._resolve_model(name)
            estimated_cost = round(float(endpoint.estimated_cost_per_call_usd or 0.0) * count, 6)
            usage[name] = {
                "calls": int(count),
                "model_id": endpoint.model,
                "estimated_cost_usd": estimated_cost,
            }
        return usage

    @staticmethod
    def _merge_usage(
        left: dict[str, dict[str, object]],
        right: dict[str, dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        merged = json.loads(json.dumps(left, ensure_ascii=True))
        for name, item in right.items():
            current = merged.setdefault(name, {"calls": 0, "estimated_cost_usd": 0.0, "model_id": ""})
            current["calls"] = int(current.get("calls", 0) or 0) + int(item.get("calls", 0) or 0)
            current["estimated_cost_usd"] = round(
                float(current.get("estimated_cost_usd", 0.0) or 0.0)
                + float(item.get("estimated_cost_usd", 0.0) or 0.0),
                6,
            )
            if item.get("model_id"):
                current["model_id"] = str(item.get("model_id") or "")
        return merged

    @staticmethod
    def _usage_total(usage: dict[str, dict[str, object]]) -> float:
        total = 0.0
        for item in usage.values():
            total += float(item.get("estimated_cost_usd", 0.0) or 0.0)
        return round(total, 6)

    @staticmethod
    def _dedupe_names(names: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for name in names:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def _default_vote_models(self) -> list[str]:
        ordered = [self.default_model]
        ordered.extend(name for name in self._endpoints if name != self.default_model)
        return ordered[: self.default_vote_candidates]

    @staticmethod
    def _extract_user_objective(messages: list[dict[str, str]]) -> str:
        for item in reversed(messages):
            if not isinstance(item, dict):
                continue
            if str(item.get("role", "")).strip() != "user":
                continue
            content = str(item.get("content", "")).strip()
            if content:
                return content
        return json.dumps(messages, ensure_ascii=True)

    @staticmethod
    def _parse_subtasks(raw: str, *, max_items: int) -> list[dict[str, object]]:
        text = str(raw or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []

        items = parsed.get("subtasks") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            return []
        out: list[dict[str, object]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            objective = str(item.get("objective") or item.get("task") or item.get("prompt") or "").strip()
            if not objective:
                continue
            depends_on = []
            raw_depends = item.get("depends_on")
            if isinstance(raw_depends, list):
                depends_on = [str(dep).strip() for dep in raw_depends if str(dep).strip()]
            out.append(
                {
                    "id": str(item.get("id") or f"s{index}"),
                    "objective": objective,
                    "model": str(item.get("model") or "").strip(),
                    "agent": str(item.get("agent") or "").strip(),
                    "depends_on": depends_on,
                    "review_with": str(item.get("review_with") or "").strip(),
                }
            )
            if len(out) >= max(1, int(max_items)):
                break
        return out

    @staticmethod
    def _parse_review(raw: str) -> dict[str, object]:
        text = str(raw or "").strip()
        if not text:
            return {"approved": True, "feedback": ""}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            lowered = text.lower()
            if "not approved" in lowered or "revise" in lowered or "retry" in lowered:
                return {"approved": False, "feedback": text}
            return {"approved": True, "feedback": text}
        if not isinstance(parsed, dict):
            return {"approved": True, "feedback": text}
        return {
            "approved": bool(parsed.get("approved", False) if "approved" in parsed else parsed.get("ok", True)),
            "feedback": str(parsed.get("feedback") or parsed.get("reason") or "").strip(),
        }

    @staticmethod
    def _normalize(text: str) -> str:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            return "json:" + json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return " ".join(text.lower().split())

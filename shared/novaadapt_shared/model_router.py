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


@dataclass(frozen=True)
class RouterResult:
    model_name: str
    model_id: str
    content: str
    strategy: str
    votes: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    attempted_models: list[str] = field(default_factory=list)


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
        if strategy not in {"single", "vote"}:
            raise ValueError("strategy must be 'single' or 'vote'")

        if strategy == "single":
            primary_name = model_name or self.default_model
            fallback_names = list(fallback_models or [])
            ordered_names = self._dedupe_names([primary_name, *fallback_names])
            errors: dict[str, str] = {}
            endpoint = self._resolve_model(ordered_names[0])
            content = ""
            for name in ordered_names:
                endpoint = self._resolve_model(name)
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
                attempted_models=ordered_names,
            )

        names = list(candidate_models or [self.default_model])
        if not names:
            raise ValueError("candidate_models must not be empty when strategy='vote'")

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

        chosen = self._majority_vote(outputs)
        winner = next((k for k, v in votes.items() if self._normalize(v) == self._normalize(chosen)), endpoints[0].name)

        return RouterResult(
            model_name=winner,
            model_id=self._endpoints[winner].model,
            content=chosen,
            strategy="vote",
            votes=votes,
            errors=errors,
            attempted_models=names,
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
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Model endpoint '{endpoint.name}' failed ({exc.code}): {body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Model endpoint '{endpoint.name}' unreachable: {exc.reason}") from exc

        choices = raw.get("choices") or []
        if not choices:
            raise RuntimeError(f"Model endpoint '{endpoint.name}' returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
            return text.strip()

        return str(content).strip()

    def _majority_vote(self, outputs: list[str]) -> str:
        normalized = [self._normalize(item) for item in outputs]
        counts = Counter(normalized)
        winner_norm = counts.most_common(1)[0][0]
        for item in outputs:
            if self._normalize(item) == winner_norm:
                return item
        return outputs[0]

    @staticmethod
    def _dedupe_names(names: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for name in names:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().split())

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .service import NovaAdaptService


def run_doctor(
    service: NovaAdaptService,
    *,
    config_path: Path,
    include_execution: bool = False,
    include_plugins: bool = True,
    include_model_health: bool = True,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    cfg_path = Path(config_path)

    if cfg_path.exists():
        checks.append(_check("config.exists", "pass", {"path": str(cfg_path)}))
    else:
        checks.append(
            _check(
                "config.exists",
                "fail",
                {"path": str(cfg_path)},
                recommendation="Provide a valid --config path to a model config JSON file.",
            )
        )
        return _build_report(checks)

    config_payload = _load_config(cfg_path)
    if isinstance(config_payload, dict):
        checks.extend(_check_config_shape(config_payload))
    else:
        checks.append(
            _check(
                "config.parse",
                "fail",
                {"path": str(cfg_path)},
                recommendation="Ensure the model config file contains valid JSON.",
            )
        )
        return _build_report(checks)

    checks.extend(_check_security_env())

    checks.extend(_check_models(service, cfg_path, include_model_health=include_model_health))
    checks.extend(_check_memory(service))
    checks.extend(_check_novaprime(service))

    if include_plugins:
        checks.extend(_check_plugins(service))
    if include_execution:
        checks.extend(_check_execution(service))

    return _build_report(checks)


def _load_config(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _check_config_shape(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    models = payload.get("models")
    model_names: list[str] = []
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    model_names.append(name)
    if model_names:
        checks.append(_check("config.models", "pass", {"count": len(model_names), "names": model_names}))
    else:
        checks.append(
            _check(
                "config.models",
                "fail",
                {"count": 0},
                recommendation="Define at least one model in config.models.",
            )
        )

    default_model = str(payload.get("default_model", "")).strip()
    if not default_model:
        checks.append(
            _check(
                "config.default_model",
                "fail",
                {"default_model": default_model},
                recommendation="Set default_model to one of the configured model names.",
            )
        )
    elif default_model in model_names:
        checks.append(_check("config.default_model", "pass", {"default_model": default_model}))
    else:
        checks.append(
            _check(
                "config.default_model",
                "fail",
                {"default_model": default_model, "available_models": model_names},
                recommendation="Update default_model to a value present in config.models[].name.",
            )
        )
    return checks


def _check_security_env() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    core_token = str(os.getenv("NOVAADAPT_API_TOKEN", "")).strip()
    if core_token:
        checks.append(_check("security.core_api_token", "pass", {"configured": True}))
    else:
        checks.append(
            _check(
                "security.core_api_token",
                "warn",
                {"configured": False},
                recommendation="Set NOVAADAPT_API_TOKEN when exposing core API beyond localhost.",
            )
        )

    bridge_token = str(os.getenv("NOVAADAPT_BRIDGE_TOKEN", "")).strip()
    if bridge_token:
        checks.append(_check("security.bridge_token", "pass", {"configured": True}))
    else:
        checks.append(
            _check(
                "security.bridge_token",
                "warn",
                {"configured": False},
                recommendation="Set NOVAADAPT_BRIDGE_TOKEN for authenticated bridge access.",
            )
        )
    return checks


def _check_models(
    service: NovaAdaptService,
    config_path: Path,
    *,
    include_model_health: bool,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        models = service.models(config_path=config_path)
    except Exception as exc:
        checks.append(
            _check(
                "models.load",
                "fail",
                {"error": str(exc)},
                recommendation="Fix model config format and endpoint definitions.",
            )
        )
        return checks

    if isinstance(models, list) and models:
        checks.append(_check("models.load", "pass", {"count": len(models)}))
    else:
        checks.append(
            _check(
                "models.load",
                "fail",
                {"count": 0},
                recommendation="Add at least one valid model endpoint in the model config.",
            )
        )
        return checks

    if not include_model_health:
        return checks

    try:
        rows = service.check(config_path=config_path)
    except Exception as exc:
        checks.append(
            _check(
                "models.health",
                "warn",
                {"error": str(exc)},
                recommendation="Model health probes failed; verify network/access keys for providers.",
            )
        )
        return checks

    healthy = 0
    total = 0
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        total += 1
        if bool(item.get("ok", False)):
            healthy += 1
    if total <= 0:
        checks.append(
            _check(
                "models.health",
                "warn",
                {"healthy": 0, "total": 0},
                recommendation="No model health results returned; verify model router configuration.",
            )
        )
    elif healthy == total:
        checks.append(_check("models.health", "pass", {"healthy": healthy, "total": total}))
    elif healthy > 0:
        checks.append(
            _check(
                "models.health",
                "warn",
                {"healthy": healthy, "total": total},
                recommendation="Some model endpoints are unhealthy; inspect provider credentials/network.",
            )
        )
    else:
        checks.append(
            _check(
                "models.health",
                "fail",
                {"healthy": healthy, "total": total},
                recommendation="All model endpoints failed health probes.",
            )
        )
    return checks


def _check_memory(service: NovaAdaptService) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        status = service.memory_status()
    except Exception as exc:
        checks.append(
            _check(
                "memory.status",
                "fail",
                {"error": str(exc)},
                recommendation="Repair memory backend configuration or disable required mode.",
            )
        )
        return checks
    if bool(status.get("ok", False)):
        checks.append(_check("memory.status", "pass", status))
    elif bool(status.get("enabled", True)):
        checks.append(
            _check(
                "memory.status",
                "warn",
                status,
                recommendation="Memory backend is enabled but unhealthy; inspect NovaSpine endpoint.",
            )
        )
    else:
        checks.append(
            _check(
                "memory.status",
                "warn",
                status,
                recommendation="Memory backend is disabled; long-term recall will be unavailable.",
            )
        )
    return checks


def _check_novaprime(service: NovaAdaptService) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        status = service.novaprime_status()
    except Exception as exc:
        checks.append(
            _check(
                "novaprime.status",
                "warn",
                {"error": str(exc)},
                recommendation="NovaPrime integration unavailable; SIB identity/mesh flows will degrade.",
            )
        )
        return checks
    if bool(status.get("enabled", False)) and bool(status.get("ok", False)):
        checks.append(_check("novaprime.status", "pass", status))
    elif bool(status.get("enabled", False)):
        checks.append(
            _check(
                "novaprime.status",
                "warn",
                status,
                recommendation="NovaPrime configured but unreachable; verify NOVAADAPT_NOVAPRIME_URL/token.",
            )
        )
    else:
        checks.append(
            _check(
                "novaprime.status",
                "warn",
                status,
                recommendation="NovaPrime backend disabled; enable for full SIB identity/mesh features.",
            )
        )
    return checks


def _check_plugins(service: NovaAdaptService) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        plugins = service.plugins()
    except Exception as exc:
        checks.append(
            _check(
                "plugins.list",
                "warn",
                {"error": str(exc)},
                recommendation="Unable to load plugin registry; verify plugin configuration.",
            )
        )
        return checks

    names = [str(item.get("name", "")).strip() for item in plugins if isinstance(item, dict)]
    names = [item for item in names if item]
    if names:
        checks.append(_check("plugins.list", "pass", {"count": len(names), "names": names}))
    else:
        checks.append(
            _check(
                "plugins.list",
                "warn",
                {"count": 0},
                recommendation="No plugins registered; NovaBridge/NovaBlox integrations are unavailable.",
            )
        )
        return checks

    healthy = 0
    for name in names:
        try:
            status = service.plugin_health(name)
        except Exception as exc:
            checks.append(
                _check(
                    f"plugins.health.{name}",
                    "warn",
                    {"error": str(exc)},
                    recommendation=f"Check plugin endpoint/config for '{name}'.",
                )
            )
            continue
        if bool(status.get("ok", False)):
            healthy += 1
            checks.append(_check(f"plugins.health.{name}", "pass", status))
        else:
            checks.append(
                _check(
                    f"plugins.health.{name}",
                    "warn",
                    status,
                    recommendation=f"Plugin '{name}' is unhealthy; verify base URL and auth headers.",
                )
            )

    if healthy == len(names):
        checks.append(_check("plugins.health.summary", "pass", {"healthy": healthy, "total": len(names)}))
    elif healthy > 0:
        checks.append(
            _check(
                "plugins.health.summary",
                "warn",
                {"healthy": healthy, "total": len(names)},
                recommendation="Some plugins are unhealthy; SIB bridge functionality may be partial.",
            )
        )
    else:
        checks.append(
            _check(
                "plugins.health.summary",
                "warn",
                {"healthy": healthy, "total": len(names)},
                recommendation="All plugins are unhealthy; verify plugin targets before production use.",
            )
        )
    return checks


def _check_execution(service: NovaAdaptService) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        probe = service.directshell_probe()
    except Exception as exc:
        checks.append(
            _check(
                "execution.directshell",
                "fail",
                {"error": str(exc)},
                recommendation="Fix DirectShell runtime before enabling --execute workflows.",
            )
        )
    else:
        if bool(probe.get("ok", False)):
            checks.append(_check("execution.directshell", "pass", probe))
        else:
            checks.append(
                _check(
                    "execution.directshell",
                    "fail",
                    probe,
                    recommendation="DirectShell probe failed; inspect transport/native runtime settings.",
                )
            )

    try:
        browser = service.browser_status()
    except Exception as exc:
        checks.append(
            _check(
                "execution.browser",
                "warn",
                {"error": str(exc)},
                recommendation="Browser runtime unavailable; install Playwright extras if required.",
            )
        )
    else:
        if bool(browser.get("ok", False)):
            checks.append(_check("execution.browser", "pass", browser))
        else:
            checks.append(
                _check(
                    "execution.browser",
                    "warn",
                    browser,
                    recommendation="Browser runtime unhealthy; run browser-status and check Playwright setup.",
                )
            )
    return checks


def _check(
    name: str,
    status: str,
    details: dict[str, Any] | None = None,
    *,
    recommendation: str = "",
) -> dict[str, Any]:
    normalized = status.lower().strip()
    if normalized not in {"pass", "warn", "fail"}:
        normalized = "warn"
    out: dict[str, Any] = {
        "name": name,
        "status": normalized,
        "ok": normalized == "pass",
        "details": details if isinstance(details, dict) else {},
    }
    if recommendation:
        out["recommendation"] = recommendation
    return out


def _build_report(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = str(check.get("status", "warn")).strip().lower()
        if status not in counts:
            status = "warn"
        counts[status] += 1
    return {
        "ok": counts["fail"] == 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": counts,
        "checks": checks,
    }


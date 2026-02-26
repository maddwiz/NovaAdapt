#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from novaadapt_shared import APIClientError, NovaAdaptAPIClient


TERMINAL_JOB_STATES = {"succeeded", "failed", "canceled"}
TERMINAL_PLAN_STATES = {"executed", "failed", "rejected"}


@dataclass
class HaloIntent:
    transcript: str
    confidence: float
    source: str = "halo"


def _env_int(key: str, fallback: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def _env_bool(key: str, fallback: bool) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if not raw:
        return fallback
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return fallback


def _parse_scopes(raw: str) -> list[str]:
    scopes = [item.strip() for item in raw.split(",") if item.strip()]
    if not scopes:
        raise ValueError("session scopes must not be empty")
    return scopes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Halo/Omi wearable intent bridge for NovaAdapt")
    parser.add_argument(
        "--bridge-url",
        default=os.getenv("NOVAADAPT_BRIDGE_URL"),
        help="Bridge base URL (preferred for remote/session workflows)",
    )
    parser.add_argument(
        "--core-url",
        default=os.getenv("NOVAADAPT_CORE_URL", "http://127.0.0.1:8787"),
        help="Core API URL fallback when --bridge-url is not provided",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("NOVAADAPT_BRIDGE_TOKEN") or os.getenv("NOVAADAPT_API_TOKEN"),
        help="Bearer token for selected endpoint (--bridge-url or --core-url)",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("NOVAADAPT_BRIDGE_ADMIN_TOKEN"),
        help="Bridge admin token used to mint a scoped short-lived session token",
    )
    parser.add_argument(
        "--session-scopes",
        default=os.getenv("NOVAADAPT_BRIDGE_SESSION_SCOPES", "read,run,plan,approve,reject,undo,cancel"),
        help="Comma-separated scopes for minted bridge session token",
    )
    parser.add_argument(
        "--session-ttl",
        type=int,
        default=_env_int("NOVAADAPT_BRIDGE_SESSION_TTL", 900),
        help="TTL seconds for issued bridge session token",
    )
    parser.add_argument(
        "--session-device-id",
        default=os.getenv("NOVAADAPT_BRIDGE_DEVICE_ID"),
        help="Optional bridge device_id claim for session token",
    )
    parser.add_argument(
        "--session-subject",
        default=os.getenv("NOVAADAPT_BRIDGE_SESSION_SUBJECT", "halo-bridge"),
        help="Bridge session subject value",
    )
    parser.add_argument(
        "--ensure-device-allowlisted",
        action="store_true",
        default=_env_bool("NOVAADAPT_BRIDGE_ENSURE_DEVICE_ALLOWLISTED", False),
        help="When using --admin-token, pre-add --session-device-id into bridge allowlist before issuing session",
    )
    parser.add_argument(
        "--no-revoke-session",
        action="store_true",
        help="Do not revoke leased bridge session token on exit",
    )
    parser.add_argument("--objective", required=True, help="Intent transcript/objective to submit")
    parser.add_argument("--confidence", type=float, default=0.92, help="Intent confidence [0,1]")
    parser.add_argument("--source", default="halo", help="Intent source tag (halo, omi, etc.)")
    parser.add_argument(
        "--submission-mode",
        choices=("run_async", "plan"),
        default="run_async",
        help="Submit as immediate async run or pending plan",
    )
    parser.add_argument("--wait", action="store_true", help="Poll for terminal state when possible")
    parser.add_argument("--wait-timeout", type=float, default=90.0, help="Max wait seconds with --wait")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval seconds")
    parser.add_argument("--idempotency-prefix", default="halo", help="Idempotency key prefix")
    return parser


def _build_runtime_client(
    endpoint_url: str,
    token: str | None,
    admin_token: str | None,
    session_scopes: list[str],
    session_ttl: int,
    session_device_id: str | None,
    session_subject: str | None,
    ensure_device_allowlisted: bool,
) -> tuple[NovaAdaptAPIClient, NovaAdaptAPIClient | None, str | None, dict[str, Any] | None]:
    direct_token = (token or "").strip()
    admin = (admin_token or "").strip()

    if admin:
        admin_client = NovaAdaptAPIClient(
            base_url=endpoint_url,
            token=admin,
            timeout_seconds=30,
            max_retries=1,
            retry_backoff_seconds=0.25,
        )
        normalized_device_id = (session_device_id or "").strip() or None
        if ensure_device_allowlisted:
            if not normalized_device_id:
                raise ValueError("--ensure-device-allowlisted requires --session-device-id")
            admin_client.add_allowed_device(normalized_device_id)
        issued = admin_client.issue_session_token(
            scopes=session_scopes,
            subject=(session_subject or "").strip() or "halo-bridge",
            device_id=normalized_device_id,
            ttl_seconds=max(60, int(session_ttl)),
        )
        leased_token = str(issued.get("token", "")).strip()
        if not leased_token:
            raise APIClientError("session token issuance succeeded without token")
        runtime_client = NovaAdaptAPIClient(
            base_url=endpoint_url,
            token=leased_token,
            timeout_seconds=30,
            max_retries=1,
            retry_backoff_seconds=0.25,
        )
        return runtime_client, admin_client, leased_token, issued

    if not direct_token:
        raise ValueError("either --token or --admin-token is required")

    runtime_client = NovaAdaptAPIClient(
        base_url=endpoint_url,
        token=direct_token,
        timeout_seconds=30,
        max_retries=1,
        retry_backoff_seconds=0.25,
    )
    return runtime_client, None, None, None


def _build_submission_payload(intent: HaloIntent) -> dict[str, Any]:
    return {
        "objective": intent.transcript,
        "metadata": {
            "source": intent.source,
            "confidence": intent.confidence,
            "intent_type": "wearable_voice",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _submit_intent(
    client: NovaAdaptAPIClient,
    intent: HaloIntent,
    *,
    submission_mode: str,
    wait: bool,
    wait_timeout_seconds: float,
    poll_interval_seconds: float,
    idempotency_prefix: str,
) -> dict[str, Any]:
    payload = _build_submission_payload(intent)
    idem_key = f"{idempotency_prefix}-{int(time.time() * 1000)}"
    mode = str(submission_mode).strip().lower() or "run_async"

    if mode == "plan":
        submitted = client.create_plan(idempotency_key=idem_key, **payload)
        out: dict[str, Any] = {"submission_mode": mode, "submitted": submitted}
        plan_id = str(submitted.get("id", "")).strip()
        if wait and plan_id:
            out["plan"] = _wait_for_plan(
                client=client,
                plan_id=plan_id,
                timeout_seconds=wait_timeout_seconds,
                interval_seconds=poll_interval_seconds,
            )
        return out

    submitted = client.run_async(idempotency_key=idem_key, **payload)
    out = {"submission_mode": "run_async", "submitted": submitted}
    job_id = str(submitted.get("job_id", "")).strip()
    if wait and job_id:
        out["job"] = _wait_for_job(
            client=client,
            job_id=job_id,
            timeout_seconds=wait_timeout_seconds,
            interval_seconds=poll_interval_seconds,
        )
    return out


def _wait_for_job(
    client: NovaAdaptAPIClient,
    job_id: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    interval = min(5.0, max(0.1, float(interval_seconds)))
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    last: dict[str, Any] = {}
    while True:
        last = client.job(job_id)
        status = str(last.get("status", "")).strip().lower()
        if status in TERMINAL_JOB_STATES:
            return last
        if time.monotonic() >= deadline:
            return {"id": job_id, "status": status or "timeout", "timeout": True, "last": last}
        time.sleep(interval)


def _wait_for_plan(
    client: NovaAdaptAPIClient,
    plan_id: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    interval = min(5.0, max(0.1, float(interval_seconds)))
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    last: dict[str, Any] = {}
    while True:
        last = client.plan(plan_id)
        status = str(last.get("status", "")).strip().lower()
        if status in TERMINAL_PLAN_STATES:
            return last
        if time.monotonic() >= deadline:
            return {"id": plan_id, "status": status or "timeout", "timeout": True, "last": last}
        time.sleep(interval)


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def main() -> int:
    args = _build_parser().parse_args()

    endpoint_url = str(args.bridge_url or args.core_url or "").strip()
    if not endpoint_url:
        print(json.dumps({"ok": False, "error": "bridge/core URL is required"}, indent=2))
        return 1

    try:
        session_scopes = _parse_scopes(str(args.session_scopes))
        client, admin_client, leased_token, issued = _build_runtime_client(
            endpoint_url=endpoint_url,
            token=args.token,
            admin_token=args.admin_token,
            session_scopes=session_scopes,
            session_ttl=int(args.session_ttl),
            session_device_id=args.session_device_id,
            session_subject=args.session_subject,
            ensure_device_allowlisted=bool(args.ensure_device_allowlisted),
        )
    except (APIClientError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    intent = HaloIntent(
        transcript=str(args.objective).strip(),
        confidence=_clamp_confidence(float(args.confidence)),
        source=str(args.source).strip() or "halo",
    )
    if not intent.transcript:
        print(json.dumps({"ok": False, "error": "objective must not be empty"}, indent=2))
        return 1

    session_context: dict[str, Any] | None = None
    if issued:
        session_context = {
            "session_id": issued.get("session_id"),
            "subject": issued.get("subject"),
            "scopes": issued.get("scopes"),
            "device_id": issued.get("device_id"),
            "expires_at": issued.get("expires_at"),
        }

    started = time.time()
    try:
        payload = _submit_intent(
            client=client,
            intent=intent,
            submission_mode=str(args.submission_mode),
            wait=bool(args.wait),
            wait_timeout_seconds=float(args.wait_timeout),
            poll_interval_seconds=float(args.poll_interval),
            idempotency_prefix=str(args.idempotency_prefix).strip() or "halo",
        )
        elapsed_ms = int((time.time() - started) * 1000)
        output: dict[str, Any] = {
            "ok": True,
            "endpoint_url": endpoint_url,
            "elapsed_ms": elapsed_ms,
            "intent": {
                "objective": intent.transcript,
                "source": intent.source,
                "confidence": intent.confidence,
            },
            **payload,
        }
        if session_context:
            output["session"] = session_context
        print(json.dumps(output, indent=2))
        return 0
    except (APIClientError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    finally:
        if admin_client and leased_token and not bool(args.no_revoke_session):
            try:
                admin_client.revoke_session_token(leased_token)
            except APIClientError as exc:
                print(
                    json.dumps(
                        {"ok": False, "warning": f"failed to revoke leased session token: {exc}"},
                        indent=2,
                    ),
                    file=sys.stderr,
                )


if __name__ == "__main__":
    raise SystemExit(main())

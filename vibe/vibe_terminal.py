from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from novaadapt_shared import APIClientError, NovaAdaptAPIClient


TERMINAL_JOB_STATES = {"succeeded", "failed", "canceled"}


def _env_int(key: str, fallback: int) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def _parse_scopes(raw: str) -> list[str]:
    scopes = [item.strip() for item in raw.split(",") if item.strip()]
    if not scopes:
        raise ValueError("session scopes must not be empty")
    return scopes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe-terminal",
        description="Send wearable-style objective intents to NovaAdapt bridge/core",
    )
    parser.add_argument(
        "--bridge-url",
        default=os.getenv("NOVAADAPT_BRIDGE_URL", "http://127.0.0.1:9797"),
        help="Bridge base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("NOVAADAPT_BRIDGE_TOKEN"),
        help="Bridge bearer token (or NOVAADAPT_BRIDGE_TOKEN env var)",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("NOVAADAPT_BRIDGE_ADMIN_TOKEN"),
        help="Bridge admin token used to mint scoped session tokens",
    )
    parser.add_argument(
        "--session-scopes",
        default=os.getenv("NOVAADAPT_BRIDGE_SESSION_SCOPES", "read,run,plan,approve,reject,undo,cancel"),
        help="Comma-separated scopes when issuing a session token from --admin-token",
    )
    parser.add_argument(
        "--session-ttl",
        type=int,
        default=_env_int("NOVAADAPT_BRIDGE_SESSION_TTL", 900),
        help="Session token TTL seconds when issuing from --admin-token",
    )
    parser.add_argument(
        "--session-device-id",
        default=os.getenv("NOVAADAPT_BRIDGE_DEVICE_ID"),
        help="Optional device_id to bind issued session token",
    )
    parser.add_argument(
        "--session-subject",
        default=os.getenv("NOVAADAPT_BRIDGE_SESSION_SUBJECT", "vibe-terminal"),
        help="Subject used when issuing session token from --admin-token",
    )
    parser.add_argument(
        "--no-revoke-session",
        action="store_true",
        help="Do not revoke leased session token on exit",
    )
    parser.add_argument(
        "--objective",
        default=None,
        help="Single objective to submit (omit for interactive loop)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll submitted jobs until terminal state",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Polling interval seconds when --wait is enabled",
    )
    parser.add_argument(
        "--idempotency-prefix",
        default="vibe",
        help="Idempotency key prefix used for submissions",
    )
    return parser


def _submit_and_optionally_wait(
    client: NovaAdaptAPIClient,
    objective: str,
    wait: bool,
    poll_interval: float,
    idempotency_prefix: str,
) -> dict[str, Any]:
    objective = objective.strip()
    if not objective:
        raise ValueError("objective must not be empty")

    idem_key = f"{idempotency_prefix}-{int(time.time() * 1000)}"
    response = client.run_async(objective=objective, idempotency_key=idem_key)

    payload: dict[str, Any] = {
        "objective": objective,
        "submitted": response,
    }
    job_id = str(response.get("job_id", "")).strip()
    if not wait or not job_id:
        return payload

    interval = max(0.1, float(poll_interval))
    while True:
        current = client.job(job_id)
        payload["job"] = current
        status = str(current.get("status", "")).strip().lower()
        if status in TERMINAL_JOB_STATES:
            return payload
        time.sleep(interval)


def _build_runtime_client(
    bridge_url: str,
    token: str | None,
    admin_token: str | None,
    session_scopes: list[str],
    session_ttl: int,
    session_device_id: str | None,
    session_subject: str | None,
) -> tuple[NovaAdaptAPIClient, NovaAdaptAPIClient | None, str | None, dict[str, Any] | None]:
    direct_token = (token or "").strip()
    admin = (admin_token or "").strip()

    if admin:
        admin_client = NovaAdaptAPIClient(
            base_url=bridge_url,
            token=admin,
            timeout_seconds=30,
            max_retries=1,
            retry_backoff_seconds=0.25,
        )
        issued = admin_client.issue_session_token(
            scopes=session_scopes,
            subject=(session_subject or "").strip() or "vibe-terminal",
            device_id=(session_device_id or "").strip() or None,
            ttl_seconds=max(60, int(session_ttl)),
        )
        leased_token = str(issued.get("token", "")).strip()
        if not leased_token:
            raise APIClientError("session token issuance succeeded without token")
        runtime_client = NovaAdaptAPIClient(
            base_url=bridge_url,
            token=leased_token,
            timeout_seconds=30,
            max_retries=1,
            retry_backoff_seconds=0.25,
        )
        return runtime_client, admin_client, leased_token, issued

    if not direct_token:
        raise ValueError("either --token or --admin-token is required")

    runtime_client = NovaAdaptAPIClient(
        base_url=bridge_url,
        token=direct_token,
        timeout_seconds=30,
        max_retries=1,
        retry_backoff_seconds=0.25,
    )
    return runtime_client, None, None, None


def _interactive_loop(
    client: NovaAdaptAPIClient,
    wait: bool,
    poll_interval: float,
    idempotency_prefix: str,
) -> int:
    print("vibe-terminal interactive mode. Type objectives, or 'quit' to exit.")
    while True:
        try:
            line = input("vibe> ")
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 130

        objective = line.strip()
        if not objective:
            continue
        if objective.lower() in {"quit", "exit"}:
            return 0

        try:
            result = _submit_and_optionally_wait(
                client=client,
                objective=objective,
                wait=wait,
                poll_interval=poll_interval,
                idempotency_prefix=idempotency_prefix,
            )
        except (APIClientError, ValueError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            continue

        print(json.dumps({"ok": True, **result}, indent=2))


def main() -> int:
    args = _build_parser().parse_args()

    try:
        session_scopes = _parse_scopes(str(args.session_scopes))
        client, admin_client, leased_token, issued = _build_runtime_client(
            bridge_url=str(args.bridge_url).strip(),
            token=args.token,
            admin_token=args.admin_token,
            session_scopes=session_scopes,
            session_ttl=int(args.session_ttl),
            session_device_id=args.session_device_id,
            session_subject=args.session_subject,
        )
    except (APIClientError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
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

    try:
        if args.objective:
            try:
                result = _submit_and_optionally_wait(
                    client=client,
                    objective=args.objective,
                    wait=bool(args.wait),
                    poll_interval=float(args.poll_interval),
                    idempotency_prefix=str(args.idempotency_prefix).strip() or "vibe",
                )
            except (APIClientError, ValueError) as exc:
                print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
                return 1

            output: dict[str, Any] = {"ok": True, **result}
            if session_context:
                output["session"] = session_context
            print(json.dumps(output, indent=2))
            return 0

        return _interactive_loop(
            client=client,
            wait=bool(args.wait),
            poll_interval=float(args.poll_interval),
            idempotency_prefix=str(args.idempotency_prefix).strip() or "vibe",
        )
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

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from novaadapt_shared import APIClientError, NovaAdaptAPIClient


TERMINAL_JOB_STATES = {"succeeded", "failed", "canceled"}


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

    client = NovaAdaptAPIClient(
        base_url=args.bridge_url,
        token=args.token,
        timeout_seconds=30,
        max_retries=1,
        retry_backoff_seconds=0.25,
    )

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

        print(json.dumps({"ok": True, **result}, indent=2))
        return 0

    return _interactive_loop(
        client=client,
        wait=bool(args.wait),
        poll_interval=float(args.poll_interval),
        idempotency_prefix=str(args.idempotency_prefix).strip() or "vibe",
    )


if __name__ == "__main__":
    raise SystemExit(main())

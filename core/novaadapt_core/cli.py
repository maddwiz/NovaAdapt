from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .benchmark import run_benchmark
from .server import run_server
from .service import NovaAdaptService


def _default_config_path() -> Path:
    env = os.getenv("NOVAADAPT_MODEL_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "config" / "models.example.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novaadapt", description="NovaAdapt desktop orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("models", help="List configured model endpoints")
    list_cmd.add_argument("--config", type=Path, default=_default_config_path())

    run_cmd = sub.add_parser("run", help="Run objective through model router and DirectShell")
    run_cmd.add_argument("--config", type=Path, default=_default_config_path())
    run_cmd.add_argument("--db-path", type=Path, default=None)
    run_cmd.add_argument("--objective", required=True)
    run_cmd.add_argument("--strategy", choices=["single", "vote"], default="single")
    run_cmd.add_argument("--model", default=None)
    run_cmd.add_argument(
        "--candidates",
        default="",
        help="Comma-separated model endpoint names for vote mode",
    )
    run_cmd.add_argument(
        "--fallbacks",
        default="",
        help="Comma-separated fallback model endpoint names for single mode",
    )
    run_cmd.add_argument(
        "--execute",
        action="store_true",
        help="Execute actions via DirectShell (default is dry-run preview)",
    )
    run_cmd.add_argument(
        "--allow-dangerous",
        action="store_true",
        help="Allow potentially destructive actions when --execute is enabled",
    )
    run_cmd.add_argument(
        "--max-actions",
        type=int,
        default=25,
        help="Cap the number of actions executed from the generated plan",
    )

    history_cmd = sub.add_parser("history", help="Show recent action history")
    history_cmd.add_argument("--limit", type=int, default=20)
    history_cmd.add_argument("--db-path", type=Path, default=None)

    undo_cmd = sub.add_parser("undo", help="Undo a recorded action")
    undo_cmd.add_argument("--id", type=int, default=None, help="Specific action log id to undo")
    undo_cmd.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to actions.db (defaults to ~/.novaadapt/actions.db)",
    )
    undo_cmd.add_argument(
        "--execute",
        action="store_true",
        help="Execute the undo action via DirectShell (default preview only)",
    )
    undo_cmd.add_argument(
        "--mark-only",
        action="store_true",
        help="Mark action as undone even if no undo action is stored",
    )

    check_cmd = sub.add_parser("check", help="Probe model endpoints and report health")
    check_cmd.add_argument("--config", type=Path, default=_default_config_path())
    check_cmd.add_argument(
        "--models",
        default="",
        help="Comma-separated model endpoint names to probe (default all)",
    )
    check_cmd.add_argument(
        "--probe",
        default="Reply with: OK",
        help="Probe prompt text sent to each model",
    )

    bench_cmd = sub.add_parser("benchmark", help="Run benchmark suite and report success metrics")
    bench_cmd.add_argument("--config", type=Path, default=_default_config_path())
    bench_cmd.add_argument("--db-path", type=Path, default=None)
    bench_cmd.add_argument("--suite", type=Path, required=True, help="Path to benchmark suite JSON")
    bench_cmd.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path for benchmark report JSON",
    )

    serve_cmd = sub.add_parser("serve", help="Run NovaAdapt HTTP API server")
    serve_cmd.add_argument("--config", type=Path, default=_default_config_path())
    serve_cmd.add_argument("--db-path", type=Path, default=None)
    serve_cmd.add_argument(
        "--jobs-db-path",
        type=Path,
        default=Path(os.getenv("NOVAADAPT_JOBS_DB", str(Path.home() / ".novaadapt" / "jobs.db"))),
        help="Path to persisted async jobs SQLite database",
    )
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8787)
    serve_cmd.add_argument(
        "--api-token",
        default=os.getenv("NOVAADAPT_API_TOKEN"),
        help="Require Bearer auth token for all API routes except /health",
    )
    serve_cmd.add_argument(
        "--log-requests",
        action="store_true",
        help="Emit per-request access logs from the core API server",
    )
    serve_cmd.add_argument(
        "--rate-limit-rps",
        type=float,
        default=float(os.getenv("NOVAADAPT_RATE_LIMIT_RPS", "0")),
        help="Per-second request rate limit for core API (0 disables limit)",
    )
    serve_cmd.add_argument(
        "--rate-limit-burst",
        type=int,
        default=None,
        help="Burst requests allowed inside 1 second window (defaults to rate limit rounded down)",
    )
    serve_cmd.add_argument(
        "--max-body-bytes",
        type=int,
        default=int(os.getenv("NOVAADAPT_MAX_BODY_BYTES", str(1 << 20))),
        help="Maximum HTTP request body size in bytes",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "serve":
            service = NovaAdaptService(default_config=args.config, db_path=args.db_path)
            run_server(
                host=args.host,
                port=args.port,
                service=service,
                api_token=args.api_token,
                log_requests=args.log_requests,
                rate_limit_rps=max(0.0, float(args.rate_limit_rps)),
                rate_limit_burst=args.rate_limit_burst,
                max_request_body_bytes=max(1, int(args.max_body_bytes)),
                jobs_db_path=str(args.jobs_db_path),
            )
            return

        if args.command == "run":
            service = NovaAdaptService(default_config=args.config, db_path=args.db_path)
            payload = {
                "objective": args.objective,
                "strategy": args.strategy,
                "model": args.model,
                "candidates": args.candidates,
                "fallbacks": args.fallbacks,
                "execute": bool(args.execute),
                "allow_dangerous": bool(args.allow_dangerous),
                "max_actions": max(1, args.max_actions),
            }
            print(json.dumps(service.run(payload), indent=2))
            return

        if args.command == "history":
            service = NovaAdaptService(default_config=_default_config_path(), db_path=args.db_path)
            print(json.dumps(service.history(limit=max(1, args.limit)), indent=2))
            return

        if args.command == "undo":
            service = NovaAdaptService(default_config=_default_config_path(), db_path=args.db_path)
            payload = {
                "id": args.id,
                "execute": bool(args.execute),
                "mark_only": bool(args.mark_only),
            }
            print(json.dumps(service.undo(payload), indent=2))
            return

        if args.command == "check":
            service = NovaAdaptService(default_config=args.config)
            models = [name.strip() for name in args.models.split(",") if name.strip()]
            print(json.dumps(service.check(model_names=models or None, probe_prompt=args.probe), indent=2))
            return

        if args.command == "benchmark":
            service = NovaAdaptService(default_config=args.config, db_path=args.db_path)
            result = run_benchmark(
                run_fn=service.run,
                suite_path=args.suite,
                output_path=args.out,
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "models":
            service = NovaAdaptService(default_config=args.config)
            print(json.dumps(service.models(), indent=2))
            return
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()

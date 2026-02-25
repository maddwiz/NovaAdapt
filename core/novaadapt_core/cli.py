from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .backup import backup_databases, restore_databases
from .benchmark import run_benchmark
from .cleanup import prune_local_state
from .directshell import DirectShellClient
from .mcp_server import NovaAdaptMCPServer
from .native_daemon import NativeExecutionDaemon
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
    default_actions_db = Path.home() / ".novaadapt" / "actions.db"
    default_plans_db = Path(os.getenv("NOVAADAPT_PLANS_DB", str(Path.home() / ".novaadapt" / "plans.db")))
    default_jobs_db = Path(os.getenv("NOVAADAPT_JOBS_DB", str(Path.home() / ".novaadapt" / "jobs.db")))
    default_idempotency_db = Path(
        os.getenv("NOVAADAPT_IDEMPOTENCY_DB", str(Path.home() / ".novaadapt" / "idempotency.db"))
    )
    default_audit_db = Path(os.getenv("NOVAADAPT_AUDIT_DB", str(Path.home() / ".novaadapt" / "events.db")))
    default_backup_dir = Path(os.getenv("NOVAADAPT_BACKUP_DIR", str(Path.home() / ".novaadapt" / "backups")))

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

    events_cmd = sub.add_parser("events", help="Show recent audit events")
    events_cmd.add_argument("--limit", type=int, default=100)
    events_cmd.add_argument("--category", default=None)
    events_cmd.add_argument("--entity-type", default=None)
    events_cmd.add_argument("--entity-id", default=None)
    events_cmd.add_argument("--since-id", type=int, default=None)
    events_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db)

    events_watch_cmd = sub.add_parser("events-watch", help="Wait for new audit events")
    events_watch_cmd.add_argument("--timeout-seconds", type=float, default=30.0)
    events_watch_cmd.add_argument("--interval-seconds", type=float, default=0.25)
    events_watch_cmd.add_argument("--limit", type=int, default=100)
    events_watch_cmd.add_argument("--category", default=None)
    events_watch_cmd.add_argument("--entity-type", default=None)
    events_watch_cmd.add_argument("--entity-id", default=None)
    events_watch_cmd.add_argument("--since-id", type=int, default=None)
    events_watch_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db)

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

    plans_cmd = sub.add_parser("plans", help="List recent approval plans")
    plans_cmd.add_argument("--limit", type=int, default=20)
    plans_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db)

    plan_get_cmd = sub.add_parser("plan-get", help="Fetch a stored approval plan by id")
    plan_get_cmd.add_argument("--id", required=True)
    plan_get_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db)

    plan_create_cmd = sub.add_parser("plan-create", help="Create a pending approval plan from objective")
    plan_create_cmd.add_argument("--config", type=Path, default=_default_config_path())
    plan_create_cmd.add_argument("--db-path", type=Path, default=None)
    plan_create_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db)
    plan_create_cmd.add_argument("--objective", required=True)
    plan_create_cmd.add_argument("--strategy", choices=["single", "vote"], default="single")
    plan_create_cmd.add_argument("--model", default=None)
    plan_create_cmd.add_argument(
        "--candidates",
        default="",
        help="Comma-separated model endpoint names for vote mode",
    )
    plan_create_cmd.add_argument(
        "--fallbacks",
        default="",
        help="Comma-separated fallback model endpoint names for single mode",
    )
    plan_create_cmd.add_argument(
        "--max-actions",
        type=int,
        default=25,
        help="Cap the number of generated plan actions",
    )

    plan_approve_cmd = sub.add_parser("plan-approve", help="Approve plan and optionally execute actions")
    plan_approve_cmd.add_argument("--id", required=True)
    plan_approve_cmd.add_argument("--db-path", type=Path, default=None)
    plan_approve_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db)
    plan_approve_cmd.add_argument(
        "--no-execute",
        action="store_true",
        help="Mark approved without executing plan actions",
    )
    plan_approve_cmd.add_argument(
        "--allow-dangerous",
        action="store_true",
        help="Allow potentially destructive actions during execution",
    )
    plan_approve_cmd.add_argument(
        "--max-actions",
        type=int,
        default=25,
        help="Cap number of actions executed from the stored plan",
    )

    plan_reject_cmd = sub.add_parser("plan-reject", help="Reject a plan with optional reason")
    plan_reject_cmd.add_argument("--id", required=True)
    plan_reject_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db)
    plan_reject_cmd.add_argument("--reason", default=None)

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

    directshell_check_cmd = sub.add_parser(
        "directshell-check",
        help="Probe DirectShell execution transport readiness",
    )
    directshell_check_cmd.add_argument(
        "--transport",
        choices=["native", "subprocess", "http", "daemon"],
        default=None,
        help="Optional DirectShell transport override for probe",
    )
    directshell_check_cmd.add_argument(
        "--native-fallback-transport",
        choices=["subprocess", "http", "daemon"],
        default=None,
        help="Fallback transport used when native transport action execution fails",
    )
    directshell_check_cmd.add_argument(
        "--http-token",
        default=None,
        help="Optional DirectShell HTTP token override",
    )
    directshell_check_cmd.add_argument(
        "--daemon-token",
        default=None,
        help="Optional DirectShell daemon token override",
    )
    directshell_check_cmd.add_argument(
        "--timeout-seconds",
        type=int,
        default=5,
        help="Probe timeout in seconds",
    )

    native_daemon_cmd = sub.add_parser(
        "native-daemon",
        help="Run built-in Native DirectShell-compatible daemon",
    )
    native_daemon_cmd.add_argument(
        "--socket",
        default=os.getenv("DIRECTSHELL_DAEMON_SOCKET", "/tmp/directshell.sock"),
        help="Unix socket path (set empty string to use TCP mode)",
    )
    native_daemon_cmd.add_argument(
        "--host",
        default=os.getenv("DIRECTSHELL_DAEMON_HOST", "127.0.0.1"),
        help="TCP host when --socket is empty",
    )
    native_daemon_cmd.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("DIRECTSHELL_DAEMON_PORT", "8766")),
        help="TCP port when --socket is empty",
    )
    native_daemon_cmd.add_argument(
        "--daemon-token",
        default=os.getenv("DIRECTSHELL_DAEMON_TOKEN", ""),
        help="Optional shared token required by daemon requests",
    )
    native_daemon_cmd.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Per-connection timeout in seconds",
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

    backup_cmd = sub.add_parser("backup", help="Create timestamped SQLite backups for local NovaAdapt state")
    backup_cmd.add_argument(
        "--out-dir",
        type=Path,
        default=default_backup_dir,
        help="Output directory for backup snapshots (default: ~/.novaadapt/backups)",
    )
    backup_cmd.add_argument(
        "--timestamp",
        default=None,
        help="Optional UTC timestamp suffix used in backup filenames (YYYYMMDDTHHMMSSZ)",
    )
    backup_cmd.add_argument(
        "--db-path",
        type=Path,
        default=default_actions_db,
        help="Path to actions database",
    )
    backup_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db, help="Path to plans database")
    backup_cmd.add_argument("--jobs-db-path", type=Path, default=default_jobs_db, help="Path to jobs database")
    backup_cmd.add_argument(
        "--idempotency-db-path",
        type=Path,
        default=default_idempotency_db,
        help="Path to idempotency database",
    )
    backup_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db, help="Path to audit database")

    restore_cmd = sub.add_parser(
        "restore",
        help="Restore SQLite databases from backup snapshots (archives existing DBs before overwrite)",
    )
    restore_cmd.add_argument(
        "--from-dir",
        type=Path,
        default=default_backup_dir,
        help="Directory containing backup snapshots (default: ~/.novaadapt/backups)",
    )
    restore_cmd.add_argument(
        "--timestamp",
        default=None,
        help="Optional snapshot timestamp (YYYYMMDDTHHMMSSZ); defaults to latest discovered snapshot",
    )
    restore_cmd.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Optional output directory for pre-restore safety snapshots of current DBs",
    )
    restore_cmd.add_argument(
        "--db-path",
        type=Path,
        default=default_actions_db,
        help="Path to actions database",
    )
    restore_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db, help="Path to plans database")
    restore_cmd.add_argument("--jobs-db-path", type=Path, default=default_jobs_db, help="Path to jobs database")
    restore_cmd.add_argument(
        "--idempotency-db-path",
        type=Path,
        default=default_idempotency_db,
        help="Path to idempotency database",
    )
    restore_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db, help="Path to audit database")

    prune_cmd = sub.add_parser("prune", help="Prune stale SQLite records from local NovaAdapt state")
    prune_cmd.add_argument("--db-path", type=Path, default=default_actions_db, help="Path to actions database")
    prune_cmd.add_argument("--plans-db-path", type=Path, default=default_plans_db, help="Path to plans database")
    prune_cmd.add_argument("--jobs-db-path", type=Path, default=default_jobs_db, help="Path to jobs database")
    prune_cmd.add_argument(
        "--idempotency-db-path",
        type=Path,
        default=default_idempotency_db,
        help="Path to idempotency database",
    )
    prune_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db, help="Path to audit database")
    prune_cmd.add_argument(
        "--actions-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_ACTION_RETENTION_SECONDS", str(30 * 24 * 60 * 60))),
        help="Delete action-log rows older than this retention window (0 disables deletion)",
    )
    prune_cmd.add_argument(
        "--plans-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_PLANS_RETENTION_SECONDS", str(30 * 24 * 60 * 60))),
        help="Delete terminal plan rows older than this retention window (0 disables deletion)",
    )
    prune_cmd.add_argument(
        "--jobs-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_JOBS_RETENTION_SECONDS", str(30 * 24 * 60 * 60))),
        help="Delete terminal job rows older than this retention window (0 disables deletion)",
    )
    prune_cmd.add_argument(
        "--idempotency-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_IDEMPOTENCY_RETENTION_SECONDS", str(7 * 24 * 60 * 60))),
        help="Delete idempotency rows older than this retention window (0 disables deletion)",
    )
    prune_cmd.add_argument(
        "--audit-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_AUDIT_RETENTION_SECONDS", str(30 * 24 * 60 * 60))),
        help="Delete audit rows older than this retention window (0 disables deletion)",
    )

    serve_cmd = sub.add_parser("serve", help="Run NovaAdapt HTTP API server")
    serve_cmd.add_argument("--config", type=Path, default=_default_config_path())
    serve_cmd.add_argument("--db-path", type=Path, default=None)
    serve_cmd.add_argument(
        "--jobs-db-path",
        type=Path,
        default=default_jobs_db,
        help="Path to persisted async jobs SQLite database",
    )
    serve_cmd.add_argument(
        "--plans-db-path",
        type=Path,
        default=default_plans_db,
        help="Path to persisted approval plans SQLite database",
    )
    serve_cmd.add_argument(
        "--idempotency-db-path",
        type=Path,
        default=default_idempotency_db,
        help="Path to idempotency key SQLite database",
    )
    serve_cmd.add_argument(
        "--audit-db-path",
        type=Path,
        default=default_audit_db,
        help="Path to audit events SQLite database",
    )
    serve_cmd.add_argument(
        "--idempotency-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_IDEMPOTENCY_RETENTION_SECONDS", str(7 * 24 * 60 * 60))),
        help="Retention window for persisted idempotency records (0 disables expiry)",
    )
    serve_cmd.add_argument(
        "--idempotency-cleanup-interval-seconds",
        type=float,
        default=float(os.getenv("NOVAADAPT_IDEMPOTENCY_CLEANUP_INTERVAL_SECONDS", "60")),
        help="How often idempotency expiry cleanup runs during writes",
    )
    serve_cmd.add_argument(
        "--audit-retention-seconds",
        type=int,
        default=int(os.getenv("NOVAADAPT_AUDIT_RETENTION_SECONDS", str(30 * 24 * 60 * 60))),
        help="Retention window for persisted audit events (0 disables expiry)",
    )
    serve_cmd.add_argument(
        "--audit-cleanup-interval-seconds",
        type=float,
        default=float(os.getenv("NOVAADAPT_AUDIT_CLEANUP_INTERVAL_SECONDS", "60")),
        help="How often audit expiry cleanup runs during writes",
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
        "--trusted-proxy-cidrs",
        default=os.getenv("NOVAADAPT_TRUSTED_PROXY_CIDRS", ""),
        help="Comma-separated trusted reverse proxy CIDRs/IPs allowed to set X-Forwarded-For",
    )
    serve_cmd.add_argument(
        "--max-body-bytes",
        type=int,
        default=int(os.getenv("NOVAADAPT_MAX_BODY_BYTES", str(1 << 20))),
        help="Maximum HTTP request body size in bytes",
    )
    serve_cmd.add_argument(
        "--otel-enabled",
        action="store_true",
        default=str(os.getenv("NOVAADAPT_OTEL_ENABLED", "")).strip().lower() in {"1", "true", "yes"},
        help="Enable OpenTelemetry tracing export from core API",
    )
    serve_cmd.add_argument(
        "--otel-service-name",
        default=os.getenv("NOVAADAPT_OTEL_SERVICE_NAME", "novaadapt-core"),
        help="OpenTelemetry service.name value when tracing is enabled",
    )
    serve_cmd.add_argument(
        "--otel-exporter-endpoint",
        default=os.getenv("NOVAADAPT_OTEL_EXPORTER_ENDPOINT", ""),
        help="Optional OTLP HTTP exporter endpoint (for example http://127.0.0.1:4318/v1/traces)",
    )

    mcp_cmd = sub.add_parser("mcp", help="Run MCP-compatible stdio server")
    mcp_cmd.add_argument("--config", type=Path, default=_default_config_path())
    mcp_cmd.add_argument("--db-path", type=Path, default=None)
    mcp_cmd.add_argument("--audit-db-path", type=Path, default=default_audit_db)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "serve":
            service = NovaAdaptService(
                default_config=args.config,
                db_path=args.db_path,
                plans_db_path=args.plans_db_path,
            )
            run_server(
                host=args.host,
                port=args.port,
                service=service,
                api_token=args.api_token,
                log_requests=args.log_requests,
                rate_limit_rps=max(0.0, float(args.rate_limit_rps)),
                rate_limit_burst=args.rate_limit_burst,
                trusted_proxy_cidrs=_parse_csv(args.trusted_proxy_cidrs),
                idempotency_retention_seconds=max(0, int(args.idempotency_retention_seconds)),
                idempotency_cleanup_interval_seconds=max(0.0, float(args.idempotency_cleanup_interval_seconds)),
                audit_retention_seconds=max(0, int(args.audit_retention_seconds)),
                audit_cleanup_interval_seconds=max(0.0, float(args.audit_cleanup_interval_seconds)),
                otel_enabled=bool(args.otel_enabled),
                otel_service_name=str(args.otel_service_name or "novaadapt-core"),
                otel_exporter_endpoint=(str(args.otel_exporter_endpoint).strip() or None),
                max_request_body_bytes=max(1, int(args.max_body_bytes)),
                jobs_db_path=str(args.jobs_db_path),
                idempotency_db_path=str(args.idempotency_db_path),
                audit_db_path=str(args.audit_db_path),
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

        if args.command == "plan-create":
            service = NovaAdaptService(
                default_config=args.config,
                db_path=args.db_path,
                plans_db_path=args.plans_db_path,
            )
            payload = {
                "objective": args.objective,
                "strategy": args.strategy,
                "model": args.model,
                "candidates": args.candidates,
                "fallbacks": args.fallbacks,
                "max_actions": max(1, args.max_actions),
            }
            print(json.dumps(service.create_plan(payload), indent=2))
            return

        if args.command == "plans":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                plans_db_path=args.plans_db_path,
            )
            print(json.dumps(service.list_plans(limit=max(1, args.limit)), indent=2))
            return

        if args.command == "plan-get":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                plans_db_path=args.plans_db_path,
            )
            item = service.get_plan(args.id)
            if item is None:
                raise ValueError(f"Plan not found: {args.id}")
            print(json.dumps(item, indent=2))
            return

        if args.command == "plan-approve":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                db_path=args.db_path,
                plans_db_path=args.plans_db_path,
            )
            payload = {
                "execute": not bool(args.no_execute),
                "allow_dangerous": bool(args.allow_dangerous),
                "max_actions": max(1, args.max_actions),
            }
            print(json.dumps(service.approve_plan(args.id, payload), indent=2))
            return

        if args.command == "plan-reject":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                plans_db_path=args.plans_db_path,
            )
            print(json.dumps(service.reject_plan(args.id, reason=args.reason), indent=2))
            return

        if args.command == "history":
            service = NovaAdaptService(default_config=_default_config_path(), db_path=args.db_path)
            print(json.dumps(service.history(limit=max(1, args.limit)), indent=2))
            return

        if args.command == "events":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                audit_db_path=args.audit_db_path,
            )
            print(
                json.dumps(
                    service.events(
                        limit=max(1, args.limit),
                        category=(str(args.category).strip() if args.category else None),
                        entity_type=(str(args.entity_type).strip() if args.entity_type else None),
                        entity_id=(str(args.entity_id).strip() if args.entity_id else None),
                        since_id=args.since_id,
                    ),
                    indent=2,
                )
            )
            return

        if args.command == "events-watch":
            service = NovaAdaptService(
                default_config=_default_config_path(),
                audit_db_path=args.audit_db_path,
            )
            print(
                json.dumps(
                    service.events_wait(
                        timeout_seconds=float(args.timeout_seconds),
                        interval_seconds=float(args.interval_seconds),
                        limit=max(1, args.limit),
                        category=(str(args.category).strip() if args.category else None),
                        entity_type=(str(args.entity_type).strip() if args.entity_type else None),
                        entity_id=(str(args.entity_id).strip() if args.entity_id else None),
                        since_id=args.since_id,
                    ),
                    indent=2,
                )
            )
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

        if args.command == "directshell-check":
            client = DirectShellClient(
                transport=args.transport,
                http_token=args.http_token,
                daemon_token=args.daemon_token,
                native_fallback_transport=args.native_fallback_transport,
                timeout_seconds=max(1, int(args.timeout_seconds)),
            )
            print(json.dumps(client.probe(), indent=2))
            return

        if args.command == "native-daemon":
            daemon = NativeExecutionDaemon(
                socket_path=str(args.socket or ""),
                host=str(args.host or "127.0.0.1"),
                port=max(1, int(args.port)),
                daemon_token=str(args.daemon_token or "").strip() or None,
                timeout_seconds=max(1, int(args.timeout_seconds)),
            )
            daemon.serve_forever()
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

        if args.command == "backup":
            result = backup_databases(
                out_dir=args.out_dir,
                timestamp=args.timestamp,
                databases={
                    "actions": args.db_path,
                    "plans": args.plans_db_path,
                    "jobs": args.jobs_db_path,
                    "idempotency": args.idempotency_db_path,
                    "audit": args.audit_db_path,
                },
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "restore":
            result = restore_databases(
                backups_dir=args.from_dir,
                timestamp=args.timestamp,
                archive_dir=args.archive_dir,
                databases={
                    "actions": args.db_path,
                    "plans": args.plans_db_path,
                    "jobs": args.jobs_db_path,
                    "idempotency": args.idempotency_db_path,
                    "audit": args.audit_db_path,
                },
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "prune":
            result = prune_local_state(
                actions_db_path=args.db_path,
                plans_db_path=args.plans_db_path,
                jobs_db_path=args.jobs_db_path,
                idempotency_db_path=args.idempotency_db_path,
                audit_db_path=args.audit_db_path,
                actions_retention_seconds=max(0, int(args.actions_retention_seconds)),
                plans_retention_seconds=max(0, int(args.plans_retention_seconds)),
                jobs_retention_seconds=max(0, int(args.jobs_retention_seconds)),
                idempotency_retention_seconds=max(0, int(args.idempotency_retention_seconds)),
                audit_retention_seconds=max(0, int(args.audit_retention_seconds)),
            )
            print(json.dumps(result, indent=2))
            return

        if args.command == "mcp":
            service = NovaAdaptService(
                default_config=args.config,
                db_path=args.db_path,
                audit_db_path=args.audit_db_path,
            )
            server = NovaAdaptMCPServer(service=service)
            server.serve_stdio()
            return

        if args.command == "models":
            service = NovaAdaptService(default_config=args.config)
            print(json.dumps(service.models(), indent=2))
            return
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

def _parse_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


if __name__ == "__main__":
    main()

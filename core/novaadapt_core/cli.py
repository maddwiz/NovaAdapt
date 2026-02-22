from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from novaadapt_shared import ModelRouter

from .agent import NovaAdaptAgent


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
    run_cmd.add_argument("--objective", required=True)
    run_cmd.add_argument("--strategy", choices=["single", "vote"], default="single")
    run_cmd.add_argument("--model", default=None)
    run_cmd.add_argument(
        "--candidates",
        default="",
        help="Comma-separated model endpoint names for vote mode",
    )
    run_cmd.add_argument(
        "--execute",
        action="store_true",
        help="Execute actions via DirectShell (default is dry-run preview)",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    router = ModelRouter.from_config_file(args.config)

    if args.command == "models":
        models = [
            {
                "name": item.name,
                "model": item.model,
                "provider": item.provider,
                "base_url": item.base_url,
            }
            for item in router.list_models()
        ]
        print(json.dumps(models, indent=2))
        return

    candidate_models = [name.strip() for name in args.candidates.split(",") if name.strip()]

    agent = NovaAdaptAgent(router=router)
    outcome = agent.run_objective(
        objective=args.objective,
        strategy=args.strategy,
        model_name=args.model,
        candidate_models=candidate_models or None,
        dry_run=not args.execute,
    )
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    main()

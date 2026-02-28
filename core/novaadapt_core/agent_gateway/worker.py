from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .job_queue import GatewayJobQueue, JobRecord


RunnerFn = Callable[[JobRecord], dict[str, Any]]


def run_agent_job_in_process(job: JobRecord) -> dict[str, Any]:
    from novaprime.kernel.entrypoint import run_agent_job
    from novaprime.kernel.schemas import AgentJob

    payload = dict(job.payload)
    objective = str(payload.get("objective") or payload.get("input_text") or "").strip()
    if not objective:
        raise ValueError("job payload requires 'objective' or 'input_text'")

    agent_job = AgentJob.from_dict(
        {
            "job_id": job.job_id,
            "session_id": str(payload.get("session_id") or ""),
            "source": str(payload.get("source") or "novaagent-gateway"),
            "workspace_id": job.workspace_id,
            "profile_name": job.profile_name,
            "reply_to": dict(job.reply_to),
            "parent_job_id": job.parent_job_id,
            "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
            "input_text": objective,
        }
    )
    router = payload.get("router")
    if router is None:
        raise RuntimeError("job payload missing in-process router reference")
    result = run_agent_job(agent_job, router=router, profile=job.profile_name)
    if hasattr(result, "to_dict"):
        parsed = result.to_dict()
        if isinstance(parsed, dict):
            return parsed
    if isinstance(result, dict):
        return result
    return {"ok": False, "error": "unsupported run_agent_job result"}


@dataclass
class WorkerOutcome:
    processed: bool
    job_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class GatewayWorker:
    def __init__(
        self,
        *,
        queue: GatewayJobQueue,
        runner: RunnerFn | None = None,
        retry_delay_seconds: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        self.queue = queue
        self.runner = runner or run_agent_job_in_process
        self.retry_delay_seconds = max(1.0, float(retry_delay_seconds))
        self.max_attempts = max(1, int(max_attempts))

    def process_once(self) -> WorkerOutcome:
        job = self.queue.claim_next()
        if job is None:
            return WorkerOutcome(processed=False)
        try:
            result = self.runner(job)
            self.queue.mark_done(job.job_id)
            return WorkerOutcome(processed=True, job_id=job.job_id, result=result if isinstance(result, dict) else {})
        except Exception as exc:
            self.queue.mark_failed(
                job.job_id,
                retry_delay_seconds=self.retry_delay_seconds,
                max_attempts=self.max_attempts,
            )
            return WorkerOutcome(processed=True, job_id=job.job_id, error=str(exc))

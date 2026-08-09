from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4


@dataclass
class Job:
    id: str
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None


@dataclass
class LocalJobRunner:
    jobs: dict[str, Job] = field(default_factory=dict)

    def start(self, fn: Callable[[Job], Any], *, job_id: str | None = None) -> Job:
        job = Job(id=job_id or uuid4().hex[:12])
        self.jobs[job.id] = job

        def run() -> None:
            job.status = "running"
            try:
                job.result = fn(job)
                job.status = "completed"
                job.progress = 1.0
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = str(exc)

        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Job:
        return self.jobs[job_id]

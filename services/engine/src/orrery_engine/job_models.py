"""Mutable reconstruction job state and lifecycle exceptions."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from orrery_engine.generated.contract import (
    JobArtifact,
    JobError,
    ReconstructJobRequest,
)


class JobCanceledError(RuntimeError):
    pass


class JobFailureError(RuntimeError):
    def __init__(self, error: JobError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass
class JobRecord:
    request: ReconstructJobRequest
    callback_secret: str | None
    status_url: str
    status: Literal["queued", "running", "failed", "canceled"] = "queued"
    current_stage: str | None = None
    progress: float = 0.0
    artifacts: list[JobArtifact] = field(default_factory=list[JobArtifact])
    error: JobError | None = None
    completed_stages: set[str] = field(default_factory=set[str])
    stage_runtimes: dict[str, float] = field(default_factory=dict[str, float])
    seq: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def job_id(self) -> UUID:
        return self.request.job_id


__all__ = ["JobCanceledError", "JobFailureError", "JobRecord"]

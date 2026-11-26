"""Filesystem checkpoint serialization for asynchronous reconstruction jobs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from orrery_engine.generated.contract import (
    JobArtifact,
    JobError,
    ReconstructJobRequest,
)


class CheckpointRecord(Protocol):
    request: ReconstructJobRequest
    status_url: str
    status: Literal["queued", "running", "failed", "canceled"]
    current_stage: str | None
    progress: float
    artifacts: list[JobArtifact]
    error: JobError | None
    completed_stages: set[str]
    stage_runtimes: dict[str, float]
    seq: int


@dataclass(frozen=True)
class LoadedCheckpoint:
    request: ReconstructJobRequest
    status_url: str
    status: Literal["queued", "running", "failed", "canceled"]
    current_stage: str | None
    progress: float
    artifacts: list[JobArtifact]
    error: JobError | None
    completed_stages: set[str]
    stage_runtimes: dict[str, float]
    seq: int


def write_checkpoint(record: CheckpointRecord, job_dir: Path) -> None:
    path = job_dir / "checkpoint.json"
    payload = {
        "request": record.request.model_dump(by_alias=True, mode="json"),
        "statusUrl": record.status_url,
        "status": record.status,
        "currentStage": record.current_stage,
        "progress": record.progress,
        "artifacts": [item.model_dump(by_alias=True, mode="json") for item in record.artifacts],
        "error": (
            record.error.model_dump(by_alias=True, mode="json", exclude_none=True)
            if record.error
            else None
        ),
        "completedStages": sorted(record.completed_stages),
        "stageRuntimes": record.stage_runtimes,
        "seq": record.seq,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    os.replace(temporary, path)


def load_checkpoints(jobs_dir: Path) -> tuple[LoadedCheckpoint, ...]:
    loaded: list[LoadedCheckpoint] = []
    for path in jobs_dir.glob("*/checkpoint.json"):
        try:
            raw = json.loads(path.read_text())
            request = ReconstructJobRequest.model_validate(raw["request"])
            status = "canceled" if raw["status"] in {"queued", "running"} else raw["status"]
            error = JobError.model_validate(raw["error"]) if raw.get("error") else None
            if status == "canceled" and error is None:
                error = JobError.model_validate(
                    {
                        "code": "canceled",
                        "message": "The engine restarted before the job completed.",
                        "retryable": False,
                    }
                )
            loaded.append(
                LoadedCheckpoint(
                    request,
                    str(raw["statusUrl"]),
                    status,
                    raw.get("currentStage"),
                    float(raw.get("progress", 0.0)),
                    [JobArtifact.model_validate(item) for item in raw.get("artifacts", [])],
                    error,
                    set(raw.get("completedStages", [])),
                    {str(key): float(value) for key, value in raw.get("stageRuntimes", {}).items()},
                    int(raw.get("seq", 0)),
                )
            )
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return tuple(loaded)


__all__ = ["LoadedCheckpoint", "load_checkpoints", "write_checkpoint"]

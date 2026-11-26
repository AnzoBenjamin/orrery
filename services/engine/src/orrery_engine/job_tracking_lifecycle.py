"""Tracking lifecycle mixin kept separate from the bounded core job manager."""

# The mixin intentionally operates on the job manager's protected lifecycle surface.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID

from orrery_engine.generated.contract import AnalysisArtifacts, JobArtifact
from orrery_engine.job_artifacts import build_analysis_artifact
from orrery_engine.job_camera_motion import CameraMotionStageOutput
from orrery_engine.job_ingest import load_ingest_manifests
from orrery_engine.job_models import JobRecord
from orrery_engine.job_seeding import SeedingStageOutput
from orrery_engine.job_tracking import TrackingStageOutput, run_tracking_stage
from orrery_engine.settings import Settings


class _TrackingLifecycleHost(Protocol):
    _settings: Settings

    def _job_dir(self, job_id: UUID) -> Path: ...

    def _checkpoint(self, record: JobRecord) -> None: ...

    def _emit(self, record: JobRecord, event_type: str, payload: object) -> None: ...

    def _progress(self, record: JobRecord, fraction: float, description: str) -> None: ...

    def _check_canceled(self, record: JobRecord) -> None: ...

    def _upload_artifact(self, record: JobRecord, artifact: AnalysisArtifacts) -> JobArtifact: ...

    def _complete_stage(
        self, record: JobRecord, stage: str, runtime_ms: float, descriptor: JobArtifact
    ) -> None: ...


class TrackingLifecycleMixin:
    """Run tracking through the same checkpoint/upload/callback transaction as prior stages."""

    def _run_tracking(
        self: _TrackingLifecycleHost,
        record: JobRecord,
        camera: CameraMotionStageOutput,
        seeding: SeedingStageOutput,
    ) -> TrackingStageOutput:
        with record.lock:
            record.current_stage = "tracking"
            record.progress = 0.0
            self._checkpoint(record)
        self._emit(record, "stage_started", {"stage": "tracking"})
        ingest = load_ingest_manifests(self._job_dir(record.job_id))
        output = run_tracking_stage(
            record.request,
            self._job_dir(record.job_id),
            self._settings,
            camera,
            seeding,
            ingest_manifests=ingest,
            check_canceled=lambda: self._check_canceled(record),
            progress=lambda fraction, description: self._progress(record, fraction, description),
        )
        artifact = build_analysis_artifact(
            self._settings.engine_version,
            record,
            ingest=list(ingest),
            camera=camera,
            seeding=seeding,
            tracking=output,
            pending_runtime=("tracking", output.runtime_ms),
        )
        descriptor = self._upload_artifact(record, artifact)
        self._complete_stage(record, "tracking", output.runtime_ms, descriptor)
        return output


__all__ = ["TrackingLifecycleMixin"]

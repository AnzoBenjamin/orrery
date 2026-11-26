"""Construction of versioned aggregate reconstruction artifacts from completed real stages."""

from __future__ import annotations

from typing import Protocol

from orrery_engine.generated.contract import AnalysisArtifacts
from orrery_engine.job_camera_motion import CameraMotionStageOutput
from orrery_engine.job_seeding import SeedingStageOutput
from orrery_engine.job_tracking import TrackingStageOutput


class RuntimeRecord(Protocol):
    stage_runtimes: dict[str, float]


def build_analysis_artifact(
    engine_version: str,
    record: RuntimeRecord,
    *,
    ingest: list[dict[str, object]],
    camera: CameraMotionStageOutput | None = None,
    seeding: SeedingStageOutput | None = None,
    tracking: TrackingStageOutput | None = None,
    pending_runtime: tuple[str, float] | None = None,
) -> AnalysisArtifacts:
    """Validate the aggregate artifact without inventing outputs for later stages."""
    runtimes = dict(record.stage_runtimes)
    if pending_runtime is not None:
        runtimes[pending_runtime[0]] = pending_runtime[1]
    return AnalysisArtifacts.model_validate(
        {
            "format": "orrery.engine.analysis-artifacts",
            "schemaVersion": 1,
            "engineVersion": engine_version,
            "tracks": list(tracking.tracks) if tracking else [],
            "cameraMotion": list(camera.motions) if camera else [],
            "cameraMotionAnalysis": list(camera.manifests) if camera else None,
            "seedingAnalysis": list(seeding.manifests) if seeding else None,
            "trackingAnalysis": list(tracking.manifests) if tracking else None,
            "bodies": [],
            "joints": [],
            "parameters": [],
            "diagnosis": [],
            "resurrection": [],
            "stageRuntimes": [
                {"stage": stage, "runtimeMs": runtime} for stage, runtime in runtimes.items()
            ],
            "ingest": ingest,
        }
    )


__all__ = ["build_analysis_artifact"]

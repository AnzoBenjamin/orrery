"""Camera-motion stage orchestration and durable local stage outputs."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from orrery_engine.camera_motion import CameraMotionConfig, analyze_camera_motion
from orrery_engine.generated.contract import ReconstructJobRequest
from orrery_engine.settings import Settings

CancelCheck = Callable[[], None]
ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class CameraMotionStageOutput:
    motions: tuple[dict[str, object], ...]
    manifests: tuple[dict[str, object], ...]
    runtime_ms: float
    requires_spatial: bool
    routing_reasons: tuple[str, ...]


def run_camera_motion_stage(
    request: ReconstructJobRequest,
    job_dir: Path,
    settings: Settings,
    *,
    check_canceled: CancelCheck,
    progress: ProgressCallback,
) -> CameraMotionStageOutput:
    """Estimate every footage item and persist contract-ready stage data."""
    started = time.monotonic()
    motions: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    reasons: list[str] = []
    count = len(request.inputs.footage)
    config = CameraMotionConfig(
        ransac_threshold_px=settings.camera_motion_ransac_threshold_px,
        parallax_threshold_px=settings.camera_motion_parallax_threshold_px,
        min_matches=settings.camera_motion_min_matches,
        preview_long_side=settings.proxy_long_side,
    )
    for index, footage in enumerate(request.inputs.footage):
        check_canceled()
        ingest_dir = job_dir / "ingest" / f"{index:02d}"
        stage_dir = job_dir / "camera_motion" / f"{index:02d}"

        def item_progress(fraction: float, description: str, item_index: int = index) -> None:
            progress((item_index + fraction) / count, description)

        result = analyze_camera_motion(
            ingest_dir / "analysis.mkv",
            stage_dir,
            footage_id=footage.footage_id,
            config=config,
            check_canceled=check_canceled,
            progress=item_progress,
        )
        motions.extend(result.motions)
        manifests.append(result.manifest)
        if result.estimate.routing_reason is not None:
            reasons.append(result.estimate.routing_reason)
    output = CameraMotionStageOutput(
        tuple(motions),
        tuple(manifests),
        (time.monotonic() - started) * 1000,
        bool(reasons),
        tuple(reasons),
    )
    _write_json(
        job_dir / "camera_motion" / "manifest.json",
        {
            "motions": output.motions,
            "analysis": output.manifests,
            "requiresSpatial": output.requires_spatial,
            "routingReasons": output.routing_reasons,
        },
    )
    return output


def load_camera_motion_stage(job_dir: Path) -> CameraMotionStageOutput:
    value: object = json.loads((job_dir / "camera_motion" / "manifest.json").read_text())
    if not isinstance(value, dict):
        raise ValueError("the camera-motion checkpoint manifest is invalid")
    value = cast(dict[str, object], value)
    motions = value.get("motions")
    analysis = value.get("analysis")
    reasons = value.get("routingReasons")
    if (
        not isinstance(motions, list)
        or not isinstance(analysis, list)
        or not isinstance(reasons, list)
    ):
        raise ValueError("the camera-motion checkpoint fields are invalid")
    motion_items = cast(list[object], motions)
    analysis_items = cast(list[object], analysis)
    reason_items = cast(list[object], reasons)
    return CameraMotionStageOutput(
        _dictionary_items(motion_items),
        _dictionary_items(analysis_items),
        0.0,
        bool(value.get("requiresSpatial")),
        tuple(str(item) for item in reason_items),
    )


def _dictionary_items(value: object) -> tuple[dict[str, object], ...]:
    items = cast(list[object], value)
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("the camera-motion checkpoint entries are invalid")
    return tuple(cast(dict[str, object], item) for item in items)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    os.replace(temporary, path)


__all__ = [
    "CameraMotionStageOutput",
    "load_camera_motion_stage",
    "run_camera_motion_stage",
]

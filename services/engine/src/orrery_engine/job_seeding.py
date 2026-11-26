"""Seeding-stage orchestration and durable versioned stage artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np

from orrery_engine.camera_motion import decode_frames
from orrery_engine.generated.contract import ReconstructJobRequest
from orrery_engine.ingest import full_resolution_frames
from orrery_engine.job_camera_motion import CameraMotionStageOutput
from orrery_engine.seeding import (
    SeedingConfig,
    UserPointInput,
    detect_hole_seeds,
    merge_seed_sources,
    seed_moving_regions,
    user_annotation_seeds,
)
from orrery_engine.seeding_types import Image, Matrix, RegionCoverage, SeedPoint
from orrery_engine.settings import Settings

CancelCheck = Callable[[], None]
ProgressCallback = Callable[[float, str], None]


class SeedingError(RuntimeError):
    """Normalized footage or stage provenance cannot produce valid track seeds."""


@dataclass(frozen=True)
class SeedingStageOutput:
    manifests: tuple[dict[str, object], ...]
    runtime_ms: float


def run_seeding_stage(
    request: ReconstructJobRequest,
    job_dir: Path,
    settings: Settings,
    camera: CameraMotionStageOutput,
    *,
    ingest_manifests: tuple[dict[str, object], ...],
    check_canceled: CancelCheck,
    progress: ProgressCallback,
) -> SeedingStageOutput:
    """Seed every footage item and persist complete source, scale, and coverage provenance."""
    started = time.monotonic()
    manifests: list[dict[str, object]] = []
    count = len(request.inputs.footage)
    config = SeedingConfig(
        max_points=settings.seeding_max_points,
        grid_size_px=settings.seeding_grid_size_px,
        per_cell_cap=settings.seeding_per_cell_cap,
        min_region_pixels=settings.seeding_min_region_pixels,
        reseed_coverage_threshold=settings.seeding_coverage_threshold,
    )
    for index, footage in enumerate(request.inputs.footage):
        check_canceled()
        progress(index / count, f"Finding moving regions in footage {index + 1} of {count}.")
        ingest_dir = job_dir / "ingest" / f"{index:02d}"
        output_dir = job_dir / "seeding" / f"{index:02d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        frames, _ = decode_frames(ingest_dir / "analysis.mkv", check_canceled)
        matrices = _motion_matrices(camera, footage.footage_id, len(frames))
        estimate = seed_moving_regions(
            frames,
            matrices,
            config=config,
            check_canceled=check_canceled,
        )
        ingest = ingest_manifests[index]
        source_size = (_integer(ingest, "displayWidth"), _integer(ingest, "displayHeight"))
        analysis_size = (frames[0].shape[1], frames[0].shape[0])
        progress(
            (index + 0.55) / count,
            f"Detecting full-resolution holes in footage {index + 1} of {count}.",
        )
        full_frames = _full_keyframes(
            ingest_dir / "source",
            ingest,
            estimate.keyframe_indices,
            check_canceled,
        )
        holes = detect_hole_seeds(full_frames, analysis_size=analysis_size)
        annotations = tuple(
            UserPointInput(
                item.annotation_id,
                item.kind,
                item.frame_index,
                item.point.x_px,
                item.point.y_px,
            )
            for item in (request.inputs.annotations or ())
            if item.footage_id == footage.footage_id
        )
        if any(item.frame_index >= len(frames) for item in annotations):
            raise SeedingError("A user point annotation references a frame outside the footage.")
        users = user_annotation_seeds(
            annotations,
            source_size=source_size,
            analysis_size=analysis_size,
        )
        points = merge_seed_sources(users, holes, estimate.points)
        mask_path = output_dir / "moving-mask.png"
        encoded, content = cv2.imencode(".png", estimate.moving_mask)
        if not encoded:
            raise SeedingError("OpenCV could not encode the moving-region mask.")
        mask_path.write_bytes(content.tobytes())
        manifest = _footage_manifest(
            footage.footage_id,
            source_size=source_size,
            analysis_size=analysis_size,
            keyframes=estimate.keyframe_indices,
            mask_path=mask_path,
            points=points,
            coverage=estimate.coverage,
            settings=settings,
        )
        manifests.append(manifest)
        progress((index + 1) / count, f"Track seeds selected for footage {index + 1} of {count}.")
    output = SeedingStageOutput(tuple(manifests), (time.monotonic() - started) * 1000)
    _write_json(job_dir / "seeding" / "manifest.json", list(output.manifests))
    return output


def load_seeding_stage(job_dir: Path) -> SeedingStageOutput:
    value: object = json.loads((job_dir / "seeding" / "manifest.json").read_text())
    if not isinstance(value, list):
        raise ValueError("the seeding checkpoint manifest is invalid")
    items = cast(list[object], value)
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("the seeding checkpoint manifest is invalid")
    return SeedingStageOutput(tuple(cast(dict[str, object], item) for item in items), 0.0)


def _motion_matrices(
    camera: CameraMotionStageOutput, footage_id: str, frame_count: int
) -> tuple[Matrix, ...]:
    selected = sorted(
        (item for item in camera.motions if item.get("footageId") == footage_id),
        key=lambda item: int(cast(int, item["frameIndex"])),
    )
    if len(selected) != frame_count:
        raise SeedingError("Camera-motion and normalized frame counts do not match.")
    matrices: list[Matrix] = []
    for item in selected:
        raw = item.get("referenceToFrame")
        if not isinstance(raw, list):
            raise SeedingError("A camera-motion homography is malformed.")
        values = cast(list[object], raw)
        if len(values) != 9:  # noqa: PLR2004
            raise SeedingError("A camera-motion homography is malformed.")
        matrix = np.asarray(values, dtype=np.float64).reshape(3, 3)
        if not np.all(np.isfinite(matrix)):
            raise SeedingError("A camera-motion homography contains non-finite values.")
        matrices.append(matrix)
    return tuple(matrices)


def _full_keyframes(
    source: Path,
    ingest: dict[str, object],
    keyframes: tuple[int, ...],
    check_canceled: CancelCheck,
) -> dict[int, Image]:
    normalized = ingest.get("normalizedFrames")
    if not isinstance(normalized, list):
        raise SeedingError("The ingest normalized-frame provenance is missing.")
    normalized_items = cast(list[object], normalized)
    source_by_normalized: dict[int, int] = {}
    for raw_value in normalized_items:
        if not isinstance(raw_value, dict):
            raise SeedingError("The ingest normalized-frame provenance is malformed.")
        value = cast(dict[str, object], raw_value)
        frame_index = value.get("frameIndex")
        source_index = value.get("sourceFrameIndex")
        if isinstance(frame_index, int) and isinstance(source_index, int):
            source_by_normalized[frame_index] = source_index
    try:
        wanted = {source_by_normalized[index] for index in keyframes}
    except KeyError as error:
        raise SeedingError("A seeding keyframe has no source-frame provenance.") from error
    decoded: dict[int, Image] = {}
    for source_index, frame in full_resolution_frames(source, wanted):
        check_canceled()
        decoded[source_index] = cast(Image, frame.to_ndarray(format="bgr24"))
    if set(decoded) != wanted:
        raise SeedingError(
            "The source footage ended before full-resolution keyframes were decoded."
        )
    return {index: decoded[source_by_normalized[index]] for index in keyframes}


def _footage_manifest(
    footage_id: str,
    *,
    source_size: tuple[int, int],
    analysis_size: tuple[int, int],
    keyframes: tuple[int, ...],
    mask_path: Path,
    points: tuple[SeedPoint, ...],
    coverage: Sequence[RegionCoverage],
    settings: Settings,
) -> dict[str, object]:
    return {
        "format": "orrery.engine.seeding",
        "schemaVersion": 1,
        "footageId": footage_id,
        "coordinateSpace": "analysis_pixels",
        "analysisWidth": analysis_size[0],
        "analysisHeight": analysis_size[1],
        "sourceWidth": source_size[0],
        "sourceHeight": source_size[1],
        "scaleXFromSource": analysis_size[0] / source_size[0],
        "scaleYFromSource": analysis_size[1] / source_size[1],
        "keyFrameIndices": list(keyframes),
        "movingMask": _embedded(mask_path, "image/png"),
        "points": [_point_value(point) for point in points],
        "coverage": [
            {
                "regionId": item.region_id,
                "boundingBox": list(item.bounding_box),
                "movingPixelCount": item.moving_pixel_count,
                "eligibleCellCount": item.eligible_cell_count,
                "coveredCellCount": item.covered_cell_count,
                "seedCount": item.seed_count,
                "coverageFraction": item.coverage_fraction,
            }
            for item in coverage
        ],
        "reseedingPolicy": {
            "intervalFrames": settings.seeding_reseed_interval_frames,
            "regionalCoverageThreshold": settings.seeding_coverage_threshold,
        },
    }


def _point_value(point: SeedPoint) -> dict[str, object]:
    value: dict[str, object] = {
        "seedId": point.seed_id,
        "xPx": point.x_px,
        "yPx": point.y_px,
        "source": point.source,
        "type": point.kind,
        "confidence": point.confidence,
        "frameIndex": point.frame_index,
        "detectionScale": point.detection_scale,
    }
    optional = {
        "regionId": point.region_id,
        "sourceXPx": point.source_x_px,
        "sourceYPx": point.source_y_px,
        "annotationId": point.annotation_id,
    }
    value.update({key: item for key, item in optional.items() if item is not None})
    return value


def _integer(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or item <= 0:
        raise SeedingError(f"The ingest {key} provenance is invalid.")
    return item


def _embedded(path: Path, media_type: str) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "filename": path.name,
        "mediaType": media_type,
        "encoding": "base64",
        "byteSize": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "data": base64.b64encode(content).decode("ascii"),
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    os.replace(temporary, path)


__all__ = ["SeedingError", "SeedingStageOutput", "load_seeding_stage", "run_seeding_stage"]

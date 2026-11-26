"""Tracking-stage orchestration, regional re-seeding, metrics, and durable artifacts."""

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
from orrery_engine.job_camera_motion import CameraMotionStageOutput
from orrery_engine.job_seeding import SeedingStageOutput
from orrery_engine.seeding import reseed_regions
from orrery_engine.seeding_types import (
    DetectionScale,
    Image,
    Matrix,
    RegionCoverage,
    SeedingConfig,
    SeedKind,
    SeedPoint,
    SeedSource,
)
from orrery_engine.settings import Settings
from orrery_engine.tracking import select_tracker, with_footage
from orrery_engine.tracking_arrow import write_tracks_arrow
from orrery_engine.tracking_types import (
    FrameSource,
    PointTrack,
    PointTracker,
    TrackingConfig,
    TrackSample,
)

CancelCheck = Callable[[], None]
ProgressCallback = Callable[[float, str], None]


class TrackingError(RuntimeError):
    """Upstream stage data cannot produce a valid tracking artifact."""


@dataclass(frozen=True)
class TrackingStageOutput:
    tracks: tuple[dict[str, object], ...]
    manifests: tuple[dict[str, object], ...]
    runtime_ms: float


def run_tracking_stage(
    request: ReconstructJobRequest,
    job_dir: Path,
    settings: Settings,
    camera: CameraMotionStageOutput,
    seeding: SeedingStageOutput,
    *,
    ingest_manifests: tuple[dict[str, object], ...],
    check_canceled: CancelCheck,
    progress: ProgressCallback,
) -> TrackingStageOutput:
    """Track every seed over normalized frames and refill depleted moving regions."""
    started = time.monotonic()
    tracker = select_tracker(settings.tracker_backend, _tracking_config(settings))
    all_tracks: list[dict[str, object]] = []
    manifests: list[dict[str, object]] = []
    count = len(request.inputs.footage)
    if len(seeding.manifests) != count or len(ingest_manifests) != count:
        raise TrackingError("Tracking inputs do not cover every footage item.")
    for index, footage in enumerate(request.inputs.footage):
        check_canceled()
        progress(index / count, f"Tracking points in footage {index + 1} of {count}.")
        frames, _ = decode_frames(
            job_dir / "ingest" / f"{index:02d}" / "analysis.mkv", check_canceled
        )
        frame_source = FrameSource(
            frames,
            _camera_matrices(camera, footage.footage_id, len(frames)),
            _timestamps(ingest_manifests[index], len(frames)),
        )
        seed_manifest = seeding.manifests[index]
        seeds = _seeds(seed_manifest)
        tracked = with_footage(
            tracker.track(frame_source, seeds, check_canceled=check_canceled),
            footage.footage_id,
        )
        point_tracks = list(tracked.tracks)
        reseeding = _reseed(
            tracker,
            frame_source,
            point_tracks,
            seed_manifest,
            job_dir / "seeding" / f"{index:02d}" / "moving-mask.png",
            settings,
            check_canceled,
        )
        output_dir = job_dir / "tracking" / f"{index:02d}"
        arrow_path = output_dir / "tracks.arrow"
        write_tracks_arrow(arrow_path, point_tracks)
        track_values = [_track_value(track) for track in point_tracks]
        all_tracks.extend(track_values)
        manifests.append(
            _manifest(
                footage.footage_id,
                frame_source,
                seeds,
                point_tracks,
                reseeding,
                arrow_path,
                settings.tracker_backend,
            )
        )
        progress((index + 1) / count, f"Point tracks completed for footage {index + 1} of {count}.")
    output = TrackingStageOutput(
        tuple(all_tracks), tuple(manifests), (time.monotonic() - started) * 1000
    )
    _write_json(
        job_dir / "tracking" / "manifest.json",
        {"tracks": list(output.tracks), "analysis": list(output.manifests)},
    )
    return output


def load_tracking_stage(job_dir: Path) -> TrackingStageOutput:
    value: object = json.loads((job_dir / "tracking" / "manifest.json").read_text())
    if not isinstance(value, dict):
        raise ValueError("the tracking checkpoint manifest is invalid")
    raw = cast(dict[str, object], value)
    tracks = _dictionary_items(raw.get("tracks"), "tracks")
    analysis = _dictionary_items(raw.get("analysis"), "analysis")
    return TrackingStageOutput(tracks, analysis, 0.0)


def _reseed(  # noqa: PLR0917 - complete regional re-seeding context
    tracker: PointTracker,
    source: FrameSource,
    tracks: list[PointTrack],
    seed_manifest: dict[str, object],
    moving_mask_path: Path,
    settings: Settings,
    check_canceled: CancelCheck,
) -> list[dict[str, object]]:
    baseline = _coverage(seed_manifest)
    if not baseline:
        return []
    moving_mask = cast(Image | None, cv2.imread(str(moving_mask_path), cv2.IMREAD_GRAYSCALE))
    if moving_mask is None:
        raise TrackingError("The seeding moving-region mask is unavailable.")
    config = SeedingConfig(
        max_points=settings.seeding_max_points,
        grid_size_px=settings.seeding_grid_size_px,
        per_cell_cap=settings.seeding_per_cell_cap,
        min_region_pixels=settings.seeding_min_region_pixels,
        reseed_coverage_threshold=settings.seeding_coverage_threshold,
    )
    events: list[dict[str, object]] = []
    interval = settings.seeding_reseed_interval_frames
    for frame_index in range(interval, len(source.frames), interval):
        check_canceled()
        live = _live_points(tracks, frame_index)
        result = reseed_regions(
            source.frames[frame_index],
            moving_mask,
            live,
            baseline,
            frame_index=frame_index,
            reference_to_frame=source.reference_to_frames[frame_index],
            config=config,
        )
        if result.points:
            extra = with_footage(
                tracker.track(
                    source,
                    result.points,
                    check_canceled=check_canceled,
                    forward_only=True,
                ),
                tracks[0].footage_id if tracks else "unknown",
            )
            tracks.extend(extra.tracks)
        events.append(
            {
                "frameIndex": frame_index,
                "coverage": [
                    {
                        "regionId": item.region_id,
                        "baselineSeedCount": item.baseline_seed_count,
                        "liveSeedCount": item.live_seed_count,
                        "addedSeedCount": item.added_seed_count,
                        "coverageBefore": item.coverage_before,
                        "coverageAfter": item.coverage_after,
                    }
                    for item in result.coverage
                ],
                "addedSeedIds": [item.seed_id for item in result.points],
            }
        )
    return events


def _live_points(tracks: Sequence[PointTrack], frame_index: int) -> tuple[SeedPoint, ...]:
    live: list[SeedPoint] = []
    for track in tracks:
        sample = track.samples[frame_index]
        if not sample.visible or sample.x_px is None or sample.y_px is None:
            continue
        live.append(
            SeedPoint(
                track.seed.seed_id,
                sample.x_px,
                sample.y_px,
                track.seed.source,
                track.seed.kind,
                sample.confidence,
                frame_index,
                "analysis",
                track.seed.region_id,
            )
        )
    return tuple(live)


def _manifest(  # noqa: PLR0917 - complete contracted footage artifact
    footage_id: str,
    source: FrameSource,
    seeds: Sequence[SeedPoint],
    tracks: Sequence[PointTrack],
    reseeding: list[dict[str, object]],
    arrow_path: Path,
    backend: str,
) -> dict[str, object]:
    reasons = [
        sample.rejection_reason
        for track in tracks
        for sample in track.samples
        if sample.rejection_reason is not None
    ]
    considered = [
        sample for track in tracks for sample in track.samples if sample.status != "not_seeded"
    ]
    observed = sum(sample.visible for sample in considered)
    reseeded = sum(track.seed.source == "reseeded_shi_tomasi" for track in tracks)
    return {
        "format": "orrery.engine.tracking",
        "schemaVersion": 1,
        "footageId": footage_id,
        "backend": backend,
        "coordinateSpace": "analysis_pixels",
        "analysisWidth": source.frames[0].shape[1],
        "analysisHeight": source.frames[0].shape[0],
        "frameCount": len(source.frames),
        "tracksArrow": _embedded(arrow_path, "application/vnd.apache.arrow.file"),
        "metrics": {
            "inputSeedCount": len(seeds),
            "outputTrackCount": len(tracks),
            "reseededTrackCount": reseeded,
            "observedSampleCount": observed,
            "observedFraction": round(observed / len(considered), 6) if considered else 0.0,
            "forwardBackwardRejections": reasons.count("forward_backward"),
            "appearanceRejections": reasons.count("appearance"),
            "lkRejections": reasons.count("lk_failure"),
            "boundaryRejections": reasons.count("out_of_bounds"),
        },
        "reseeding": reseeding,
    }


def _track_value(track: PointTrack) -> dict[str, object]:
    return {
        "trackId": track.track_id,
        "footageId": track.footage_id,
        "seedId": track.seed.seed_id,
        "regionId": track.seed.region_id,
        "source": track.seed.source,
        "samples": [_sample_value(sample) for sample in track.samples],
    }


def _sample_value(item: TrackSample) -> dict[str, object]:
    value: dict[str, object] = {
        "frameIndex": item.frame_index,
        "visible": item.visible,
        "confidence": item.confidence,
        "status": item.status,
    }
    if item.x_px is not None and item.y_px is not None:
        value.update({"xPx": item.x_px, "yPx": item.y_px})
    if item.rejection_reason is not None:
        value["rejectionReason"] = item.rejection_reason
    if item.uncertainty_px is not None:
        value["uncertaintyPx"] = item.uncertainty_px
    return value


def _seeds(manifest: dict[str, object]) -> tuple[SeedPoint, ...]:
    raw = manifest.get("points")
    if not isinstance(raw, list):
        raise TrackingError("The seeding point manifest is malformed.")
    points: list[SeedPoint] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            raise TrackingError("A seeding point is malformed.")
        value = cast(dict[str, object], item)
        points.append(
            SeedPoint(
                str(value["seedId"]),
                float(cast(float, value["xPx"])),
                float(cast(float, value["yPx"])),
                cast(SeedSource, value["source"]),
                cast(SeedKind, value["type"]),
                float(cast(float, value["confidence"])),
                int(cast(int, value["frameIndex"])),
                cast(DetectionScale, value["detectionScale"]),
                cast(str | None, value.get("regionId")),
                _optional_float(value.get("sourceXPx")),
                _optional_float(value.get("sourceYPx")),
                cast(str | None, value.get("annotationId")),
            )
        )
    return tuple(points)


def _coverage(manifest: dict[str, object]) -> tuple[RegionCoverage, ...]:
    raw = manifest.get("coverage")
    if not isinstance(raw, list):
        raise TrackingError("The seeding coverage manifest is malformed.")
    values: list[RegionCoverage] = []
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            raise TrackingError("A seeding coverage record is malformed.")
        value = cast(dict[str, object], item)
        box = cast(list[object], value["boundingBox"])
        values.append(
            RegionCoverage(
                str(value["regionId"]),
                cast(tuple[int, int, int, int], tuple(int(cast(int, part)) for part in box)),
                int(cast(int, value["movingPixelCount"])),
                int(cast(int, value["eligibleCellCount"])),
                int(cast(int, value["coveredCellCount"])),
                int(cast(int, value["seedCount"])),
                float(cast(float, value["coverageFraction"])),
            )
        )
    return tuple(values)


def _camera_matrices(
    camera: CameraMotionStageOutput, footage_id: str, frame_count: int
) -> tuple[Matrix, ...]:
    selected = sorted(
        (item for item in camera.motions if item.get("footageId") == footage_id),
        key=lambda item: int(cast(int, item["frameIndex"])),
    )
    if len(selected) != frame_count:
        raise TrackingError("Camera-motion and tracking frame counts do not match.")
    return tuple(
        np.asarray(cast(list[object], item["referenceToFrame"]), dtype=np.float64).reshape(3, 3)
        for item in selected
    )


def _timestamps(manifest: dict[str, object], frame_count: int) -> tuple[float, ...]:
    raw = manifest.get("normalizedFrames")
    if not isinstance(raw, list):
        raise TrackingError("The ingest normalized-frame timestamps are malformed.")
    items = cast(list[object], raw)
    if len(items) != frame_count:
        raise TrackingError("Ingest timestamps and tracking frame counts do not match.")
    timestamps: list[float] = []
    for item in items:
        if not isinstance(item, dict):
            raise TrackingError("An ingest normalized-frame timestamp is malformed.")
        value = cast(dict[str, object], item).get("timestampSeconds")
        if not isinstance(value, (int, float)):
            raise TrackingError("An ingest normalized-frame timestamp is malformed.")
        timestamps.append(float(value))
    return tuple(timestamps)


def _tracking_config(settings: Settings) -> TrackingConfig:
    return TrackingConfig(
        settings.tracker_window_size_px,
        settings.tracker_pyramid_levels,
        settings.tracker_forward_backward_threshold_px,
        settings.tracker_appearance_threshold,
        settings.tracker_patch_size_px,
    )


def _dictionary_items(value: object, label: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"the tracking checkpoint {label} are invalid")
    items = cast(list[object], value)
    if not all(isinstance(item, dict) for item in items):
        raise ValueError(f"the tracking checkpoint {label} are invalid")
    return tuple(cast(dict[str, object], item) for item in items)


def _optional_float(value: object) -> float | None:
    return float(cast(float, value)) if isinstance(value, (int, float)) else None


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


__all__ = ["TrackingError", "TrackingStageOutput", "load_tracking_stage", "run_tracking_stage"]

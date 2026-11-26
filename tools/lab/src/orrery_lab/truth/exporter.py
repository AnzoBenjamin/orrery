"""Atomic, deterministic export of MP4 clips and complete versioned ground truth."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import numpy as np

from orrery_lab.appearance import Appearance
from orrery_lab.dynamics import BodyPose
from orrery_lab.graph import Json
from orrery_lab.render2d import RenderedFrame
from orrery_lab.render3d import RenderedPasses
from orrery_lab.truth.arrow import SelectedFrame, build_arrow
from orrery_lab.truth.images import depth_exr, png16
from orrery_lab.truth.types import (
    FORMAT_NAME,
    FORMAT_VERSION,
    ClipTruth,
    ExportResult,
    Pose3D,
    TruthFrame,
    pose3d,
)

MAX_INSTANCE_ID = 0xFFFF


def export_clip(truth: ClipTruth, directory: Path) -> ExportResult:
    """Validate and atomically write one self-contained truth directory."""
    document, appearance = _source(truth)
    mode, object_ids = _validate(truth, document)
    selected = _selected_frames(truth)
    arrow = build_arrow(document, selected)
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise FileExistsError(f"truth export destination already exists: {directory}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{directory.name}-", dir=parent))
    try:
        clip_path = temporary / "clip.mp4"
        frames_path = temporary / "frames.arrow"
        points_path = temporary / "points.arrow"
        clip_path.write_bytes(truth.encoding.encoded_bytes)
        frames_path.write_bytes(arrow.frames)
        points_path.write_bytes(arrow.points)
        masks = _write_masks(temporary, selected)
        depths = _write_depth(temporary, selected, truth.include_depth)
        assets = [clip_path, frames_path, points_path, *masks, *depths]
        manifest = _manifest(
            truth,
            document,
            appearance.record(),
            mode=mode,
            object_ids=object_ids,
            selected=selected,
            assets=assets,
            depths=depths,
            root=temporary,
        )
        truth_path = temporary / "truth.json"
        truth_path.write_bytes(_canonical_json(manifest))
        os.replace(temporary, directory)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return ExportResult(
        directory,
        directory / "truth.json",
        directory / "frames.arrow",
        directory / "points.arrow",
        directory / "clip.mp4",
        tuple(directory / path.relative_to(temporary) for path in masks),
        tuple(directory / path.relative_to(temporary) for path in depths),
    )


def _source(truth: ClipTruth) -> tuple[Json, Appearance]:
    if truth.breakage is None:
        return truth.sample.built.document, truth.sample.appearance
    return truth.breakage.document, truth.breakage.appearance


def _validate(truth: ClipTruth, document: Json) -> tuple[str, dict[str, int]]:
    encoding = truth.encoding
    if (
        encoding.metadata.codec.container != "mp4"
        or encoding.metadata.codec.file_extension != ".mp4"
    ):
        raise ValueError("truth export requires an H.264 or H.265 MP4 encoding")
    if not encoding.encoded_bytes:
        raise ValueError("encoded MP4 bytes cannot be empty")
    source_timestamps = encoding.metadata.timing.source_timestamps_seconds
    frame_timestamps = tuple(frame.timestamp for frame in truth.frames)
    if frame_timestamps != source_timestamps:
        raise ValueError("truth frame timestamps must exactly match encoding source timestamps")
    expected_bodies = {str(body["id"]) for body in document["bodies"]}
    moving_bodies = {
        str(body["id"]) for body in document["bodies"] if body["kind"] != "ground"
    }
    expected_drivers = {str(driver["id"]) for driver in document["drivers"]}
    first_type = type(truth.frames[0].rendered)
    if first_type not in (RenderedFrame, RenderedPasses):
        raise ValueError("truth frames contain an unsupported renderer output")
    if any(type(frame.rendered) is not first_type for frame in truth.frames):
        raise ValueError("a truth clip cannot mix 2D and 3D renderer outputs")
    expected_dimensions = encoding.metadata.dimensions
    first_ids: dict[str, int] | None = None
    for frame in truth.frames:
        if set(frame.body_poses) != expected_bodies:
            raise ValueError("every truth frame must contain exactly one pose for every body")
        if set(frame.driver_values) != expected_drivers:
            raise ValueError("every truth frame must contain exactly one value for every driver")
        _validate_render(frame, document, expected_dimensions)
        expected_objects = (
            expected_bodies if isinstance(frame.rendered, RenderedFrame) else moving_bodies
        )
        if set(frame.rendered.object_ids) != expected_objects:
            raise ValueError("renderer object IDs do not match the mechanism bodies")
        if first_ids is None:
            first_ids = frame.rendered.object_ids
        elif frame.rendered.object_ids != first_ids:
            raise ValueError("instance ID mappings must remain stable for the entire clip")
    _validate_dynamics(truth)
    return ("2d" if first_type is RenderedFrame else "3d", dict(first_ids or {}))


def _validate_render(
    frame: TruthFrame, document: Json, dimensions: tuple[int, int]
) -> None:
    rendered = frame.rendered
    height, width = _validate_instances(rendered, dimensions)
    if isinstance(rendered, RenderedFrame):
        if rendered.pixels.shape != (height, width, 4) or rendered.pixels.dtype != np.uint8:
            raise ValueError("2D RGBA and instance dimensions or dtypes differ")
        _validate_2d_pose(frame, document)
        return
    if rendered.rgb.shape != (height, width, 3) or rendered.rgb.dtype != np.float32:
        raise ValueError("3D RGB and instance dimensions or dtypes differ")
    if rendered.depth.shape != rendered.instance_id.shape:
        raise ValueError("3D depth and instance dimensions differ")
    if rendered.depth.dtype != np.float32 or np.any(np.isnan(rendered.depth)):
        raise ValueError("3D depth must be float32 without NaNs")
    if not np.isfinite(rendered.depth[rendered.instance_id > 0]).all():
        raise ValueError("3D foreground depth must be finite")
    identity = Pose3D((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    if any(pose3d(pose) != identity for pose in frame.body_poses.values()):
        raise ValueError("the current 3D renderer only exports its actual static body pose")


def _validate_instances(
    rendered: RenderedFrame | RenderedPasses, dimensions: tuple[int, int]
) -> tuple[int, int]:
    height, width = rendered.instance_id.shape
    if (width, height) != dimensions:
        raise ValueError("render, mask, and encoded MP4 dimensions must agree")
    if rendered.instance_id.dtype != np.int32 or np.any(rendered.instance_id < 0):
        raise ValueError("instance masks must contain nonnegative int32 IDs")
    if max(rendered.object_ids.values(), default=0) > MAX_INSTANCE_ID:
        raise ValueError("instance IDs must fit the exported 16-bit PNG format")
    if (
        len(set(rendered.object_ids.values())) != len(rendered.object_ids)
        or any(instance_id <= 0 for instance_id in rendered.object_ids.values())
    ):
        raise ValueError("mapped instance IDs must be unique and positive")
    observed = {int(value) for value in np.unique(rendered.instance_id) if value != 0}
    if not observed <= set(rendered.object_ids.values()):
        raise ValueError("instance masks contain IDs absent from their object mapping")
    return height, width


def _validate_2d_pose(frame: TruthFrame, document: Json) -> None:
    rendered = cast(RenderedFrame, frame.rendered)
    rendered_poses = rendered.body_poses
    for body in document["bodies"]:
        body_id = str(body["id"])
        actual = rendered_poses.get(body_id, BodyPose(0.0, 0.0, 0.0))
        supplied = pose3d(frame.body_poses[body_id])
        if supplied != pose3d(actual):
            raise ValueError(f"truth pose for body {body_id} differs from the 2D render pose")


def _validate_dynamics(truth: ClipTruth) -> None:
    if truth.dynamics is None:
        return
    by_time = {frame.time: frame for frame in truth.dynamics.frames}
    for frame in truth.frames:
        dynamic = by_time.get(frame.timestamp)
        if dynamic is None:
            raise ValueError("every source timestamp must have a matching dynamics frame")
        for body_id in truth.dynamics.active_body_ids:
            if dynamic.poses[body_id] != frame.body_poses[body_id]:
                raise ValueError(f"dynamics and exported pose differ for body {body_id}")


def _selected_frames(truth: ClipTruth) -> tuple[SelectedFrame, ...]:
    timing = truth.encoding.metadata.timing
    if len(timing.kept_source_indices) != len(timing.encoded_timestamps_seconds):
        raise ValueError("encoding kept-frame indices and timestamps differ in length")
    selected: list[SelectedFrame] = []
    for frame_index, (source_index, timestamp) in enumerate(
        zip(timing.kept_source_indices, timing.encoded_timestamps_seconds, strict=True)
    ):
        if not 0 <= source_index < len(truth.frames):
            raise ValueError("encoding kept-frame index lies outside truth source frames")
        selected.append((frame_index, source_index, timestamp, truth.frames[source_index]))
    return tuple(selected)


def _write_masks(directory: Path, selected: tuple[SelectedFrame, ...]) -> list[Path]:
    mask_directory = directory / "masks"
    mask_directory.mkdir()
    paths: list[Path] = []
    for frame_index, _source, _timestamp, frame in selected:
        path = mask_directory / f"{frame_index:06d}.png"
        path.write_bytes(png16(frame.rendered.instance_id))
        paths.append(path)
    return paths


def _write_depth(
    directory: Path, selected: tuple[SelectedFrame, ...], include: bool
) -> list[Path]:
    if not include or not isinstance(selected[0][3].rendered, RenderedPasses):
        return []
    depth_directory = directory / "depth"
    depth_directory.mkdir()
    paths: list[Path] = []
    for frame_index, _source, _timestamp, frame in selected:
        rendered = cast(RenderedPasses, frame.rendered)
        path = depth_directory / f"{frame_index:06d}.exr"
        path.write_bytes(depth_exr(rendered.depth))
        paths.append(path)
    return paths


def _manifest(
    truth: ClipTruth,
    document: Json,
    appearance: Json,
    *,
    mode: str,
    object_ids: dict[str, int],
    selected: tuple[SelectedFrame, ...],
    assets: Sequence[Path],
    depths: Sequence[Path],
    root: Path,
) -> Json:
    return {
        "format": FORMAT_NAME,
        "schemaVersion": FORMAT_VERSION,
        "labVersion": truth.lab_version,
        "clipId": truth.clip_id,
        "sampleId": truth.sample.id,
        "family": truth.sample.family,
        "seed": truth.sample.seed,
        "acceptedAttempt": truth.sample.attempt,
        "params": _json_value(truth.sample.params),
        "sourceMechanismSha256": hashlib.sha256(
            _canonical_json(truth.sample.built.document)
        ).hexdigest(),
        "captureProfile": truth.capture_profile,
        "renderMode": mode,
        "sourceFrameCount": len(truth.frames),
        "encodedFrameCount": len(selected),
        "mechanismGraph": _json_value(document),
        "appearance": _json_value(appearance),
        "breakage": _json_value(truth.breakage.record.record())
        if truth.breakage is not None
        else None,
        "dynamics": _json_value(truth.dynamics),
        "degradations": {
            name: _json_value(value) for name, value in sorted(truth.degradations.items())
        },
        "encoding": _json_value(truth.encoding.metadata),
        "instanceIds": dict(sorted(object_ids.items())),
        "maskFormat": "image/png; bit-depth=16; color-type=grayscale; background=0",
        "depthFormat": "image/x-exr; channel=Z; dtype=float32; background=+inf"
        if depths
        else None,
        "arrow": {
            "frames": "one row per encoded frame with drivers, body poses, and camera",
            "points": "one row per encoded frame and named point",
        },
        "files": [_file_record(path, root) for path in sorted(assets)],
    }


def _file_record(path: Path, root: Path) -> Json:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("truth JSON cannot contain non-finite floats")
        return value
    if isinstance(value, np.generic):
        return _json_value(cast(object, value.item()))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_value(cast(object, dataclasses.asdict(value)))
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        if not all(isinstance(key, str) for key in mapping):
            raise ValueError("truth JSON object keys must be strings")
        items = ((cast(str, key), item) for key, item in mapping.items())
        return {key: _json_value(item) for key, item in sorted(items)}
    if isinstance(value, (tuple, list)):
        sequence = cast(Sequence[object], value)
        return [_json_value(item) for item in sequence]
    raise TypeError(f"unsupported truth JSON value {type(value).__name__}")


def _canonical_json(value: Json) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


__all__ = ["export_clip"]

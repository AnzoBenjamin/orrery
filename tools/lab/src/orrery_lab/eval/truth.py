"""Load and validate one versioned synthetic truth export for evaluation."""

# pyarrow is dynamic at this adapter boundary.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pyarrow as pa

from orrery_lab.graph import Json
from orrery_lab.truth import FORMAT_NAME, FORMAT_VERSION


@dataclass(frozen=True)
class TruthPoint:
    frame_index: int
    timestamp_seconds: float
    body_id: str
    point_id: str
    x_px: float
    y_px: float
    visible: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.body_id, self.point_id)


@dataclass(frozen=True)
class TruthPose:
    body_id: str
    translation: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]


@dataclass(frozen=True)
class TruthFrame:
    frame_index: int
    timestamp_seconds: float
    drivers: dict[str, float]
    poses: tuple[TruthPose, ...]
    camera: Json


@dataclass(frozen=True)
class LoadedTruth:
    directory: Path
    manifest: Json
    frames: tuple[TruthFrame, ...]
    points: tuple[TruthPoint, ...]

    @property
    def clip_id(self) -> str:
        return str(self.manifest["clipId"])

    @property
    def graph(self) -> Json:
        return cast(Json, self.manifest["mechanismGraph"])


def load_truth(directory: Path) -> LoadedTruth:
    """Read canonical JSON/Arrow files and verify their declared hashes and versions."""
    manifest_path = directory / "truth.json"
    value: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("truth manifest must be a JSON object")
    manifest = cast(Json, value)
    if manifest.get("format") != FORMAT_NAME or manifest.get("schemaVersion") != FORMAT_VERSION:
        raise ValueError("unsupported synthetic truth format or schema version")
    _verify_files(directory, manifest)
    frame_rows = _rows(directory / "frames.arrow", "frames")
    point_rows = _rows(directory / "points.arrow", "points")
    frames = tuple(_frame(row) for row in frame_rows)
    points = tuple(_point(row) for row in point_rows)
    expected = int(manifest["encodedFrameCount"])
    if len(frames) != expected:
        raise ValueError("truth frame table count differs from manifest")
    valid_indices = {frame.frame_index for frame in frames}
    if any(point.frame_index not in valid_indices for point in points):
        raise ValueError("truth point references an absent frame")
    return LoadedTruth(directory, manifest, frames, points)


def _verify_files(directory: Path, manifest: Json) -> None:
    records = manifest.get("files")
    if not isinstance(records, list):
        raise ValueError("truth manifest files must be a list")
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError("truth file record must be an object")
        path = directory / str(raw["path"])
        data = path.read_bytes()
        if len(data) != int(raw["bytes"]):
            raise ValueError(f"truth file size mismatch: {path.name}")
        if hashlib.sha256(data).hexdigest() != raw["sha256"]:
            raise ValueError(f"truth file checksum mismatch: {path.name}")


def _rows(path: Path, table_name: str) -> list[dict[str, object]]:
    with pa.ipc.open_file(path) as reader:
        table = reader.read_all()
    metadata = table.schema.metadata or {}
    if metadata.get(b"orrery.format") != FORMAT_NAME.encode():
        raise ValueError(f"{table_name} Arrow format metadata is invalid")
    if metadata.get(b"orrery.schema_version") != str(FORMAT_VERSION).encode():
        raise ValueError(f"{table_name} Arrow schema version is unsupported")
    if metadata.get(b"orrery.table") != table_name.encode():
        raise ValueError(f"expected {table_name} Arrow table")
    return cast(list[dict[str, object]], table.to_pylist())


def _number(value: object, label: str) -> float:
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _frame(row: dict[str, object]) -> TruthFrame:
    drivers = cast(list[dict[str, object]], row["drivers"])
    poses = cast(list[dict[str, object]], row["body_poses"])
    return TruthFrame(
        _integer(row["frame_index"], "frame index"),
        _number(row["timestamp_seconds"], "frame timestamp"),
        {str(item["driver_id"]): _number(item["value"], "driver value") for item in drivers},
        tuple(
            TruthPose(
                str(item["body_id"]),
                tuple(float(value) for value in cast(list[float], item["translation"])),  # type: ignore[arg-type]
                tuple(float(value) for value in cast(list[float], item["quaternion_xyzw"])),  # type: ignore[arg-type]
            )
            for item in poses
        ),
        cast(Json, row["camera"]),
    )


def _point(row: dict[str, object]) -> TruthPoint:
    return TruthPoint(
        _integer(row["frame_index"], "point frame index"),
        _number(row["timestamp_seconds"], "point timestamp"),
        str(row["body_id"]),
        str(row["point_id"]),
        _number(row["x_px"], "point x"),
        _number(row["y_px"], "point y"),
        bool(row["visible"]),
    )


__all__ = ["LoadedTruth", "TruthFrame", "TruthPoint", "TruthPose", "load_truth"]

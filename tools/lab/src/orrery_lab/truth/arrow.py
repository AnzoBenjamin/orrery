"""Deterministic Apache Arrow IPC tables for per-frame and per-point truth."""

# pyarrow ships partially typed dynamic construction APIs; this module is the adapter boundary.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

from orrery_lab.graph import Json
from orrery_lab.truth.projection import ProjectedPoint, camera_record, projected_points
from orrery_lab.truth.types import TruthFrame, pose3d

SelectedFrame = tuple[int, int, float, TruthFrame]


@dataclass(frozen=True)
class ArrowPayload:
    frames: bytes
    points: bytes
    projections: tuple[tuple[ProjectedPoint, ...], ...]


def build_arrow(document: Json, selected: tuple[SelectedFrame, ...]) -> ArrowPayload:
    frame_rows: list[dict[str, object]] = []
    point_rows: list[dict[str, object]] = []
    all_projections: list[tuple[ProjectedPoint, ...]] = []
    driver_order = tuple(str(driver["id"]) for driver in document["drivers"])
    body_order = tuple(str(body["id"]) for body in document["bodies"])
    for frame_index, source_index, presentation_timestamp, frame in selected:
        projections = projected_points(document, frame)
        all_projections.append(projections)
        frame_rows.append(
            {
                "frame_index": frame_index,
                "source_frame_index": source_index,
                "timestamp_seconds": presentation_timestamp,
                "source_timestamp_seconds": frame.timestamp,
                "drivers": [
                    {"driver_id": driver_id, "value": frame.driver_values[driver_id]}
                    for driver_id in driver_order
                ],
                "body_poses": [
                    _pose_record(body_id, frame.body_poses[body_id]) for body_id in body_order
                ],
                "camera": camera_record(frame.rendered),
            }
        )
        point_rows.extend(
            {
                "frame_index": frame_index,
                "source_frame_index": source_index,
                "timestamp_seconds": presentation_timestamp,
                "body_id": point.body_id,
                "point_id": point.point_id,
                "x_px": point.x,
                "y_px": point.y,
                "visible": point.visible,
                "occluded_by": point.occluded_by,
            }
            for point in projections
        )
    frame_table = pa.Table.from_pylist(frame_rows, schema=_frame_schema())
    point_table = pa.Table.from_pylist(point_rows, schema=_point_schema())
    return ArrowPayload(
        _ipc_bytes(frame_table),
        _ipc_bytes(point_table),
        tuple(all_projections),
    )


def _pose_record(body_id: str, value: object) -> dict[str, object]:
    pose = pose3d(value)  # type: ignore[arg-type] -- values were validated as BodyPoseTruth
    return {
        "body_id": body_id,
        "translation": list(pose.translation),
        "quaternion_xyzw": list(pose.quaternion_xyzw),
    }


def _metadata(table: str) -> dict[bytes, bytes]:
    return {
        b"orrery.format": b"orrery.synthetic.truth",
        b"orrery.schema_version": b"1",
        b"orrery.table": table.encode("ascii"),
    }


def _frame_schema() -> pa.Schema:
    driver = pa.struct(
        (
            pa.field("driver_id", pa.string(), False),
            pa.field("value", pa.float64(), False),
        )
    )
    body_pose = pa.struct(
        (
            pa.field("body_id", pa.string(), False),
            pa.field("translation", pa.list_(pa.float64(), 3), False),
            pa.field("quaternion_xyzw", pa.list_(pa.float64(), 4), False),
        )
    )
    camera = pa.struct(
        (
            pa.field("model", pa.string(), False),
            pa.field("width", pa.int32(), False),
            pa.field("height", pa.int32(), False),
            pa.field("focalPx", pa.float64(), False),
            pa.field("principalXPx", pa.float64(), False),
            pa.field("principalYPx", pa.float64(), False),
            pa.field("centerWorld", pa.list_(pa.float64(), 2)),
            pa.field("distance", pa.float64()),
            pa.field("tiltX", pa.float64()),
            pa.field("tiltY", pa.float64()),
            pa.field("roll", pa.float64()),
            pa.field("distortion", pa.list_(pa.float64()), False),
            pa.field("worldToCamera", pa.list_(pa.float64(), 16)),
            pa.field("nearClip", pa.float64()),
            pa.field("farClip", pa.float64()),
            pa.field("path", pa.string()),
        )
    )
    return pa.schema(
        (
            pa.field("frame_index", pa.int32(), False),
            pa.field("source_frame_index", pa.int32(), False),
            pa.field("timestamp_seconds", pa.float64(), False),
            pa.field("source_timestamp_seconds", pa.float64(), False),
            pa.field("drivers", pa.list_(driver), False),
            pa.field("body_poses", pa.list_(body_pose), False),
            pa.field("camera", camera, False),
        ),
        metadata=_metadata("frames"),
    )


def _point_schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field("frame_index", pa.int32(), False),
            pa.field("source_frame_index", pa.int32(), False),
            pa.field("timestamp_seconds", pa.float64(), False),
            pa.field("body_id", pa.string(), False),
            pa.field("point_id", pa.string(), False),
            pa.field("x_px", pa.float64(), False),
            pa.field("y_px", pa.float64(), False),
            pa.field("visible", pa.bool_(), False),
            pa.field("occluded_by", pa.string()),
        ),
        metadata=_metadata("points"),
    )


def _ipc_bytes(table: pa.Table) -> bytes:
    sink = pa.BufferOutputStream()
    options = pa.ipc.IpcWriteOptions(
        metadata_version=pa.ipc.MetadataVersion.V5,
        use_legacy_format=False,
        compression=None,
    )
    with pa.ipc.new_file(sink, table.schema, options=options) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


__all__ = ["ArrowPayload", "SelectedFrame", "build_arrow"]

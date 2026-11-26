"""Deterministic versioned Arrow IPC output for point tracking."""

# PyArrow exposes dynamic construction APIs without complete type information.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pyarrow as pa

from orrery_engine.tracking_types import PointTrack


def write_tracks_arrow(path: Path, tracks: Sequence[PointTrack]) -> bytes:
    """Write one canonical row per track/frame, with nullable coordinates when unobserved."""
    rows = [
        {
            "track_id": track.track_id,
            "footage_id": track.footage_id,
            "seed_id": track.seed.seed_id,
            "region_id": track.seed.region_id,
            "source": track.seed.source,
            "frame_index": sample.frame_index,
            "timestamp_seconds": sample.timestamp_seconds,
            "x_px": sample.x_px,
            "y_px": sample.y_px,
            "visible": sample.visible,
            "confidence": sample.confidence,
            "status": sample.status,
            "rejection_reason": sample.rejection_reason,
            "uncertainty_px": sample.uncertainty_px,
        }
        for track in sorted(tracks, key=lambda item: item.track_id)
        for sample in track.samples
    ]
    table = pa.Table.from_pylist(rows, schema=_schema())
    sink = pa.BufferOutputStream()
    options = pa.ipc.IpcWriteOptions(
        metadata_version=pa.ipc.MetadataVersion.V5,
        use_legacy_format=False,
        compression=None,
    )
    with pa.ipc.new_file(sink, table.schema, options=options) as writer:
        writer.write_table(table)
    content = cast(bytes, sink.getvalue().to_pybytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return content


def _schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field("track_id", pa.string(), False),
            pa.field("footage_id", pa.string(), False),
            pa.field("seed_id", pa.string(), False),
            pa.field("region_id", pa.string()),
            pa.field("source", pa.string(), False),
            pa.field("frame_index", pa.int32(), False),
            pa.field("timestamp_seconds", pa.float64(), False),
            pa.field("x_px", pa.float64()),
            pa.field("y_px", pa.float64()),
            pa.field("visible", pa.bool_(), False),
            pa.field("confidence", pa.float64(), False),
            pa.field("status", pa.string(), False),
            pa.field("rejection_reason", pa.string()),
            pa.field("uncertainty_px", pa.float64()),
        ),
        metadata={
            b"orrery.format": b"orrery.engine.tracking",
            b"orrery.schema_version": b"1",
            b"orrery.table": b"tracks",
            b"orrery.coordinate_space": b"analysis_pixels",
        },
    )


__all__ = ["write_tracks_arrow"]

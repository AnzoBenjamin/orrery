"""Versioned clip truth export: MP4, JSON, Arrow, masks, and optional depth."""

from orrery_lab.truth.exporter import export_clip
from orrery_lab.truth.types import (
    FORMAT_NAME,
    FORMAT_VERSION,
    ClipTruth,
    ExportResult,
    Pose3D,
    TruthFrame,
)

__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "ClipTruth",
    "ExportResult",
    "Pose3D",
    "TruthFrame",
    "export_clip",
]

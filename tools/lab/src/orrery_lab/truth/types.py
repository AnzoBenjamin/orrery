"""Typed inputs and outputs for versioned synthetic-lab truth export."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from orrery_lab.breakage import Broken
from orrery_lab.degrade import EncodingResult
from orrery_lab.dynamics import BodyPose, Trajectory
from orrery_lab.render2d import RenderedFrame
from orrery_lab.render3d import RenderedPasses
from orrery_lab.sampling import Sample

FORMAT_NAME = "orrery.synthetic.truth"
FORMAT_VERSION = 1


@dataclass(frozen=True)
class Pose3D:
    """Rigid body pose as a translation and an x/y/z/w unit quaternion."""

    translation: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        values = (*self.translation, *self.quaternion_xyzw)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("body pose values must be finite")
        norm = math.sqrt(sum(value * value for value in self.quaternion_xyzw))
        if not math.isclose(norm, 1.0, abs_tol=1e-9):
            raise ValueError("body pose quaternion must have unit length")


BodyPoseTruth = BodyPose | Pose3D
FrameRender = RenderedFrame | RenderedPasses


@dataclass(frozen=True)
class TruthFrame:
    """Actual simulation and render outputs for one source frame."""

    timestamp: float
    driver_values: dict[str, float]
    body_poses: dict[str, BodyPoseTruth]
    rendered: FrameRender

    def __post_init__(self) -> None:
        if not math.isfinite(self.timestamp) or self.timestamp < 0.0:
            raise ValueError("frame timestamp must be finite and nonnegative")
        if not all(math.isfinite(value) for value in self.driver_values.values()):
            raise ValueError("driver values must be finite")


@dataclass(frozen=True)
class ClipTruth:
    """Complete non-fabricated inputs for one clip export.

    Degradation values are the metadata objects returned by the degradation stages. The exporter
    canonicalizes dataclasses and JSON-shaped values but never invents an absent stage.
    """

    clip_id: str
    lab_version: str
    capture_profile: str
    sample: Sample
    frames: tuple[TruthFrame, ...]
    encoding: EncodingResult
    breakage: Broken | None = None
    dynamics: Trajectory | None = None
    degradations: dict[str, object] = field(default_factory=dict[str, object])
    include_depth: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("clip id", self.clip_id),
            ("lab version", self.lab_version),
            ("capture profile", self.capture_profile),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be non-empty and have no surrounding whitespace")
        if not self.frames:
            raise ValueError("truth export needs at least one source frame")
        if len(set(self.degradations)) != len(self.degradations):
            raise ValueError("degradation names must be unique")


@dataclass(frozen=True)
class ExportResult:
    directory: Path
    truth_json: Path
    frames_arrow: Path
    points_arrow: Path
    clip_mp4: Path
    mask_paths: tuple[Path, ...]
    depth_paths: tuple[Path, ...]


def pose3d(pose: BodyPoseTruth) -> Pose3D:
    if isinstance(pose, Pose3D):
        return pose
    half = 0.5 * pose.angle
    return Pose3D((pose.x, pose.y, 0.0), (0.0, 0.0, math.sin(half), math.cos(half)))


__all__ = [
    "FORMAT_NAME",
    "FORMAT_VERSION",
    "BodyPoseTruth",
    "ClipTruth",
    "ExportResult",
    "FrameRender",
    "Pose3D",
    "TruthFrame",
    "pose3d",
]

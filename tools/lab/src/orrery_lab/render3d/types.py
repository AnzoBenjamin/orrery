"""Typed public contracts for deterministic Blender/Cycles rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

CameraPath = Literal["orbit", "handheld"]
Vec3 = tuple[float, float, float]
MIN_FIELD_OF_VIEW = 10.0
MAX_FIELD_OF_VIEW = 120.0
MIN_ROD_SIDES = 6


class SceneBuildError(RuntimeError):
    """The mechanism cannot be converted into a Blender scene."""


class CyclesRenderError(RuntimeError):
    """Cycles failed to produce one of the requested real render passes."""


@dataclass(frozen=True)
class RenderConfig:
    width: int = 640
    height: int = 480
    samples: int = 32
    seed: int = 0
    camera_path: CameraPath = "orbit"
    frame_index: int = 0
    frame_count: int = 120
    field_of_view_degrees: float = 50.0
    threads: int = 1
    rod_sides: int = 12

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("render dimensions must be positive")
        if self.samples <= 0:
            raise ValueError("Cycles samples must be positive")
        if self.seed < 0:
            raise ValueError("render seed cannot be negative")
        if self.camera_path not in ("orbit", "handheld"):
            raise ValueError(f"unknown camera path {self.camera_path!r}")
        if self.frame_count <= 0 or not 0 <= self.frame_index < self.frame_count:
            raise ValueError("frame index must be within the camera path")
        if not MIN_FIELD_OF_VIEW <= self.field_of_view_degrees <= MAX_FIELD_OF_VIEW:
            raise ValueError("field of view must be between 10 and 120 degrees")
        if self.threads <= 0:
            raise ValueError("thread count must be positive")
        if self.rod_sides < MIN_ROD_SIDES:
            raise ValueError("rods need at least six sides")


@dataclass(frozen=True)
class CameraMetadata:
    path: CameraPath
    frame_index: int
    frame_count: int
    location: Vec3
    target: Vec3
    field_of_view_degrees: float
    near_clip: float
    far_clip: float
    # Row-major world-to-camera transform after Blender has aimed the camera.
    world_to_camera: tuple[float, ...]


@dataclass(frozen=True)
class SceneBuild:
    """A built scene and stable mapping from mechanism body IDs to IndexOB values."""

    scene_name: str
    object_ids: dict[str, int]
    camera: CameraMetadata


@dataclass(frozen=True)
class RenderedPasses:
    """Real Cycles passes.

    ``rgb`` is linear scene-referred float32 RGB. ``depth`` is camera-space distance in meters;
    background pixels are normalized from Blender's Z sentinel to ``+inf``. ``instance_id`` is
    int32 and uses zero for background; positive values are the entries in ``object_ids``.
    Arrays use image coordinates, with row zero at the top.
    """

    rgb: npt.NDArray[np.float32]
    depth: npt.NDArray[np.float32]
    instance_id: npt.NDArray[np.int32]
    object_ids: dict[str, int]
    camera: CameraMetadata

    def __post_init__(self) -> None:
        height, width = self.depth.shape
        if self.rgb.shape != (height, width, 3):
            raise ValueError("RGB and depth dimensions differ")
        if self.instance_id.shape != (height, width):
            raise ValueError("instance and depth dimensions differ")
        if self.rgb.dtype != np.float32:
            raise ValueError("RGB must be float32")
        if self.depth.dtype != np.float32:
            raise ValueError("depth must be float32")
        if self.instance_id.dtype != np.int32:
            raise ValueError("instance IDs must be int32")
        if np.any(self.instance_id < 0):
            raise ValueError("instance IDs cannot be negative")
        if not math.isinf(float(self.depth[self.instance_id == 0].min(initial=math.inf))):
            raise ValueError("background depth must be infinite")


__all__ = [
    "CameraMetadata",
    "CameraPath",
    "CyclesRenderError",
    "RenderConfig",
    "RenderedPasses",
    "SceneBuild",
    "SceneBuildError",
    "Vec3",
]

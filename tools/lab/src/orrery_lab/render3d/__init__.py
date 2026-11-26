"""Deterministic CPU-Cycles renderer for planar, multi-plane, and spatial mechanisms."""

from orrery_lab.render3d.camera import CameraPose, camera_pose, sampled_path
from orrery_lab.render3d.renderer import render
from orrery_lab.render3d.scene import build_scene
from orrery_lab.render3d.types import (
    CameraMetadata,
    CameraPath,
    CyclesRenderError,
    RenderConfig,
    RenderedPasses,
    SceneBuild,
    SceneBuildError,
)

__all__ = [
    "CameraMetadata",
    "CameraPath",
    "CameraPose",
    "CyclesRenderError",
    "RenderConfig",
    "RenderedPasses",
    "SceneBuild",
    "SceneBuildError",
    "build_scene",
    "camera_pose",
    "render",
    "sampled_path",
]

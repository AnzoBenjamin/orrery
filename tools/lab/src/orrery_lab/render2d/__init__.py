"""Fast deterministic Skia renderer for planar synthetic mechanisms."""

from orrery_lab.render2d.camera import Camera, fit_camera
from orrery_lab.render2d.occluders import AnimatedOccluder
from orrery_lab.render2d.renderer import RenderConfig, RenderedFrame, render_frame

__all__ = [
    "AnimatedOccluder",
    "Camera",
    "RenderConfig",
    "RenderedFrame",
    "fit_camera",
    "render_frame",
]

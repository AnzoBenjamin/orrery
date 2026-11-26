"""Deterministic orbit and smooth handheld camera paths."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from orrery_lab.render3d.types import CameraPath, RenderConfig, Vec3

type Array3 = np.ndarray[tuple[int, ...], np.dtype[np.float64]]

POINT_ARRAY_DIMENSIONS = 2
POINT_DIMENSIONS = 3
PERPENDICULAR_TOLERANCE = 1e-8


@dataclass(frozen=True)
class CameraPose:
    location: Vec3
    target: Vec3
    near_clip: float
    far_clip: float


def camera_pose(points: tuple[Vec3, ...], config: RenderConfig) -> CameraPose:
    cloud = np.asarray(points, dtype=np.float64)
    if (
        cloud.ndim != POINT_ARRAY_DIMENSIONS
        or cloud.shape[1] != POINT_DIMENSIONS
        or not np.all(np.isfinite(cloud))
    ):
        raise ValueError("camera fitting requires finite 3D points")
    low, high = cloud.min(axis=0), cloud.max(axis=0)
    center = 0.5 * (low + high)
    radius = max(float(np.linalg.norm(cloud - center, axis=1).max()), 1e-3)
    half_horizontal = math.radians(config.field_of_view_degrees) / 2.0
    half_vertical = math.atan(math.tan(half_horizontal) * config.height / config.width)
    half_angle = min(half_horizontal, half_vertical)
    distance = 1.35 * radius / math.sin(half_angle)
    phase = _seed_phase(config.seed)
    progress = config.frame_index / config.frame_count
    if config.camera_path == "orbit":
        location, target = _orbit(center, distance, phase + math.tau * progress)
    else:
        location, target = _handheld(center, distance, progress, config.seed)
    near = max(1e-5, distance - 2.5 * radius)
    far = distance + 4.0 * radius
    return CameraPose(_triple(location), _triple(target), near, far)


def sampled_path(
    points: tuple[Vec3, ...],
    path: CameraPath,
    *,
    seed: int,
    frame_count: int,
    width: int = 640,
    height: int = 480,
) -> tuple[CameraPose, ...]:
    """Return every pose of a path, useful for metadata generation without rendering."""
    return tuple(
        camera_pose(
            points,
            RenderConfig(
                width=width,
                height=height,
                seed=seed,
                camera_path=path,
                frame_index=index,
                frame_count=frame_count,
            ),
        )
        for index in range(frame_count)
    )


def _seed_phase(seed: int) -> float:
    return float(np.random.default_rng(seed).uniform(0.0, math.tau))


def _orbit(center: Array3, distance: float, azimuth: float) -> tuple[Array3, Array3]:
    elevation = math.radians(28.0) + math.radians(8.0) * math.sin(0.5 * azimuth)
    direction = np.array(
        [
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        ]
    )
    return center + distance * direction, center


def _handheld(
    center: Array3,
    distance: float,
    progress: float,
    seed: int,
) -> tuple[Array3, Array3]:
    """A finite Fourier path: nearby frames are correlated, unlike independent frame jitter."""
    phase = _seed_phase(seed)
    base_location, _ = _orbit(center, distance, phase + 0.35)
    view = (center - base_location) / np.linalg.norm(center - base_location)
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(view, world_up)
    if np.linalg.norm(right) < PERPENDICULAR_TOLERANCE:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, view)
    rng = np.random.default_rng(seed ^ 0xA5A5_3C3C)
    coefficients = rng.uniform(-1.0, 1.0, size=(4, 3, 2))

    def signal(channel: int) -> float:
        value = 0.0
        for harmonic in range(1, 5):
            amplitude = 1.0 / (harmonic * harmonic)
            sin_weight, cos_weight = coefficients[harmonic - 1, channel]
            angle = math.tau * harmonic * progress
            value += amplitude * (sin_weight * math.sin(angle) + cos_weight * math.cos(angle))
        return value

    location = base_location + distance * (
        0.025 * signal(0) * right + 0.018 * signal(1) * up + 0.008 * signal(2) * view
    )
    target = center + distance * (0.006 * signal(1) * right + 0.004 * signal(0) * up)
    return location, target


def _triple(value: Array3) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


__all__ = ["CameraPose", "camera_pose", "sampled_path"]

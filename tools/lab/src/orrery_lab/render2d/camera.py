"""Pinhole view of a mechanism plane with Brown-Conrady lens distortion."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from orrery_lab.geometry import Point2

MAX_TILT = math.radians(25)
MIN_DEPTH = 1e-9
MAX_MARGIN = 0.45


@dataclass(frozen=True)
class Camera:
    width: int
    height: int
    center_world: Point2
    focal_px: float
    distance: float = 1.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    roll: float = 0.0
    k1: float = 0.0
    k2: float = 0.0
    p1: float = 0.0
    p2: float = 0.0

    def __post_init__(self) -> None:
        numeric = (
            self.focal_px,
            self.distance,
            self.tilt_x,
            self.tilt_y,
            self.roll,
            self.k1,
            self.k2,
            self.p1,
            self.p2,
            *self.center_world,
        )
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera dimensions must be positive")
        if self.focal_px <= 0.0 or self.distance <= 0.0:
            raise ValueError("camera focal length and distance must be positive")
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("camera values must be finite")
        if abs(self.tilt_x) > MAX_TILT or abs(self.tilt_y) > MAX_TILT:
            raise ValueError("camera tilt exceeds 25 degrees")

    def normalized(self, point: Point2) -> Point2:
        x, y = point[0] - self.center_world[0], point[1] - self.center_world[1]
        cr, sr = math.cos(self.roll), math.sin(self.roll)
        x, y = cr * x - sr * y, sr * x + cr * y
        cx, sx = math.cos(self.tilt_x), math.sin(self.tilt_x)
        y, z = cx * y, sx * y
        cy, sy = math.cos(self.tilt_y), math.sin(self.tilt_y)
        x, z = cy * x + sy * z, -sy * x + cy * z
        depth = self.distance + z
        if depth <= MIN_DEPTH:
            raise ValueError("a projected point lies behind the camera")
        return (x / depth, y / depth)

    def project(self, point: Point2) -> Point2:
        x, y = self.normalized(point)
        radius2 = x * x + y * y
        radial = 1.0 + self.k1 * radius2 + self.k2 * radius2 * radius2
        distorted_x = x * radial + 2.0 * self.p1 * x * y + self.p2 * (radius2 + 2.0 * x * x)
        distorted_y = y * radial + self.p1 * (radius2 + 2.0 * y * y) + 2.0 * self.p2 * x * y
        return (
            0.5 * self.width + self.focal_px * distorted_x,
            0.5 * self.height - self.focal_px * distorted_y,
        )


def fit_camera(
    points: Sequence[Point2],
    width: int,
    height: int,
    rng: np.random.Generator,
    *,
    margin: float = 0.1,
) -> Camera:
    """Sample a legal tilted camera, then fit its focal length around all scene points."""
    if not points:
        raise ValueError("camera fitting needs at least one scene point")
    if not 0.0 <= margin < MAX_MARGIN:
        raise ValueError("camera margin must be between 0 and 0.45")
    xs, ys = zip(*points, strict=True)
    center = (0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys)))
    values = {
        "tilt_x": float(rng.uniform(-MAX_TILT, MAX_TILT)),
        "tilt_y": float(rng.uniform(-MAX_TILT, MAX_TILT)),
        "roll": float(rng.uniform(-math.pi, math.pi)),
        "k1": float(rng.uniform(-0.08, 0.08)),
        "k2": float(rng.uniform(-0.02, 0.02)),
        "p1": float(rng.uniform(-0.004, 0.004)),
        "p2": float(rng.uniform(-0.004, 0.004)),
    }
    probe = Camera(width, height, center, 1.0, **values)
    projected = [probe.project(point) for point in points]
    dx = max(abs(point[0] - 0.5 * width) for point in projected) or 1.0
    dy = max(abs(point[1] - 0.5 * height) for point in projected) or 1.0
    focal = min((0.5 - margin) * width / dx, (0.5 - margin) * height / dy)
    return Camera(width, height, center, focal, **values)


__all__ = ["MAX_TILT", "Camera", "fit_camera"]

"""Mass properties and polygon transforms for planar loose-part dynamics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.appearance import BodyAppearance
from orrery_lab.geometry import Point2

MIN_AREA = 1e-15
MIN_DOUBLE_AREA = 1e-18


class InvalidMassPropertiesError(ValueError):
    """An appearance does not leave a finite positive rigid body."""


@dataclass(frozen=True)
class MassProperties:
    area: float
    mass: float
    centroid: Point2
    inertia: float
    vertices_com: tuple[Point2, ...]


def _polygon_moments(points: Sequence[Point2]) -> tuple[float, Point2, float]:
    if len(points) < 3:  # noqa: PLR2004
        raise InvalidMassPropertiesError("a dynamic outline needs at least three vertices")
    twice_area = 0.0
    first_x = 0.0
    first_y = 0.0
    polar = 0.0
    for first, second in zip(points, (*points[1:], points[0]), strict=True):
        cross = first[0] * second[1] - second[0] * first[1]
        twice_area += cross
        first_x += (first[0] + second[0]) * cross
        first_y += (first[1] + second[1]) * cross
        polar += cross * (
            first[0] ** 2
            + first[0] * second[0]
            + second[0] ** 2
            + first[1] ** 2
            + first[1] * second[1]
            + second[1] ** 2
        )
    if abs(twice_area) <= MIN_DOUBLE_AREA:
        raise InvalidMassPropertiesError("a dynamic outline has zero area")
    centroid = (first_x / (3.0 * twice_area), first_y / (3.0 * twice_area))
    sign = 1.0 if twice_area > 0.0 else -1.0
    return (0.5 * abs(twice_area), centroid, sign * polar / 12.0)


def mass_properties(look: BodyAppearance, density: float) -> MassProperties:
    """Uniform plate properties after subtracting decorative cut-outs and joint holes."""
    if not math.isfinite(density) or density <= 0.0:
        raise InvalidMassPropertiesError("density must be finite and positive")
    if not math.isfinite(look.thickness) or look.thickness <= 0.0:
        raise InvalidMassPropertiesError(f"body {look.body_id} has no positive thickness")
    outer_area, outer_center, outer_polar = _polygon_moments(look.outline)
    area = outer_area
    first = np.array(outer_center) * outer_area
    polar = outer_polar
    for cutout in look.cutouts:
        cut_area, cut_center, cut_polar = _polygon_moments(cutout)
        area -= cut_area
        first -= np.array(cut_center) * cut_area
        polar -= cut_polar
    seen_holes: set[tuple[Point2, float]] = set()
    for hole in look.holes:
        key = (hole.center, hole.radius)
        if key in seen_holes:
            continue
        seen_holes.add(key)
        hole_area = math.pi * hole.radius**2
        area -= hole_area
        first -= np.array(hole.center) * hole_area
        polar -= 0.5 * math.pi * hole.radius**4 + hole_area * (
            hole.center[0] ** 2 + hole.center[1] ** 2
        )
    if not math.isfinite(area) or area <= MIN_AREA:
        raise InvalidMassPropertiesError(f"body {look.body_id} has no positive area after cut-outs")
    centroid_array: npt.NDArray[np.float64] = first / area
    centroid = (float(centroid_array[0]), float(centroid_array[1]))
    polar_com = polar - area * (centroid[0] ** 2 + centroid[1] ** 2)
    mass = density * look.thickness * area
    inertia = density * look.thickness * polar_com
    if not all(math.isfinite(value) and value > 0.0 for value in (mass, inertia)):
        raise InvalidMassPropertiesError(f"body {look.body_id} has invalid mass or inertia")
    vertices = tuple((x - centroid[0], y - centroid[1]) for x, y in look.outline)
    return MassProperties(area, mass, centroid, inertia, vertices)


def rotate(point: Point2, angle: float) -> Point2:
    c, s = math.cos(angle), math.sin(angle)
    return (c * point[0] - s * point[1], s * point[0] + c * point[1])


def world_vertices(
    vertices_com: Sequence[Point2], com_world: Point2, angle: float
) -> tuple[Point2, ...]:
    return tuple(
        (com_world[0] + turned[0], com_world[1] + turned[1])
        for point in vertices_com
        for turned in (rotate(point, angle),)
    )


__all__ = [
    "InvalidMassPropertiesError",
    "MassProperties",
    "mass_properties",
    "rotate",
    "world_vertices",
]

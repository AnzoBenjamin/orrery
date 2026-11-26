"""Pure geometry conversion for Blender scene construction."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.appearance import Appearance, BodyAppearance
from orrery_lab.graph import Json
from orrery_lab.render3d.types import SceneBuildError, Vec3

type Array3 = npt.NDArray[np.float64]

MIN_OUTLINE_POINTS = 3
MIN_ROD_POINTS = 2
TINY = 1e-12
ORTHOGONAL_TOLERANCE = 1e-6
AXIS_REFERENCE_LIMIT = 0.9


@dataclass(frozen=True)
class MeshData:
    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PlaneFrame:
    origin: Array3
    x_axis: Array3
    y_axis: Array3
    normal: Array3

    def world(self, point: tuple[float, float], offset: float = 0.0) -> Array3:
        return self.origin + point[0] * self.x_axis + point[1] * self.y_axis + offset * self.normal


def _array(value: Json) -> Array3:
    return np.array([value[axis] for axis in "xyz"], dtype=np.float64)


def _unit(value: Array3, label: str) -> Array3:
    length = float(np.linalg.norm(value))
    if length <= TINY or not math.isfinite(length):
        raise SceneBuildError(f"{label} is degenerate")
    return value / length


def plane_frames(document: Json) -> dict[str, PlaneFrame]:
    frames: dict[str, PlaneFrame] = {}
    for plane in document["planes"]:
        plane_id = str(plane["id"])
        normal = _unit(_array(plane["normalWorld"]), f"plane {plane_id} normal")
        x_axis = _unit(_array(plane["xAxisWorld"]), f"plane {plane_id} x axis")
        if abs(float(normal @ x_axis)) > ORTHOGONAL_TOLERANCE:
            raise SceneBuildError(f"plane {plane_id} axes are not perpendicular")
        y_axis = _unit(np.cross(normal, x_axis), f"plane {plane_id} y axis")
        frames[plane_id] = PlaneFrame(_array(plane["originWorld"]), x_axis, y_axis, normal)
    return frames


def point_world(point: Json, plane: PlaneFrame | None) -> Array3:
    local = _array(point["local"])
    if plane is None:
        return local
    return plane.world((float(local[0]), float(local[1])))


def scene_points(document: Json, appearance: Appearance) -> tuple[Vec3, ...]:
    frames = plane_frames(document)
    result: list[Vec3] = []
    for body in document["bodies"]:
        plane_id = body["planeId"]
        plane = frames.get(str(plane_id)) if plane_id is not None else None
        if plane_id is not None and plane is None:
            raise SceneBuildError(f"body {body['id']} references missing plane {plane_id}")
        look = appearance.bodies[str(body["id"])]
        if plane is not None:
            result.extend(_triple(plane.world(point, look.offset)) for point in look.outline)
        result.extend(_triple(point_world(point, plane)) for point in body["points"])
    if appearance.base_plate and document["planes"]:
        main = frames[str(document["planes"][0]["id"])]
        result.extend(
            _triple(main.world(point, -appearance.thickness)) for point in appearance.base_plate
        )
    if not result:
        raise SceneBuildError("the scene contains no geometry or named points")
    return tuple(result)


def extruded_outline(look: BodyAppearance, plane: PlaneFrame) -> MeshData:
    if len(look.outline) < MIN_OUTLINE_POINTS or look.thickness <= 0.0:
        raise SceneBuildError(f"body {look.body_id} has no extrudable outline")
    half = 0.5 * look.thickness
    lower = [plane.world(point, look.offset - half) for point in look.outline]
    upper = [plane.world(point, look.offset + half) for point in look.outline]
    count = len(lower)
    vertices = tuple(_triple(vertex) for vertex in (*lower, *upper))
    faces: list[tuple[int, ...]] = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces.extend(
        (index, (index + 1) % count, count + (index + 1) % count, count + index)
        for index in range(count)
    )
    return MeshData(vertices, tuple(faces))


def rod_mesh(points: tuple[Array3, ...], radius: float, sides: int) -> MeshData:
    if len(points) < MIN_ROD_POINTS or radius <= 0.0:
        raise SceneBuildError("a spatial rod body needs two points and a positive radius")
    vertices: list[Vec3] = []
    faces: list[tuple[int, ...]] = []
    for first, second in _minimum_spanning_edges(points):
        _append_cylinder(
            vertices,
            faces,
            points[first],
            points[second],
            radius=radius,
            sides=sides,
        )
    return MeshData(tuple(vertices), tuple(faces))


def _minimum_spanning_edges(points: tuple[Array3, ...]) -> tuple[tuple[int, int], ...]:
    """A deterministic short rod network; tracked collinear points become intermediate joints."""
    reached = {0}
    edges: list[tuple[int, int]] = []
    while len(reached) < len(points):
        candidates = (
            (float(np.linalg.norm(points[a] - points[b])), a, b)
            for a in sorted(reached)
            for b in range(len(points))
            if b not in reached
        )
        _, first, second = min(candidates)
        if float(np.linalg.norm(points[first] - points[second])) <= TINY:
            reached.add(second)
            continue
        edges.append((first, second))
        reached.add(second)
    if not edges:
        raise SceneBuildError("all spatial body points coincide")
    return tuple(edges)


def _append_cylinder(
    vertices: list[Vec3],
    faces: list[tuple[int, ...]],
    start: Array3,
    end: Array3,
    *,
    radius: float,
    sides: int,
) -> None:
    axis = _unit(end - start, "rod segment")
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(axis @ reference)) > AXIS_REFERENCE_LIMIT:
        reference = np.array([0.0, 1.0, 0.0])
    first = _unit(np.cross(axis, reference), "rod radial axis")
    second = np.cross(axis, first)
    base = len(vertices)
    for center in (start, end):
        for index in range(sides):
            angle = math.tau * index / sides
            vertex = center + radius * (math.cos(angle) * first + math.sin(angle) * second)
            vertices.append(_triple(vertex))
    faces.extend(
        (
            base + index,
            base + (index + 1) % sides,
            base + sides + (index + 1) % sides,
            base + sides + index,
        )
        for index in range(sides)
    )
    faces.append(tuple(reversed(range(base, base + sides))))
    faces.append(tuple(range(base + sides, base + 2 * sides)))


def spatial_body_points(body: Json) -> tuple[Array3, ...]:
    return tuple(_array(point["local"]) for point in body["points"])


def _triple(value: Array3) -> Vec3:
    return (float(value[0]), float(value[1]), float(value[2]))


__all__ = [
    "MeshData",
    "PlaneFrame",
    "extruded_outline",
    "plane_frames",
    "point_world",
    "rod_mesh",
    "scene_points",
    "spatial_body_points",
]

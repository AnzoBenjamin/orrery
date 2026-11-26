"""Camera records and named-point projection/visibility from actual render outputs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt

from orrery_lab.graph import Json
from orrery_lab.render2d import RenderedFrame
from orrery_lab.render3d import RenderedPasses
from orrery_lab.render3d.geometry import plane_frames, point_world
from orrery_lab.truth.types import TruthFrame


@dataclass(frozen=True)
class ProjectedPoint:
    body_id: str
    point_id: str
    x: float
    y: float
    visible: bool
    occluded_by: str | None


def camera_record(rendered: RenderedFrame | RenderedPasses) -> dict[str, object]:
    if isinstance(rendered, RenderedFrame):
        camera = rendered.camera
        return {
            "model": "pinhole-brown-conrady-planar",
            "width": camera.width,
            "height": camera.height,
            "focalPx": camera.focal_px,
            "principalXPx": 0.5 * camera.width,
            "principalYPx": 0.5 * camera.height,
            "centerWorld": list(camera.center_world),
            "distance": camera.distance,
            "tiltX": camera.tilt_x,
            "tiltY": camera.tilt_y,
            "roll": camera.roll,
            "distortion": [camera.k1, camera.k2, camera.p1, camera.p2],
            "worldToCamera": None,
            "nearClip": None,
            "farClip": None,
            "path": None,
        }
    camera = rendered.camera
    height, width = rendered.instance_id.shape
    focal = 0.5 * width / math.tan(0.5 * math.radians(camera.field_of_view_degrees))
    return {
        "model": "blender-perspective",
        "width": width,
        "height": height,
        "focalPx": focal,
        "principalXPx": 0.5 * width,
        "principalYPx": 0.5 * height,
        "centerWorld": None,
        "distance": None,
        "tiltX": None,
        "tiltY": None,
        "roll": None,
        "distortion": [],
        "worldToCamera": list(camera.world_to_camera),
        "nearClip": camera.near_clip,
        "farClip": camera.far_clip,
        "path": camera.path,
    }


def projected_points(document: Json, frame: TruthFrame) -> tuple[ProjectedPoint, ...]:
    rendered = frame.rendered
    expected = tuple(
        (str(body["id"]), str(point["id"]))
        for body in document["bodies"]
        for point in body["points"]
    )
    if isinstance(rendered, RenderedFrame):
        if set(rendered.point_projections) != set(expected):
            raise ValueError("2D render point projections do not match the mechanism graph")
        coordinates = rendered.point_projections
        base_visibility = rendered.point_visibility
    else:
        coordinates = _project_3d(document, rendered)
        base_visibility = dict.fromkeys(expected, True)
    inverse = {value: key for key, value in rendered.object_ids.items()}
    result: list[ProjectedPoint] = []
    for body_id, point_id in expected:
        x, y = coordinates[(body_id, point_id)]
        own_id = rendered.object_ids.get(body_id)
        owner = _pixel_owner(rendered.instance_id, x, y)
        interior = own_id is not None and _interior_owner(rendered.instance_id, x, y, own_id)
        visible = bool(base_visibility[(body_id, point_id)] and interior)
        if visible:
            occluded_by = None
        elif not base_visibility[(body_id, point_id)]:
            occluded_by = "animated-occluder"
        elif owner == 0:
            occluded_by = "background-or-boundary"
        else:
            occluded_by = f"body:{inverse.get(owner, f'instance-{owner}')}"
        result.append(ProjectedPoint(body_id, point_id, x, y, visible, occluded_by))
    return tuple(result)


def _project_3d(
    document: Json, rendered: RenderedPasses
) -> dict[tuple[str, str], tuple[float, float]]:
    frames = plane_frames(document)
    matrix = np.asarray(rendered.camera.world_to_camera, dtype=np.float64).reshape(4, 4)
    height, width = rendered.instance_id.shape
    focal = 0.5 * width / math.tan(0.5 * math.radians(rendered.camera.field_of_view_degrees))
    result: dict[tuple[str, str], tuple[float, float]] = {}
    for body in document["bodies"]:
        plane_id = body["planeId"]
        plane = frames.get(str(plane_id)) if plane_id is not None else None
        for point in body["points"]:
            world = point_world(cast(Json, point), plane)
            camera = matrix @ np.array([*world, 1.0], dtype=np.float64)
            depth = -float(camera[2])
            if depth <= 0.0:
                raise ValueError(
                    f"named point {body['id']}/{point['id']} lies behind the 3D camera"
                )
            result[(str(body["id"]), str(point["id"]))] = (
                0.5 * width + focal * float(camera[0]) / depth,
                0.5 * height - focal * float(camera[1]) / depth,
            )
    return result


def _pixel_owner(instance_id: npt.NDArray[np.int32], x: float, y: float) -> int:
    if not math.isfinite(x) or not math.isfinite(y):
        return 0
    column, row = math.floor(x), math.floor(y)
    if not 0 <= row < instance_id.shape[0] or not 0 <= column < instance_id.shape[1]:
        return 0
    return int(instance_id[row, column])


def _interior_owner(
    instance_id: npt.NDArray[np.int32], x: float, y: float, expected: int
) -> bool:
    if not math.isfinite(x) or not math.isfinite(y):
        return False
    column, row = math.floor(x), math.floor(y)
    if not 1 <= row < instance_id.shape[0] - 1:
        return False
    if not 1 <= column < instance_id.shape[1] - 1:
        return False
    return bool(np.all(instance_id[row - 1 : row + 2, column - 1 : column + 2] == expected))


__all__ = ["ProjectedPoint", "camera_record", "projected_points"]

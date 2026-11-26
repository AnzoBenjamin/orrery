"""Output-to-input composition of two accepted planar mechanisms (requirement 1.4).
The second graph is namespaced, similarity-transformed, and merged into the first graph's frame.
Its driver is removed, leaving the first graph's driver as the compound input. A coupling link makes
an intentionally non-singular double-crank between two fixed axles, or an external gear mesh joins
two existing output/input gears. Inputs may already be dressed; outlines are removed so the whole
compound can be dressed and layered again after composition.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from orrery_lab.family import Built, Infeasible, PartRef
from orrery_lab.geometry import Point2, circle_intersection, distance
from orrery_lab.graph import Json, vec3

Coupling = Literal["auto", "link", "gear_pair"]
SECONDARY_PREFIX = "stage-2-"
COUPLING_BODY = "coupling-link"
MIN_LENGTH = 1e-9


@dataclass(frozen=True)
class _Revolute:
    body: str
    body_point: str
    ground_point: str
    pivot: Point2


@dataclass(frozen=True)
class _Similarity:
    scale: float
    angle: float
    translation: Point2

    def point(self, point: Point2) -> Point2:
        c, s = math.cos(self.angle), math.sin(self.angle)
        x, y = self.scale * point[0], self.scale * point[1]
        return (
            c * x - s * y + self.translation[0],
            s * x + c * y + self.translation[1],
        )

    def direction(self, direction: Point2) -> Point2:
        c, s = math.cos(self.angle), math.sin(self.angle)
        x, y = direction
        return (c * x - s * y, s * x + c * y)


@dataclass(frozen=True)
class _Merged:
    document: Json
    body_map: dict[str, str]
    point_map: dict[tuple[str, str], str]
    joint_map: dict[str, str]


def _xy(value: Json) -> Point2:
    return (float(value["x"]), float(value["y"]))


def _ground(document: Json) -> Json:
    grounds = [body for body in document["bodies"] if body["kind"] == "ground"]
    if len(grounds) != 1:
        raise Infeasible("a compound stage must have exactly one ground body")
    return grounds[0]


def _plane(document: Json) -> str:
    if len(document["planes"]) != 1:
        raise Infeasible("the compound composer currently accepts one-plane mechanisms")
    plane = str(document["planes"][0]["id"])
    if any(body["planeId"] != plane for body in document["bodies"]):
        raise Infeasible("the compound composer currently accepts planar mechanisms")
    if any(body["kind"] == "cam" for body in document["bodies"]):
        raise Infeasible("translated cam profiles are not supported by the compound composer")
    return plane


def _points(document: Json) -> dict[tuple[str, str], Point2]:
    return {
        (body["id"], point["id"]): _xy(point["local"])
        for body in document["bodies"]
        for point in body["points"]
    }


def _ground_revolute(document: Json, body_id: str) -> _Revolute:
    ground_id = str(_ground(document)["id"])
    points = _points(document)
    for joint in document["joints"]:
        if joint["kind"] != "revolute" or {joint["bodyA"], joint["bodyB"]} != {
            ground_id,
            body_id,
        }:
            continue
        body_side = "A" if joint["bodyA"] == body_id else "B"
        ground_side = "B" if body_side == "A" else "A"
        body_point = str(joint[f"anchor{body_side}"]["pointId"])
        ground_point = str(joint[f"anchor{ground_side}"]["pointId"])
        return _Revolute(body_id, body_point, ground_point, points[(body_id, body_point)])
    raise Infeasible(f"body {body_id} does not turn on a fixed axle")


def _source_output(document: Json, *, gear: bool) -> tuple[_Revolute, str, Point2]:
    candidates = [
        (str(body["id"]), str(point["id"]), _xy(point["local"]))
        for body in document["bodies"]
        if not gear or (body["kind"] == "gear" and not body.get("gear", {}).get("internal"))
        for point in body["points"]
        if point["role"] == "output"
    ]
    for body_id, point_id, point in sorted(candidates):
        try:
            axle = _ground_revolute(document, body_id)
        except Infeasible:
            continue
        if distance(axle.pivot, point) > MIN_LENGTH:
            return axle, point_id, point
    kind = "external output gear" if gear else "output point on a fixed-axis body"
    raise Infeasible(f"the first stage has no {kind}")


def _driven_revolute(document: Json, *, gear: bool) -> tuple[_Revolute, str | None, Point2 | None]:
    if len(document["drivers"]) != 1:
        raise Infeasible("the second stage must have exactly one driver")
    driver_joint = document["drivers"][0]["jointId"]
    joint = next((item for item in document["joints"] if item["id"] == driver_joint), None)
    if joint is None or joint["kind"] != "revolute":
        raise Infeasible("the second stage must have a revolute input")
    ground_id = str(_ground(document)["id"])
    if ground_id not in (joint["bodyA"], joint["bodyB"]):
        raise Infeasible("the second stage input must turn on the ground")
    body_id = str(joint["bodyB"] if joint["bodyA"] == ground_id else joint["bodyA"])
    body = next(item for item in document["bodies"] if item["id"] == body_id)
    if gear:
        data = body.get("gear")
        if body["kind"] != "gear" or data is None or data["internal"]:
            raise Infeasible("gear-pair composition needs an external input gear")
        return _ground_revolute(document, body_id), None, None

    axle = _ground_revolute(document, body_id)
    choices = [
        (point["id"], _xy(point["local"]))
        for point in body["points"]
        if point["id"] != axle.body_point
    ]
    if not choices:
        raise Infeasible("the second stage input has no crank pin")
    point_id, point = max(choices, key=lambda item: distance(axle.pivot, item[1]))
    if distance(axle.pivot, point) <= MIN_LENGTH:
        raise Infeasible("the second stage input crank has zero length")
    return axle, str(point_id), point


def _similarity(old_pivot: Point2, new_pivot: Point2, scale: float, angle: float) -> _Similarity:
    c, s = math.cos(angle), math.sin(angle)
    x, y = scale * old_pivot[0], scale * old_pivot[1]
    rotated = (c * x - s * y, s * x + c * y)
    return _Similarity(scale, angle, (new_pivot[0] - rotated[0], new_pivot[1] - rotated[1]))


def _map_ref(
    reference: Json,
    body_map: dict[str, str],
    point_map: dict[tuple[str, str], str],
) -> None:
    old_body = str(reference["bodyId"])
    old_point = str(reference["pointId"])
    reference["bodyId"] = body_map[old_body]
    reference["pointId"] = point_map[(old_body, old_point)]


def _transform_vec(value: Json, transform: _Similarity) -> None:
    x, y = transform.direction(_xy(value))
    value["x"], value["y"] = x, y


def _transform_curve(slot: Json, transform: _Similarity) -> None:
    if slot["type"] == "line_segment":
        for key in ("start", "end"):
            x, y = transform.point(_xy(slot[key]))
            slot[key]["x"], slot[key]["y"] = x, y
    elif slot["type"] == "circular_arc":
        x, y = transform.point(_xy(slot["center"]))
        slot["center"]["x"], slot["center"]["y"] = x, y
        slot["radius"] *= transform.scale
        slot["angleStart"] += transform.angle
        slot["angleEnd"] += transform.angle
    else:
        for point in slot["controlPoints"]:
            x, y = transform.point(_xy(point))
            point["x"], point["y"] = x, y


def _transform_joint(
    joint: Json,
    transform: _Similarity,
    body_map: dict[str, str],
    point_map: dict[tuple[str, str], str],
    joint_map: dict[str, str],
) -> Json:
    old = copy.deepcopy(joint)
    transformed = copy.deepcopy(joint)
    transformed["id"] = joint_map[str(old["id"])]
    transformed["bodyA"] = body_map[str(old["bodyA"])]
    transformed["bodyB"] = body_map[str(old["bodyB"])]
    for field in ("anchorA", "anchorB", "pin", "followerPoint"):
        if field in transformed:
            _map_ref(transformed[field], body_map, point_map)
    for field in ("axisLocalA", "axesLocal"):
        if field not in transformed:
            continue
        values = transformed[field] if field == "axesLocal" else [transformed[field]]
        for value in values:
            _transform_vec(value, transform)
    kind = transformed["kind"]
    if kind == "prismatic" and "limits" in transformed:
        transformed["limits"] = [value * transform.scale for value in transformed["limits"]]
    elif kind == "pin_in_slot":
        _transform_curve(transformed["slot"], transform)
    elif kind == "gear_mesh" and transformed.get("rack") is not None:
        _transform_vec(transformed["rack"]["axisLocalB"], transform)
        transformed["ratio"] *= transform.scale
        transformed["phase"] *= transform.scale
    elif kind == "cam_follower" and "rollerRadius" in transformed:
        transformed["rollerRadius"] *= transform.scale
    elif kind == "spring":
        transformed["freeLength"] *= transform.scale
    return transformed


def _transform_body(
    body: Json,
    transform: _Similarity,
    body_map: dict[str, str],
    point_map: dict[tuple[str, str], str],
    plane: str,
) -> Json:
    old_id = str(body["id"])
    transformed = copy.deepcopy(body)
    transformed["id"] = body_map[old_id]
    transformed["planeId"] = plane
    transformed.pop("outline", None)
    for point in transformed["points"]:
        old_point = str(point["id"])
        point["id"] = point_map[(old_id, old_point)]
        x, y = transform.point(_xy(point["local"]))
        point["local"] = {"x": x, "y": y, "z": float(point["local"]["z"]) * transform.scale}
    if "gear" in transformed:
        transformed["gear"]["module"] *= transform.scale
    if "pulley" in transformed:
        transformed["pulley"]["radius"] *= transform.scale
    if "cam" in transformed:
        transformed["cam"]["baseRadius"] *= transform.scale
        for key in ("a", "b"):
            transformed["cam"]["fourier"][key] = [
                value * transform.scale for value in transformed["cam"]["fourier"][key]
            ]
    return transformed


def _mapped_breakable(parts: tuple[PartRef, ...], merged: _Merged) -> tuple[PartRef, ...]:
    return tuple(
        PartRef(
            part.kind,
            tuple(merged.body_map[body] for body in part.bodies),
            tuple(merged.joint_map[joint] for joint in part.joints),
        )
        for part in parts
    )


def _merge(primary: Built, secondary: Built, transform: _Similarity, sample_id: str) -> _Merged:
    first = copy.deepcopy(primary.document)
    second = secondary.document
    plane = _plane(first)
    _plane(second)
    first_ground = _ground(first)
    second_ground = _ground(second)
    first_ground_id, second_ground_id = str(first_ground["id"]), str(second_ground["id"])
    for body in first["bodies"]:
        body.pop("outline", None)

    body_map = {
        str(body["id"]): first_ground_id
        if body["id"] == second_ground_id
        else f"{SECONDARY_PREFIX}{body['id']}"
        for body in second["bodies"]
    }
    point_map = {
        (str(body["id"]), str(point["id"])): f"{SECONDARY_PREFIX}{point['id']}"
        for body in second["bodies"]
        for point in body["points"]
    }
    joint_map = {str(joint["id"]): f"{SECONDARY_PREFIX}{joint['id']}" for joint in second["joints"]}

    transformed = [
        _transform_body(body, transform, body_map, point_map, plane) for body in second["bodies"]
    ]
    transformed_ground = next(body for body in transformed if body["id"] == first_ground_id)
    first_ground["points"].extend(transformed_ground["points"])
    first["bodies"].extend(body for body in transformed if body is not transformed_ground)
    first["joints"].extend(
        _transform_joint(joint, transform, body_map, point_map, joint_map)
        for joint in second["joints"]
    )
    first["id"] = sample_id
    first["name"] = f"{primary.document['name']} driving {secondary.document['name']}"
    return _Merged(first, body_map, point_map, joint_map)


def _centroid(document: Json) -> Point2:
    points = [
        _xy(point["local"])
        for body in document["bodies"]
        for point in body["points"]
        if body["kind"] != "ground"
    ]
    if not points:
        return (0.0, 0.0)
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _compose_link(
    primary: Built,
    secondary: Built,
    rng: np.random.Generator,
    sample_id: str,
) -> Built:
    source, source_point_id, source_point = _source_output(primary.document, gear=False)
    target, target_point_id, target_point = _driven_revolute(secondary.document, gear=False)
    if target_point_id is None or target_point is None:
        raise Infeasible("the second stage input has no crank pin")
    source_radius = distance(source.pivot, source_point)
    target_radius = distance(target.pivot, target_point)
    scale = source_radius / target_radius

    ux = (source_point[0] - source.pivot[0]) / source_radius
    uy = (source_point[1] - source.pivot[1]) / source_radius
    side = -1.0 if int(rng.integers(2)) else 1.0
    frame_length = 0.8 * source_radius
    target_pivot = (
        source.pivot[0] - side * frame_length * uy,
        source.pivot[1] + side * frame_length * ux,
    )
    target_pin = circle_intersection(
        target_pivot,
        source_radius,
        source_point,
        1.1 * source_radius,
        bool(rng.integers(2)),
    )
    if target_pin is None:
        raise Infeasible("the compound coupling link does not close")
    old_angle = math.atan2(target_point[1] - target.pivot[1], target_point[0] - target.pivot[0])
    new_angle = math.atan2(target_pin[1] - target_pivot[1], target_pin[0] - target_pivot[0])
    transform = _similarity(target.pivot, target_pivot, scale, new_angle - old_angle)
    merged = _merge(primary, secondary, transform, sample_id)
    target_body = merged.body_map[target.body]
    target_point_mapped = merged.point_map[(target.body, target_point_id)]
    plane = _plane(merged.document)
    merged.document["bodies"].append(
        {
            "id": COUPLING_BODY,
            "label": "Coupling",
            "kind": "link",
            "planeId": plane,
            "points": [
                {"id": "source", "local": vec3(source_point), "role": "joint_anchor"},
                {"id": "target", "local": vec3(target_pin), "role": "joint_anchor"},
            ],
            "status": "observed",
            "confidence": 1.0,
        }
    )
    merged.document["joints"].extend(
        [
            {
                "id": "compound-source-pin",
                "kind": "revolute",
                "bodyA": source.body,
                "bodyB": COUPLING_BODY,
                "anchorA": {"bodyId": source.body, "pointId": source_point_id},
                "anchorB": {"bodyId": COUPLING_BODY, "pointId": "source"},
                "status": "observed",
                "confidence": 1.0,
            },
            {
                "id": "compound-target-pin",
                "kind": "revolute",
                "bodyA": COUPLING_BODY,
                "bodyB": target_body,
                "anchorA": {"bodyId": COUPLING_BODY, "pointId": "target"},
                "anchorB": {"bodyId": target_body, "pointId": target_point_mapped},
                "status": "observed",
                "confidence": 1.0,
            },
        ]
    )
    return Built(
        merged.document,
        primary.drive_range,
        primary.cyclic,
        (
            *primary.breakable,
            *_mapped_breakable(secondary.breakable, merged),
            PartRef("binary_link", bodies=(COUPLING_BODY,)),
        ),
    )


def _compose_gears(
    primary: Built,
    secondary: Built,
    rng: np.random.Generator,
    sample_id: str,
) -> Built:
    del rng
    source, _, _ = _source_output(primary.document, gear=True)
    target, _, _ = _driven_revolute(secondary.document, gear=True)
    source_body = next(body for body in primary.document["bodies"] if body["id"] == source.body)
    target_body = next(body for body in secondary.document["bodies"] if body["id"] == target.body)
    source_gear, target_gear = source_body["gear"], target_body["gear"]
    scale = float(source_gear["module"]) / float(target_gear["module"])
    source_radius = float(source_gear["module"]) * int(source_gear["teeth"]) / 2
    target_radius = float(target_gear["module"]) * scale * int(target_gear["teeth"]) / 2

    primary_center = _centroid(primary.document)
    outward = (source.pivot[0] - primary_center[0], source.pivot[1] - primary_center[1])
    norm = math.hypot(*outward)
    direction = (outward[0] / norm, outward[1] / norm) if norm > MIN_LENGTH else (1.0, 0.0)
    target_pivot = (
        source.pivot[0] + (source_radius + target_radius) * direction[0],
        source.pivot[1] + (source_radius + target_radius) * direction[1],
    )
    secondary_center = _centroid(secondary.document)
    center_angle = math.atan2(
        secondary_center[1] - target.pivot[1], secondary_center[0] - target.pivot[0]
    )
    outward_angle = math.atan2(direction[1], direction[0])
    transform = _similarity(target.pivot, target_pivot, scale, outward_angle - center_angle)
    merged = _merge(primary, secondary, transform, sample_id)
    merged.document["joints"].append(
        {
            "id": "compound-gear-mesh",
            "kind": "gear_mesh",
            "bodyA": source.body,
            "bodyB": merged.body_map[target.body],
            "ratio": -int(target_gear["teeth"]) / int(source_gear["teeth"]),
            "phase": 0.0,
            "status": "observed",
            "confidence": 1.0,
        }
    )
    return Built(
        merged.document,
        primary.drive_range,
        primary.cyclic,
        (*primary.breakable, *_mapped_breakable(secondary.breakable, merged)),
    )


def compose(
    primary: Built,
    secondary: Built,
    rng: np.random.Generator,
    sample_id: str,
    *,
    coupling: Coupling = "auto",
) -> Built:
    """Attach the first stage's output to the second stage's input.

    `link` needs a fixed-axis output point and a fixed-axis input crank. `gear_pair` needs an
    external output gear and an external input gear. `auto` uses a gear pair when both sides are
    compatible, otherwise a coupling link. The returned graph is intentionally undressed; call
    :func:`orrery_lab.appearance.dress` once to layer the complete machine.
    """
    _plane(primary.document)
    _plane(secondary.document)
    if coupling == "gear_pair":
        return _compose_gears(primary, secondary, rng, sample_id)
    if coupling == "link":
        return _compose_link(primary, secondary, rng, sample_id)
    try:
        return _compose_gears(primary, secondary, rng, sample_id)
    except Infeasible:
        return _compose_link(primary, secondary, rng, sample_id)

__all__ = ["Coupling", "compose"]

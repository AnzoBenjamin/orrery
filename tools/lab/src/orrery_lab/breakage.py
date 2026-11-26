"""Part removal with exact ground truth, empty holes, and wear marks (requirements 2.1, 2.3)."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

import numpy as np

from orrery_lab.appearance import Appearance, BodyAppearance
from orrery_lab.decoration import Circle, WearKind, WearMark
from orrery_lab.family import PartKind, PartRef
from orrery_lab.graph import Json, checked
from orrery_lab.sampling import Sample

type Local3 = tuple[float, float, float]


class InvalidBreakageError(ValueError):
    """A requested removal is not one of the family's declared breakable parts."""


@dataclass(frozen=True)
class RemovedBody:
    id: str
    document: Json
    appearance: BodyAppearance

    def record(self) -> Json:
        return {
            "id": self.id,
            "document": self.document,
            "appearance": asdict(self.appearance),
        }


@dataclass(frozen=True)
class RemovedJoint:
    id: str
    document: Json

    def record(self) -> Json:
        return {"id": self.id, "document": self.document}


@dataclass(frozen=True)
class HoleRecord:
    body_id: str
    point_id: str
    local: Local3
    source_joint_id: str
    removed_body_id: str
    removed_point_id: str | None
    removed_local: Local3 | None

    def record(self) -> Json:
        return {
            "bodyId": self.body_id,
            "pointId": self.point_id,
            "local": _vec3(self.local),
            "sourceJointId": self.source_joint_id,
            "removedBodyId": self.removed_body_id,
            "removedPointId": self.removed_point_id,
            "removedLocal": _vec3(self.removed_local) if self.removed_local is not None else None,
        }


@dataclass(frozen=True)
class WearRecord:
    body_id: str
    center_local: Local3
    radius: float
    kind: WearKind
    source_joint_id: str

    def record(self) -> Json:
        return {
            "bodyId": self.body_id,
            "centerLocal": _vec3(self.center_local),
            "radius": self.radius,
            "kind": self.kind,
            "sourceJointId": self.source_joint_id,
        }


@dataclass(frozen=True)
class BreakageRecord:
    id: str
    kind: PartKind
    removed_bodies: tuple[RemovedBody, ...]
    removed_joints: tuple[RemovedJoint, ...]
    holes: tuple[HoleRecord, ...]
    wear_marks: tuple[WearRecord, ...]
    schema_version: int = 1

    def record(self) -> Json:
        """The versioned breakage object embedded in `truth.json`."""
        return {
            "schemaVersion": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "removedBodies": [body.record() for body in self.removed_bodies],
            "removedJoints": [joint.record() for joint in self.removed_joints],
            "holes": [hole.record() for hole in self.holes],
            "wearMarks": [mark.record() for mark in self.wear_marks],
        }


@dataclass(frozen=True)
class Broken:
    document: Json
    appearance: Appearance
    record: BreakageRecord


@dataclass(frozen=True)
class _Boundary:
    remaining: Json
    removed_body: str
    removed: Json | None


def _vec3(value: Local3) -> Json:
    return {"x": value[0], "y": value[1], "z": value[2]}


def _local(reference: Json, bodies: dict[str, Json]) -> Local3:
    body = bodies[str(reference["bodyId"])]
    point = next(point for point in body["points"] if point["id"] == reference["pointId"])
    local = point["local"]
    return (float(local["x"]), float(local["y"]), float(local["z"]))


def _point_pairs(joint: Json) -> list[tuple[Json, Json]]:
    if "anchorA" in joint and "anchorB" in joint:
        return [(joint["anchorA"], joint["anchorB"])]
    return []


def _single_point(joint: Json) -> Json | None:
    for field in ("pin", "followerPoint"):
        if field in joint:
            return joint[field]
    return None


def _boundaries(joint: Json, removed: set[str]) -> list[_Boundary]:
    out: list[_Boundary] = []
    for first, second in _point_pairs(joint):
        first_removed = first["bodyId"] in removed
        second_removed = second["bodyId"] in removed
        if first_removed == second_removed:
            continue
        remaining, gone = (second, first) if first_removed else (first, second)
        out.append(_Boundary(remaining, str(gone["bodyId"]), gone))
    single = _single_point(joint)
    if single is not None:
        other = joint["bodyB"] if single["bodyId"] == joint["bodyA"] else joint["bodyA"]
        if single["bodyId"] not in removed and other in removed:
            out.append(_Boundary(single, str(other), None))
    return out


def _unique_point_id(body: Json, base: str) -> str:
    used = {point["id"] for point in body["points"]}
    if base not in used:
        return base
    suffix = 2
    while f"{base}-{suffix}" in used:
        suffix += 1
    return f"{base}-{suffix}"


def _body_center(body_id: str, bodies: dict[str, Json], joints: list[Json]) -> Local3:
    ground = next(body["id"] for body in bodies.values() if body["kind"] == "ground")
    for joint in joints:
        if joint["kind"] != "revolute" or body_id not in (joint["bodyA"], joint["bodyB"]):
            continue
        other = joint["bodyB"] if joint["bodyA"] == body_id else joint["bodyA"]
        if other != ground:
            continue
        side = "A" if joint["bodyA"] == body_id else "B"
        return _local(joint[f"anchor{side}"], bodies)
    points = [point["local"] for point in bodies[body_id]["points"]]
    if not points:
        return (0.0, 0.0, 0.0)
    count = len(points)
    return tuple(float(sum(point[axis] for point in points) / count) for axis in "xyz")  # type: ignore[return-value]


def _wear_radius(body: Json, appearance: Appearance) -> float:
    if "pulley" in body:
        return float(body["pulley"]["radius"])
    if "gear" in body:
        return float(body["gear"]["module"]) * int(body["gear"]["teeth"]) / 2
    if "cam" in body:
        return float(body["cam"]["baseRadius"])
    return 1.4 * appearance.pin_radius


def _contact_wear_kind(joint: Json) -> WearKind:
    return {"belt": "belt", "gear_mesh": "mesh"}.get(joint["kind"], "scuff")  # type: ignore[return-value]


def _add_wear(
    records: list[WearRecord],
    appearance: Appearance,
    body_id: str,
    *,
    center: Local3,
    radius: float,
    kind: WearKind,
    joint_id: str,
) -> None:
    key = (body_id, center, kind, joint_id)
    if any(
        (mark.body_id, mark.center_local, mark.kind, mark.source_joint_id) == key
        for mark in records
    ):
        return
    records.append(WearRecord(body_id, center, radius, kind, joint_id))
    look = appearance.bodies.get(body_id)
    if look is not None:
        look.wear_marks.append(WearMark(center[:2], radius, kind))


def _add_boundary_hole(
    boundary: _Boundary,
    joint: Json,
    bodies: dict[str, Json],
    *,
    appearance: Appearance,
    holes: list[HoleRecord],
    wear: list[WearRecord],
) -> None:
    body_id = str(boundary.remaining["bodyId"])
    body = bodies[body_id]
    remaining_local = _local(boundary.remaining, bodies)
    coincident = joint["kind"] in {"revolute", "spherical", "universal", "cylindrical"}
    removed_local = (
        _local(boundary.removed, bodies) if coincident and boundary.removed is not None else None
    )
    local = removed_local or remaining_local
    base = f"hole-{joint['id']}-{boundary.remaining['pointId']}"
    point_id = _unique_point_id(body, base)
    body["points"].append({"id": point_id, "local": _vec3(local), "role": "hole"})
    removed_point = str(boundary.removed["pointId"]) if boundary.removed is not None else None
    holes.append(
        HoleRecord(
            body_id,
            point_id,
            local,
            str(joint["id"]),
            boundary.removed_body,
            removed_point,
            removed_local,
        )
    )
    look = appearance.bodies.get(body_id)
    if look is not None and not any(circle.center == local[:2] for circle in look.holes):
        look.holes.append(Circle(local[:2], appearance.pin_radius))
    _add_wear(
        wear,
        appearance,
        body_id,
        center=local,
        radius=1.4 * appearance.pin_radius,
        kind="scuff",
        joint_id=str(joint["id"]),
    )


def _add_contact_wear(
    joint: Json,
    removed: set[str],
    bodies: dict[str, Json],
    *,
    all_joints: list[Json],
    appearance: Appearance,
    wear: list[WearRecord],
) -> None:
    for body_id in (str(joint["bodyA"]), str(joint["bodyB"])):
        if body_id in removed:
            continue
        body = bodies[body_id]
        center = _body_center(body_id, bodies, all_joints)
        _add_wear(
            wear,
            appearance,
            body_id,
            center=center,
            radius=_wear_radius(body, appearance),
            kind=_contact_wear_kind(joint),
            joint_id=str(joint["id"]),
        )


def _validate_part(sample: Sample, selected: PartRef) -> None:
    if selected not in sample.built.breakable:
        raise InvalidBreakageError(f"{selected} is not breakable in sample {sample.id}")
    if selected.kind == "belt" and (selected.bodies or not selected.joints):
        raise InvalidBreakageError("a belt breakage must name belt joints only")
    if selected.kind != "belt" and not selected.bodies:
        raise InvalidBreakageError(f"a {selected.kind} breakage must name bodies")


def apply_breakage(sample: Sample, selected: PartRef, breakage_id: str) -> Broken:
    """Remove one declared part choice and return the broken graph plus exact ground truth."""
    _validate_part(sample, selected)
    if not breakage_id:
        raise InvalidBreakageError("a breakage id cannot be empty")
    original = sample.built.document
    document = copy.deepcopy(original)
    appearance = copy.deepcopy(sample.appearance)
    original_bodies = {str(body["id"]): body for body in original["bodies"]}
    mutable_bodies = {str(body["id"]): body for body in document["bodies"]}
    removed_body_ids = set(selected.bodies)
    explicit_joints = set(selected.joints)
    removed_joint_ids = {
        str(joint["id"])
        for joint in original["joints"]
        if joint["bodyA"] in removed_body_ids or joint["bodyB"] in removed_body_ids
    } | explicit_joints
    removed_joint_docs = [joint for joint in original["joints"] if joint["id"] in removed_joint_ids]

    holes: list[HoleRecord] = []
    wear: list[WearRecord] = []
    for joint in removed_joint_docs:
        boundaries = _boundaries(joint, removed_body_ids)
        for boundary in boundaries:
            _add_boundary_hole(
                boundary,
                joint,
                mutable_bodies,
                appearance=appearance,
                holes=holes,
                wear=wear,
            )
        if not boundaries or joint["kind"] in {"belt", "gear_mesh", "cam_follower", "pin_in_slot"}:
            _add_contact_wear(
                joint,
                removed_body_ids,
                mutable_bodies,
                all_joints=list(original["joints"]),
                appearance=appearance,
                wear=wear,
            )

    removed_bodies = tuple(
        RemovedBody(
            body_id,
            copy.deepcopy(original_bodies[body_id]),
            copy.deepcopy(appearance.bodies[body_id]),
        )
        for body_id in selected.bodies
    )
    removed_joints = tuple(
        RemovedJoint(str(joint["id"]), copy.deepcopy(joint)) for joint in removed_joint_docs
    )
    document["bodies"] = [body for body in document["bodies"] if body["id"] not in removed_body_ids]
    document["joints"] = [
        joint for joint in document["joints"] if joint["id"] not in removed_joint_ids
    ]
    document["drivers"] = [
        driver for driver in document["drivers"] if driver["jointId"] not in removed_joint_ids
    ]
    document["id"] = breakage_id
    document["name"] = f"{original['name']} (broken)"
    for body_id in removed_body_ids:
        appearance.bodies.pop(body_id, None)
    checked(document)
    record = BreakageRecord(
        breakage_id,
        selected.kind,
        removed_bodies,
        removed_joints,
        tuple(holes),
        tuple(wear),
    )
    return Broken(document, appearance, record)


def generate_breakage(
    sample: Sample,
    rng: np.random.Generator,
    *,
    breakage_id: str | None = None,
) -> Broken:
    """Choose one declared breakage deterministically from `rng` and apply it."""
    if not sample.built.breakable:
        raise InvalidBreakageError(f"sample {sample.id} has no breakable parts")
    selected = sample.built.breakable[int(rng.integers(len(sample.built.breakable)))]
    chosen_id = breakage_id or f"{sample.id}-broken-{selected.kind}"
    return apply_breakage(sample, selected, chosen_id)


__all__ = [
    "BreakageRecord",
    "Broken",
    "HoleRecord",
    "InvalidBreakageError",
    "RemovedBody",
    "RemovedJoint",
    "WearRecord",
    "apply_breakage",
    "generate_breakage",
]

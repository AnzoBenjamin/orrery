"""Building mechanism graph documents, and checking them against the shared schema.

Families draw every body in world coordinates at the driver's zero: each body's local frame
coincides with the world (and plane) frame there, so the drawn pose already satisfies the joints and
the solver starts from the branch the family chose (open or crossed, elbow up or down).

A document is checked twice: by the Pydantic models generated from the shared JSON Schema (types,
bounds, required fields), and by the Rust solver's validation of the schema's cross-reference rules
(`orrery_kinematics.Solver`), which TypeScript and Rust also enforce. Nothing here restates them.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from orrery_kinematics import Solver

from orrery_lab.generated.mechanism import Mechanism

type Json = dict[str, Any]
type Point2 = tuple[float, float]

PLANE = "plane-main"

BodyKind = Literal["ground", "link", "slider_block", "gear", "cam", "pulley", "compliant"]
PointRole = Literal["joint_anchor", "tracked", "output", "hole"]


def vec2(p: Point2) -> Json:
    return {"x": p[0], "y": p[1]}


def vec3(p: Point2 | tuple[float, float, float]) -> Json:
    z = p[2] if len(p) == 3 else 0.0  # noqa: PLR2004 (a 3-vector)
    return {"x": p[0], "y": p[1], "z": z}


def ref(body: str, point: str) -> Json:
    return {"bodyId": body, "pointId": point}


def unit(dx: float, dy: float) -> Point2:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


@dataclass
class Body:
    """A body under construction. Points are in its local frame (the world frame at drive zero)."""

    id: str
    label: str
    kind: BodyKind
    points: dict[str, tuple[Point2 | tuple[float, float, float], PointRole]] = field(
        default_factory=dict[str, tuple[Point2 | tuple[float, float, float], PointRole]]
    )
    plane: str | None = PLANE
    extra: Json = field(default_factory=dict[str, Any])

    def point(
        self,
        point_id: str,
        at: Point2 | tuple[float, float, float],
        role: PointRole = "joint_anchor",
    ) -> str:
        if point_id in self.points:
            raise ValueError(f"body {self.id} already has a point {point_id}")
        self.points[point_id] = (at, role)
        return point_id

    def at(self, point_id: str) -> Point2:
        p = self.points[point_id][0]
        return (p[0], p[1])

    def document(self) -> Json:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "planeId": self.plane,
            "points": [
                {"id": pid, "local": vec3(at), "role": role}
                for pid, (at, role) in self.points.items()
            ],
            **self.extra,
            "status": "observed",
            "confidence": 1.0,
        }


@dataclass
class Graph:
    """A mechanism graph under construction, in one plane unless spatial planes are added."""

    id: str
    name: str
    bodies: dict[str, Body] = field(default_factory=dict[str, Body])
    joints: list[Json] = field(default_factory=list[Json])
    drivers: list[Json] = field(default_factory=list[Json])
    planes: list[Json] = field(
        default_factory=lambda: [
            {
                "id": PLANE,
                "originWorld": vec3((0.0, 0.0)),
                "normalWorld": vec3((0.0, 0.0, 1.0)),
                "xAxisWorld": vec3((1.0, 0.0)),
            }
        ]
    )

    def body(self, body_id: str, label: str, kind: BodyKind = "link") -> Body:
        if body_id in self.bodies:
            raise ValueError(f"duplicate body {body_id}")
        body = Body(body_id, label, kind)
        self.bodies[body_id] = body
        return body

    def _joint(self, kind: str, joint_id: str, a: str, b: str, **fields: Any) -> str:  # noqa: ANN401
        self.joints.append(
            {
                "id": joint_id,
                "kind": kind,
                "bodyA": a,
                "bodyB": b,
                **fields,
                "status": "observed",
                "confidence": 1.0,
            }
        )
        return joint_id

    def revolute(self, joint_id: str, a: str, pa: str, b: str, pb: str) -> str:
        return self._joint("revolute", joint_id, a, b, anchorA=ref(a, pa), anchorB=ref(b, pb))

    def prismatic(
        self,
        joint_id: str,
        a: str,
        pa: str,
        b: str,
        pb: str,
        *,
        axis: Point2,
        limits: tuple[float, float] | None = None,
    ) -> str:
        extra: Json = {"limits": list(limits)} if limits is not None else {}
        return self._joint(
            "prismatic",
            joint_id,
            a,
            b,
            anchorA=ref(a, pa),
            anchorB=ref(b, pb),
            axisLocalA=vec3(axis),
            **extra,
        )

    def pin_in_slot(
        self, joint_id: str, pin_body: str, pin: str, slot_body: str, *, start: Point2, end: Point2
    ) -> str:
        return self._joint(
            "pin_in_slot",
            joint_id,
            pin_body,
            slot_body,
            pin=ref(pin_body, pin),
            slot={"type": "line_segment", "start": vec2(start), "end": vec2(end)},
        )

    def gear_mesh(self, joint_id: str, a: str, b: str, ratio: float, phase: float = 0.0) -> str:
        return self._joint("gear_mesh", joint_id, a, b, ratio=ratio, phase=phase)

    def belt(self, joint_id: str, a: str, b: str, ratio: float, crossed: bool) -> str:
        return self._joint("belt", joint_id, a, b, ratio=ratio, crossed=crossed)

    def cam_follower(
        self,
        joint_id: str,
        cam: str,
        follower: str,
        point: str,
        *,
        kind: Literal["knife", "roller", "flat"],
        roller_radius: float | None = None,
    ) -> str:
        extra: Json = {"rollerRadius": roller_radius} if roller_radius is not None else {}
        return self._joint(
            "cam_follower",
            joint_id,
            cam,
            follower,
            follower=kind,
            followerPoint=ref(follower, point),
            **extra,
        )

    def spring(
        self,
        joint_id: str,
        a: str,
        pa: str,
        b: str,
        pb: str,
        *,
        stiffness: float,
        free_length: float,
    ) -> str:
        return self._joint(
            "spring",
            joint_id,
            a,
            b,
            anchorA=ref(a, pa),
            anchorB=ref(b, pb),
            stiffness=stiffness,
            freeLength=free_length,
        )

    def drive(
        self,
        joint_id: str,
        coordinate: Literal["angle", "displacement"] = "angle",
        rate: float = math.tau,
        driver_id: str = "drive",
    ) -> None:
        self.drivers.append(
            {
                "id": driver_id,
                "jointId": joint_id,
                "coordinate": coordinate,
                "profile": {"type": "constant_rate", "rate": rate, "phase0": 0.0},
            }
        )

    def document(self) -> Json:
        return {
            "schemaVersion": 1,
            "id": self.id,
            "name": self.name,
            "scale": {"source": "user_measurement", "metersPerUnit": 1.0},
            "planes": self.planes,
            "bodies": [b.document() for b in self.bodies.values()],
            "joints": self.joints,
            "drivers": self.drivers,
            "provenance": {"createdBy": "lab", "footageIds": []},
        }


def checked(document: Json) -> tuple[Mechanism, Solver]:
    """The document as the shared model and a solver for it.

    Raises `pydantic.ValidationError` when it breaks the JSON Schema, and
    `orrery_kinematics.InvalidGraphError` when it breaks a cross-reference rule.
    """
    mechanism = Mechanism.model_validate(document)
    return mechanism, Solver(json.dumps(document))

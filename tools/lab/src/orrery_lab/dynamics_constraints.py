"""Equality constraints and projections for the bounded planar dynamics integrator."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from orrery_lab.dynamics_geometry import rotate
from orrery_lab.geometry import Point2
from orrery_lab.graph import Json

type Vector = npt.NDArray[np.float64]
type Matrix = npt.NDArray[np.float64]
ConstraintKind = Literal["revolute", "prismatic", "angular", "rack"]
MIN_NORM = 1e-15
MIN_DENOMINATOR = 1e-18


class UnsupportedConstraintError(ValueError):
    """An active loose mode touches a constraint this planar integrator does not model."""


@dataclass(frozen=True)
class BodyFrame:
    body_id: str
    index: int | None
    centroid: Point2


@dataclass
class Constraint:
    joint_id: str
    kind: ConstraintKind
    a: BodyFrame
    b: BodyFrame
    carrier: BodyFrame | None = None
    anchor_a: Point2 = (0.0, 0.0)
    anchor_b: Point2 = (0.0, 0.0)
    axis: Point2 = (1.0, 0.0)
    ratio: float = 1.0
    scale: float = 1.0
    reference: tuple[float, ...] = ()

    def raw(self, q: Matrix) -> Vector:
        if self.kind == "revolute":
            first = _point(self.a, self.anchor_a, q)
            second = _point(self.b, self.anchor_b, q)
            return np.array([first[0] - second[0], first[1] - second[1]])
        if self.kind == "prismatic":
            first = _point(self.a, self.anchor_a, q)
            second = _point(self.b, self.anchor_b, q)
            axis = _direction(self.a, self.axis, q)
            delta = (second[0] - first[0], second[1] - first[1])
            across = axis[0] * delta[1] - axis[1] * delta[0]
            angle = self.scale * (_angle(self.b, q) - _angle(self.a, q))
            return np.array([across, angle])
        if self.kind == "angular":
            carrier = self.carrier or _FIXED
            value = (_angle(self.a, q) - _angle(carrier, q)) - self.ratio * (
                _angle(self.b, q) - _angle(carrier, q)
            )
            return np.array([self.scale * value])
        carrier = self.carrier or _FIXED
        rack_origin = _origin(self.b, q)
        carrier_origin = _origin(carrier, q)
        axis = _direction(self.b, self.axis, q)
        displacement = (rack_origin[0] - carrier_origin[0]) * axis[0] + (
            rack_origin[1] - carrier_origin[1]
        ) * axis[1]
        value = displacement - self.ratio * (_angle(self.a, q) - _angle(carrier, q))
        return np.array([value])

    def residual(self, q: Matrix) -> Vector:
        return self.raw(q) - np.array(self.reference)


@dataclass(frozen=True)
class PrismaticLimit:
    joint_id: str
    a: BodyFrame
    b: BodyFrame
    anchor_a: Point2
    anchor_b: Point2
    axis: Point2
    low: float
    high: float
    reference: float

    def value(self, q: Matrix) -> float:
        first = _point(self.a, self.anchor_a, q)
        second = _point(self.b, self.anchor_b, q)
        axis = _direction(self.a, self.axis, q)
        return (second[0] - first[0]) * axis[0] + (second[1] - first[1]) * axis[1] - self.reference


_FIXED = BodyFrame("ground", None, (0.0, 0.0))


def _pose(body: BodyFrame, q: Matrix) -> tuple[float, float, float]:
    if body.index is None:
        return (body.centroid[0], body.centroid[1], 0.0)
    row = q[body.index]
    return (float(row[0]), float(row[1]), float(row[2]))


def _angle(body: BodyFrame, q: Matrix) -> float:
    return _pose(body, q)[2]


def _origin(body: BodyFrame, q: Matrix) -> Point2:
    x, y, angle = _pose(body, q)
    center = rotate(body.centroid, angle)
    return (x - center[0], y - center[1])


def _point(body: BodyFrame, local: Point2, q: Matrix) -> Point2:
    x, y, angle = _pose(body, q)
    relative = rotate((local[0] - body.centroid[0], local[1] - body.centroid[1]), angle)
    return (x + relative[0], y + relative[1])


def _direction(body: BodyFrame, local: Point2, q: Matrix) -> Point2:
    direction = rotate(local, _angle(body, q))
    length = math.hypot(*direction)
    if length <= MIN_NORM:
        raise UnsupportedConstraintError("a prismatic or rack axis has zero length")
    return (direction[0] / length, direction[1] / length)


def _xy(value: Json) -> Point2:
    return (float(value["x"]), float(value["y"]))


def _point_local(reference: Json, bodies: dict[str, Json]) -> Point2:
    body = bodies[str(reference["bodyId"])]
    point = next(point for point in body["points"] if point["id"] == reference["pointId"])
    return _xy(point["local"])


def _carrier(document: Json, first: str, second: str) -> str:
    def partners(body_id: str) -> list[str]:
        out: list[str] = []
        for joint in document["joints"]:
            if joint["kind"] != "revolute":
                continue
            if joint["bodyA"] == body_id:
                out.append(str(joint["bodyB"]))
            elif joint["bodyB"] == body_id:
                out.append(str(joint["bodyA"]))
        return out

    second_partners = set(partners(second))
    match = next((body for body in partners(first) if body in second_partners), None)
    if match is None:
        raise UnsupportedConstraintError(f"gear or belt bodies {first} and {second} lack a carrier")
    return match


def compile_constraints(
    document: Json,
    active_ids: tuple[str, ...],
    centroids: dict[str, Point2],
    q0: Matrix,
    characteristic_length: float,
) -> tuple[list[Constraint], list[PrismaticLimit]]:
    bodies = {str(body["id"]): body for body in document["bodies"]}
    active = set(active_ids)
    frames = {
        body_id: BodyFrame(
            body_id,
            active_ids.index(body_id) if body_id in active else None,
            centroids.get(body_id, (0.0, 0.0)),
        )
        for body_id in bodies
    }
    constraints: list[Constraint] = []
    limits: list[PrismaticLimit] = []
    for joint in document["joints"]:
        a_id, b_id = str(joint["bodyA"]), str(joint["bodyB"])
        if a_id not in active and b_id not in active:
            continue
        kind = str(joint["kind"])
        if kind == "revolute":
            constraint = Constraint(
                str(joint["id"]),
                "revolute",
                frames[a_id],
                frames[b_id],
                anchor_a=_point_local(joint["anchorA"], bodies),
                anchor_b=_point_local(joint["anchorB"], bodies),
            )
        elif kind == "prismatic":
            anchor_a = _point_local(joint["anchorA"], bodies)
            anchor_b = _point_local(joint["anchorB"], bodies)
            axis = _xy(joint["axisLocalA"])
            constraint = Constraint(
                str(joint["id"]),
                "prismatic",
                frames[a_id],
                frames[b_id],
                anchor_a=anchor_a,
                anchor_b=anchor_b,
                axis=axis,
                scale=characteristic_length,
            )
            if "limits" in joint:
                probe = PrismaticLimit(
                    str(joint["id"]),
                    frames[a_id],
                    frames[b_id],
                    anchor_a,
                    anchor_b,
                    axis,
                    float(joint["limits"][0]),
                    float(joint["limits"][1]),
                    0.0,
                )
                limits.append(
                    PrismaticLimit(
                        probe.joint_id,
                        probe.a,
                        probe.b,
                        probe.anchor_a,
                        probe.anchor_b,
                        probe.axis,
                        probe.low,
                        probe.high,
                        probe.value(q0),
                    )
                )
        elif kind in {"gear_mesh", "belt"} and not joint.get("rack"):
            carrier_id = _carrier(document, a_id, b_id)
            ratio = float(joint["ratio"])
            if kind == "belt" and joint["crossed"]:
                ratio = -ratio
            constraint = Constraint(
                str(joint["id"]),
                "angular",
                frames[a_id],
                frames[b_id],
                carrier=frames[carrier_id],
                ratio=ratio,
                scale=characteristic_length,
            )
        elif kind == "gear_mesh" and joint.get("rack"):
            carrier_id = _carrier(document, a_id, b_id)
            constraint = Constraint(
                str(joint["id"]),
                "rack",
                frames[a_id],
                frames[b_id],
                carrier=frames[carrier_id],
                axis=_xy(joint["rack"]["axisLocalB"]),
                ratio=float(joint["ratio"]),
            )
        else:
            raise UnsupportedConstraintError(
                f"active loose bodies touch unsupported {kind} joint {joint['id']}"
            )
        constraint.reference = tuple(float(value) for value in constraint.raw(q0))
        constraints.append(constraint)
    return constraints, limits


def _stack(constraints: list[Constraint], q: Matrix) -> Vector:
    if not constraints:
        return np.zeros(0)
    return np.concatenate([constraint.residual(q) for constraint in constraints])


def jacobian(constraints: list[Constraint], q: Matrix, epsilon: float = 1e-7) -> Matrix:
    rows = len(_stack(constraints, q))
    result = np.zeros((rows, q.size))
    flat = q.reshape(-1)
    for column in range(q.size):
        before = float(flat[column])
        flat[column] = before + epsilon
        plus = _stack(constraints, q)
        flat[column] = before - epsilon
        minus = _stack(constraints, q)
        flat[column] = before
        result[:, column] = (plus - minus) / (2.0 * epsilon)
    return result


def project_positions(
    q: Matrix,
    inverse_mass: Vector,
    constraints: list[Constraint],
    *,
    tolerance: float,
    iterations: int,
) -> float:
    for _ in range(iterations):
        residual = _stack(constraints, q)
        maximum = float(np.max(np.abs(residual), initial=0.0))
        if maximum <= tolerance:
            return maximum
        derivative = jacobian(constraints, q)
        weighted = derivative * inverse_mass[np.newaxis, :]
        system = weighted @ derivative.T
        multiplier = np.linalg.lstsq(system, -residual, rcond=1e-12)[0]
        q.reshape(-1)[:] += inverse_mass * (derivative.T @ multiplier)
    return float(np.max(np.abs(_stack(constraints, q)), initial=0.0))


def project_velocities(
    q: Matrix,
    velocity: Matrix,
    inverse_mass: Vector,
    constraints: list[Constraint],
) -> None:
    if not constraints:
        return
    derivative = jacobian(constraints, q)
    residual = derivative @ velocity.reshape(-1)
    weighted = derivative * inverse_mass[np.newaxis, :]
    system = weighted @ derivative.T
    multiplier = np.linalg.lstsq(system, -residual, rcond=1e-12)[0]
    velocity.reshape(-1)[:] += inverse_mass * (derivative.T @ multiplier)


def apply_limits(q: Matrix, inverse_mass: Vector, limits: list[PrismaticLimit]) -> None:
    for limit in limits:
        value = limit.value(q)
        bound = limit.low if value < limit.low else limit.high if value > limit.high else None
        if bound is None:
            continue

        target: float = bound

        def residual(current_limit: PrismaticLimit = limit, target_value: float = target) -> float:
            return current_limit.value(q) - target_value

        gradient = np.zeros(q.size)
        flat = q.reshape(-1)
        epsilon = 1e-7
        for column in range(q.size):
            before = float(flat[column])
            flat[column] = before + epsilon
            plus = residual()
            flat[column] = before - epsilon
            minus = residual()
            flat[column] = before
            gradient[column] = (plus - minus) / (2.0 * epsilon)
        denominator = float(np.sum(inverse_mass * gradient * gradient))
        if denominator > MIN_DENOMINATOR:
            flat[:] -= inverse_mass * gradient * residual() / denominator


def max_residual(constraints: list[Constraint], q: Matrix) -> float:
    return float(np.max(np.abs(_stack(constraints, q)), initial=0.0))


__all__ = [
    "Constraint",
    "PrismaticLimit",
    "UnsupportedConstraintError",
    "apply_limits",
    "compile_constraints",
    "jacobian",
    "max_residual",
    "project_positions",
    "project_velocities",
]

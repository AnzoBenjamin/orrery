"""Spatial and multi-plane families (requirement 1.1): the RSSR linkage, and two planar four-bars
in different planes joined by a double-Cardan shaft.

Spatial bodies (no plane) are drawn in world coordinates, as planar ones are drawn in their
plane's coordinates, so in the drawn pose every body sits at its local frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.families.linkages import BRANCH, grashof_crank, is_left
from orrery_lab.families.pinned import dyad
from orrery_lab.family import Built, Infeasible, PartRef, Requirements
from orrery_lab.geometry import Point2, distance, polar
from orrery_lab.graph import Body, BodyKind, Graph, Json, PointRole, ref, vec3
from orrery_lab.space import LogUniform, ParameterSpace, Params, Uniform

type Vec = npt.NDArray[np.float64]

FULL_TURN = (0.0, math.tau)
#: No four-bar loop is planar here, so the solver reports no transmission angles to hold.
SPATIAL = Requirements()
PLANAR_LOOPS = Requirements(min_transmission=math.radians(20))
#: Below this length a direction is degenerate.
TINY = 1e-12
#: Axles closer to parallel than this (|cos|) make a planar four-bar, not a spatial one.
NEARLY_PARALLEL = 0.95
#: The steepest a universal joint here may bend (|cos| of the shaft against a plane normal).
UNIVERSAL_BEND = 0.8


def normalized(v: Vec) -> Vec:
    n = float(np.linalg.norm(v))
    if n < TINY:
        raise Infeasible("a direction degenerates")
    return v / n


def direction(azimuth: float, elevation: float) -> Vec:
    return np.array(
        [
            math.cos(elevation) * math.cos(azimuth),
            math.cos(elevation) * math.sin(azimuth),
            math.sin(elevation),
        ]
    )


def perpendicular(axis: Vec, angle: float) -> Vec:
    """A unit vector perpendicular to `axis`, turned by `angle` about it from a fixed reference."""
    z_axis = np.array([0.0, 0.0, 1.0])
    reference = np.array([1.0, 0.0, 0.0]) if abs(float(axis @ z_axis)) > NEARLY_PARALLEL else z_axis
    u = normalized(np.cross(axis, reference))
    w = np.cross(axis, u)
    return math.cos(angle) * u + math.sin(angle) * w


def triple(v: Vec) -> tuple[float, float, float]:
    return (float(v[0]), float(v[1]), float(v[2]))


def joint(
    kind: str, joint_id: str, a: tuple[str, str], b: tuple[str, str], **extra: object
) -> Json:
    """A joint between point `a` = (body, point) and point `b`."""
    return {
        "id": joint_id,
        "kind": kind,
        "bodyA": a[0],
        "bodyB": b[0],
        "anchorA": ref(*a),
        "anchorB": ref(*b),
        **extra,
        "status": "observed",
        "confidence": 1.0,
    }


@dataclass(frozen=True)
class SpatialRSSR:
    """RSSR: a crank on one axle drives a rocker on a skew axle through a coupler with ball
    joints at both ends. The coupler can spin about the line through its balls, a motion that
    moves no point on that line."""

    name: str = "spatial-rssr"
    requirements: Requirements = SPATIAL

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": LogUniform(0.05, 0.4),
                "input_angle": Uniform(0.0, math.tau),
                "crank": Uniform(0.12, 0.3),
                "rocker": Uniform(0.4, 0.8),
                "rocker_angle": Uniform(0.0, math.tau),
                "offset_azimuth": Uniform(-math.pi, math.pi),
                "offset_elevation": Uniform(-0.5, 0.5),
                "offset": Uniform(0.7, 1.2),
                "axis_azimuth": Uniform(-math.pi, math.pi),
                "axis_elevation": Uniform(-1.2, 1.2),
                "input_azimuth": Uniform(-math.pi, math.pi),
                "input_elevation": Uniform(0.6, 1.5),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"]
        u1 = direction(params["input_azimuth"], params["input_elevation"])
        u2 = direction(params["axis_azimuth"], params["axis_elevation"])
        if abs(float(u1 @ u2)) > NEARLY_PARALLEL:
            raise Infeasible("the axles are nearly parallel: that is a planar four-bar")
        o1 = np.zeros(3)
        o2 = (
            unit
            * params["offset"]
            * direction(params["offset_azimuth"], params["offset_elevation"])
        )
        b = o1 + unit * params["crank"] * perpendicular(u1, params["input_angle"])
        c = o2 + unit * params["rocker"] * perpendicular(u2, params["rocker_angle"])
        coupler = float(np.linalg.norm(c - b))
        if coupler < 0.3 * unit:
            raise Infeasible("the coupler is too short")
        mid = 0.5 * (b + c)
        tip = o2 + 1.2 * (c - o2)
        graph = Graph(sample_id, "Spatial RSSR")

        def body(
            body_id: str, label: str, kind: BodyKind, points: dict[str, tuple[Vec, PointRole]]
        ) -> None:
            graph.bodies[body_id] = _spatial_body(body_id, label, kind, points)

        body("frame", "Frame", "ground", {"o1": (o1, "joint_anchor"), "o2": (o2, "joint_anchor")})
        body("crank", "A", "link", {"o1": (o1, "joint_anchor"), "b": (b, "joint_anchor")})
        body(
            "coupler",
            "B",
            "link",
            {"b": (b, "joint_anchor"), "c": (c, "joint_anchor"), "mid": (mid, "tracked")},
        )
        body(
            "rocker",
            "C",
            "link",
            {"o2": (o2, "joint_anchor"), "c": (c, "joint_anchor"), "tip": (tip, "output")},
        )
        graph.joints.extend(
            [
                joint(
                    "revolute",
                    "r-input",
                    ("frame", "o1"),
                    ("crank", "o1"),
                    axisLocalA=vec3(triple(u1)),
                ),
                joint("spherical", "s-crank", ("crank", "b"), ("coupler", "b")),
                joint("spherical", "s-rocker", ("coupler", "c"), ("rocker", "c")),
                joint(
                    "revolute",
                    "r-output",
                    ("frame", "o2"),
                    ("rocker", "o2"),
                    axisLocalA=vec3(triple(u2)),
                ),
            ]
        )
        graph.drive("r-input")
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("coupler",)),
                PartRef("binary_link", bodies=("rocker",)),
                PartRef("adjacent_links", bodies=("coupler", "rocker")),
            ),
        )


def _spatial_body(
    body_id: str, label: str, kind: BodyKind, points: dict[str, tuple[Vec, PointRole]]
) -> Body:
    """A body with no plane, its points in world coordinates."""
    body = Body(body_id, label, kind, plane=None)
    for point_id, (at, role) in points.items():
        body.point(point_id, triple(at), role)
    return body


@dataclass(frozen=True)
class Plane:
    id: str
    origin: Vec
    normal: Vec
    x_axis: Vec

    @property
    def y_axis(self) -> Vec:
        return np.cross(self.normal, self.x_axis)

    def world(self, p: Point2) -> Vec:
        return self.origin + p[0] * self.x_axis + p[1] * self.y_axis

    def local(self, v: Vec) -> Point2:
        """A world direction in the plane's coordinates (it must lie in the plane)."""
        return (float(v @ self.x_axis), float(v @ self.y_axis))

    def document(self) -> Json:
        return {
            "id": self.id,
            "originWorld": vec3(triple(self.origin)),
            "normalWorld": vec3(triple(self.normal)),
            "xAxisWorld": vec3(triple(self.x_axis)),
        }


@dataclass(frozen=True)
class TwoPlaneCardan:
    """Two planar crank-rockers in different planes, the second driven from the first through a
    double-Cardan shaft (two universal joints and a slip joint). With the planes parallel the
    output turns with the input; tilted, the joints' angles differ and the output speed varies
    through each turn."""

    name: str = "two-plane-cardan"
    requirements: Requirements = PLANAR_LOOPS

    def parameter_space(self) -> ParameterSpace:
        four_bar = {
            f"{side}_{k}": r
            for side in ("front", "rear")
            for k, r in {
                "frame": Uniform(0.6, 1.2),
                "crank": Uniform(0.15, 0.4),
                "coupler": Uniform(0.6, 1.3),
                "rocker": Uniform(0.5, 1.2),
                "frame_angle": Uniform(-math.pi, math.pi),
            }.items()
        }
        return ParameterSpace(
            {
                "scale": LogUniform(0.05, 0.3),
                "input_angle": Uniform(0.0, math.tau),
                "spacing": Uniform(1.0, 2.5),
                "shift_y": Uniform(-0.6, 0.6),
                "shift_z": Uniform(-0.6, 0.6),
                "tilt": Uniform(-0.35, 0.35),
                "front_branch": BRANCH,
                "rear_branch": BRANCH,
                **four_bar,
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"] / 2.5
        tilt = params["tilt"]
        front = Plane(
            "plane-front", np.zeros(3), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
        )
        rear_origin = unit * np.array(
            [params["spacing"] * 2.5, params["shift_y"] * 2.5, params["shift_z"] * 2.5]
        )
        rear = Plane(
            "plane-rear",
            rear_origin,
            np.array([math.cos(tilt), math.sin(tilt), 0.0]),
            np.array([-math.sin(tilt), math.cos(tilt), 0.0]),
        )
        shaft = normalized(rear.origin - front.origin)
        if min(abs(float(shaft @ p.normal)) for p in (front, rear)) < UNIVERSAL_BEND:
            raise Infeasible("a universal joint would bend more than 37 degrees")
        theta0 = params["input_angle"]
        # The input yoke's cross arm lies in the front plane, along the crank. The shaft's arms
        # (both ends in phase) are perpendicular to it and to the shaft, and the output yoke's
        # arm is perpendicular to the shaft's in the rear plane.
        arm_front = normalized(front.world(polar((0.0, 0.0), 1.0, theta0)) - front.origin)
        arm_shaft = normalized(np.cross(shaft, arm_front))
        arm_rear = normalized(np.cross(rear.normal, arm_shaft))

        graph = Graph(sample_id, "Two planes joined by a double-Cardan shaft")
        graph.planes = [front.document(), rear.document()]
        ground_points: dict[str, tuple[Vec, PointRole]] = {}
        loops: list[tuple[str, Plane, float]] = [("front", front, theta0)]
        # The output crank's drawn angle: its arm (perpendicular to the shaft's) is the crank.
        rear_crank_dir = rear.local(arm_rear)
        loops.append(("rear", rear, math.atan2(rear_crank_dir[1], rear_crank_dir[0])))

        for side, plane, angle in loops:
            self._crank_rocker(
                graph,
                params,
                unit,
                side=side,
                plane=plane,
                angle=angle,
                ground_points=ground_points,
            )

        mid = 0.5 * (front.origin + rear.origin)
        frame = _spatial_body("frame", "Frame", "ground", ground_points)
        shaft_front = _spatial_body(
            "shaft-front",
            "G",
            "link",
            {"cross": (front.origin, "joint_anchor"), "slip": (mid, "joint_anchor")},
        )
        shaft_rear = _spatial_body(
            "shaft-rear",
            "H",
            "link",
            {"slip": (mid, "joint_anchor"), "cross": (rear.origin, "joint_anchor")},
        )
        graph.bodies = {
            "frame": frame,
            "shaft-front": shaft_front,
            "shaft-rear": shaft_rear,
            **graph.bodies,
        }
        joints: list[Json] = []
        for side, plane in (("front", front), ("rear", rear)):
            joints.extend(
                [
                    joint(
                        "revolute",
                        f"j-{side}-axle",
                        ("frame", f"{side}-axle"),
                        (f"{side}-yoke", "hub"),
                    ),
                    joint(
                        "revolute",
                        f"j-{side}-pin",
                        (f"{side}-yoke", "pin"),
                        (f"{side}-coupler", "pin"),
                    ),
                    joint(
                        "revolute", f"j-{side}-c", (f"{side}-coupler", "c"), (f"{side}-rocker", "c")
                    ),
                    joint(
                        "revolute",
                        f"j-{side}-pivot",
                        ("frame", f"{side}-pivot"),
                        (f"{side}-rocker", "pivot"),
                    ),
                ]
            )
            del plane
        front_arm = front.local(arm_front)
        rear_arm = rear.local(arm_rear)
        joints.extend(
            [
                joint(
                    "universal",
                    "u-front",
                    ("front-yoke", "cross"),
                    ("shaft-front", "cross"),
                    axesLocal=[vec3(front_arm), vec3(triple(arm_shaft))],
                ),
                joint(
                    "prismatic",
                    "slip",
                    ("shaft-front", "slip"),
                    ("shaft-rear", "slip"),
                    axisLocalA=vec3(triple(shaft)),
                ),
                joint(
                    "universal",
                    "u-rear",
                    ("shaft-rear", "cross"),
                    ("rear-yoke", "cross"),
                    axesLocal=[vec3(triple(arm_shaft)), vec3(rear_arm)],
                ),
            ]
        )
        graph.joints.extend(joints)
        graph.drive("j-front-axle")
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("front-coupler",)),
                PartRef("binary_link", bodies=("rear-coupler",)),
                PartRef("binary_link", bodies=("rear-rocker",)),
                PartRef("adjacent_links", bodies=("rear-coupler", "rear-rocker")),
            ),
        )

    @staticmethod
    def _crank_rocker(
        graph: Graph,
        params: Params,
        unit: float,
        *,
        side: str,
        plane: Plane,
        angle: float,
        ground_points: dict[str, tuple[Vec, PointRole]],
    ) -> None:
        """One plane's crank-rocker, its crank (the yoke) drawn at `angle` in plane coordinates;
        adds its frame pivots to `ground_points`."""
        g, a, k, r = (params[f"{side}_{n}"] * unit for n in ("frame", "crank", "coupler", "rocker"))
        grashof_crank((g, a, k, r))
        o4 = polar((0.0, 0.0), g, params[f"{side}_frame_angle"])
        pb = polar((0.0, 0.0), a, angle)
        pc = dyad(pb, k, o4, r, is_left(params, f"{side}_branch"))
        if distance(pb, pc) < 0.05 * unit:
            raise Infeasible("a coupler is too short")
        tip = (o4[0] + 1.2 * (pc[0] - o4[0]), o4[1] + 1.2 * (pc[1] - o4[1]))
        ground_points[f"{side}-axle"] = (plane.world((0.0, 0.0)), "joint_anchor")
        ground_points[f"{side}-pivot"] = (plane.world(o4), "joint_anchor")
        labels = "ABC" if side == "front" else "DEF"
        yoke = graph.body(f"{side}-yoke", labels[0])
        coupler = graph.body(f"{side}-coupler", labels[1])
        rocker = graph.body(f"{side}-rocker", labels[2])
        for body in (yoke, coupler, rocker):
            body.plane = plane.id
        yoke.point("hub", (0.0, 0.0))
        yoke.point("cross", (0.0, 0.0))
        yoke.point("pin", pb)
        coupler.point("pin", pb)
        coupler.point("c", pc)
        coupler.point("trace", (0.5 * (pb[0] + pc[0]), 0.5 * (pb[1] + pc[1])), "tracked")
        rocker.point("pivot", o4)
        rocker.point("c", pc)
        rocker.point("tip", tip, "output")


FAMILIES = (SpatialRSSR(), TwoPlaneCardan())

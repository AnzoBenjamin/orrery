"""Deterministic constrained planar dynamics for loose parts in a broken sample.

Implements synthetic-lab requirement 2.2.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from orrery_kinematics import Solver

from orrery_lab.breakage import Broken
from orrery_lab.dynamics_constraints import (
    Constraint,
    PrismaticLimit,
    UnsupportedConstraintError,
    apply_limits,
    compile_constraints,
    max_residual,
    project_positions,
    project_velocities,
)
from orrery_lab.dynamics_geometry import MassProperties, mass_properties, rotate, world_vertices
from orrery_lab.geometry import Point2

type Matrix = npt.NDArray[np.float64]
type Vector = npt.NDArray[np.float64]


class UnsupportedDynamicsError(ValueError):
    """A free mode is spatial or touches a constraint outside the planar dynamics scope."""


class DynamicsConvergenceError(RuntimeError):
    """Constraint projection did not reach its declared tolerance."""


class InvalidPushError(ValueError):
    """A push does not target an active body at an exact simulation step."""


@dataclass(frozen=True)
class DynamicsConfig:
    step: float = 1.0 / 480.0
    gravity: Point2 = (0.0, -9.80665)
    density: float = 7800.0
    ground_y: float | None = None
    ground_friction: float = 0.45
    restitution: float = 0.0
    revolute_friction: float = 0.005
    prismatic_friction: float = 0.05
    projection_tolerance: float = 1e-8
    projection_iterations: int = 16
    contact_iterations: int = 4


@dataclass(frozen=True)
class Push:
    time: float
    body_id: str
    impulse: Point2
    point_local: Point2 | None = None


@dataclass(frozen=True)
class BodyPose:
    x: float
    y: float
    angle: float


@dataclass(frozen=True)
class BodyVelocity:
    x: float
    y: float
    angular: float


@dataclass(frozen=True)
class DynamicsFrame:
    time: float
    poses: dict[str, BodyPose]
    velocities: dict[str, BodyVelocity]
    minimum_heights: dict[str, float]
    constraint_residual: float


@dataclass(frozen=True)
class Trajectory:
    active_body_ids: tuple[str, ...]
    frames: tuple[DynamicsFrame, ...]
    energies: tuple[float, ...]


@dataclass(frozen=True)
class _DynamicBody:
    body_id: str
    properties: MassProperties


class DynamicsWorld:
    """One fixed-step world; surviving graph drivers are locked at the break pose."""

    def __init__(
        self,
        broken: Broken,
        config: DynamicsConfig,
        bodies: tuple[_DynamicBody, ...],
        *,
        q: Matrix,
        velocity: Matrix,
        inverse_mass: Vector,
        constraints: list[Constraint],
        limits: list[PrismaticLimit],
        ground_y: float,
    ) -> None:
        self.broken = broken
        self.config = config
        self._bodies = bodies
        self._q = q
        self._velocity = velocity
        self._inverse_mass = inverse_mass
        self._constraints = constraints
        self._limits = limits
        self._ground_y = ground_y
        self._step_index = 0

    @classmethod
    def from_broken(
        cls, broken: Broken, config: DynamicsConfig = DynamicsConfig()
    ) -> DynamicsWorld:
        _validate_config(config)
        solver = Solver(json.dumps(broken.document))
        drive = np.zeros(solver.driver_count)
        state = solver.assemble(drive)
        mobility = solver.mobility(state, drive)
        active_set = {
            motion.body_id for free_motion in mobility.free_motions for motion in free_motion
        }
        documents = {str(body["id"]): body for body in broken.document["bodies"]}
        active_ids = tuple(
            str(body["id"]) for body in broken.document["bodies"] if body["id"] in active_set
        )
        planes = {documents[body_id]["planeId"] for body_id in active_ids}
        if None in planes:
            spatial = next(
                body_id for body_id in active_ids if documents[body_id]["planeId"] is None
            )
            raise UnsupportedDynamicsError(f"spatial loose body {spatial} is not planar")
        if len(planes) > 1:
            raise UnsupportedDynamicsError("a loose mode spanning multiple planes is not planar")

        dynamic: list[_DynamicBody] = []
        centroids: dict[str, Point2] = {}
        for body_id in active_ids:
            look = broken.appearance.bodies.get(body_id)
            if look is None or not look.outline:
                raise UnsupportedDynamicsError(f"active planar body {body_id} has no outline")
            properties = mass_properties(look, config.density)
            dynamic.append(_DynamicBody(body_id, properties))
            centroids[body_id] = properties.centroid
        q = np.array([[*body.properties.centroid, 0.0] for body in dynamic], dtype=np.float64)
        if not dynamic:
            q = np.zeros((0, 3), dtype=np.float64)
        velocity = np.zeros_like(q)
        inverse_mass = np.array(
            [
                value
                for body in dynamic
                for value in (
                    1.0 / body.properties.mass,
                    1.0 / body.properties.mass,
                    1.0 / body.properties.inertia,
                )
            ],
            dtype=np.float64,
        )
        try:
            constraints, limits = compile_constraints(
                broken.document,
                active_ids,
                centroids,
                q,
                broken.appearance.width,
            )
        except UnsupportedConstraintError as error:
            raise UnsupportedDynamicsError(str(error)) from error
        ground_y = _ground_height(broken, config)
        return cls(
            broken,
            config,
            tuple(dynamic),
            q=q,
            velocity=velocity,
            inverse_mass=inverse_mass,
            constraints=constraints,
            limits=limits,
            ground_y=ground_y,
        )

    @property
    def active_body_ids(self) -> tuple[str, ...]:
        return tuple(body.body_id for body in self._bodies)

    @property
    def time(self) -> float:
        return self._step_index * self.config.step

    def _forces(self) -> Matrix:
        force = np.zeros_like(self._q)
        for index, body in enumerate(self._bodies):
            force[index, 0] = body.properties.mass * self.config.gravity[0]
            force[index, 1] = body.properties.mass * self.config.gravity[1]
        for constraint in self._constraints:
            a, b = constraint.a.index, constraint.b.index
            if constraint.kind == "revolute" and self.config.revolute_friction > 0.0:
                wa = self._velocity[a, 2] if a is not None else 0.0
                wb = self._velocity[b, 2] if b is not None else 0.0
                torque = self.config.revolute_friction * (wb - wa)
                if a is not None:
                    force[a, 2] += torque
                if b is not None:
                    force[b, 2] -= torque
            elif constraint.kind == "prismatic" and self.config.prismatic_friction > 0.0:
                angle = self._q[a, 2] if a is not None else 0.0
                axis = rotate(constraint.axis, float(angle))
                va = self._velocity[a, :2] if a is not None else np.zeros(2)
                vb = self._velocity[b, :2] if b is not None else np.zeros(2)
                speed = float((vb - va) @ np.array(axis))
                drag = self.config.prismatic_friction * speed * np.array(axis)
                if a is not None:
                    force[a, :2] += drag
                if b is not None:
                    force[b, :2] -= drag
        return force

    def step(self) -> DynamicsFrame:
        if not self._bodies:
            self._step_index += 1
            return self.frame()
        dt = self.config.step
        acceleration = self._inverse_mass.reshape((-1, 3)) * self._forces()
        self._velocity += 0.5 * dt * acceleration
        project_velocities(self._q, self._velocity, self._inverse_mass, self._constraints)
        self._q += dt * self._velocity
        apply_limits(self._q, self._inverse_mass, self._limits)
        residual = project_positions(
            self._q,
            self._inverse_mass,
            self._constraints,
            tolerance=self.config.projection_tolerance,
            iterations=self.config.projection_iterations,
        )
        self._correct_ground_positions()
        residual = max(
            residual,
            project_positions(
                self._q,
                self._inverse_mass,
                self._constraints,
                tolerance=self.config.projection_tolerance,
                iterations=self.config.projection_iterations,
            ),
        )
        acceleration = self._inverse_mass.reshape((-1, 3)) * self._forces()
        self._velocity += 0.5 * dt * acceleration
        project_velocities(self._q, self._velocity, self._inverse_mass, self._constraints)
        self._resolve_ground_velocities()
        project_velocities(self._q, self._velocity, self._inverse_mass, self._constraints)
        if residual > 10.0 * self.config.projection_tolerance:
            raise DynamicsConvergenceError(
                f"constraint residual {residual:.3g} exceeds the projection tolerance"
            )
        if not np.isfinite(self._q).all() or not np.isfinite(self._velocity).all():
            raise DynamicsConvergenceError("the dynamics state became non-finite")
        self._step_index += 1
        return self.frame()

    def _correct_ground_positions(self) -> None:
        for index, _body in enumerate(self._bodies):
            low = self.minimum_height(self._bodies[index].body_id)
            if low < self._ground_y:
                self._q[index, 1] += self._ground_y - low

    def _resolve_ground_velocities(self) -> None:
        for _ in range(self.config.contact_iterations):
            for index, _body in enumerate(self._bodies):
                vertices = self._vertices(index)
                if not vertices:
                    continue
                lowest = min(range(len(vertices)), key=lambda item: vertices[item][1])
                point = vertices[lowest]
                if point[1] > self._ground_y + 1e-8:
                    continue
                center = self._q[index, :2]
                arm = np.array([point[0] - center[0], point[1] - center[1]])
                velocity = self._velocity[index]
                normal_speed = float(velocity[1] + velocity[2] * arm[0])
                if normal_speed >= 0.0:
                    continue
                inverse_mass = self._inverse_mass[3 * index]
                inverse_inertia = self._inverse_mass[3 * index + 2]
                denominator = inverse_mass + arm[0] ** 2 * inverse_inertia
                normal_impulse = -(1.0 + self.config.restitution) * normal_speed / denominator
                velocity[1] += normal_impulse * inverse_mass
                velocity[2] += arm[0] * normal_impulse * inverse_inertia
                tangent_speed = float(velocity[0] - velocity[2] * arm[1])
                tangent_denominator = inverse_mass + arm[1] ** 2 * inverse_inertia
                tangent_impulse = -tangent_speed / tangent_denominator
                limit = self.config.ground_friction * normal_impulse
                tangent_impulse = float(np.clip(tangent_impulse, -limit, limit))
                velocity[0] += tangent_impulse * inverse_mass
                velocity[2] -= arm[1] * tangent_impulse * inverse_inertia

    def _vertices(self, index: int) -> tuple[Point2, ...]:
        body = self._bodies[index]
        return world_vertices(
            body.properties.vertices_com,
            (float(self._q[index, 0]), float(self._q[index, 1])),
            float(self._q[index, 2]),
        )

    def minimum_height(self, body_id: str) -> float:
        index = self.active_body_ids.index(body_id)
        return min(point[1] for point in self._vertices(index))

    def constraint_residual(self) -> float:
        return max_residual(self._constraints, self._q)

    def apply_push(self, push: Push) -> None:
        if not math.isclose(push.time, self.time, abs_tol=1e-12):
            raise InvalidPushError(
                f"push time {push.time} is not the current step time {self.time}"
            )
        if push.body_id not in self.active_body_ids:
            raise InvalidPushError(f"push target {push.body_id} is not an active loose body")
        if not all(math.isfinite(value) for value in (*push.impulse, push.time)):
            raise InvalidPushError("push values must be finite")
        index = self.active_body_ids.index(push.body_id)
        body = self._bodies[index]
        impulse = np.array(push.impulse, dtype=np.float64)
        self._velocity[index, :2] += impulse / body.properties.mass
        if push.point_local is not None:
            arm = rotate(
                (
                    push.point_local[0] - body.properties.centroid[0],
                    push.point_local[1] - body.properties.centroid[1],
                ),
                float(self._q[index, 2]),
            )
            torque = arm[0] * impulse[1] - arm[1] * impulse[0]
            self._velocity[index, 2] += torque / body.properties.inertia
        project_velocities(self._q, self._velocity, self._inverse_mass, self._constraints)

    def energy(self) -> float:
        total = 0.0
        gravity = np.array(self.config.gravity)
        for index, body in enumerate(self._bodies):
            velocity = self._velocity[index]
            total += 0.5 * body.properties.mass * float(velocity[:2] @ velocity[:2])
            total += 0.5 * body.properties.inertia * float(velocity[2] ** 2)
            reference = np.array([0.0, self._ground_y])
            total -= body.properties.mass * float(gravity @ (self._q[index, :2] - reference))
        return total

    def frame(self) -> DynamicsFrame:
        poses: dict[str, BodyPose] = {}
        velocities: dict[str, BodyVelocity] = {}
        minimums: dict[str, float] = {}
        for index, body in enumerate(self._bodies):
            angle = float(self._q[index, 2])
            center = rotate(body.properties.centroid, angle)
            poses[body.body_id] = BodyPose(
                float(self._q[index, 0] - center[0]),
                float(self._q[index, 1] - center[1]),
                angle,
            )
            velocities[body.body_id] = BodyVelocity(
                float(self._velocity[index, 0]),
                float(self._velocity[index, 1]),
                float(self._velocity[index, 2]),
            )
            minimums[body.body_id] = self.minimum_height(body.body_id)
        return DynamicsFrame(
            self.time,
            poses,
            velocities,
            minimums,
            self.constraint_residual(),
        )

    def run(self, duration: float, pushes: tuple[Push, ...] = ()) -> Trajectory:
        steps = _grid_index(duration, self.config.step, "duration")
        schedule: dict[int, list[Push]] = {}
        for push in sorted(
            pushes,
            key=lambda item: (
                item.time,
                item.body_id,
                item.impulse,
                item.point_local or (0.0, 0.0),
            ),
        ):
            index = _grid_index(push.time, self.config.step, "push time")
            if index < self._step_index or index > self._step_index + steps:
                raise InvalidPushError(f"push time {push.time} lies outside this run")
            schedule.setdefault(index, []).append(push)
        for push in schedule.get(self._step_index, []):
            self.apply_push(push)
        frames = [self.frame()]
        energies = [self.energy()]
        target = self._step_index + steps
        while self._step_index < target:
            self.step()
            for push in schedule.get(self._step_index, []):
                self.apply_push(push)
            frames.append(self.frame())
            energies.append(self.energy())
        return Trajectory(self.active_body_ids, tuple(frames), tuple(energies))


def _validate_config(config: DynamicsConfig) -> None:
    numeric = (
        config.step,
        *config.gravity,
        config.density,
        config.ground_friction,
        config.restitution,
        config.revolute_friction,
        config.prismatic_friction,
        config.projection_tolerance,
    )
    if not all(math.isfinite(value) for value in numeric):
        raise ValueError("dynamics configuration values must be finite")
    if config.step <= 0.0 or config.density <= 0.0 or config.projection_tolerance <= 0.0:
        raise ValueError("step, density, and projection tolerance must be positive")
    if config.projection_iterations < 1 or config.contact_iterations < 1:
        raise ValueError("projection and contact iterations must be positive")
    if not 0.0 <= config.restitution <= 1.0 or config.ground_friction < 0.0:
        raise ValueError("restitution or ground friction is outside its physical range")


def _ground_height(broken: Broken, config: DynamicsConfig) -> float:
    if config.ground_y is not None:
        if not math.isfinite(config.ground_y):
            raise ValueError("ground_y must be finite")
        return config.ground_y
    if broken.appearance.base_plate:
        return min(point[1] for point in broken.appearance.base_plate)
    points = [point for look in broken.appearance.bodies.values() for point in look.outline]
    return min((point[1] for point in points), default=0.0) - 3.0 * broken.appearance.width


def _grid_index(value: float, step: float, label: str) -> int:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    index = round(value / step)
    if not math.isclose(value, index * step, abs_tol=1e-12):
        raise ValueError(f"{label} {value} is not on the fixed-step grid")
    return index


def simulate(
    broken: Broken,
    duration: float,
    *,
    config: DynamicsConfig = DynamicsConfig(),
    pushes: tuple[Push, ...] = (),
) -> Trajectory:
    return DynamicsWorld.from_broken(broken, config).run(duration, pushes)


__all__ = [
    "BodyPose",
    "BodyVelocity",
    "DynamicsConfig",
    "DynamicsConvergenceError",
    "DynamicsFrame",
    "DynamicsWorld",
    "InvalidPushError",
    "Push",
    "Trajectory",
    "UnsupportedDynamicsError",
    "simulate",
]

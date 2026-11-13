"""Solver checks a drawn sample must pass (requirement 1.2, design "Feasibility").

The sample is valid against the shared schema, assembles exactly where it was drawn, reaches its
whole driver range without the reachable range breaking (no dead center or lockup of the loop
before the end), keeps its transmission angles above the family's minimum, has no branch points
unless the family is defined by them, and its outlines do not collide.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pydantic
from orrery_kinematics import (
    AssemblyFailedError,
    InvalidGraphError,
    SingularityKind,
    Solver,
)

from orrery_lab.family import Built, Requirements
from orrery_lab.generated.mechanism import Mechanism as MechanismModel
from orrery_lab.graph import Json, checked


@dataclass(frozen=True)
class Verdict:
    """Accepted with the checked model and solver, or rejected with a reason."""

    reason: str | None
    mechanism: MechanismModel | None = None
    solver: Solver | None = None
    #: Least transmission angle seen, in radians (`math.pi / 2` when there is no four-bar loop).
    min_transmission: float = math.pi / 2

    @property
    def accepted(self) -> bool:
        return self.reason is None


def _covers(reachable: list[tuple[float, float]], start: float, end: float, step: float) -> bool:
    """One reachable range from `start` to within half a step of `end`."""
    if len(reachable) != 1:
        return False
    lo, hi = sorted(reachable[0])
    return math.isclose(min(lo, hi), min(start, end), abs_tol=step / 2) and math.isclose(
        max(lo, hi), max(start, end), abs_tol=step / 2
    )


def _drawn_world(document: Json) -> dict[tuple[str, str], tuple[float, float, float]]:
    """Every named point where it was drawn, in world coordinates: a planar body's points are in
    its plane's coordinates, a spatial body's in the world's."""
    planes = {p["id"]: p for p in document["planes"]}

    def vec(v: Json) -> npt.NDArray[np.float64]:
        return np.array([v["x"], v["y"], v["z"]], dtype=np.float64)

    out: dict[tuple[str, str], tuple[float, float, float]] = {}
    for body in document["bodies"]:
        plane = planes.get(body["planeId"]) if body["planeId"] is not None else None
        for point in body["points"]:
            local = vec(point["local"])
            if plane is not None:
                x, n = vec(plane["xAxisWorld"]), vec(plane["normalWorld"])
                local = vec(plane["originWorld"]) + local[0] * x + local[1] * np.cross(n, x)
            out[(body["id"], point["id"])] = (float(local[0]), float(local[1]), float(local[2]))
    return out


def _holds_drawn_pose(built: Built, solver: Solver, state: npt.NDArray[np.float64]) -> bool:
    """Whether the assembled points are where the family drew them (bodies drawn in place)."""
    drawn = _drawn_world(built.document)
    positions = solver.point_positions(state)
    expected = np.array([drawn[name] for name in solver.point_names])
    extent = float(np.ptp(expected, axis=0).max()) or 1.0
    return bool(np.abs(positions - expected).max() <= 1e-9 * extent)


def _sweep(
    solver: Solver, drawn: npt.NDArray[np.float64], end: float, requirements: Requirements
) -> tuple[str | None, float]:
    """Sweeps from the drawn pose to `end`: a rejection reason or None, and the least driven
    transmission angle seen."""
    drive = np.zeros(solver.driver_count)
    step = requirements.step
    sim = solver.simulate(0, drive, 0.0, end, step, seed=drawn)
    if not _covers(sim.reachable, 0.0, end, step):
        return f"the driver range breaks off: reachable {sim.reachable}", math.pi / 2
    kinds = {s.kind for s in sim.singularities}
    if SingularityKind.DEAD_CENTER in kinds:
        return "a dead center inside the driver range", math.pi / 2
    if SingularityKind.BIFURCATION in kinds and not requirements.allow_bifurcation:
        return "a branch point inside the driver range", math.pi / 2
    report = solver.plausibility(0, drive, 0.0, end, step, seed=drawn)
    if report.collisions:
        a, b = report.collisions[0].bodies
        return f"bodies {a} and {b} collide", math.pi / 2
    # The transmission angle of a driven loop is at the coupler-output joint. The angle at the
    # input-coupler joint folds flat at every rocker extreme of a crank-rocker; it only matters
    # when the output drives.
    least = min(
        (
            t.min_angle
            for loop in report.loops
            for t in loop.transmission
            if t.joint_id == loop.joints[2]
        ),
        default=math.pi / 2,
    )
    return None, least


def _parse(built: Built) -> tuple[MechanismModel, Solver] | str:
    try:
        return checked(built.document)
    except pydantic.ValidationError as e:
        return f"schema: {e.errors()[0]['msg']}"
    except InvalidGraphError as e:
        return f"graph: {e.issues[0].message}"


def check(built: Built, requirements: Requirements) -> Verdict:
    parsed = _parse(built)
    if isinstance(parsed, str):
        return Verdict(parsed)
    model, solver = parsed
    try:
        drawn = solver.assemble(np.zeros(solver.driver_count))
    except AssemblyFailedError:
        return Verdict("the drawn pose does not assemble")
    if not _holds_drawn_pose(built, solver, drawn):
        # The solver assembled elsewhere, perhaps on another branch than the one drawn.
        return Verdict("the drawn pose does not satisfy the joints")
    least = math.pi / 2
    # Sweep outward from the drawn pose, so both halves keep the drawn branch.
    for end in (e for e in built.drive_range if e != 0.0):
        reason, angle = _sweep(solver, drawn, end, requirements)
        if reason is not None:
            return Verdict(reason)
        least = min(least, angle)
    if least < requirements.min_transmission:
        return Verdict(
            f"transmission angle {math.degrees(least):.1f}° is below "
            f"{math.degrees(requirements.min_transmission):.1f}°",
            min_transmission=least,
        )
    return Verdict(None, model, solver, least)

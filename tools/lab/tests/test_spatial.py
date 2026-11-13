"""Spatial and multi-plane families (requirement 1.1)."""

import json
import math

import numpy as np
import numpy.typing as npt
import pytest
from orrery_kinematics import Simulation, Solver
from orrery_lab.families import family
from orrery_lab.feasibility import check
from orrery_lab.graph import Json
from orrery_lab.sampling import Sample, generate

STEP = math.tau / 120


def full_turn(document: Json) -> tuple[Solver, Simulation]:
    solver = Solver(json.dumps(document))
    drive = np.zeros(solver.driver_count)
    drawn = solver.assemble(drive)
    return solver, solver.simulate(0, drive, 0.0, math.tau, STEP, seed=drawn)


def track(solver: Solver, sim: Simulation, body: str, point: str) -> npt.NDArray[np.float64]:
    return sim.points[:, solver.point_names.index((body, point)), :]


def axis(sample: Sample, joint_id: str) -> npt.NDArray[np.float64]:
    joint = next(j for j in sample.built.document["joints"] if j["id"] == joint_id)
    a = joint["axisLocalA"]
    return np.array([a["x"], a["y"], a["z"]])


def test_rssr_bodies_stay_rigid_and_the_rocker_turns_about_its_skew_axle() -> None:
    for seed in range(3):
        sample = generate(family("spatial-rssr"), seed)
        solver, sim = full_turn(sample.built.document)
        ((start, end),) = sim.reachable
        assert (start, end) == (0.0, pytest.approx(math.tau))
        b, c = track(solver, sim, "coupler", "b"), track(solver, sim, "coupler", "c")
        length = np.linalg.norm(c - b, axis=1)
        assert np.ptp(length) < 1e-9
        o2 = track(solver, sim, "frame", "o2")
        arm = track(solver, sim, "rocker", "c") - o2
        u2 = axis(sample, "r-output")
        # The rocker's ball stays in the plane through its axle perpendicular to the axle.
        assert np.abs(arm @ u2 - (arm @ u2)[0]).max() < 1e-9
        assert np.ptp(np.linalg.norm(arm, axis=1)) < 1e-9
        # And it moves: the rocker swings through a real angle.
        lengths: npt.NDArray[np.float64] = np.linalg.norm(arm, axis=1)
        cos = (arm @ arm[0]) / (lengths * lengths[0])
        assert math.acos(float(np.clip(cos, -1.0, 1.0).min())) > 0.1


def yoke_angle(
    solver: Solver, sim: Simulation, document: Json, side: str
) -> npt.NDArray[np.float64]:
    plane = next(p for p in document["planes"] if p["id"] == f"plane-{side}")
    x = np.array([plane["xAxisWorld"][k] for k in "xyz"])
    n = np.array([plane["normalWorld"][k] for k in "xyz"])
    y = np.cross(n, x)
    arm = track(solver, sim, f"{side}-yoke", "pin") - track(solver, sim, "frame", f"{side}-axle")
    return np.unwrap(np.arctan2(arm @ y, arm @ x))


def test_two_planes_hold_bodies_in_each_plane() -> None:
    sample = generate(family("two-plane-cardan"), 0)
    planes = {b["planeId"] for b in sample.built.document["bodies"]}
    assert planes == {None, "plane-front", "plane-rear"}


def test_a_double_cardan_between_parallel_planes_turns_the_output_with_the_input() -> None:
    chosen = family("two-plane-cardan")
    accepted = 0
    for seed in range(12):
        params = dict(generate(chosen, seed).params)
        params["tilt"] = 0.0
        built = chosen.build(params, np.random.default_rng(0), f"parallel-{seed}")
        if not check(built, chosen.requirements).accepted:
            continue
        accepted += 1
        solver, sim = full_turn(built.document)
        turned_in = yoke_angle(solver, sim, built.document, "front")
        turned_out = yoke_angle(solver, sim, built.document, "rear")
        # Equal joint angles at both ends, yokes in phase: a constant-velocity coupling.
        np.testing.assert_allclose(turned_out - turned_out[0], turned_in - turned_in[0], atol=1e-8)
    assert accepted >= 3


def test_a_tilted_rear_plane_makes_the_output_speed_vary() -> None:
    chosen = family("two-plane-cardan")
    for seed in range(20):
        sample = generate(chosen, seed)
        if abs(sample.params["tilt"]) < 0.2:
            continue
        solver, sim = full_turn(sample.built.document)
        turned_in = yoke_angle(solver, sim, sample.built.document, "front")
        turned_out = yoke_angle(solver, sim, sample.built.document, "rear")
        lag = (turned_out - turned_out[0]) - (turned_in - turned_in[0])
        # One output turn per input turn, but not in step within it.
        assert abs(lag[-1]) < 1e-8
        assert np.ptp(lag) > 1e-3
        return
    raise AssertionError("no tilted sample in 20 seeds")

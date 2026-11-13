"""The solver's Python bindings (mechanism-core requirement 10) on the golden mechanisms.

These run the real extension module built by maturin; nothing is mocked.
"""

import copy
import json
import math
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from orrery_kinematics import (
    AssemblyFailedError,
    DriverCountError,
    GrashofClass,
    InvalidGraphError,
    SeedLengthError,
    Solver,
    SolverError,
    fit,
)

GOLDEN = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "mechanism"
VALID = sorted(GOLDEN.glob("*.json"))


def four_bar() -> dict[str, Any]:
    return json.loads((GOLDEN / "four-bar-crank-rocker.json").read_text())


def point_index(solver: Solver, body: str, point: str) -> int:
    return solver.point_names.index((body, point))


# Requirement 2.4 and property 10: the same rules fail in Python as in TypeScript and Rust.
INVALID = {
    "dangling-body.json": "references non-existent body missing-body",
    "dangling-driver-joint.json": "references non-existent joint missing-joint",
    "dangling-plane.json": "references non-existent plane missing-plane",
    "dangling-point.json": "references non-existent point missing-point",
    "duplicate-body-id.json": "Duplicate body IDs",
    "duplicate-joint-id.json": "Duplicate joint IDs",
    "self-joint.json": "connects body coupler to itself",
    "two-grounds.json": "exactly one ground body, found 2",
}


def test_the_invalid_golden_set_is_the_one_listed() -> None:
    assert sorted(p.name for p in (GOLDEN / "invalid").glob("*.json")) == sorted(INVALID)


@pytest.mark.parametrize(("name", "message"), sorted(INVALID.items()))
def test_every_invalid_golden_file_fails_for_the_rule_it_breaks(name: str, message: str) -> None:
    with pytest.raises(InvalidGraphError) as raised:
        Solver((GOLDEN / "invalid" / name).read_text())
    error = raised.value
    assert error.kind == "invalidGraph"
    assert any(message in issue.message for issue in error.issues), error.issues
    assert all(issue.path for issue in error.issues)
    assert message in str(error)


def test_a_document_that_does_not_parse_is_an_invalid_graph_without_a_path() -> None:
    with pytest.raises(InvalidGraphError) as raised:
        Solver("{ not json")
    assert [issue.path for issue in raised.value.issues] == [""]


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_every_golden_mechanism_assembles_at_its_drawn_pose(path: Path) -> None:
    solver = Solver(path.read_text())
    graph = json.loads(path.read_text())
    assert solver.driver_count == len(graph["drivers"])
    state = solver.assemble(np.zeros(solver.driver_count))
    assert state.shape == (solver.state_size,)
    assert state.dtype == np.float64
    positions = solver.point_positions(state)
    assert positions.shape == (len(solver.point_names), 3)
    assert np.isfinite(positions).all()


def test_driver_values_may_be_any_sequence_of_numbers() -> None:
    solver = Solver(json.dumps(four_bar()))
    from_list = solver.assemble([0.4])
    from_ints = solver.assemble(np.array([0], dtype=np.int32))
    np.testing.assert_allclose(from_list, solver.assemble(np.array([0.4])), atol=0.0)
    np.testing.assert_allclose(from_ints, solver.assemble([0.0]), atol=0.0)


def test_a_cycle_keeps_every_body_rigid() -> None:
    # Property 2: two points of one body stay the same distance apart over the cycle.
    solver = Solver(json.dumps(four_bar()))
    sim = solver.simulate(0, [0.0], 0.0, math.tau, 0.05)
    assert sim.reachable == [(0.0, pytest.approx(math.tau))]
    samples = sim.drive.shape[0]
    assert samples == 127
    assert sim.states.shape == (samples, solver.state_size)
    assert sim.points.shape == (samples, len(solver.point_names), 3)
    b = point_index(solver, "coupler", "b")
    trace = point_index(solver, "coupler", "trace")
    distance = np.linalg.norm(sim.points[:, b] - sim.points[:, trace], axis=1)
    assert np.ptp(distance) < 1e-9
    # Each sample's points are the positions at its state.
    np.testing.assert_allclose(solver.point_positions(sim.states[40]), sim.points[40], atol=1e-12)


def test_result_arrays_are_handed_over_without_copies() -> None:
    # Requirement 10.2: each array wraps the solver's own buffer (its base is the Rust vector)
    # and is created once, so reading a field never copies.
    sim = Solver(json.dumps(four_bar())).simulate(0, [0.0], 0.0, 1.0, 0.1)
    for array in (sim.drive, sim.states, sim.points):
        assert array.base is not None
        assert array.flags.c_contiguous
    assert sim.states is sim.states


def test_a_seed_keeps_its_assembly_branch() -> None:
    solver = Solver(json.dumps(four_bar()))
    drawn = solver.assemble([0.0])
    again = solver.assemble([0.0], seed=drawn)
    np.testing.assert_allclose(again, drawn, atol=1e-12)


def test_errors_carry_the_typed_fields() -> None:
    solver = Solver(json.dumps(four_bar()))
    with pytest.raises(DriverCountError) as count:
        solver.assemble([0.0, 1.0])
    assert (count.value.kind, count.value.expected, count.value.got) == ("driverCount", 1, 2)
    with pytest.raises(SeedLengthError) as seed:
        solver.point_positions([0.0])
    assert (seed.value.kind, seed.value.expected, seed.value.got) == (
        "seedLength",
        solver.state_size,
        1,
    )
    assert isinstance(seed.value, SolverError)


def test_a_loop_that_cannot_close_reports_its_worst_joints() -> None:
    graph = four_bar()
    # Move the rocker's pivot out of reach of crank, coupler, and rocker together.
    graph["bodies"][0]["points"][1]["local"]["x"] = 2.0
    solver = Solver(json.dumps(graph))
    with pytest.raises(AssemblyFailedError) as raised:
        solver.assemble([0.0])
    worst = raised.value.worst_joints
    assert raised.value.kind == "assemblyFailed"
    assert worst
    assert worst[0].residual > 0.1
    assert [j.residual for j in worst] == sorted((j.residual for j in worst), reverse=True)


def test_mobility_of_the_four_bar() -> None:
    solver = Solver(json.dumps(four_bar()))
    state = solver.assemble([0.3])
    mobility = solver.mobility(state, [0.3])
    assert (mobility.grubler, mobility.numerical) == (1, 1)
    assert mobility.redundant == []
    # With the crank driven, nothing is left free.
    assert mobility.free_motions == []


def test_plausibility_of_the_four_bar() -> None:
    solver = Solver(json.dumps(four_bar()))
    report = solver.plausibility(0, [0.0], 0.0, math.tau, 0.02)
    (loop,) = report.loops
    assert loop.grashof == GrashofClass.CRANK_ROCKER
    assert loop.lengths == pytest.approx((0.3, 0.1, 0.25, 0.2))
    assert all(0.0 <= t.min_angle <= math.pi / 2 for t in loop.transmission)


def observations(angles: list[float]) -> list[dict[str, Any]]:
    truth = Solver(json.dumps(four_bar()))
    tracked = [("crank", "b"), ("coupler", "trace"), ("rocker", "tip")]
    out: list[dict[str, Any]] = []
    seed = None
    for frame, angle in enumerate(angles):
        state = truth.assemble([angle], seed=seed)
        positions = truth.point_positions(state)
        for body, point in tracked:
            x, y, _ = positions[point_index(truth, body, point)]
            out.append(
                {
                    "frame": frame,
                    "body": body,
                    "point": point,
                    "position": [float(x), float(y)],
                    "weight": 1.0,
                }
            )
        seed = state
    return out


PATHS = {
    "bodies.ground.points.o4.local.x": 0.3,
    "bodies.crank.points.b.local.x": 0.1,
    "bodies.coupler.points.c.local.x": 0.25,
    "bodies.rocker.points.c.local.x": 0.2,
}


def fit_problem(frames: int) -> dict[str, Any]:
    angles = [0.3 + 5.5 * t / frames for t in range(frames)]
    start = copy.deepcopy(four_bar())
    start["bodies"][0]["points"][1]["local"]["x"] = 0.31
    start["bodies"][1]["points"][1]["local"]["x"] = 0.104
    start["bodies"][2]["points"][1]["local"]["x"] = 0.265
    start["bodies"][3]["points"][1]["local"]["x"] = 0.19
    return {
        "mechanism": start,
        "parameters": [{"path": p} for p in PATHS],
        "drive": [[a + 0.03 * math.sin(7 * a)] for a in angles],
        "observations": observations(angles),
        "camera": {"type": "plane", "plane": "plane-main"},
        "loss": {"type": "squared"},
        "maxIterations": 50,
    }


def test_exact_tracks_fit_back_to_the_true_geometry() -> None:
    frames = 30
    result = fit(json.dumps(fit_problem(frames)))
    np.testing.assert_allclose(result.values, list(PATHS.values()), atol=1e-7)
    assert result.sigma.shape == (len(PATHS),)
    assert result.drive.shape == (frames, 1)
    assert result.poses.shape[0] == frames
    assert result.residuals.shape == (3 * frames, 2)
    np.testing.assert_array_equal(result.weights, np.ones(3 * frames))
    assert result.rms < 1e-8
    assert result.camera_global.shape == (0,)
    fitted = json.loads(result.mechanism_json)
    assert fitted["bodies"][1]["points"][1]["local"]["x"] == pytest.approx(0.1, abs=1e-7)
    # The fitted graph is a valid mechanism whose poses satisfy the joints.
    refitted = Solver(result.mechanism_json)
    np.testing.assert_allclose(
        refitted.assemble(result.drive[5], seed=result.poses[5]), result.poses[5], atol=1e-9
    )


def test_a_fit_problem_that_does_not_parse_is_an_invalid_graph() -> None:
    problem = fit_problem(3)
    del problem["camera"]
    with pytest.raises(InvalidGraphError, match="camera"):
        fit(json.dumps(problem))


def test_solving_releases_the_gil() -> None:
    # Requirement 10.3: while a long sweep runs on another thread, this thread keeps running.
    solver = Solver(json.dumps(four_bar()))
    done = threading.Event()
    elapsed: list[float] = []

    def sweep() -> None:
        start = time.perf_counter()
        solver.simulate(0, [0.0], 0.0, 40 * math.tau, 0.002)
        elapsed.append(time.perf_counter() - start)
        done.set()

    worker = threading.Thread(target=sweep)
    last = time.perf_counter()
    longest_gap = 0.0
    worker.start()
    while not done.is_set():
        now = time.perf_counter()
        longest_gap = max(longest_gap, now - last)
        last = now
    worker.join()
    (duration,) = elapsed
    assert duration > 0.2, "the sweep is too short to tell"
    assert longest_gap < duration / 4, (longest_gap, duration)

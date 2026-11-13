"""Each linkage family moves the way its namesake does (requirement 1.1)."""

import math

import numpy as np
import numpy.typing as npt
import pytest
from orrery_kinematics import Simulation, Solver
from orrery_lab.families import FAMILIES, family
from orrery_lab.sampling import Sample, generate

STEP = math.tau / 180


def sweep(sample: Sample) -> tuple[Solver, Simulation]:
    solver = Solver(sample.graph_json())
    drive = np.zeros(solver.driver_count)
    drawn = solver.assemble(drive)
    low, high = sample.built.drive_range
    if sample.built.cyclic:
        return solver, solver.simulate(0, drive, low, high, STEP, seed=drawn)
    # A rocking input: sweep from its low end, reached from the drawn pose.
    start = solver.simulate(0, drive, 0.0, low, STEP, seed=drawn).states[-1]
    return solver, solver.simulate(0, drive, low, high, STEP, seed=start)


def track(solver: Solver, sim: Simulation, body: str, point: str) -> npt.NDArray[np.float64]:
    return sim.points[:, solver.point_names.index((body, point)), :2]


def outputs(solver: Solver, sample: Sample) -> list[tuple[str, str]]:
    roles = {
        (b["id"], p["id"]): p["role"] for b in sample.built.document["bodies"] for p in b["points"]
    }
    return [name for name in solver.point_names if roles[name] == "output"]


def size(sample: Sample) -> float:
    """The diagonal of the drawn mechanism's bounding box."""
    points = np.array(
        [
            (p["local"]["x"], p["local"]["y"])
            for b in sample.built.document["bodies"]
            for p in b["points"]
        ]
    )
    return float(np.hypot(*np.ptp(points, axis=0)))


@pytest.mark.parametrize("name", sorted(FAMILIES))
def test_every_family_moves_its_output(name: str) -> None:
    for seed in range(3):
        sample = generate(family(name), seed)
        solver, sim = sweep(sample)
        names = outputs(solver, sample)
        assert names, "the family names no output point"
        for body, point in names:
            path = track(solver, sim, body, point)
            assert np.ptp(path, axis=0).max() > 0.02 * size(sample), (seed, body)


def line_residual(path: npt.NDArray[np.float64]) -> float:
    """Largest distance of the points from their best-fit line."""
    centered = path - path.mean(axis=0)
    _, singular, _ = np.linalg.svd(centered, full_matrices=False)
    return float(singular[-1] / math.sqrt(len(path)))


def test_peaucellier_lipkin_draws_an_exact_straight_line() -> None:
    for seed in range(4):
        sample = generate(family("peaucellier-lipkin"), seed)
        solver, sim = sweep(sample)
        pen = track(solver, sim, "side-bp", "pen")
        assert np.ptp(pen, axis=0).max() > 0.05 * sample.params["scale"]
        assert line_residual(pen) < 1e-9


def test_the_pantograph_copies_its_tracer_at_its_ratio() -> None:
    for seed in range(4):
        sample = generate(family("pantograph"), seed)
        solver, sim = sweep(sample)
        o = track(solver, sim, "frame", "o")
        tracer = track(solver, sim, "crank", "t") - o
        pen = track(solver, sim, "arm-ap", "pen") - o
        np.testing.assert_allclose(pen, sample.params["ratio"] * tracer, atol=1e-9)


def test_the_scotch_yoke_moves_in_simple_harmonic_motion() -> None:
    sample = generate(family("scotch-yoke"), 2)
    solver, sim = sweep(sample)
    turn = sample.params["frame_angle"]
    axis = np.array([math.cos(turn), math.sin(turn)])
    along = track(solver, sim, "yoke", "rod-end") @ axis
    crank = sample.params["scale"] / (1.0 + sample.params["rod_reach"])
    phase = sample.params["input_angle"] + sim.drive
    np.testing.assert_allclose(
        along - along[0], crank * (np.cos(phase) - np.cos(phase[0])), atol=1e-9
    )


def test_the_slider_crank_block_stays_on_its_guide() -> None:
    sample = generate(family("slider-crank"), 5)
    solver, sim = sweep(sample)
    path = track(solver, sim, "slider", "c")
    assert line_residual(path) < 1e-12
    # The stroke of an offset slider-crank is a little over twice the crank.
    crank = sample.params["crank"] * sample.params["scale"]
    assert 2 * crank * 0.99 < np.hypot(*np.ptp(path, axis=0)) < 2 * crank * 1.3


def test_the_whitworth_ram_returns_faster_than_it_cuts() -> None:
    for seed in range(3):
        sample = generate(family("whitworth-quick-return"), seed)
        solver, sim = sweep(sample)
        turn = sample.params["frame_angle"]
        axis = np.array([math.cos(turn), math.sin(turn)])
        ram = track(solver, sim, "ram", "tool") @ axis
        forward = np.diff(ram) > 0
        ratio = forward.sum() / (~forward).sum()
        assert max(ratio, 1 / ratio) > 1.2, (seed, ratio)


def test_the_jansen_foot_walks_a_flat_stride() -> None:
    sample = generate(family("jansen-leg"), 1)
    solver, sim = sweep(sample)
    turn = sample.params["frame_angle"]
    # Back into the leg's own frame, where the ground is horizontal.
    c, s = math.cos(-turn), math.sin(-turn)
    toe = track(solver, sim, "foot", "toe") @ np.array([[c, s], [-s, c]])
    low = toe[:, 1] < toe[:, 1].min() + 0.05 * np.ptp(toe[:, 1])
    # A good share of the turn is spent on the nearly flat bottom of the stride.
    assert low.mean() > 0.25
    assert np.ptp(toe[low, 0]) > 0.4 * np.ptp(toe[:, 0])


def test_both_wings_flap() -> None:
    sample = generate(family("flapping-wing"), 3)
    solver, sim = sweep(sample)
    for side in ("left", "right"):
        pivot = track(solver, sim, "frame", "wl" if side == "left" else "wr")
        tip = track(solver, sim, f"wing-{side}", "tip")
        angle = np.unwrap(np.arctan2(*(tip - pivot).T[::-1]))
        # The wing rocks: up and back down within the turn, through a real arc.
        assert 0.2 < np.ptp(angle) < math.pi

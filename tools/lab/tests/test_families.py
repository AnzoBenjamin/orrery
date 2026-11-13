"""Families and the sampler (synthetic-lab requirements 1.2 and 1.5, property 1)."""

import json
import math

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from orrery_kinematics import GrashofClass, Solver
from orrery_lab.families import FAMILIES, family
from orrery_lab.families.four_bar import FourBar
from orrery_lab.feasibility import check
from orrery_lab.generated.mechanism import Mechanism
from orrery_lab.sampling import generate

NAMES = sorted(FAMILIES)


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(name=st.sampled_from(NAMES), seed=st.integers(0, 2**31 - 1))
def test_every_accepted_sample_validates_and_assembles_over_its_range(name: str, seed: int) -> None:
    # Property 1.
    result = generate(family(name), seed)
    text = result.graph_json()
    Mechanism.model_validate_json(text)
    solver = Solver(text)
    drive = np.zeros(solver.driver_count)
    drawn = solver.assemble(drive)
    low, high = result.built.drive_range
    assert low <= 0.0 <= high
    for end in (low, high):
        if end != 0.0:
            sim = solver.simulate(0, drive, 0.0, end, math.tau / 90, seed=drawn)
            assert len(sim.reachable) == 1
            assert sim.reachable[0][1] == pytest.approx(end, abs=math.tau / 180)


@pytest.mark.parametrize("name", NAMES)
def test_the_same_seed_gives_the_same_sample(name: str) -> None:
    a, b = generate(family(name), 7), generate(family(name), 7)
    assert a.graph_json() == b.graph_json()
    assert a.params == b.params
    assert generate(family(name), 8).graph_json() != a.graph_json()


@pytest.mark.parametrize("name", NAMES)
def test_samples_stay_inside_the_parameter_space(name: str) -> None:
    chosen = family(name)
    for seed in range(3):
        assert chosen.parameter_space().contains(generate(chosen, seed).params)


GRASHOF = {
    "four-bar-crank-rocker": GrashofClass.CRANK_ROCKER,
    "four-bar-double-crank": GrashofClass.DOUBLE_CRANK,
    "four-bar-double-rocker": GrashofClass.DOUBLE_ROCKER,
    "four-bar-change-point": GrashofClass.CHANGE_POINT,
}


@pytest.mark.parametrize(("name", "expected"), sorted(GRASHOF.items()))
def test_four_bar_classes_are_what_the_solver_classifies(name: str, expected: GrashofClass) -> None:
    for seed in range(4):
        result = generate(family(name), seed)
        solver = Solver(result.graph_json())
        low, high = result.built.drive_range
        end = high if high != 0.0 else low
        report = solver.plausibility(0, np.zeros(1), 0.0, end, math.tau / 90)
        (loop,) = report.loops
        assert loop.grashof == expected, (seed, loop.lengths)


def test_cranks_turn_fully_and_rockers_rock() -> None:
    crank = generate(family("four-bar-crank-rocker"), 3)
    assert crank.built.cyclic
    assert crank.built.drive_range == (0.0, math.tau)
    rocker = generate(family("four-bar-double-rocker"), 3)
    assert not rocker.built.cyclic
    low, high = rocker.built.drive_range
    assert low < 0.0 < high < math.pi
    profile = rocker.built.document["drivers"][0]["profile"]
    assert profile["type"] == "samples"
    assert min(profile["q"]) == pytest.approx(low)
    assert max(profile["q"]) == pytest.approx(high)


def test_driven_loops_keep_the_minimum_transmission_angle() -> None:
    for seed in range(5):
        result = generate(family("four-bar-crank-rocker"), seed)
        assert result.min_transmission >= math.radians(20)


def test_a_rejected_draw_names_its_reason() -> None:
    # A crank-rocker whose frame minus crank is barely more than rocker minus coupler: with the
    # crank pointing at the rocker's pivot, coupler and rocker are 19.7° from folding.
    chosen = FourBar("crank-rocker")
    params = {
        "scale": 0.1,
        "frame": 0.78,
        "input": 0.3,
        "coupler": 0.6,
        "output": 1.0,
        "frame_angle": 0.0,
        "input_angle": 0.25,
        "branch": 0.0,
        "coupler_along": 0.5,
        "coupler_across": 0.2,
        "output_extension": 1.1,
    }
    built = chosen.build(params, np.random.default_rng(0), "rejected")
    verdict = check(built, chosen.requirements)
    assert not verdict.accepted
    assert verdict.reason is not None
    assert "transmission angle" in verdict.reason


def test_samples_are_drawn_in_their_assembled_pose() -> None:
    # Each body's local frame is the world frame at driver zero, so the drawn pose holds.
    result = generate(family("four-bar-double-crank"), 11)
    document = result.built.document
    solver = Solver(json.dumps(document))
    state = solver.assemble(np.zeros(1))
    positions = solver.point_positions(state)
    local = {
        (body["id"], point["id"]): (point["local"]["x"], point["local"]["y"])
        for body in document["bodies"]
        for point in body["points"]
    }
    for (body, point), xyz in zip(solver.point_names, positions, strict=True):
        assert xyz[:2] == pytest.approx(local[(body, point)], abs=1e-12)

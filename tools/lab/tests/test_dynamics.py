"""Planar loose-part dynamics (requirement 2.2 and property 5)."""

import copy
import math
from dataclasses import replace

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from orrery_lab.appearance import BodyAppearance
from orrery_lab.breakage import BreakageRecord, Broken, apply_breakage
from orrery_lab.dynamics import (
    DynamicsConfig,
    DynamicsWorld,
    Push,
    UnsupportedDynamicsError,
    simulate,
)
from orrery_lab.dynamics_geometry import mass_properties
from orrery_lab.families import FAMILIES, family
from orrery_lab.family import PartKind, PartRef
from orrery_lab.sampling import Sample, generate

FRICTIONLESS = DynamicsConfig(
    step=1.0 / 480.0,
    ground_y=-100.0,
    ground_friction=0.0,
    restitution=1.0,
    revolute_friction=0.0,
    prismatic_friction=0.0,
)


def part_of_kind(sample: Sample, kind: PartKind) -> PartRef:
    return next(part for part in sample.built.breakable if part.kind == kind)


def free_coupler(seed: int = 8) -> Broken:
    sample = generate(family("four-bar-crank-rocker"), seed)
    document = copy.deepcopy(sample.built.document)
    document["id"] = f"{sample.id}-free-coupler"
    document["joints"] = [
        joint for joint in document["joints"] if "coupler" not in (joint["bodyA"], joint["bodyB"])
    ]
    record = BreakageRecord("free-coupler", "binary_link", (), (), (), ())
    return Broken(document, copy.deepcopy(sample.appearance), record)


def test_polygon_mass_properties_include_holes_and_cutouts() -> None:
    solid = BodyAppearance(
        "plate",
        "A",
        outline=[(-2.0, -1.0), (2.0, -1.0), (2.0, 1.0), (-2.0, 1.0)],
        thickness=0.5,
    )
    plain = mass_properties(solid, density=3.0)
    assert plain.area == pytest.approx(8.0)
    assert plain.centroid == pytest.approx((0.0, 0.0))
    assert plain.mass == pytest.approx(12.0)
    assert plain.inertia == pytest.approx(plain.mass * (4.0**2 + 2.0**2) / 12)

    cut = copy.deepcopy(solid)
    cut.cutouts.append([(0.0, -0.5), (1.0, -0.5), (1.0, 0.5), (0.0, 0.5)])
    carved = mass_properties(cut, density=3.0)
    assert carved.area == pytest.approx(7.0)
    assert carved.centroid[0] < 0.0
    assert carved.mass < plain.mass


def test_solver_mobility_selects_only_newly_loose_bodies() -> None:
    sample = generate(family("four-bar-crank-rocker"), 3)
    broken = apply_breakage(sample, part_of_kind(sample, "binary_link"), "loose-four-bar")
    world = DynamicsWorld.from_broken(broken, FRICTIONLESS)

    assert world.active_body_ids == ("output",)
    assert "input" not in world.active_body_ids


def test_a_free_body_follows_ballistic_motion() -> None:
    broken = free_coupler()
    world = DynamicsWorld.from_broken(broken, FRICTIONLESS)
    body = "coupler"
    start = world.frame().poses[body]
    world.apply_push(Push(0.0, body, (0.3, 0.2)))
    velocity = world.frame().velocities[body]
    duration = 0.25
    trajectory = world.run(duration)
    end = trajectory.frames[-1].poses[body]

    assert end.x == pytest.approx(start.x + velocity.x * duration, rel=2e-4)
    expected_y = start.y + velocity.y * duration + 0.5 * FRICTIONLESS.gravity[1] * duration**2
    assert end.y == pytest.approx(expected_y, rel=2e-4, abs=2e-5)


def test_a_ground_pinned_part_hangs_and_joint_friction_damps_it() -> None:
    sample = generate(family("four-bar-crank-rocker"), 9)
    broken = apply_breakage(sample, part_of_kind(sample, "binary_link"), "hanging-output")
    undamped = simulate(broken, 0.5, config=FRICTIONLESS)
    damped = simulate(
        broken,
        0.5,
        config=replace(FRICTIONLESS, revolute_friction=0.02),
    )

    assert undamped.frames[-1].poses["output"] != undamped.frames[0].poses["output"]
    assert damped.energies[-1] < damped.energies[0]
    assert max(frame.constraint_residual for frame in undamped.frames) < 1e-6


def test_a_prismatic_loose_part_stays_on_its_guide() -> None:
    sample = generate(family("slider-crank"), 4)
    broken = apply_breakage(sample, part_of_kind(sample, "binary_link"), "loose-slider")
    joint = next(joint for joint in broken.document["joints"] if joint["kind"] == "prismatic")
    axis = np.array([joint["axisLocalA"]["x"], joint["axisLocalA"]["y"]])
    trajectory = simulate(
        broken,
        0.2,
        config=FRICTIONLESS,
        pushes=(Push(0.0, "slider", tuple(0.2 * axis)),),
    )
    start, end = trajectory.frames[0].poses["slider"], trajectory.frames[-1].poses["slider"]
    moved = np.array([end.x - start.x, end.y - start.y])

    assert abs(float(axis[0] * moved[1] - axis[1] * moved[0])) < 1e-7
    assert end.angle == pytest.approx(start.angle, abs=1e-8)


def test_a_push_respects_a_retained_gear_ratio() -> None:
    sample = generate(family("gear-train"), 0)
    broken = apply_breakage(sample, sample.built.breakable[0], "loose-gears")
    world = DynamicsWorld.from_broken(broken, FRICTIONLESS)
    assert len(world.active_body_ids) >= 2
    body = world.active_body_ids[0]
    point = broken.appearance.bodies[body].outline[0]
    world.apply_push(Push(0.0, body, (0.0, 0.02), point_local=point))
    world.run(0.1)

    assert world.constraint_residual() < 1e-6


def test_ground_contact_prevents_persistent_penetration_and_applies_friction() -> None:
    broken = free_coupler(10)
    probe = DynamicsWorld.from_broken(broken, FRICTIONLESS)
    floor = probe.minimum_height("coupler") - 0.01
    config = replace(
        FRICTIONLESS,
        ground_y=floor,
        restitution=0.0,
        ground_friction=0.7,
    )
    trajectory = simulate(
        broken,
        0.35,
        config=config,
        pushes=(Push(0.0, "coupler", (0.2, -0.1)),),
    )
    final = trajectory.frames[-1]

    assert final.minimum_heights["coupler"] >= floor - 1e-7
    assert abs(final.velocities["coupler"].x) < abs(trajectory.frames[0].velocities["coupler"].x)


@settings(max_examples=8, deadline=None)
@given(
    seed=st.integers(0, 1000),
    impulse_x=st.floats(-0.4, 0.4, allow_nan=False, allow_infinity=False),
    impulse_y=st.floats(-0.4, 0.4, allow_nan=False, allow_infinity=False),
)
def test_frictionless_loose_motion_conserves_energy(
    seed: int, impulse_x: float, impulse_y: float
) -> None:
    # Property 5. A free removed-constraint body exercises translation, rotation, and gravity
    # without contact, so no unmodelled external work enters the one-second interval.
    broken = free_coupler(seed)
    body = "coupler"
    point = broken.appearance.bodies[body].outline[0]
    trajectory = simulate(
        broken,
        1.0,
        config=FRICTIONLESS,
        pushes=(Push(0.0, body, (impulse_x, impulse_y), point_local=point),),
    )
    baseline = max(abs(trajectory.energies[0]), 1e-9)
    drift = max(abs(energy - trajectory.energies[0]) for energy in trajectory.energies) / baseline
    assert drift < 0.01


def test_dynamics_are_exactly_deterministic() -> None:
    broken = free_coupler(13)
    pushes = (Push(0.0, "coupler", (0.2, 0.1)),)
    first = simulate(broken, 0.1, config=FRICTIONLESS, pushes=pushes)
    second = simulate(broken, 0.1, config=FRICTIONLESS, pushes=pushes)
    assert first == second


def test_every_native_planar_breakage_builds_and_steps() -> None:
    for name, chosen in sorted(FAMILIES.items()):
        if name in {"spatial-rssr", "two-plane-cardan"}:
            continue
        sample = generate(chosen, 0)
        for index, part in enumerate(sample.built.breakable):
            broken = apply_breakage(sample, part, f"{name}-broken-{index}")
            world = DynamicsWorld.from_broken(broken, FRICTIONLESS)
            world.step()
            assert math.isfinite(world.energy())
            assert world.constraint_residual() < 1e-6


def test_spatial_loose_modes_are_rejected_explicitly() -> None:
    sample = generate(family("spatial-rssr"), 0)
    broken = apply_breakage(sample, sample.built.breakable[0], "spatial-break")
    with pytest.raises(UnsupportedDynamicsError, match="spatial"):
        DynamicsWorld.from_broken(broken, FRICTIONLESS)

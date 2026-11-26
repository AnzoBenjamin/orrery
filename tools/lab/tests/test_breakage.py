"""Part removal and breakage ground truth (requirements 2.1 and 2.3, property 4)."""

import json

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from orrery_kinematics import Solver
from orrery_lab.breakage import (
    Broken,
    InvalidBreakageError,
    apply_breakage,
    generate_breakage,
)
from orrery_lab.families import FAMILIES, family
from orrery_lab.family import PartKind, PartRef
from orrery_lab.generated.mechanism import Mechanism
from orrery_lab.sampling import Sample, generate

NAMES = sorted(FAMILIES)
REPRESENTATIVES: tuple[tuple[str, PartKind], ...] = (
    ("four-bar-crank-rocker", "binary_link"),
    ("slider-crank", "slider_block"),
    ("gear-train", "gear"),
    ("belt-drive", "belt"),
    ("four-bar-crank-rocker", "adjacent_links"),
)


def part_of_kind(sample: Sample, kind: PartKind) -> PartRef:
    return next(part for part in sample.built.breakable if part.kind == kind)


@pytest.mark.parametrize(("name", "kind"), REPRESENTATIVES)
def test_every_breakage_kind_removes_exact_ground_truth(name: str, kind: PartKind) -> None:
    sample = generate(family(name), 6)
    selected = part_of_kind(sample, kind)
    broken = apply_breakage(sample, selected, f"{sample.id}-{kind}")
    document = broken.document

    Mechanism.model_validate(document)
    Solver(json.dumps(document))
    remaining_bodies = {body["id"] for body in document["bodies"]}
    remaining_joints = {joint["id"] for joint in document["joints"]}
    removed_bodies = {body.id for body in broken.record.removed_bodies}
    removed_joints = {joint.id for joint in broken.record.removed_joints}

    assert broken.record.kind == kind
    assert removed_bodies == set(selected.bodies)
    assert set(selected.joints) <= removed_joints
    assert removed_bodies.isdisjoint(remaining_bodies)
    assert removed_joints.isdisjoint(remaining_joints)
    assert all(driver["jointId"] in remaining_joints for driver in document["drivers"])
    assert removed_bodies.isdisjoint(broken.appearance.bodies)
    assert json.loads(json.dumps(broken.record.record()))["kind"] == kind


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(name=st.sampled_from(NAMES), seed=st.integers(0, 2**31 - 1))
def test_removed_anchors_coincide_with_hole_points(name: str, seed: int) -> None:
    # Property 4.
    sample = generate(family(name), seed)
    broken = generate_breakage(sample, np.random.default_rng((seed, 4)))
    bodies = {body["id"]: body for body in broken.document["bodies"]}

    for hole in broken.record.holes:
        point = next(
            point for point in bodies[hole.body_id]["points"] if point["id"] == hole.point_id
        )
        assert point["role"] == "hole"
        local = tuple(point["local"][axis] for axis in "xyz")
        assert local == pytest.approx(hole.local, abs=1e-12)
        if hole.removed_local is not None:
            assert hole.local == pytest.approx(hole.removed_local, abs=1e-12)


def test_holes_and_wear_marks_remain_on_the_surviving_parts() -> None:
    sample = generate(family("four-bar-crank-rocker"), 9)
    broken = apply_breakage(sample, part_of_kind(sample, "binary_link"), "worn-four-bar")

    assert broken.record.holes
    assert broken.record.wear_marks
    for hole in broken.record.holes:
        look = broken.appearance.bodies[hole.body_id]
        assert any(mark.center == hole.local[:2] for mark in look.wear_marks)
        assert any(circle.center == hole.local[:2] for circle in look.holes)


def test_a_removed_belt_leaves_wear_on_both_pulleys() -> None:
    sample = generate(family("belt-drive"), 4)
    selected = part_of_kind(sample, "belt")
    broken = apply_breakage(sample, selected, "missing-belt")

    assert not broken.record.removed_bodies
    assert {joint.id for joint in broken.record.removed_joints} == set(selected.joints)
    worn = {mark.body_id for mark in broken.record.wear_marks if mark.kind == "belt"}
    original_joint = next(
        joint for joint in sample.built.document["joints"] if joint["id"] in selected.joints
    )
    assert worn == {original_joint["bodyA"], original_joint["bodyB"]}


def test_breakage_selection_and_records_are_deterministic() -> None:
    sample = generate(family("sewing-machine"), 12)

    def make() -> Broken:
        return generate_breakage(sample, np.random.default_rng((44, 2)))

    first, second = make(), make()
    assert first.document == second.document
    assert first.appearance.record() == second.appearance.record()
    assert first.record.record() == second.record.record()


def test_a_part_not_offered_by_the_family_is_rejected() -> None:
    sample = generate(family("slider-crank"), 1)
    with pytest.raises(InvalidBreakageError, match="not breakable"):
        apply_breakage(sample, PartRef("binary_link", bodies=("crank",)), "invalid")

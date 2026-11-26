"""Compound machines driven output-to-input (synthetic-lab requirement 1.4)."""

import json
import math

import numpy as np
import pytest
from orrery_kinematics import Solver
from orrery_lab.appearance import dress
from orrery_lab.composer import Coupling, compose
from orrery_lab.families import family
from orrery_lab.family import Built, Requirements
from orrery_lab.feasibility import check
from orrery_lab.sampling import generate

COMPOUND_REQUIREMENTS = Requirements(min_transmission=0.0)


def dressed_compound(primary: str, secondary: str, coupling: Coupling) -> Built:
    first = generate(family(primary), 3).built
    second = generate(family(secondary), 5).built
    compound = compose(
        first,
        second,
        np.random.default_rng(17),
        f"{primary}-to-{secondary}",
        coupling=coupling,
    )
    dressed = dress(compound, COMPOUND_REQUIREMENTS, np.random.default_rng(29))
    return Built(
        dressed.document,
        compound.drive_range,
        compound.cyclic,
        compound.breakable,
    )


def assert_real_solver_sweep(built: Built) -> Solver:
    verdict = check(built, COMPOUND_REQUIREMENTS)
    assert verdict.accepted, verdict.reason
    solver = Solver(json.dumps(built.document))
    drawn = solver.assemble(np.zeros(solver.driver_count))
    low, high = built.drive_range
    for end in (low, high):
        if end == 0.0:
            continue
        simulation = solver.simulate(
            0,
            np.zeros(solver.driver_count),
            0.0,
            end,
            math.tau / 120,
            seed=drawn,
        )
        assert simulation.reachable == [(pytest.approx(0.0), pytest.approx(end))]
    return solver


def test_a_coupling_link_drives_the_second_machine() -> None:
    built = dressed_compound("four-bar-double-crank", "slider-crank", "link")
    document = built.document

    assert len(document["drivers"]) == 1
    assert sum(body["kind"] == "ground" for body in document["bodies"]) == 1
    assert any(body["id"] == "coupling-link" for body in document["bodies"])
    assert any(body["id"].startswith("stage-2-") for body in document["bodies"])
    solver = assert_real_solver_sweep(built)

    drawn = solver.assemble(np.zeros(solver.driver_count))
    simulation = solver.simulate(
        0,
        np.zeros(solver.driver_count),
        0.0,
        built.drive_range[1],
        math.tau / 120,
        seed=drawn,
    )
    output = simulation.points[:, solver.point_names.index(("stage-2-slider", "stage-2-face")), :2]
    assert np.hypot(*np.ptp(output, axis=0)) > 0.0


def test_a_gear_pair_drives_a_second_gear_train() -> None:
    built = dressed_compound("gear-train", "gear-train", "gear_pair")
    meshes = [joint for joint in built.document["joints"] if joint["kind"] == "gear_mesh"]

    assert len(built.document["drivers"]) == 1
    assert any(joint["id"] == "compound-gear-mesh" for joint in meshes)
    assert_real_solver_sweep(built)


def test_composition_is_deterministic_for_one_rng_seed() -> None:
    primary = generate(family("four-bar-double-crank"), 3).built
    secondary = generate(family("slider-crank"), 5).built

    def make() -> Built:
        return compose(
            primary,
            secondary,
            np.random.default_rng(11),
            "deterministic-compound",
            coupling="link",
        )

    assert make() == make()

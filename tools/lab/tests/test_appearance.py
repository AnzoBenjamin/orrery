"""Generated part appearance (synthetic-lab requirements 1.3 and 1.5)."""

import math

import numpy as np
import pytest
from orrery_lab.families import family
from orrery_lab.generated.mechanism import Mechanism
from orrery_lab.sampling import generate
from orrery_lab.shapes import area, spur_gear


@pytest.mark.parametrize(
    "name",
    [
        "four-bar-crank-rocker",
        "gear-train",
        "rack-and-pinion",
        "geneva-drive",
        "cam-follower-roller",
        "spatial-rssr",
        "two-plane-cardan",
    ],
)
def test_samples_have_schema_valid_part_appearance(name: str) -> None:
    sample = generate(family(name), 0)
    document = sample.built.document
    Mechanism.model_validate(document)

    for body in document["bodies"]:
        look = sample.appearance.bodies[body["id"]]
        assert look.tag == body["label"]
        if body["kind"] == "ground":
            continue
        if body["planeId"] is None:
            assert "outline" not in body
            assert look.rod_radius > 0.0
            continue

        outline = body["outline"]
        polygon = [(point["x"], point["y"]) for point in outline["polygonLocal"]]
        assert polygon == look.outline
        assert area(polygon) > 0.0
        assert outline["thickness"] == sample.appearance.thickness
        assert outline["offset"] == look.offset
        assert look.thickness == sample.appearance.thickness
        body_points = {(point["local"]["x"], point["local"]["y"]) for point in body["points"]}
        assert all(hole.center in body_points for hole in look.holes)


def test_appearance_is_deterministic_but_varies_between_seeds() -> None:
    chosen = family("slider-crank")
    first = generate(chosen, 14).appearance.record()
    assert generate(chosen, 14).appearance.record() == first
    assert generate(chosen, 15).appearance.record() != first


def test_external_gear_outline_uses_standard_involute_radii() -> None:
    center = (0.03, -0.02)
    teeth, module = 24, 0.002
    polygon = spur_gear(center, teeth, module)
    radii = [math.hypot(x - center[0], y - center[1]) for x, y in polygon]
    pitch = module * teeth / 2

    assert area(polygon) > 0.0
    assert max(radii) == pytest.approx(pitch + module)
    assert min(radii) == pytest.approx(pitch - 1.25 * module)
    assert np.isfinite(polygon).all()

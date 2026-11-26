"""Animated hand and tool occluders (synthetic-lab requirement 3.4)."""

import numpy as np
import pytest
from orrery_lab.families import family
from orrery_lab.render2d.camera import fit_camera
from orrery_lab.render2d.occluders import AnimatedOccluder
from orrery_lab.render2d.renderer import RenderConfig, RenderedFrame, render_frame
from orrery_lab.sampling import generate


def test_occluder_follows_its_cubic_path_only_inside_the_interval() -> None:
    occluder = AnimatedOccluder(
        "hand",
        1.0,
        3.0,
        ((0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (40.0, 20.0)),
        30.0,
    )

    assert not occluder.active(0.99)
    assert occluder.active(1.0)
    assert occluder.active(3.0)
    assert not occluder.active(3.01)
    assert occluder.position(1.0) == pytest.approx((0.0, 0.0))
    assert occluder.position(2.0) == pytest.approx((20.0, 10.0))
    assert occluder.position(3.0) == pytest.approx((40.0, 20.0))


def test_a_hand_occludes_named_points_without_changing_their_projection() -> None:
    sample = generate(family("four-bar-crank-rocker"), 5)
    config = RenderConfig(width=420, height=300, clutter_count=0)
    clean = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(1),
        config=config,
    )
    target = clean.point_projections[("coupler", "trace")]
    hand = AnimatedOccluder("hand", 0.2, 0.8, (target, target, target, target), 70.0)
    covered = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(1),
        camera=clean.camera,
        time=0.5,
        occluders=(hand,),
        config=config,
    )

    assert covered.point_projections == clean.point_projections
    assert not covered.point_visibility[("coupler", "trace")]
    assert covered.png != clean.png


def test_inactive_occluders_do_not_change_the_frame() -> None:
    sample = generate(family("slider-crank"), 2)
    config = RenderConfig(width=360, height=240, clutter_count=2)
    tool = AnimatedOccluder(
        "tool",
        2.0,
        3.0,
        ((20.0, 20.0), (80.0, 30.0), (160.0, 80.0), (250.0, 100.0)),
        45.0,
    )
    camera = fit_camera(sample.appearance.base_plate, 360, 240, np.random.default_rng(7))
    clean = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(9),
        camera=camera,
        time=1.0,
        config=config,
    )
    inactive = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(9),
        camera=camera,
        time=1.0,
        occluders=(tool,),
        config=config,
    )

    assert inactive.png == clean.png
    assert all(inactive.point_visibility.values())


def test_tool_frames_are_deterministic() -> None:
    sample = generate(family("gear-train"), 4)
    tool = AnimatedOccluder(
        "tool",
        0.0,
        1.0,
        ((30.0, 40.0), (100.0, 60.0), (180.0, 100.0), (260.0, 130.0)),
        36.0,
        angle=0.4,
    )
    config = RenderConfig(width=360, height=240, clutter_count=0)

    def make() -> RenderedFrame:
        return render_frame(
            sample.built.document,
            sample.appearance,
            np.random.default_rng(33),
            time=0.4,
            occluders=(tool,),
            config=config,
        )

    first, second = make(), make()
    assert first.png == second.png
    assert first.point_visibility == second.point_visibility

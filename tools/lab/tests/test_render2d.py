"""Skia planar renderer, camera, materials, shadows, and clutter (requirement 3.1)."""

import math

import numpy as np
import pytest
from orrery_lab.dynamics import BodyPose
from orrery_lab.families import family
from orrery_lab.render2d.camera import Camera, fit_camera
from orrery_lab.render2d.materials import CC0_TEXTURES, MATERIAL_KINDS, assign_materials
from orrery_lab.render2d.renderer import RenderConfig, RenderedFrame, render_frame
from orrery_lab.sampling import generate


def test_camera_projects_the_plane_and_applies_brown_conrady_distortion() -> None:
    plain = Camera(320, 240, (0.0, 0.0), 100.0)
    distorted = Camera(320, 240, (0.0, 0.0), 100.0, k1=0.2, p1=0.01)

    assert plain.project((0.0, 0.0)) == pytest.approx((160.0, 120.0))
    assert plain.project((1.0, 0.0)) == pytest.approx((260.0, 120.0))
    assert distorted.project((1.0, 0.0))[0] > plain.project((1.0, 0.0))[0]


def test_fitted_camera_keeps_the_scene_in_frame_and_respects_the_tilt_limit() -> None:
    points = [(-0.2, -0.1), (0.3, -0.1), (0.3, 0.25), (-0.2, 0.25)]
    camera = fit_camera(points, 640, 360, np.random.default_rng(12))
    projected = np.array([camera.project(point) for point in points])

    assert np.all(projected[:, 0] >= 0.0)
    assert np.all(projected[:, 0] < 640.0)
    assert np.all(projected[:, 1] >= 0.0)
    assert np.all(projected[:, 1] < 360.0)
    assert abs(camera.tilt_x) <= math.radians(25)
    assert abs(camera.tilt_y) <= math.radians(25)


def test_material_assignment_is_deterministic_and_uses_real_material_families() -> None:
    body_ids = tuple(f"body-{index}" for index in range(24))
    first = assign_materials(body_ids, np.random.default_rng(9))
    second = assign_materials(body_ids, np.random.default_rng(9))

    assert first == second
    assert {material.kind for material in first.values()} == set(MATERIAL_KINDS)
    assert CC0_TEXTURES["plywood"].is_file()
    assert any(material.texture_path is not None for material in first.values())


def test_rendered_pixels_and_png_are_deterministic() -> None:
    sample = generate(family("sewing-machine"), 7)
    config = RenderConfig(width=480, height=320, clutter_count=6)

    def render() -> RenderedFrame:
        return render_frame(
            sample.built.document,
            sample.appearance,
            np.random.default_rng(88),
            config=config,
        )

    first, second = render(), render()
    assert first.png == second.png
    assert np.array_equal(first.pixels, second.pixels)
    assert first.pixels.shape == (320, 480, 4)
    assert first.pixels.dtype == np.uint8
    assert np.ptp(first.pixels[:, :, :3]) > 0
    assert set(first.point_projections) == {
        (body["id"], point["id"])
        for body in sample.built.document["bodies"]
        for point in body["points"]
    }


def test_body_pose_moves_its_rendered_points() -> None:
    sample = generate(family("four-bar-crank-rocker"), 2)
    config = RenderConfig(width=400, height=300, clutter_count=0)
    camera = fit_camera(sample.appearance.base_plate, 400, 300, np.random.default_rng(1))
    still = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(2),
        camera=camera,
        config=config,
    )
    moved = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(2),
        camera=camera,
        poses={"input": BodyPose(0.02, 0.0, 0.0)},
        config=config,
    )

    before = still.point_projections[("input", "b")]
    after = moved.point_projections[("input", "b")]
    point = next(
        point
        for body in sample.built.document["bodies"]
        if body["id"] == "input"
        for point in body["points"]
        if point["id"] == "b"
    )["local"]
    expected = camera.project((point["x"] + 0.02, point["y"]))
    assert after == pytest.approx(expected)
    assert after != pytest.approx(before)
    assert moved.png != still.png


def test_shadows_and_clutter_change_only_the_render_not_ground_truth() -> None:
    sample = generate(family("gear-train"), 3)
    clean = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(4),
        config=RenderConfig(width=420, height=280, clutter_count=0, shadows=False),
    )
    dressed = render_frame(
        sample.built.document,
        sample.appearance,
        np.random.default_rng(4),
        camera=clean.camera,
        config=RenderConfig(width=420, height=280, clutter_count=8, shadows=True),
    )

    assert not np.array_equal(clean.pixels, dressed.pixels)
    assert clean.point_projections == dressed.point_projections
    assert clean.camera == dressed.camera

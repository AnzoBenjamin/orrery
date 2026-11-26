"""Blender/Cycles 3D scene construction and real render passes (requirement 3.3)."""

import math

import numpy as np
from orrery_lab.families import family
from orrery_lab.render3d import RenderConfig, build_scene, render, sampled_path
from orrery_lab.render3d.geometry import scene_points
from orrery_lab.sampling import Sample, generate

TINY = RenderConfig(width=32, height=24, samples=1, seed=17, threads=1, rod_sides=6)


def _moving_ids(sample: Sample) -> set[str]:
    return {str(body["id"]) for body in sample.built.document["bodies"] if body["kind"] != "ground"}


def test_planar_dressed_family_builds_one_indexed_object_per_body() -> None:
    sample = generate(family("four-bar-crank-rocker"), 2)
    built = build_scene(sample.built.document, sample.appearance, TINY)

    assert set(built.object_ids) == _moving_ids(sample)
    assert len(set(built.object_ids.values())) == len(built.object_ids)
    assert all(index > 0 for index in built.object_ids.values())
    assert built.camera.path == "orbit"
    assert len(built.camera.world_to_camera) == 16
    assert all(sample.appearance.bodies[body_id].outline for body_id in built.object_ids)
    assert all(sample.appearance.bodies[body_id].thickness > 0.0 for body_id in built.object_ids)


def test_spatial_rssr_builds_rods_from_world_points() -> None:
    sample = generate(family("spatial-rssr"), 0)
    built = build_scene(sample.built.document, sample.appearance, TINY)

    assert set(built.object_ids) == {"crank", "coupler", "rocker"}
    for body_id in built.object_ids:
        body = next(body for body in sample.built.document["bodies"] if body["id"] == body_id)
        assert body["planeId"] is None
        assert len(body["points"]) >= 2
        assert sample.appearance.bodies[body_id].rod_radius > 0.0


def test_multi_plane_scene_and_both_camera_paths_cover_3d_extent() -> None:
    sample = generate(family("two-plane-cardan"), 0)
    points = scene_points(sample.built.document, sample.appearance)
    planes = {body["planeId"] for body in sample.built.document["bodies"]}
    assert planes == {None, "plane-front", "plane-rear"}

    for path in ("orbit", "handheld"):
        poses = sampled_path(points, path, seed=5, frame_count=60, width=320, height=240)
        repeated = sampled_path(points, path, seed=5, frame_count=60, width=320, height=240)
        locations = np.asarray([pose.location for pose in poses])
        assert poses == repeated
        assert np.all(np.isfinite(locations))
        assert np.ptp(locations, axis=0).max() > 0.0
        assert all(pose.near_clip > 0.0 and pose.far_clip > pose.near_clip for pose in poses)
        # Finite Fourier/orbit paths have correlated frame-to-frame motion, not white-noise jitter.
        velocity = np.linalg.norm(np.diff(locations, axis=0), axis=1)
        acceleration = np.linalg.norm(np.diff(locations, n=2, axis=0), axis=1)
        assert float(acceleration.max()) < 0.25 * float(velocity.max())

    orbit = build_scene(sample.built.document, sample.appearance, TINY)
    handheld = build_scene(
        sample.built.document,
        sample.appearance,
        RenderConfig(
            width=32,
            height=24,
            samples=1,
            seed=17,
            camera_path="handheld",
            frame_index=8,
            frame_count=60,
            threads=1,
            rod_sides=6,
        ),
    )
    assert orbit.object_ids == handheld.object_ids
    assert orbit.camera.location != handheld.camera.location
    assert orbit.camera.target != handheld.camera.target


def test_real_cycles_rgb_depth_and_instance_passes_are_deterministic() -> None:
    sample = generate(family("four-bar-crank-rocker"), 2)
    first = render(sample.built.document, sample.appearance, TINY)
    second = render(sample.built.document, sample.appearance, TINY)

    assert first.camera == second.camera
    assert first.object_ids == second.object_ids
    assert np.array_equal(first.rgb, second.rgb)
    assert np.array_equal(first.depth, second.depth)
    assert np.array_equal(first.instance_id, second.instance_id)
    assert first.rgb.shape == (24, 32, 3)
    assert first.rgb.dtype == np.float32
    assert first.depth.shape == (24, 32)
    assert first.depth.dtype == np.float32
    assert first.instance_id.dtype == np.int32
    assert np.ptp(first.rgb) > 0.0
    assert np.any(first.instance_id == 0)
    foreground = first.instance_id > 0
    assert np.any(foreground)
    assert np.isinf(first.depth[~foreground]).all()
    assert np.isfinite(first.depth[foreground]).all()
    assert {int(value) for value in np.unique(first.instance_id[foreground])} <= set(
        first.object_ids.values()
    )
    assert math.isfinite(float(first.rgb.mean()))

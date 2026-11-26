"""Deterministic moving-region, hole, user-point, and re-seeding tests."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from orrery_engine.camera_motion import decode_frames, estimate_camera_motion
from orrery_engine.seeding import (
    SeedingConfig,
    SeedPoint,
    UserPointInput,
    detect_hole_seeds,
    reseed_regions,
    seed_moving_regions,
    user_annotation_seeds,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "e2e/fixtures/synthetic-lab/suite/phone-slider-crank/clip.mp4"
HEIGHT = 180
WIDTH = 240


def _checker(frame: npt.NDArray[np.uint8], box: tuple[int, int, int, int]) -> None:
    left, top, width, height = box
    frame[top : top + height, left : left + width] = (80, 130, 190)
    for row in range(top + 3, top + height - 3, 7):
        cv2.line(frame, (left + 2, row), (left + width - 3, row), (230, 225, 50), 2)
    for column in range(left + 3, left + width - 3, 7):
        cv2.line(frame, (column, top + 2), (column, top + height - 3), (25, 40, 220), 2)


def _moving_frames() -> tuple[npt.NDArray[np.uint8], ...]:
    frames: list[npt.NDArray[np.uint8]] = []
    for index in range(9):
        frame = np.full((HEIGHT, WIDTH, 3), 28, dtype=np.uint8)
        _checker(frame, (18 + index * 2, 28 + index, 42, 34))
        _checker(frame, (164 - index * 2, 112 - index, 48, 38))
        frames.append(frame)
    return tuple(frames)


def _identities(count: int) -> tuple[npt.NDArray[np.float64], ...]:
    return tuple(np.eye(3, dtype=np.float64) for _ in range(count))


def test_moving_regions_receive_strong_corners_with_even_deterministic_coverage() -> None:
    frames = _moving_frames()
    config = SeedingConfig(grid_size_px=20, per_cell_cap=3, min_region_pixels=40)
    first = seed_moving_regions(frames, _identities(len(frames)), config=config)
    second = seed_moving_regions(frames, _identities(len(frames)), config=config)

    assert first == second
    assert len(first.coverage) >= 2
    assert all(metric.seed_count > 0 for metric in first.coverage)
    assert all(metric.coverage_fraction >= 0.5 for metric in first.coverage)
    assert all(point.source == "shi_tomasi" for point in first.points)
    assert all(point.kind == "corner" for point in first.points)
    assert all(0.0 < point.confidence <= 1.0 for point in first.points)
    seeded_regions = {point.region_id for point in first.points}
    assert seeded_regions == {metric.region_id for metric in first.coverage}


def test_real_synthetic_fixture_has_reproducible_moving_region_seeds() -> None:
    frames, _ = decode_frames(FIXTURE, lambda: None)
    motion = estimate_camera_motion(frames)
    matrices = tuple(item.reference_to_frame for item in motion.frames)
    first = seed_moving_regions(frames, matrices)
    second = seed_moving_regions(frames, matrices)

    assert first == second
    assert first.points
    assert first.coverage
    assert all(metric.seed_count > 0 for metric in first.coverage)
    assert all(0 <= point.frame_index < len(frames) for point in first.points)


def _hole_frames() -> dict[int, npt.NDArray[np.uint8]]:
    frames: dict[int, npt.NDArray[np.uint8]] = {}
    for frame_index in (0, 2, 4, 6, 8):
        image = np.full((360, 480, 3), 235, dtype=np.uint8)
        center = (142 + frame_index, 176 + frame_index // 2)
        cv2.rectangle(image, (80, 115), (225, 240), (150, 165, 180), -1)
        cv2.circle(image, center, 22, (25, 25, 25), -1, lineType=cv2.LINE_AA)
        cv2.circle(image, center, 12, (215, 215, 215), -1, lineType=cv2.LINE_AA)
        if frame_index == 4:
            cv2.circle(image, (390, 55), 18, (20, 20, 20), -1, lineType=cv2.LINE_AA)
        frames[frame_index] = image
    return frames


def test_full_resolution_holes_require_multi_keyframe_consistency_and_scale_provenance() -> None:
    points = detect_hole_seeds(_hole_frames(), analysis_size=(240, 180))

    assert points
    assert all(point.source == "circular_hole" for point in points)
    assert all(point.kind == "hole" for point in points)
    assert all(point.detection_scale == "full_resolution" for point in points)
    assert all(point.source_x_px is not None and point.source_y_px is not None for point in points)
    assert any(abs(point.x_px - 71) < 8 and abs(point.y_px - 88) < 8 for point in points)
    assert not any(point.x_px > 180 and point.y_px < 45 for point in points)


def test_contracted_user_joint_and_prompt_points_are_preserved_and_scaled() -> None:
    annotations = (
        UserPointInput("joint-a", "joint", 3, 320.0, 120.0),
        UserPointInput("prompt-b", "part_prompt", 4, 80.0, 300.0),
    )
    points = user_annotation_seeds(
        annotations,
        source_size=(640, 480),
        analysis_size=(320, 240),
    )

    assert [(point.x_px, point.y_px) for point in points] == [(160.0, 60.0), (40.0, 150.0)]
    assert [point.source for point in points] == ["user_joint", "user_part_prompt"]
    assert [point.kind for point in points] == ["pivot", "prompt"]
    assert all(point.confidence == 1.0 for point in points)
    assert all(point.detection_scale == "user_full_resolution" for point in points)


def test_reseeding_only_refills_regions_below_the_coverage_threshold() -> None:
    frames = _moving_frames()
    config = SeedingConfig(
        grid_size_px=20,
        per_cell_cap=3,
        min_region_pixels=40,
        reseed_coverage_threshold=0.6,
    )
    estimate = seed_moving_regions(frames, _identities(len(frames)), config=config)
    depleted_region = estimate.coverage[-1].region_id
    live = tuple(point for point in estimate.points if point.region_id != depleted_region)

    first = reseed_regions(
        frames[4],
        estimate.moving_mask,
        live,
        estimate.coverage,
        frame_index=4,
        config=config,
    )
    second = reseed_regions(
        frames[4],
        estimate.moving_mask,
        live,
        estimate.coverage,
        frame_index=4,
        config=config,
    )

    assert first == second
    assert first.points
    assert {point.region_id for point in first.points} == {depleted_region}
    assert all(point.source == "reseeded_shi_tomasi" for point in first.points)
    assert all(point.frame_index == 4 for point in first.points)
    depleted = next(item for item in first.coverage if item.region_id == depleted_region)
    retained = next(item for item in first.coverage if item.region_id != depleted_region)
    assert depleted.coverage_before < config.reseed_coverage_threshold
    assert depleted.coverage_after > depleted.coverage_before
    assert retained.added_seed_count == 0


def _point_signature(point: SeedPoint) -> tuple[object, ...]:
    return (
        point.seed_id,
        point.x_px,
        point.y_px,
        point.source,
        point.kind,
        point.confidence,
        point.frame_index,
        point.detection_scale,
        point.region_id,
    )


def test_seed_identity_contains_stable_provenance() -> None:
    estimate = seed_moving_regions(_moving_frames(), _identities(9))
    assert len({_point_signature(point) for point in estimate.points}) == len(estimate.points)
    assert all(point.seed_id.startswith("seed-") for point in estimate.points)

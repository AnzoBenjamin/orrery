"""Deterministic camera-motion tests, including vision correctness property 1."""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import cast

import av
import cv2
import numpy as np
import numpy.typing as npt
from hypothesis import given, settings
from hypothesis import strategies as st
from orrery_engine.camera_motion import (
    CameraMotionConfig,
    analyze_camera_motion,
    decode_frames,
    estimate_camera_motion,
    refine_with_ground_tracks,
)

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "e2e/fixtures/synthetic-lab/suite"
HEIGHT = 180
WIDTH = 240
FRAME_COUNT = 6


def _texture(seed: int = 123) -> npt.NDArray[np.uint8]:
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 256, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    return cast(npt.NDArray[np.uint8], cv2.GaussianBlur(noise, (3, 3), 0))


def _shake_clip(
    tx: float, ty: float, angle_degrees: float, perspective_millionths: float
) -> tuple[tuple[npt.NDArray[np.uint8], ...], tuple[npt.NDArray[np.float64], ...]]:
    base = _texture()
    frames: list[npt.NDArray[np.uint8]] = []
    homographies: list[npt.NDArray[np.float64]] = []
    for index in range(FRAME_COUNT):
        fraction = index / (FRAME_COUNT - 1)
        affine = cv2.getRotationMatrix2D((WIDTH / 2, HEIGHT / 2), angle_degrees * fraction, 1.0)
        affine[:, 2] += (tx * fraction, ty * fraction)
        homography = np.vstack(
            (
                affine,
                [
                    perspective_millionths * 1e-6 * fraction,
                    -perspective_millionths * 0.7e-6 * fraction,
                    1.0,
                ],
            )
        ).astype(np.float64)
        frame = cast(
            npt.NDArray[np.uint8],
            cv2.warpPerspective(base, homography, (WIDTH, HEIGHT), borderMode=cv2.BORDER_REFLECT),
        )
        cv2.circle(frame, (30 + index * 12, 130), 18, (0, 0, 255), -1)
        frames.append(frame)
        homographies.append(homography)
    return tuple(frames), tuple(homographies)


def _stabilized_ground_rms(
    true_homographies: tuple[npt.NDArray[np.float64], ...],
    estimated: tuple[npt.NDArray[np.float64], ...],
) -> float:
    points = np.asarray(
        [[x, y] for y in (25, 60, 100, 150) for x in (25, 70, 120, 170, 215)],
        dtype=np.float32,
    )
    stabilized: list[npt.NDArray[np.float32]] = []
    for truth, prediction in zip(true_homographies, estimated, strict=True):
        observed = cv2.perspectiveTransform(points[None], truth)[0]
        stabilized.append(cv2.perspectiveTransform(observed[None], np.linalg.inv(prediction))[0])
    samples = np.stack(stabilized)
    return math.sqrt(float(np.mean(np.square(samples - np.mean(samples, axis=0)))))


@given(
    tx=st.floats(-5.0, 5.0, allow_nan=False, allow_infinity=False),
    ty=st.floats(-4.0, 4.0, allow_nan=False, allow_infinity=False),
    angle=st.floats(-2.0, 2.0, allow_nan=False, allow_infinity=False),
    perspective=st.floats(-20.0, 20.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=20, deadline=None)
def test_property_stabilized_ground_points_stay_within_one_pixel_rms(
    tx: float, ty: float, angle: float, perspective: float
) -> None:
    """Property 1: camera shake leaves planar ground points stable to less than one pixel RMS."""
    frames, truth = _shake_clip(tx, ty, angle, perspective)
    result = estimate_camera_motion(frames)
    matrices = tuple(frame.reference_to_frame for frame in result.frames)
    assert _stabilized_ground_rms(truth, matrices) < 1.0
    assert result.stabilized_rms_px < 1.0
    assert not result.requires_spatial


def test_camera_motion_is_deterministic_on_real_handheld_fixture() -> None:
    path = FIXTURES / "phone-slider-crank/clip.mp4"
    frames, _ = decode_frames(path, lambda: None)
    first = estimate_camera_motion(frames)
    second = estimate_camera_motion(frames)
    assert [item.reference_to_frame.tolist() for item in first.frames] == [
        item.reference_to_frame.tolist() for item in second.frames
    ]
    assert first.stabilized_rms_px < 1.0
    assert first.valid_frame_fraction == 1.0
    assert first.static_pixel_fraction > 0.1
    assert not first.requires_spatial


def test_real_fixture_produces_decodable_stabilized_preview_and_metrics(tmp_path: Path) -> None:
    result = analyze_camera_motion(
        FIXTURES / "phone-slider-crank/clip.mp4",
        tmp_path,
        footage_id="phone-slider-crank",
        config=CameraMotionConfig(),
        check_canceled=lambda: None,
        progress=lambda _fraction, _description: None,
    )
    artifact_value = result.manifest["stabilizedPreview"]
    assert isinstance(artifact_value, dict)
    artifact = cast(dict[str, object], artifact_value)
    data = artifact["data"]
    byte_size = artifact["byteSize"]
    assert isinstance(data, str)
    assert isinstance(byte_size, int)
    encoded = base64.b64decode(data)
    assert encoded == result.preview_path.read_bytes()
    assert byte_size == len(encoded) > 0
    preview = av.open(result.preview_path)
    with preview:
        decoded = list(preview.decode(video=0))
    assert len(decoded) == 8
    assert result.manifest["quality"] == {
        "stabilizedRmsPx": result.estimate.stabilized_rms_px,
        "medianResidualPx": result.estimate.median_residual_px,
        "p95ResidualPx": result.estimate.p95_residual_px,
        "meanInlierRatio": result.estimate.mean_inlier_ratio,
        "validFrameFraction": result.estimate.valid_frame_fraction,
        "staticPixelFraction": result.estimate.static_pixel_fraction,
        "parallaxEvidenceFrames": result.estimate.parallax_evidence_frames,
    }


def test_coherent_two_plane_parallax_routes_to_spatial_reconstruction() -> None:
    base = _texture(5)
    frames: list[npt.NDArray[np.uint8]] = []
    for index in range(FRAME_COUNT):
        offset = index * 2
        background = np.roll(base, offset, axis=1)
        foreground = np.roll(base, -offset, axis=1)
        frame = background.copy()
        frame[:, WIDTH // 2 :] = foreground[:, WIDTH // 2 :]
        frames.append(frame)
    result = estimate_camera_motion(
        frames,
        config=CameraMotionConfig(parallax_threshold_px=1.5),
    )
    assert result.requires_spatial
    assert result.parallax_evidence_frames >= 2
    assert result.routing_reason is not None
    assert "multiple coherent planes" in result.routing_reason


def test_ground_track_refinement_hook_uses_magsac_and_is_deterministic() -> None:
    reference = np.asarray(
        [[10, 10], [100, 10], [10, 80], [100, 80], [55, 45], [30, 60], [80, 30], [90, 70]],
        dtype=np.float32,
    )
    matrix = np.asarray([[1.0, 0.01, 3.0], [-0.01, 1.0, -2.0], [1e-5, -2e-5, 1.0]])
    target = cv2.perspectiveTransform(reference[None], matrix)[0]
    first = refine_with_ground_tracks(reference, {1: target})
    second = refine_with_ground_tracks(reference, {1: target})
    np.testing.assert_allclose(first[1], matrix, atol=1e-4)
    np.testing.assert_array_equal(first[1], second[1])

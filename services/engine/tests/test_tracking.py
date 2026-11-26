"""Typed deterministic KLT tracking behavior, artifact, and fixture tests."""

# PyArrow and OpenCV expose dynamic adapter APIs.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from orrery_engine.camera_motion import decode_frames, estimate_camera_motion
from orrery_engine.seeding import seed_moving_regions
from orrery_engine.seeding_types import SeedPoint
from orrery_engine.tracking import KLTTracker, TrackerSelectionError, select_tracker, with_footage
from orrery_engine.tracking_arrow import write_tracks_arrow
from orrery_engine.tracking_types import FrameSource, TrackingConfig

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "e2e/fixtures/synthetic-lab/suite/phone-slider-crank/clip.mp4"
HEIGHT = 96
WIDTH = 128


def _texture(seed: int = 7) -> npt.NDArray[np.uint8]:
    rng = np.random.default_rng(seed)
    image = rng.integers(0, 256, size=(HEIGHT, WIDTH, 3), dtype=np.uint8)
    return cast(npt.NDArray[np.uint8], cv2.GaussianBlur(image, (3, 3), 0))


def _translated_frames(
    *,
    dx: int = 2,
    dy: int = 1,
    blur_frame: int | None = None,
    occluded_frame: int | None = None,
) -> tuple[npt.NDArray[np.uint8], ...]:
    base = _texture()
    frames: list[npt.NDArray[np.uint8]] = []
    for index in range(7):
        matrix = np.asarray([[1.0, 0.0, index * dx], [0.0, 1.0, index * dy]], np.float32)
        frame = cast(npt.NDArray[np.uint8], cv2.warpAffine(base, matrix, (WIDTH, HEIGHT)))
        if blur_frame == index:
            frame = cast(npt.NDArray[np.uint8], cv2.GaussianBlur(frame, (5, 5), 0))
        if occluded_frame == index:
            cv2.rectangle(frame, (35, 30), (75, 70), (0, 0, 0), -1)
        frames.append(frame)
    return tuple(frames)


def _source(frames: tuple[npt.NDArray[np.uint8], ...]) -> FrameSource:
    return FrameSource(
        frames,
        tuple(np.eye(3, dtype=np.float64) for _ in frames),
        tuple(index / 30 for index in range(len(frames))),
    )


def _seed() -> SeedPoint:
    return SeedPoint(
        "seed-test",
        48.0,
        45.0,
        "shi_tomasi",
        "corner",
        1.0,
        0,
        "analysis",
        "region-000",
    )


def _track(frames: tuple[npt.NDArray[np.uint8], ...]):
    return KLTTracker().track(_source(frames), (_seed(),), check_canceled=lambda: None).tracks[0]


def test_klt_tracks_controlled_translation_with_subpixel_accuracy_and_determinism() -> None:
    frames = _translated_frames()
    first = _track(frames)
    second = _track(frames)

    assert first == second
    assert all(sample.visible for sample in first.samples)
    for index, sample in enumerate(first.samples):
        assert sample.x_px is not None
        assert sample.y_px is not None
        assert math.hypot(sample.x_px - (48 + 2 * index), sample.y_px - (45 + index)) < 0.08
        assert 0 < sample.confidence <= 1
        assert sample.status == "observed"


@given(dx=st.integers(-3, 3), dy=st.integers(-3, 3))
@settings(max_examples=12, deadline=None)
def test_klt_translation_property(dx: int, dy: int) -> None:
    track = _track(_translated_frames(dx=dx, dy=dy))

    assert all(sample.visible for sample in track.samples)
    for index, sample in enumerate(track.samples):
        assert sample.x_px is not None
        assert sample.y_px is not None
        error = math.hypot(sample.x_px - (48 + dx * index), sample.y_px - (45 + dy * index))
        assert error < 0.1


def test_klt_handles_moderate_blur_with_reduced_confidence() -> None:
    track = _track(_translated_frames(blur_frame=3))

    assert all(sample.visible for sample in track.samples)
    assert track.samples[3].confidence < track.samples[2].confidence
    assert track.samples[3].confidence > 0.8


def test_klt_marks_occlusion_and_loss_without_reporting_unobserved_positions() -> None:
    track = _track(_translated_frames(occluded_frame=3))

    rejected = track.samples[3]
    assert not rejected.visible
    assert rejected.status == "occluded"
    assert rejected.rejection_reason in {"appearance", "forward_backward", "lk_failure"}
    assert rejected.x_px is None
    assert rejected.y_px is None
    assert all(sample.status == "lost" for sample in track.samples[4:])
    assert all(sample.x_px is None and sample.y_px is None for sample in track.samples[3:])


def test_adapter_selects_only_the_requested_available_backend() -> None:
    assert select_tracker("klt").name == "klt"
    with pytest.raises(TrackerSelectionError, match="unavailable"):
        select_tracker("cotracker3_onnx")
    with pytest.raises(ValueError, match="odd"):
        TrackingConfig(window_size_px=20)


def test_tracker_checks_cancellation_cooperatively() -> None:
    checks = 0

    def cancel() -> None:
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("canceled")

    with pytest.raises(RuntimeError, match="canceled"):
        KLTTracker().track(_source(_translated_frames()), (_seed(),), check_canceled=cancel)


def test_real_fixture_tracks_are_deterministic_and_arrow_contract_is_versioned(
    tmp_path: Path,
) -> None:
    frames, _ = decode_frames(FIXTURE, lambda: None)
    motion = estimate_camera_motion(frames)
    matrices = tuple(item.reference_to_frame for item in motion.frames)
    seeds = seed_moving_regions(frames, matrices).points[:12]
    source = FrameSource(frames, matrices, tuple(index / 12 for index in range(len(frames))))
    tracker = KLTTracker()
    first = with_footage(
        tracker.track(source, seeds, check_canceled=lambda: None), "phone-slider-crank"
    )
    second = with_footage(
        tracker.track(source, seeds, check_canceled=lambda: None), "phone-slider-crank"
    )
    first_path = tmp_path / "first.arrow"
    second_path = tmp_path / "second.arrow"
    first_bytes = write_tracks_arrow(first_path, first.tracks)
    second_bytes = write_tracks_arrow(second_path, second.tracks)

    assert first == second
    assert first.tracks
    assert first_bytes == second_bytes
    assert hashlib.sha256(first_bytes).digest() == hashlib.sha256(second_bytes).digest()
    with pa.ipc.open_file(io.BytesIO(first_bytes)) as reader:
        table = reader.read_all()
    assert table.schema.metadata == {
        b"orrery.format": b"orrery.engine.tracking",
        b"orrery.schema_version": b"1",
        b"orrery.table": b"tracks",
        b"orrery.coordinate_space": b"analysis_pixels",
    }
    assert table.num_rows == len(first.tracks) * len(frames)
    rows = table.to_pylist()
    assert all(row["x_px"] is None and row["y_px"] is None for row in rows if not row["visible"])
    assert all(
        row["x_px"] is not None and row["y_px"] is not None for row in rows if row["visible"]
    )

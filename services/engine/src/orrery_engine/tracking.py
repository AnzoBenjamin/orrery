"""Deterministic CPU pyramidal Lucas-Kanade tracker and backend adapter registry."""

# OpenCV's generated stubs are incomplete at this numerical adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import cast

import cv2
import numpy as np
import numpy.typing as npt

from orrery_engine.seeding_types import Image, SeedPoint
from orrery_engine.tracking_types import (
    CancelCheck,
    FrameSource,
    PointTrack,
    PointTracker,
    PosePredictor,
    RejectionReason,
    TrackingConfig,
    TrackingResult,
    TrackSample,
)

_MIN_PATCH_STD = 1.0
_HOMOGRAPHY_EPSILON = 1e-9
DEFAULT_TRACKING_CONFIG = TrackingConfig()


class TrackerSelectionError(ValueError):
    """The requested tracker backend is unavailable or misconfigured."""


class KLTTracker:
    """OpenCV pyramidal LK with round-trip and camera-warped patch validation."""

    name = "klt"

    def __init__(self, config: TrackingConfig = DEFAULT_TRACKING_CONFIG) -> None:
        self._config = config

    def track(
        self,
        frames: FrameSource,
        seeds: tuple[SeedPoint, ...],
        predictor: PosePredictor | None = None,
        *,
        check_canceled: CancelCheck,
        forward_only: bool = False,
    ) -> TrackingResult:
        del predictor  # The base KLT pass is deliberately model-free.
        cv2.setNumThreads(1)
        cv2.setRNGSeed(0)
        grays = tuple(
            cast(Image, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)) for frame in frames.frames
        )
        valid = tuple(seed for seed in seeds if 0 <= seed.frame_index < len(grays))
        samples = [self._initial_samples(frames, seed, forward_only) for seed in valid]
        references = [self._reference_patch(grays, seed) for seed in valid]
        self._propagate(
            frames,
            grays,
            valid,
            references,
            samples,
            range(len(grays) - 1),
            step=1,
            check_canceled=check_canceled,
        )
        if not forward_only:
            self._propagate(
                frames,
                grays,
                valid,
                references,
                samples,
                range(len(grays) - 1, 0, -1),
                step=-1,
                check_canceled=check_canceled,
            )
        tracks = tuple(
            PointTrack(seed.seed_id, "", seed, tuple(track_samples))
            for seed, track_samples in zip(valid, samples, strict=True)
        )
        return TrackingResult(self.name, tracks)

    def _initial_samples(
        self, frames: FrameSource, seed: SeedPoint, forward_only: bool
    ) -> list[TrackSample]:
        values = [
            TrackSample(
                index,
                timestamp,
                None,
                None,
                False,
                0.0,
                "not_seeded" if forward_only and index < seed.frame_index else "lost",
            )
            for index, timestamp in enumerate(frames.timestamps_seconds)
        ]
        height, width = frames.frames[0].shape[:2]
        if _in_bounds(seed.x_px, seed.y_px, width, height):
            values[seed.frame_index] = TrackSample(
                seed.frame_index,
                frames.timestamps_seconds[seed.frame_index],
                seed.x_px,
                seed.y_px,
                True,
                seed.confidence,
                "observed",
                uncertainty_px=0.05,
            )
        else:
            values[seed.frame_index] = TrackSample(
                seed.frame_index,
                frames.timestamps_seconds[seed.frame_index],
                None,
                None,
                False,
                0.0,
                "occluded",
                "out_of_bounds",
            )
        return values

    def _reference_patch(self, grays: tuple[Image, ...], seed: SeedPoint) -> Image | None:
        if not _patch_in_bounds(
            seed.x_px,
            seed.y_px,
            grays[seed.frame_index].shape[1],
            grays[seed.frame_index].shape[0],
            self._config.patch_size_px,
        ):
            return None
        return cast(
            Image,
            cv2.getRectSubPix(
                grays[seed.frame_index],
                (self._config.patch_size_px, self._config.patch_size_px),
                (seed.x_px, seed.y_px),
            ),
        )

    def _propagate(  # noqa: PLR0917 - cohesive batched transition state
        self,
        frames: FrameSource,
        grays: tuple[Image, ...],
        seeds: tuple[SeedPoint, ...],
        references: Sequence[Image | None],
        samples: list[list[TrackSample]],
        frame_indices: range,
        *,
        step: int,
        check_canceled: CancelCheck,
    ) -> None:
        for frame_index in frame_indices:
            check_canceled()
            target_index = frame_index + step
            if not 0 <= target_index < len(grays):
                continue
            active = [
                index
                for index, seed in enumerate(seeds)
                if samples[index][frame_index].visible
                and (step > 0 or target_index < seed.frame_index)
            ]
            if not active:
                continue
            previous = np.asarray(
                [
                    [
                        cast(float, samples[index][frame_index].x_px),
                        cast(float, samples[index][frame_index].y_px),
                    ]
                    for index in active
                ],
                dtype=np.float32,
            ).reshape(-1, 1, 2)
            current, forward_status, _ = self._lk(grays[frame_index], grays[target_index], previous)
            if current is None or forward_status is None:
                self._reject_all(frames, samples, active, target_index, "lk_failure")
                continue
            returned, backward_status, _ = self._lk(
                grays[target_index], grays[frame_index], current
            )
            for offset, track_index in enumerate(active):
                reason = self._validate_candidate(
                    frames,
                    grays[target_index],
                    seeds[track_index],
                    references[track_index],
                    previous[offset, 0],
                    current[offset, 0],
                    None if returned is None else returned[offset, 0],
                    bool(forward_status[offset, 0]),
                    bool(backward_status[offset, 0]) if backward_status is not None else False,
                    target_index,
                )
                if isinstance(reason, str):
                    samples[track_index][target_index] = _rejected_sample(
                        frames, target_index, reason
                    )
                    continue
                x_px, y_px, appearance, round_trip = reason
                prior = samples[track_index][frame_index].confidence
                confidence = min(
                    1.0,
                    max(0.0, prior * appearance * math.exp(-round_trip)),
                )
                samples[track_index][target_index] = TrackSample(
                    target_index,
                    frames.timestamps_seconds[target_index],
                    round(x_px, 6),
                    round(y_px, 6),
                    True,
                    round(confidence, 6),
                    "observed",
                    uncertainty_px=round(max(0.05, round_trip + (1.0 - appearance)), 6),
                )

    def _lk(
        self, before: Image, after: Image, points: npt.NDArray[np.float32]
    ) -> tuple[
        npt.NDArray[np.float32] | None,
        npt.NDArray[np.uint8] | None,
        npt.NDArray[np.float32] | None,
    ]:
        result = cv2.calcOpticalFlowPyrLK(
            before,
            after,
            points,
            None,
            winSize=(self._config.window_size_px, self._config.window_size_px),
            maxLevel=self._config.pyramid_levels - 1,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
            flags=0,
            minEigThreshold=1e-4,
        )
        return cast(
            tuple[
                npt.NDArray[np.float32] | None,
                npt.NDArray[np.uint8] | None,
                npt.NDArray[np.float32] | None,
            ],
            result,
        )

    def _validate_candidate(  # noqa: PLR0917 - complete candidate evidence
        self,
        frames: FrameSource,
        gray: Image,
        seed: SeedPoint,
        reference: Image | None,
        previous: npt.NDArray[np.float32],
        current: npt.NDArray[np.float32],
        returned: npt.NDArray[np.float32] | None,
        forward_ok: bool,
        backward_ok: bool,
        target_index: int,
    ) -> tuple[float, float, float, float] | RejectionReason:
        if not forward_ok or not backward_ok or returned is None:
            return "lk_failure"
        x_px, y_px = float(current[0]), float(current[1])
        height, width = gray.shape
        if not _patch_in_bounds(x_px, y_px, width, height, self._config.patch_size_px):
            return "out_of_bounds"
        round_trip = float(np.linalg.norm(returned - previous))
        if round_trip > self._config.forward_backward_threshold_px:
            return "forward_backward"
        if reference is None:
            return "appearance"
        patch = _warped_patch(
            gray,
            (x_px, y_px),
            seed,
            frames.reference_to_frames[seed.frame_index],
            frames.reference_to_frames[target_index],
            self._config.patch_size_px,
        )
        appearance = _normalized_correlation(reference, patch)
        if appearance < self._config.appearance_threshold:
            return "appearance"
        return x_px, y_px, appearance, round_trip

    @staticmethod
    def _reject_all(
        frames: FrameSource,
        samples: list[list[TrackSample]],
        active: Sequence[int],
        frame_index: int,
        reason: RejectionReason,
    ) -> None:
        for track_index in active:
            samples[track_index][frame_index] = _rejected_sample(frames, frame_index, reason)


def select_tracker(name: str, config: TrackingConfig = DEFAULT_TRACKING_CONFIG) -> PointTracker:
    """Select a typed backend without silently falling back to a different implementation."""
    if name == "klt":
        return KLTTracker(config)
    raise TrackerSelectionError(f"tracker backend {name!r} is unavailable")


def with_footage(result: TrackingResult, footage_id: str) -> TrackingResult:
    """Attach stage provenance after a backend-independent tracking call."""
    return replace(
        result,
        tracks=tuple(
            replace(track, track_id=f"{footage_id}:{track.seed.seed_id}", footage_id=footage_id)
            for track in result.tracks
        ),
    )


def _rejected_sample(frames: FrameSource, frame_index: int, reason: RejectionReason) -> TrackSample:
    return TrackSample(
        frame_index,
        frames.timestamps_seconds[frame_index],
        None,
        None,
        False,
        0.0,
        "occluded",
        reason,
    )


def _in_bounds(x_px: float, y_px: float, width: int, height: int) -> bool:
    return 0 <= x_px < width and 0 <= y_px < height


def _patch_in_bounds(x_px: float, y_px: float, width: int, height: int, patch_size: int) -> bool:
    radius = patch_size // 2 + 1
    return radius <= x_px < width - radius and radius <= y_px < height - radius


def _warped_patch(  # noqa: PLR0917 - complete camera warp description
    gray: Image,
    center: tuple[float, float],
    seed: SeedPoint,
    seed_camera: npt.NDArray[np.float64],
    target_camera: npt.NDArray[np.float64],
    size: int,
) -> Image:
    relative = target_camera @ np.linalg.inv(seed_camera)
    jacobian = _homography_jacobian(relative, seed.x_px, seed.y_px)
    radius = size // 2
    offsets = np.arange(-radius, radius + 1, dtype=np.float32)
    dx, dy = np.meshgrid(offsets, offsets)
    map_x = center[0] + jacobian[0, 0] * dx + jacobian[0, 1] * dy
    map_y = center[1] + jacobian[1, 0] * dx + jacobian[1, 1] * dy
    return cast(
        Image,
        cv2.remap(
            gray,
            map_x.astype(np.float32),
            map_y.astype(np.float32),
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT101,
        ),
    )


def _homography_jacobian(
    matrix: npt.NDArray[np.float64], x_px: float, y_px: float
) -> npt.NDArray[np.float64]:
    a, b, c, d, e, f, g, h, i = matrix.ravel()
    denominator = g * x_px + h * y_px + i
    if abs(denominator) < _HOMOGRAPHY_EPSILON:
        return np.eye(2, dtype=np.float64)
    x_numerator = a * x_px + b * y_px + c
    y_numerator = d * x_px + e * y_px + f
    denominator_sq = denominator * denominator
    return np.asarray(
        [
            [
                (a * denominator - g * x_numerator) / denominator_sq,
                (b * denominator - h * x_numerator) / denominator_sq,
            ],
            [
                (d * denominator - g * y_numerator) / denominator_sq,
                (e * denominator - h * y_numerator) / denominator_sq,
            ],
        ],
        dtype=np.float64,
    )


def _normalized_correlation(left: Image, right: Image) -> float:
    left_values = left.astype(np.float32).ravel()
    right_values = right.astype(np.float32).ravel()
    left_values -= float(np.mean(left_values))
    right_values -= float(np.mean(right_values))
    left_std = float(np.linalg.norm(left_values))
    right_std = float(np.linalg.norm(right_values))
    if left_std < _MIN_PATCH_STD or right_std < _MIN_PATCH_STD:
        return -1.0
    return float(np.dot(left_values, right_values) / (left_std * right_std))


__all__ = ["KLTTracker", "TrackerSelectionError", "select_tracker", "with_footage"]

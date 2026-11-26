"""Strict tracker adapter types shared by CPU point-tracking backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from orrery_engine.seeding_types import Image, Matrix, SeedPoint

TrackStatus = Literal["observed", "occluded", "lost", "not_seeded"]
RejectionReason = Literal["lk_failure", "forward_backward", "appearance", "out_of_bounds"]
CancelCheck = Callable[[], None]


MIN_ODD_SIZE = 3
IMAGE_DIMENSIONS = 3
COLOR_CHANNELS = 3


@dataclass(frozen=True)
class TrackingConfig:
    window_size_px: int = 21
    pyramid_levels: int = 4
    forward_backward_threshold_px: float = 0.5
    appearance_threshold: float = 0.8
    patch_size_px: int = 15

    def __post_init__(self) -> None:
        if self.window_size_px < MIN_ODD_SIZE or self.window_size_px % 2 == 0:
            raise ValueError("the KLT window size must be an odd integer of at least 3")
        if self.pyramid_levels < 1:
            raise ValueError("the KLT pyramid must contain at least one level")
        if self.forward_backward_threshold_px <= 0:
            raise ValueError("the forward-backward threshold must be positive")
        if not -1 <= self.appearance_threshold <= 1:
            raise ValueError("the appearance threshold must be in [-1, 1]")
        if self.patch_size_px < MIN_ODD_SIZE or self.patch_size_px % 2 == 0:
            raise ValueError("the appearance patch size must be odd and at least 3")


@dataclass(frozen=True)
class FrameSource:
    frames: tuple[Image, ...]
    reference_to_frames: tuple[Matrix, ...]
    timestamps_seconds: tuple[float, ...]

    def __post_init__(self) -> None:
        count = len(self.frames)
        if (
            count < 1
            or len(self.reference_to_frames) != count
            or len(self.timestamps_seconds) != count
        ):
            raise ValueError("tracking frame, camera, and timestamp sequences must match")
        shape = self.frames[0].shape
        if (
            len(shape) != IMAGE_DIMENSIONS
            or shape[2] != COLOR_CHANNELS
            or any(frame.shape != shape for frame in self.frames)
        ):
            raise ValueError("tracking requires same-sized BGR frames")
        if any(matrix.shape != (3, 3) for matrix in self.reference_to_frames):
            raise ValueError("tracking camera motions must be 3x3 homographies")


class PosePredictor(Protocol):
    def predict(self, seed_id: str, frame_index: int) -> tuple[float, float] | None: ...


@dataclass(frozen=True)
class TrackSample:
    frame_index: int
    timestamp_seconds: float
    x_px: float | None
    y_px: float | None
    visible: bool
    confidence: float
    status: TrackStatus
    rejection_reason: RejectionReason | None = None
    uncertainty_px: float | None = None

    def __post_init__(self) -> None:
        positioned = self.x_px is not None and self.y_px is not None
        if (self.x_px is None) != (self.y_px is None):
            raise ValueError("track positions must contain both coordinates or neither")
        if positioned != self.visible or self.visible != (self.status == "observed"):
            raise ValueError("only observed track samples may contain positions")
        if not 0 <= self.confidence <= 1:
            raise ValueError("track confidence must be in [0, 1]")


@dataclass(frozen=True)
class PointTrack:
    track_id: str
    footage_id: str
    seed: SeedPoint
    samples: tuple[TrackSample, ...]


@dataclass(frozen=True)
class TrackingResult:
    backend: str
    tracks: tuple[PointTrack, ...]


class PointTracker(Protocol):
    name: str

    def track(
        self,
        frames: FrameSource,
        seeds: tuple[SeedPoint, ...],
        predictor: PosePredictor | None = None,
        *,
        check_canceled: CancelCheck,
        forward_only: bool = False,
    ) -> TrackingResult: ...


__all__ = [
    "CancelCheck",
    "FrameSource",
    "PointTrack",
    "PointTracker",
    "PosePredictor",
    "RejectionReason",
    "TrackSample",
    "TrackStatus",
    "TrackingConfig",
    "TrackingResult",
]

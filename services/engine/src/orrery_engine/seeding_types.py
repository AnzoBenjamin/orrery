"""Strict public types for deterministic track seeding and regional re-seeding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

Image = npt.NDArray[np.uint8]
Matrix = npt.NDArray[np.float64]
SeedSource = Literal[
    "shi_tomasi",
    "circular_hole",
    "user_joint",
    "user_part_prompt",
    "reseeded_shi_tomasi",
]
SeedKind = Literal["corner", "hole", "pivot", "prompt"]
DetectionScale = Literal["analysis", "full_resolution", "user_full_resolution"]
AnnotationKind = Literal["joint", "part_prompt"]
MIN_GRID_SIZE_PX = 4


@dataclass(frozen=True)
class SeedingConfig:
    max_points: int = 3000
    grid_size_px: int = 48
    per_cell_cap: int = 6
    min_region_pixels: int = 64
    corner_quality: float = 0.01
    corner_min_distance_px: float = 4.0
    keyframe_count: int = 5
    reseed_coverage_threshold: float = 0.5

    def __post_init__(self) -> None:
        if self.max_points < 1 or self.grid_size_px < MIN_GRID_SIZE_PX or self.per_cell_cap < 1:
            raise ValueError("seeding point and grid limits must be positive")
        if self.min_region_pixels < 1 or self.keyframe_count < 1:
            raise ValueError("seeding region and keyframe limits must be positive")
        if not 0 < self.corner_quality <= 1 or not 0 < self.reseed_coverage_threshold <= 1:
            raise ValueError("seeding quality and coverage thresholds must be in (0, 1]")


@dataclass(frozen=True)
class UserPointInput:
    annotation_id: str
    kind: AnnotationKind
    frame_index: int
    x_px: float
    y_px: float


@dataclass(frozen=True)
class SeedPoint:
    seed_id: str
    x_px: float
    y_px: float
    source: SeedSource
    kind: SeedKind
    confidence: float
    frame_index: int
    detection_scale: DetectionScale
    region_id: str | None = None
    source_x_px: float | None = None
    source_y_px: float | None = None
    annotation_id: str | None = None


@dataclass(frozen=True)
class RegionCoverage:
    region_id: str
    bounding_box: tuple[int, int, int, int]
    moving_pixel_count: int
    eligible_cell_count: int
    covered_cell_count: int
    seed_count: int
    coverage_fraction: float


@dataclass(frozen=True, eq=False)
class SeedingEstimate:
    __hash__ = None  # type: ignore[assignment]

    points: tuple[SeedPoint, ...]
    moving_mask: Image
    coverage: tuple[RegionCoverage, ...]
    keyframe_indices: tuple[int, ...]

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, SeedingEstimate)
            and self.points == other.points
            and self.coverage == other.coverage
            and self.keyframe_indices == other.keyframe_indices
            and np.array_equal(self.moving_mask, other.moving_mask)
        )


@dataclass(frozen=True)
class ReseedCoverage:
    region_id: str
    baseline_seed_count: int
    live_seed_count: int
    added_seed_count: int
    coverage_before: float
    coverage_after: float


@dataclass(frozen=True)
class ReseedResult:
    points: tuple[SeedPoint, ...]
    coverage: tuple[ReseedCoverage, ...]


__all__ = [
    "AnnotationKind",
    "DetectionScale",
    "Image",
    "Matrix",
    "RegionCoverage",
    "ReseedCoverage",
    "ReseedResult",
    "SeedKind",
    "SeedPoint",
    "SeedSource",
    "SeedingConfig",
    "SeedingEstimate",
    "UserPointInput",
]

"""Deterministic stabilized moving-region track seeding and regional re-seeding."""

# OpenCV's generated stubs leave image operations partially unknown at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnnecessaryComparison=false

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np
import numpy.typing as npt

from orrery_engine.seeding_holes import detect_hole_seeds
from orrery_engine.seeding_motion import CancelCheck, moving_masks, project_point, stabilized_grays
from orrery_engine.seeding_types import (
    Image,
    Matrix,
    RegionCoverage,
    ReseedCoverage,
    ReseedResult,
    SeedingConfig,
    SeedingEstimate,
    SeedPoint,
    UserPointInput,
)

DEFAULT_CONFIG = SeedingConfig()
SCORE_EPSILON = 1e-6
MIN_FRAME_COUNT = 2
IMAGE_DIMENSIONS = 3
COLOR_CHANNELS = 3


@dataclass(frozen=True)
class _Region:
    region_id: str
    mask: Image
    bounding_box: tuple[int, int, int, int]
    pixel_count: int


@dataclass(frozen=True)
class _CellSeed:
    x: float
    y: float
    confidence: float
    frame_index: int
    cell: tuple[int, int]


def _no_cancel() -> None:
    pass


def seed_moving_regions(
    frames: Sequence[Image],
    reference_to_frames: Sequence[Matrix],
    *,
    config: SeedingConfig = DEFAULT_CONFIG,
    check_canceled: CancelCheck = _no_cancel,
) -> SeedingEstimate:
    """Seed strong Shi-Tomasi corners evenly across stabilized moving regions."""
    _validate_inputs(frames, reference_to_frames)
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    grays = stabilized_grays(frames, reference_to_frames, check_canceled)
    moving_mask, activity = moving_masks(grays, check_canceled)
    regions = _regions(moving_mask, config.min_region_pixels)
    keyframes = _keyframes(len(frames), config.keyframe_count)
    candidates: dict[str, tuple[_CellSeed, ...]] = {}
    cell_counts: dict[str, int] = {}
    for region in regions:
        check_canceled()
        seeds, eligible = _seed_region(
            grays,
            activity,
            region,
            keyframes,
            config,
            check_canceled=check_canceled,
        )
        candidates[region.region_id] = seeds
        cell_counts[region.region_id] = eligible
    selected = _round_robin(candidates, config.max_points)
    points: list[SeedPoint] = []
    by_region: dict[str, list[_CellSeed]] = {region.region_id: [] for region in regions}
    for region_id, candidate in selected:
        by_region[region_id].append(candidate)
    for region in regions:
        for sequence, item in enumerate(by_region[region.region_id]):
            observed_x, observed_y = project_point(
                reference_to_frames[item.frame_index], item.x, item.y
            )
            observed_x = min(max(0.0, observed_x), frames[0].shape[1] - 1.0)
            observed_y = min(max(0.0, observed_y), frames[0].shape[0] - 1.0)
            points.append(
                SeedPoint(
                    seed_id=f"seed-corner-{region.region_id}-{sequence:04d}",
                    x_px=round(observed_x, 6),
                    y_px=round(observed_y, 6),
                    source="shi_tomasi",
                    kind="corner",
                    confidence=round(item.confidence, 6),
                    frame_index=item.frame_index,
                    detection_scale="analysis",
                    region_id=region.region_id,
                    source_x_px=round(observed_x, 6),
                    source_y_px=round(observed_y, 6),
                )
            )
    coverage = tuple(
        _coverage(region, by_region[region.region_id], cell_counts[region.region_id])
        for region in regions
    )
    return SeedingEstimate(tuple(points), moving_mask, coverage, keyframes)


def user_annotation_seeds(
    annotations: Sequence[UserPointInput],
    *,
    source_size: tuple[int, int],
    analysis_size: tuple[int, int],
) -> tuple[SeedPoint, ...]:
    """Convert contracted full-resolution point annotations to analysis coordinates."""
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        raise ValueError("annotation source size must be positive")
    scale_x = analysis_size[0] / source_width
    scale_y = analysis_size[1] / source_height
    points: list[SeedPoint] = []
    for item in sorted(annotations, key=lambda value: (value.frame_index, value.annotation_id)):
        if not 0 <= item.x_px < source_width or not 0 <= item.y_px < source_height:
            raise ValueError(f"annotation {item.annotation_id} lies outside its footage frame")
        source = "user_joint" if item.kind == "joint" else "user_part_prompt"
        kind = "pivot" if item.kind == "joint" else "prompt"
        points.append(
            SeedPoint(
                seed_id=f"seed-user-{item.annotation_id}",
                x_px=round(item.x_px * scale_x, 6),
                y_px=round(item.y_px * scale_y, 6),
                source=source,
                kind=kind,
                confidence=1.0,
                frame_index=item.frame_index,
                detection_scale="user_full_resolution",
                source_x_px=item.x_px,
                source_y_px=item.y_px,
                annotation_id=item.annotation_id,
            )
        )
    return tuple(points)


def reseed_regions(
    frame: Image,
    moving_mask: Image,
    live_points: Sequence[SeedPoint],
    baseline: Sequence[RegionCoverage],
    *,
    frame_index: int,
    reference_to_frame: Matrix | None = None,
    config: SeedingConfig = DEFAULT_CONFIG,
) -> ReseedResult:
    """Deterministically refill only regions below the configured live-coverage threshold."""
    if frame.shape[:2] != moving_mask.shape or moving_mask.dtype != np.uint8:
        raise ValueError("the re-seeding frame and moving mask must share dimensions")
    matrix = np.eye(3, dtype=np.float64) if reference_to_frame is None else reference_to_frame
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError("the re-seeding homography must be a finite 3x3 matrix")
    height, width = frame.shape[:2]
    stabilized = cv2.warpPerspective(
        frame,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REFLECT,
    )
    gray = cast(Image, cv2.cvtColor(stabilized, cv2.COLOR_BGR2GRAY))
    regions = {item.region_id: item for item in _regions(moving_mask, config.min_region_pixels)}
    points: list[SeedPoint] = []
    metrics: list[ReseedCoverage] = []
    for target in baseline:
        region = regions.get(target.region_id)
        if region is None:
            continue
        live = [item for item in live_points if item.region_id == target.region_id]
        baseline_count = max(1, target.seed_count)
        before = min(1.0, len(live) / baseline_count)
        added: list[SeedPoint] = []
        if before < config.reseed_coverage_threshold:
            raw, _ = _seed_region(
                (gray,),
                (region.mask,),
                region,
                (0,),
                config,
                check_canceled=_no_cancel,
            )
            wanted = max(0, baseline_count - len(live))
            for candidate in raw:
                if len(added) >= wanted:
                    break
                observed_x, observed_y = project_point(matrix, candidate.x, candidate.y)
                observed_x = min(max(0.0, observed_x), frame.shape[1] - 1.0)
                observed_y = min(max(0.0, observed_y), frame.shape[0] - 1.0)
                if _near_any(
                    observed_x,
                    observed_y,
                    (*live, *added),
                    config.corner_min_distance_px,
                ):
                    continue
                added.append(
                    SeedPoint(
                        seed_id=(
                            f"seed-reseed-{frame_index:06d}-{target.region_id}-{len(added):04d}"
                        ),
                        x_px=round(observed_x, 6),
                        y_px=round(observed_y, 6),
                        source="reseeded_shi_tomasi",
                        kind="corner",
                        confidence=round(candidate.confidence, 6),
                        frame_index=frame_index,
                        detection_scale="analysis",
                        region_id=target.region_id,
                        source_x_px=round(observed_x, 6),
                        source_y_px=round(observed_y, 6),
                    )
                )
        points.extend(added)
        after = min(1.0, (len(live) + len(added)) / baseline_count)
        metrics.append(
            ReseedCoverage(
                target.region_id,
                baseline_count,
                len(live),
                len(added),
                round(before, 6),
                round(after, 6),
            )
        )
    return ReseedResult(tuple(points), tuple(metrics))


def merge_seed_sources(
    *groups: Sequence[SeedPoint], minimum_distance_px: float = 2.0
) -> tuple[SeedPoint, ...]:
    """Merge sources by confidence/semantic priority without dropping explicit user points."""
    priority = {
        "user_joint": 0,
        "user_part_prompt": 1,
        "circular_hole": 2,
        "shi_tomasi": 3,
        "reseeded_shi_tomasi": 4,
    }
    ordered = sorted(
        (point for group in groups for point in group),
        key=lambda item: (priority[item.source], item.frame_index, item.seed_id),
    )
    kept: list[SeedPoint] = []
    for point in ordered:
        explicit = point.source.startswith("user_")
        if explicit or not _near_same_frame(point, kept, minimum_distance_px):
            kept.append(point)
    return tuple(kept)


def _seed_region(
    grays: Sequence[Image],
    activity: Sequence[Image],
    region: _Region,
    keyframes: Sequence[int],
    config: SeedingConfig,
    *,
    check_canceled: CancelCheck,
) -> tuple[tuple[_CellSeed, ...], int]:
    seeds: list[_CellSeed] = []
    eligible = 0
    left, top, width, height = region.bounding_box
    eigenvalues = [cv2.cornerMinEigenVal(gray, blockSize=5, ksize=3) for gray in grays]
    maxima = [max(float(np.max(values)), 1e-12) for values in eigenvalues]
    for cell_y, y0 in enumerate(range(top, top + height, config.grid_size_px)):
        for cell_x, x0 in enumerate(range(left, left + width, config.grid_size_px)):
            check_canceled()
            x1 = min(left + width, x0 + config.grid_size_px)
            y1 = min(top + height, y0 + config.grid_size_px)
            region_crop = region.mask[y0:y1, x0:x1]
            if int(np.count_nonzero(region_crop)) < max(4, round(region_crop.size * 0.03)):
                continue
            best: tuple[tuple[float, ...], int, npt.NDArray[np.float32]] | None = None
            for frame_index in keyframes:
                local_mask = cv2.bitwise_and(
                    region_crop,
                    activity[frame_index][y0:y1, x0:x1],
                )
                corners = cv2.goodFeaturesToTrack(
                    grays[frame_index][y0:y1, x0:x1],
                    maxCorners=config.per_cell_cap,
                    qualityLevel=config.corner_quality,
                    minDistance=config.corner_min_distance_px,
                    mask=local_mask,
                    blockSize=5,
                    useHarrisDetector=False,
                )
                if corners is None:
                    continue
                flat = cast(npt.NDArray[np.float32], corners.reshape(-1, 2))
                scores = tuple(
                    float(
                        eigenvalues[frame_index][
                            min(y1 - 1, y0 + round(y)),
                            min(x1 - 1, x0 + round(x)),
                        ]
                    )
                    for x, y in flat
                )
                candidate = (scores, frame_index, flat)
                if best is None or (len(scores), sum(scores), -frame_index) > (
                    len(best[0]),
                    sum(best[0]),
                    -best[1],
                ):
                    best = candidate
            if best is None:
                continue
            eligible += 1
            scores, frame_index, corners = best
            ranked = sorted(
                zip(corners, scores, strict=True),
                key=lambda item: (-item[1], float(item[0][1]), float(item[0][0])),
            )
            for corner, score in ranked[: config.per_cell_cap]:
                seeds.append(
                    _CellSeed(
                        float(corner[0]) + x0,
                        float(corner[1]) + y0,
                        min(1.0, max(SCORE_EPSILON, score / maxima[frame_index])),
                        frame_index,
                        (cell_x, cell_y),
                    )
                )
    return tuple(seeds), eligible


def _regions(mask: Image, minimum_pixels: int) -> tuple[_Region, ...]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    raw: list[tuple[int, int, int, int, int, Image]] = []
    for label in range(1, count):
        left, top, width, height, pixels = (int(value) for value in stats[label])
        if pixels >= minimum_pixels:
            region_mask = np.where(labels == label, 255, 0).astype(np.uint8)
            raw.append((top, left, width, height, pixels, region_mask))
    raw.sort(key=lambda item: (item[0], item[1]))
    return tuple(
        _Region(f"region-{index:03d}", item[5], (item[1], item[0], item[2], item[3]), item[4])
        for index, item in enumerate(raw)
    )


def _round_robin(
    candidates: dict[str, tuple[_CellSeed, ...]], maximum: int
) -> tuple[tuple[str, _CellSeed], ...]:
    ordered = {
        key: sorted(
            value,
            key=lambda item: (
                item.cell,
                -item.confidence,
                item.frame_index,
                item.y,
                item.x,
            ),
        )
        for key, value in sorted(candidates.items())
    }
    selected: list[tuple[str, _CellSeed]] = []
    offset = 0
    while len(selected) < maximum:
        added = False
        for region_id, values in ordered.items():
            if offset < len(values):
                selected.append((region_id, values[offset]))
                added = True
                if len(selected) == maximum:
                    break
        if not added:
            break
        offset += 1
    return tuple(selected)


def _coverage(region: _Region, seeds: Sequence[_CellSeed], eligible: int) -> RegionCoverage:
    covered = len({item.cell for item in seeds})
    fraction = covered / eligible if eligible else 0.0
    return RegionCoverage(
        region.region_id,
        region.bounding_box,
        region.pixel_count,
        eligible,
        covered,
        len(seeds),
        round(fraction, 6),
    )


def _keyframes(frame_count: int, requested: int) -> tuple[int, ...]:
    actual = min(frame_count, requested)
    if actual == 1:
        return (0,)
    indices = {round(index * (frame_count - 1) / (actual - 1)) for index in range(actual)}
    return tuple(sorted(indices))


def _near_any(x: float, y: float, points: Sequence[SeedPoint], distance: float) -> bool:
    return any(math.hypot(x - point.x_px, y - point.y_px) < distance for point in points)


def _near_same_frame(point: SeedPoint, kept: Sequence[SeedPoint], distance: float) -> bool:
    return any(
        point.frame_index == other.frame_index
        and math.hypot(point.x_px - other.x_px, point.y_px - other.y_px) < distance
        for other in kept
    )


def _validate_inputs(frames: Sequence[Image], matrices: Sequence[Matrix]) -> None:
    if len(frames) < MIN_FRAME_COUNT or len(frames) != len(matrices):
        raise ValueError("seeding requires matching frame and camera-motion sequences")
    shape = frames[0].shape
    if (
        len(shape) != IMAGE_DIMENSIONS
        or shape[2] != COLOR_CHANNELS
        or any(frame.shape != shape for frame in frames)
    ):
        raise ValueError("seeding frames must share one BGR image shape")
    if any(matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)) for matrix in matrices):
        raise ValueError("seeding camera motions must be finite 3x3 homographies")


__all__ = [
    "SeedPoint",
    "SeedingConfig",
    "UserPointInput",
    "detect_hole_seeds",
    "merge_seed_sources",
    "reseed_regions",
    "seed_moving_regions",
    "user_annotation_seeds",
]

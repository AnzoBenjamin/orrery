"""Full-resolution circular hole and pivot detection across keyframes."""

# OpenCV's generated stubs leave image operations partially unknown at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from orrery_engine.seeding_types import Image, SeedPoint

MIN_CIRCULARITY = 0.68
MIN_RADIAL_CONTRAST = 4.0
MAX_RADIUS_RATIO = 0.35
MIN_CONTRAST_RATIO = 0.25


@dataclass(frozen=True)
class _Circle:
    x: float
    y: float
    radius: float
    circularity: float
    contrast: float


def detect_hole_seeds(
    frames: Mapping[int, Image], *, analysis_size: tuple[int, int]
) -> tuple[SeedPoint, ...]:
    """Return circles seen consistently on full-resolution keyframes, in analysis coordinates."""
    if not frames:
        return ()
    ordered = tuple(sorted(frames.items()))
    shape = ordered[0][1].shape
    if any(frame.shape != shape for _, frame in ordered):
        raise ValueError("full-resolution hole keyframes must share one image shape")
    candidates = {index: _circle_candidates(frame) for index, frame in ordered}
    anchor_index = ordered[len(ordered) // 2][0]
    anchors = candidates[anchor_index]
    required = max(2, math.ceil(len(ordered) * 0.6)) if len(ordered) > 1 else 1
    height, width = shape[:2]
    scale_x = analysis_size[0] / width
    scale_y = analysis_size[1] / height
    accepted: list[tuple[_Circle, int]] = []
    for anchor in anchors:
        support = sum(
            any(_same_hole(anchor, candidate, width, height) for candidate in candidates[index])
            for index, _ in ordered
        )
        if support >= required:
            accepted.append((anchor, support))
    selected = _deduplicate(accepted)
    points: list[SeedPoint] = []
    for sequence, (circle, support) in enumerate(selected):
        confidence = min(
            1.0,
            0.45 * support / len(ordered)
            + 0.35 * circle.circularity
            + 0.2 * min(1.0, circle.contrast / 50.0),
        )
        points.append(
            SeedPoint(
                seed_id=f"seed-hole-{anchor_index:06d}-{sequence:04d}",
                x_px=round(circle.x * scale_x, 6),
                y_px=round(circle.y * scale_y, 6),
                source="circular_hole",
                kind="hole",
                confidence=round(confidence, 6),
                frame_index=anchor_index,
                detection_scale="full_resolution",
                source_x_px=round(circle.x, 6),
                source_y_px=round(circle.y, 6),
            )
        )
    return tuple(points)


def _circle_candidates(frame: Image) -> tuple[_Circle, ...]:
    gray = cast(Image, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    blurred = cast(Image, cv2.GaussianBlur(gray, (5, 5), 1.2))
    minimum_radius = max(3, round(min(gray.shape) * 0.008))
    maximum_radius = max(minimum_radius + 1, round(min(gray.shape) * 0.15))
    hough = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(8, minimum_radius * 2),
        param1=90,
        param2=14,
        minRadius=minimum_radius,
        maxRadius=maximum_radius,
    )
    hough_items: list[tuple[float, float, float]] = []
    if hough is not None:
        hough_items = [(float(row[0]), float(row[1]), float(row[2])) for row in hough[0]]
    _, dark = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    edges = cv2.Canny(blurred, 40, 120)
    contour_input = cast(Image, cv2.bitwise_or(dark, edges))
    contours, _ = cv2.findContours(contour_input, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[_Circle] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        perimeter = float(cv2.arcLength(contour, True))
        if area < math.pi * minimum_radius**2 * 0.35 or perimeter <= 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if circularity < MIN_CIRCULARITY:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if not minimum_radius <= radius <= maximum_radius:
            continue
        matched = [
            item
            for item in hough_items
            if math.hypot(item[0] - x, item[1] - y) <= max(4.0, radius * 0.45)
            and abs(item[2] - radius) <= max(3.0, radius * 0.5)
        ]
        if not matched:
            continue
        contrast = _radial_contrast(gray, float(x), float(y), float(radius))
        if contrast < MIN_RADIAL_CONTRAST:
            continue
        candidates.append(_Circle(float(x), float(y), float(radius), circularity, contrast))
    return tuple(item for item, _support in _deduplicate([(item, 1) for item in candidates]))


def _radial_contrast(gray: Image, x: float, y: float, radius: float) -> float:
    rows, columns = np.ogrid[: gray.shape[0], : gray.shape[1]]
    distance = np.hypot(columns - x, rows - y)
    inner = gray[distance <= radius * 0.65]
    ring = gray[(distance >= radius * 0.8) & (distance <= radius * 1.25)]
    if not len(inner) or not len(ring):
        return 0.0
    return abs(float(np.mean(inner)) - float(np.mean(ring)))


def _same_hole(first: _Circle, second: _Circle, width: int, height: int) -> bool:
    radius_ratio = abs(first.radius - second.radius) / max(first.radius, second.radius)
    distance_limit = max(3.0 * max(first.radius, second.radius), math.hypot(width, height) * 0.08)
    contrast_ratio = min(first.contrast, second.contrast) / max(first.contrast, second.contrast)
    return (
        radius_ratio <= MAX_RADIUS_RATIO
        and contrast_ratio >= MIN_CONTRAST_RATIO
        and math.hypot(first.x - second.x, first.y - second.y) <= distance_limit
    )


def _deduplicate(items: list[tuple[_Circle, int]]) -> tuple[tuple[_Circle, int], ...]:
    ordered = sorted(
        items,
        key=lambda item: (-item[1], -item[0].circularity, -item[0].contrast, item[0].y, item[0].x),
    )
    selected: list[tuple[_Circle, int]] = []
    for candidate in ordered:
        if any(
            math.hypot(candidate[0].x - existing[0].x, candidate[0].y - existing[0].y)
            <= max(4.0, min(candidate[0].radius, existing[0].radius) * 0.65)
            for existing in selected
        ):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: (item[0].y, item[0].x)))


__all__ = ["detect_hole_seeds"]

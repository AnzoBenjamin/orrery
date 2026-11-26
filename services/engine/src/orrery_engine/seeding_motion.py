"""Stabilized frame differencing, dense flow, and homography utilities for seeding."""

# OpenCV's generated stubs leave image operations partially unknown at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import cast

import cv2
import numpy as np
import numpy.typing as npt

from orrery_engine.seeding_types import Image, Matrix

CancelCheck = Callable[[], None]
SCORE_EPSILON = 1e-6


def stabilized_grays(
    frames: Sequence[Image], matrices: Sequence[Matrix], check_canceled: CancelCheck
) -> tuple[Image, ...]:
    grays: list[Image] = []
    height, width = frames[0].shape[:2]
    for frame, matrix in zip(frames, matrices, strict=True):
        check_canceled()
        stabilized = cv2.warpPerspective(
            frame,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REFLECT,
        )
        grays.append(cast(Image, cv2.cvtColor(stabilized, cv2.COLOR_BGR2GRAY)))
    return tuple(grays)


def moving_masks(
    grays: Sequence[Image], check_canceled: CancelCheck
) -> tuple[Image, tuple[Image, ...]]:
    """Combine stabilized temporal difference and adjacent dense Farneback flow support."""
    median = np.median(np.stack(grays), axis=0).astype(np.uint8)
    differences = [cv2.absdiff(gray, median).astype(np.float32) for gray in grays]
    flow_scores = [np.zeros_like(differences[0], dtype=np.float32) for _ in grays]
    for index in range(1, len(grays)):
        check_canceled()
        flow = cv2.calcOpticalFlowFarneback(
            grays[index - 1], grays[index], None, 0.5, 4, 21, 4, 7, 1.5, 0
        )
        magnitude = np.hypot(flow[..., 0], flow[..., 1]).astype(np.float32)
        flow_scores[index - 1] = np.maximum(flow_scores[index - 1], magnitude)
        flow_scores[index] = np.maximum(flow_scores[index], magnitude)
    difference_threshold = _robust_threshold(differences, floor=8.0, percentile=58)
    flow_threshold = _robust_threshold(flow_scores, floor=0.35, percentile=58)
    kernel = np.ones((5, 5), dtype=np.uint8)
    activity: list[Image] = []
    for difference, flow in zip(differences, flow_scores, strict=True):
        moving = (difference >= difference_threshold) | (flow >= flow_threshold)
        mask = np.where(moving, 255, 0).astype(np.uint8)
        mask = cast(Image, cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel))
        activity.append(mask)
    votes = np.sum(np.stack(activity) > 0, axis=0)
    required = max(1, math.ceil(len(grays) * 0.12))
    aggregate = np.where(votes >= required, 255, 0).astype(np.uint8)
    aggregate = cast(Image, cv2.morphologyEx(aggregate, cv2.MORPH_CLOSE, kernel))
    aggregate = cast(Image, cv2.dilate(aggregate, np.ones((3, 3), dtype=np.uint8)))
    return aggregate, tuple(activity)


def project_point(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    projected = cv2.perspectiveTransform(np.asarray([[[x, y]]], dtype=np.float32), matrix).reshape(
        2
    )
    return float(projected[0]), float(projected[1])


def _robust_threshold(
    samples: Sequence[npt.NDArray[np.float32]], *, floor: float, percentile: float
) -> float:
    stacked = np.stack(samples)
    positive = stacked[stacked > SCORE_EPSILON]
    return max(floor, float(np.percentile(positive, percentile))) if len(positive) else floor


__all__ = ["CancelCheck", "moving_masks", "project_point", "stabilized_grays"]

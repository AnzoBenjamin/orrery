"""Tracking, occlusion, camera-motion, and body-grouping metrics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import cast

import numpy as np
import numpy.typing as npt

from orrery_lab.eval.matching import TrackMatch, point_lookup
from orrery_lab.eval.truth import LoadedTruth
from orrery_lab.eval.types import (
    AnalysisArtifacts,
    CameraMetrics,
    GroupingMetrics,
    TrackingMetrics,
)
from orrery_lab.graph import Json
from orrery_lab.render2d import Camera

MINIMUM_ARI_SAMPLES = 2


def tracking_metrics(
    artifacts: AnalysisArtifacts, truth: LoadedTruth, matches: tuple[TrackMatch, ...]
) -> TrackingMetrics:
    lookup = point_lookup(truth)
    errors: list[float] = []
    visibility_correct = 0
    visibility_total = 0
    for match in matches:
        track = artifacts.tracks[match.predicted_index]
        for sample in track.samples:
            point = lookup.get((match.truth_key, sample.frame_index))
            if point is None:
                continue
            visibility_total += 1
            visibility_correct += sample.visible == point.visible
            if sample.x_px is not None and sample.y_px is not None and point.visible:
                errors.append(math.hypot(sample.x_px - point.x_px, sample.y_px - point.y_px))
    keys = {point.key for point in truth.points}
    return TrackingMetrics(
        endpointMedianPx=float(np.median(errors)) if errors else None,
        endpointP90Px=float(np.percentile(errors, 90)) if errors else None,
        occlusionAccuracy=visibility_correct / visibility_total if visibility_total else None,
        matchedTracks=len(matches),
        predictedTracks=len(artifacts.tracks),
        truthPoints=len(keys),
    )


def grouping_metrics(
    artifacts: AnalysisArtifacts, matches: tuple[TrackMatch, ...]
) -> GroupingMetrics:
    predicted = [
        body_id
        for match in matches
        if (body_id := artifacts.tracks[match.predicted_index].body_id) is not None
    ]
    actual = [
        match.truth_key[0]
        for match in matches
        if artifacts.tracks[match.predicted_index].body_id is not None
    ]
    return GroupingMetrics(
        adjustedRandIndex=_adjusted_rand(actual, predicted) if matches else None,
        comparedTracks=len(matches),
    )


def _adjusted_rand(actual: list[str], predicted: list[str]) -> float:
    if len(actual) != len(predicted):
        raise ValueError("ARI label arrays differ in length")
    count = len(actual)
    if count < MINIMUM_ARI_SAMPLES:
        return 1.0
    contingency: dict[tuple[str, str], int] = defaultdict(int)
    actual_counts: dict[str, int] = defaultdict(int)
    predicted_counts: dict[str, int] = defaultdict(int)
    for left, right in zip(actual, predicted, strict=True):
        contingency[left, right] += 1
        actual_counts[left] += 1
        predicted_counts[right] += 1

    def choose_two(value: int) -> float:
        return value * (value - 1) / 2

    index = sum(choose_two(value) for value in contingency.values())
    actual_sum = sum(choose_two(value) for value in actual_counts.values())
    predicted_sum = sum(choose_two(value) for value in predicted_counts.values())
    total = choose_two(count)
    expected = actual_sum * predicted_sum / total
    maximum = 0.5 * (actual_sum + predicted_sum)
    denominator = maximum - expected
    return 1.0 if denominator == 0.0 else (index - expected) / denominator


def camera_metrics(artifacts: AnalysisArtifacts, truth: LoadedTruth) -> CameraMetrics:
    true_homographies = _truth_homographies(truth)
    predicted = {item.frame_index: item.reference_to_frame for item in artifacts.camera_motion}
    width, height = _dimensions(truth)
    probes = np.asarray(
        [
            [0.0, 0.0],
            [width - 1.0, 0.0],
            [0.0, height - 1.0],
            [width - 1.0, height - 1.0],
            [0.5 * width, 0.5 * height],
        ],
        dtype=np.float64,
    )
    squared: list[float] = []
    compared = 0
    for frame_index, true_matrix in true_homographies.items():
        values = predicted.get(frame_index)
        if values is None:
            continue
        predicted_matrix = np.asarray(values, dtype=np.float64).reshape(3, 3)
        true_points = _apply_homography(true_matrix, probes)
        predicted_points = _apply_homography(predicted_matrix, probes)
        squared.extend(np.sum((true_points - predicted_points) ** 2, axis=1).tolist())
        compared += 1
    return CameraMetrics(
        motionRmsePx=math.sqrt(float(np.mean(squared))) if squared else None,
        comparedFrames=compared,
    )


def _truth_homographies(truth: LoadedTruth) -> dict[int, npt.NDArray[np.float64]]:
    if not truth.frames or any(
        frame.camera.get("model") != "pinhole-brown-conrady-planar" for frame in truth.frames
    ):
        return {}
    world = _world_probes(truth.graph)
    reference = np.asarray([_project(frame=truth.frames[0].camera, point=point) for point in world])
    result: dict[int, npt.NDArray[np.float64]] = {}
    for frame in truth.frames:
        current = np.asarray([_project(frame=frame.camera, point=point) for point in world])
        result[frame.frame_index] = _fit_homography(reference, current)
    return result


def _world_probes(graph: Json) -> tuple[tuple[float, float], ...]:
    coordinates = [
        (float(point["local"]["x"]), float(point["local"]["y"]))
        for body in cast(list[Json], graph["bodies"])
        for point in cast(list[Json], body["points"])
    ]
    if not coordinates:
        return ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (0.0, 0.0))
    xs, ys = zip(*coordinates, strict=True)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if math.isclose(x0, x1):
        x0, x1 = x0 - 0.5, x1 + 0.5
    if math.isclose(y0, y1):
        y0, y1 = y0 - 0.5, y1 + 0.5
    return ((x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2))


def _project(*, frame: Json, point: tuple[float, float]) -> tuple[float, float]:
    distortion = cast(list[float], frame["distortion"])
    camera = Camera(
        int(frame["width"]),
        int(frame["height"]),
        tuple(float(value) for value in cast(list[float], frame["centerWorld"])),  # type: ignore[arg-type]
        float(frame["focalPx"]),
        distance=float(frame["distance"]),
        tilt_x=float(frame["tiltX"]),
        tilt_y=float(frame["tiltY"]),
        roll=float(frame["roll"]),
        k1=distortion[0],
        k2=distortion[1],
        p1=distortion[2],
        p2=distortion[3],
    )
    return camera.project(point)


def _fit_homography(
    source: npt.NDArray[np.float64], target: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(source, target, strict=True):
        rows.extend(
            ([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y], [0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        )
        values.extend((u, v))
    solution, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(values), rcond=None)
    return np.asarray([*solution, 1.0]).reshape(3, 3)


def _apply_homography(
    matrix: npt.NDArray[np.float64], points: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    result = (matrix @ homogeneous.T).T
    return result[:, :2] / result[:, 2, None]


def _dimensions(truth: LoadedTruth) -> tuple[float, float]:
    camera = truth.frames[0].camera
    return float(camera["width"]), float(camera["height"])


__all__ = ["camera_metrics", "grouping_metrics", "tracking_metrics"]

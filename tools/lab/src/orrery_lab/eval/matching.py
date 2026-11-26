"""Deterministic rectangular Hungarian assignment and trajectory/body alignment."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.eval.truth import LoadedTruth, TruthPoint
from orrery_lab.eval.types import TrackArtifact

MATRIX_DIMENSIONS = 2


@dataclass(frozen=True)
class TrackMatch:
    predicted_index: int
    truth_key: tuple[str, str]
    cost_px: float


def assignment(  # noqa: PLR0912 - Hungarian augmenting-path state machine
    cost: npt.NDArray[np.float64],
) -> tuple[tuple[int, int], ...]:
    """Minimum-cost rectangular assignment in O(min(n,m)^2 max(n,m))."""
    if cost.ndim != MATRIX_DIMENSIONS:
        raise ValueError("assignment cost must be a matrix")
    rows, columns = cost.shape
    if rows == 0 or columns == 0:
        return ()
    transposed = rows > columns
    values = cost.T if transposed else cost
    n, m = values.shape
    u = np.zeros(n + 1, dtype=np.float64)
    v = np.zeros(m + 1, dtype=np.float64)
    p = np.zeros(m + 1, dtype=np.int64)
    way = np.zeros(m + 1, dtype=np.int64)
    for i in range(1, n + 1):
        p[0] = i
        minimum = np.full(m + 1, np.inf)
        used = np.zeros(m + 1, dtype=np.bool_)
        column = 0
        while True:
            used[column] = True
            row = int(p[column])
            delta = math.inf
            next_column = 0
            for candidate in range(1, m + 1):
                if used[candidate]:
                    continue
                current = float(values[row - 1, candidate - 1]) - u[row] - v[candidate]
                if current < minimum[candidate]:
                    minimum[candidate] = current
                    way[candidate] = column
                if minimum[candidate] < delta:
                    delta = float(minimum[candidate])
                    next_column = candidate
            if not math.isfinite(delta):
                raise ValueError("assignment has a row without any finite candidate")
            for candidate in range(m + 1):
                if used[candidate]:
                    u[p[candidate]] += delta
                    v[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if p[column] == 0:
                break
        while True:
            previous = int(way[column])
            p[column] = p[previous]
            column = previous
            if column == 0:
                break
    pairs = [(int(p[column]) - 1, column - 1) for column in range(1, m + 1) if p[column]]
    if transposed:
        pairs = [(column, row) for row, column in pairs]
    return tuple(sorted(pairs))


def match_tracks(
    tracks: tuple[TrackArtifact, ...], truth: LoadedTruth, *, gate_px: float
) -> tuple[TrackMatch, ...]:
    keys = tuple(sorted({point.key for point in truth.points}))
    if not tracks or not keys:
        return ()
    true_by_key_frame = {(point.key, point.frame_index): point for point in truth.points}
    costs = np.full((len(tracks), len(keys)), gate_px + 1.0, dtype=np.float64)
    for track_index, track in enumerate(tracks):
        for key_index, key in enumerate(keys):
            distances: list[float] = []
            for sample in track.samples:
                point = true_by_key_frame.get((key, sample.frame_index))
                if point is None:
                    continue
                distances.append(math.hypot(sample.x_px - point.x_px, sample.y_px - point.y_px))
            if distances:
                costs[track_index, key_index] = float(np.median(distances))
    return tuple(
        TrackMatch(row, keys[column], float(costs[row, column]))
        for row, column in assignment(costs)
        if costs[row, column] <= gate_px
    )


def body_alignment(
    tracks: tuple[TrackArtifact, ...], matches: tuple[TrackMatch, ...]
) -> dict[str, str]:
    predicted = tuple(sorted({tracks[match.predicted_index].body_id for match in matches}))
    truth = tuple(sorted({match.truth_key[0] for match in matches}))
    if not predicted or not truth:
        return {}
    counts = np.zeros((len(predicted), len(truth)), dtype=np.float64)
    pred_index = {value: index for index, value in enumerate(predicted)}
    truth_index = {value: index for index, value in enumerate(truth)}
    for match in matches:
        counts[
            pred_index[tracks[match.predicted_index].body_id], truth_index[match.truth_key[0]]
        ] += 1
    max_count = float(np.max(counts))
    pairs = assignment(max_count - counts)
    return {predicted[row]: truth[column] for row, column in pairs if counts[row, column] > 0}


def point_lookup(truth: LoadedTruth) -> dict[tuple[tuple[str, str], int], TruthPoint]:
    return {(point.key, point.frame_index): point for point in truth.points}


__all__ = ["TrackMatch", "assignment", "body_alignment", "match_tracks", "point_lookup"]

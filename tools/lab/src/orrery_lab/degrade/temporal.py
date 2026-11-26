"""Combined rolling-shutter timing and temporal supersampling in linear light."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.degrade.types import LinearRGB, validate_linear_rgb, validate_timestamps


@dataclass(frozen=True)
class TemporalDegradeConfig:
    shutter_seconds: float = 1.0 / 60.0
    rolling_shutter_seconds: float = 0.0
    integration_samples: int = 8

    def __post_init__(self) -> None:
        if not math.isfinite(self.shutter_seconds) or self.shutter_seconds < 0.0:
            raise ValueError("shutter duration must be finite and non-negative")
        if not math.isfinite(self.rolling_shutter_seconds) or self.rolling_shutter_seconds < 0.0:
            raise ValueError("rolling-shutter duration must be finite and non-negative")
        if self.integration_samples <= 0:
            raise ValueError("temporal integration needs at least one sample")


@dataclass(frozen=True)
class TemporalDegradeMetadata:
    """Timing truth; row zero is the top sensor row and is exposed first."""

    operation_order: tuple[str, str, str]
    output_timestamp_seconds: float
    source_timestamps_seconds: tuple[float, ...]
    shutter_seconds: float
    rolling_shutter_seconds: float
    row_exposure_centers_seconds: tuple[float, ...]
    integration_offsets_seconds: tuple[float, ...]


@dataclass(frozen=True)
class TemporalDegradeResult:
    """A float32 linear RGB frame in [0, 1], without sensor clipping or quantization."""

    pixels: LinearRGB
    metadata: TemporalDegradeMetadata


def degrade_temporal(
    supersamples: npt.NDArray[np.float32],
    timestamps: tuple[float, ...],
    output_timestamp: float,
    *,
    config: TemporalDegradeConfig = TemporalDegradeConfig(),
) -> TemporalDegradeResult:
    """Apply row timing first, then box-shutter integration of interpolated real samples."""
    validate_linear_rgb(supersamples, sequence=True)
    validate_timestamps(timestamps, supersamples.shape[0])
    if not math.isfinite(output_timestamp):
        raise ValueError("output timestamp must be finite")
    height = supersamples.shape[1]
    row_fraction = (np.arange(height, dtype=np.float64) + 0.5) / height - 0.5
    row_centers = output_timestamp + config.rolling_shutter_seconds * row_fraction
    if config.shutter_seconds == 0.0:
        offsets = np.array([0.0], dtype=np.float64)
    else:
        offsets = config.shutter_seconds * (
            (np.arange(config.integration_samples, dtype=np.float64) + 0.5)
            / config.integration_samples
            - 0.5
        )
    first_query = float(row_centers[0] + offsets[0])
    last_query = float(row_centers[-1] + offsets[-1])
    if first_query < timestamps[0] or last_query > timestamps[-1]:
        raise ValueError("supersamples do not cover every row exposure interval")

    if np.all(supersamples == supersamples[0]):
        output = supersamples[0].copy()
    else:
        output = np.empty(supersamples.shape[1:], dtype=np.float32)
        source_times = np.asarray(timestamps, dtype=np.float64)
        for row, center in enumerate(row_centers):
            queries = center + offsets
            accumulated = np.zeros_like(supersamples[0, row])
            for query in queries:
                right = min(max(bisect_right(timestamps, float(query)), 1), len(timestamps) - 1)
                left = right - 1
                span = source_times[right] - source_times[left]
                alpha = np.float32((query - source_times[left]) / span)
                before = supersamples[left, row]
                after = supersamples[right, row]
                accumulated += before + alpha * (after - before)
            output[row] = accumulated / len(queries)

    metadata = TemporalDegradeMetadata(
        ("rolling_shutter_row_timing", "linear_temporal_interpolation", "box_motion_blur"),
        output_timestamp,
        timestamps,
        config.shutter_seconds,
        config.rolling_shutter_seconds,
        tuple(float(value) for value in row_centers),
        tuple(float(value) for value in offsets),
    )
    return TemporalDegradeResult(output, metadata)


__all__ = [
    "TemporalDegradeConfig",
    "TemporalDegradeMetadata",
    "TemporalDegradeResult",
    "degrade_temporal",
]

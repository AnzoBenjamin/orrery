"""Sampling and raster operations for archival-film artifacts."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from orrery_lab.degrade.archival_types import (
    ArchivalDegradeConfig,
    DustEventMetadata,
    ScratchEventMetadata,
)

FloatImage = npt.NDArray[np.float64]
_MINIMUM_PERSISTENT_FRAMES = 2


def translate_bilinear_black(image: FloatImage, dx: float, dy: float) -> FloatImage:
    """Translate pixel centers by ``(dx, dy)`` using bilinear interpolation and black borders."""
    height, width, _ = image.shape
    output_y, output_x = np.indices((height, width), dtype=np.float64)
    source_x = output_x - dx
    source_y = output_y - dy
    x0 = np.floor(source_x).astype(np.int64)
    y0 = np.floor(source_y).astype(np.int64)
    x1 = x0 + 1
    y1 = y0 + 1
    wx = source_x - x0
    wy = source_y - y0
    output = np.zeros_like(image)
    for xs, ys, weight in (
        (x0, y0, (1.0 - wx) * (1.0 - wy)),
        (x1, y0, wx * (1.0 - wy)),
        (x0, y1, (1.0 - wx) * wy),
        (x1, y1, wx * wy),
    ):
        valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
        safe_x = np.clip(xs, 0, width - 1)
        safe_y = np.clip(ys, 0, height - 1)
        output += image[safe_y, safe_x] * (weight * valid)[..., np.newaxis]
    return output


def sample_scratches(
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    config: ArchivalDegradeConfig,
) -> tuple[ScratchEventMetadata, ...]:
    duration = _sampling_duration(timestamps, config.fps_range[1])
    count = _event_count(config.scratch_rate_per_second, duration, rng)
    events: list[ScratchEventMetadata] = []
    for event_id in range(count):
        sampled_lifetime = float(rng.uniform(*config.scratch_lifetime_seconds))
        start, end = _lifetime_frames(
            len(timestamps),
            sampled_lifetime,
            1.0 / _frame_period(timestamps, config.fps_range[1]),
            rng,
        )
        events.append(
            ScratchEventMetadata(
                event_id,
                start,
                end,
                timestamps[start],
                timestamps[end],
                sampled_lifetime,
                float(rng.uniform(0.0, 1.0)),
                float(
                    rng.uniform(
                        -config.scratch_max_drift_normalized_per_second,
                        config.scratch_max_drift_normalized_per_second,
                    )
                ),
                float(
                    rng.uniform(
                        -config.scratch_max_slant_normalized,
                        config.scratch_max_slant_normalized,
                    )
                ),
                (
                    float(rng.uniform(0.0, 0.3)),
                    float(rng.uniform(0.7, 1.0)),
                ),
                float(rng.uniform(*config.scratch_width_px)),
                float(rng.uniform(*config.scratch_opacity)),
                float(rng.choice((0.0, 1.0))),
            )
        )
    return tuple(events)


def sample_dust(
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    config: ArchivalDegradeConfig,
) -> tuple[DustEventMetadata, ...]:
    duration = _sampling_duration(timestamps, config.fps_range[1])
    count = _event_count(config.dust_rate_per_second, duration, rng)
    events: list[DustEventMetadata] = []
    for event_id in range(count):
        sampled_lifetime = float(rng.uniform(*config.dust_lifetime_seconds))
        start, end = _lifetime_frames(
            len(timestamps),
            sampled_lifetime,
            1.0 / _frame_period(timestamps, config.fps_range[1]),
            rng,
        )
        events.append(
            DustEventMetadata(
                event_id,
                start,
                end,
                timestamps[start],
                timestamps[end],
                sampled_lifetime,
                (float(rng.uniform(0.0, 1.0)), float(rng.uniform(0.0, 1.0))),
                (
                    float(
                        rng.uniform(
                            -config.dust_max_speed_normalized_per_second,
                            config.dust_max_speed_normalized_per_second,
                        )
                    ),
                    float(
                        rng.uniform(
                            -config.dust_max_speed_normalized_per_second,
                            config.dust_max_speed_normalized_per_second,
                        )
                    ),
                ),
                float(rng.uniform(*config.dust_radius_px)),
                float(rng.uniform(*config.dust_opacity)),
                float(rng.choice((0.0, 1.0))),
            )
        )
    return tuple(events)


def render_artifacts(
    image: FloatImage,
    frame_index: int,
    timestamp: float,
    scratches: tuple[ScratchEventMetadata, ...],
    dust: tuple[DustEventMetadata, ...],
) -> tuple[FloatImage, tuple[int, ...], tuple[int, ...]]:
    height, width, _ = image.shape
    y, x = np.indices((height, width), dtype=np.float64)
    output = image.copy()
    active_scratches: list[int] = []
    for event in scratches:
        if not event.start_frame <= frame_index <= event.end_frame_inclusive:
            continue
        active_scratches.append(event.event_id)
        age = timestamp - event.start_timestamp_seconds
        center = (event.x_start_normalized + event.x_velocity_normalized_per_second * age) * width
        center = center + event.slant_normalized * width * (y / max(height - 1, 1) - 0.5)
        distance = np.abs(x - center)
        sigma = max(event.width_px / 2.355, 1e-6)
        alpha = event.opacity * np.exp(-0.5 * (distance / sigma) ** 2)
        y_normalized = y / max(height - 1, 1)
        alpha *= (y_normalized >= event.y_range_normalized[0]) & (
            y_normalized <= event.y_range_normalized[1]
        )
        output = _blend_luminance(output, alpha, event.target_luminance)

    active_dust: list[int] = []
    for event in dust:
        if not event.start_frame <= frame_index <= event.end_frame_inclusive:
            continue
        active_dust.append(event.event_id)
        age = timestamp - event.start_timestamp_seconds
        center_x = (
            event.center_start_normalized[0] + event.velocity_normalized_per_second[0] * age
        ) * width
        center_y = (
            event.center_start_normalized[1] + event.velocity_normalized_per_second[1] * age
        ) * height
        squared_radius = (x - center_x) ** 2 + (y - center_y) ** 2
        alpha = event.opacity * np.exp(-2.0 * squared_radius / max(event.radius_px**2, 1e-12))
        output = _blend_luminance(output, alpha, event.target_luminance)
    return output, tuple(active_scratches), tuple(active_dust)


def vignette_mask(
    height: int, width: int, strength: float, radius_normalized: float
) -> npt.NDArray[np.float64]:
    y, x = np.indices((height, width), dtype=np.float64)
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    farthest = math.hypot(max(center_x, width - 1 - center_x), max(center_y, height - 1 - center_y))
    if farthest == 0.0:
        return np.ones((height, width), dtype=np.float64)
    radius = np.hypot(x - center_x, y - center_y) / farthest
    transition = np.clip((radius - radius_normalized) / (1.0 - radius_normalized), 0.0, 1.0)
    smooth = transition * transition * (3.0 - 2.0 * transition)
    return 1.0 - strength * smooth


def _blend_luminance(
    image: FloatImage, alpha: npt.NDArray[np.float64], target: float
) -> FloatImage:
    return image * (1.0 - alpha[..., np.newaxis]) + target * alpha[..., np.newaxis]


def _sampling_duration(timestamps: tuple[float, ...], fallback_fps: int) -> float:
    return max(timestamps[-1] - timestamps[0], 1.0 / fallback_fps)


def _event_count(rate: float, duration: float, rng: np.random.Generator) -> int:
    if rate == 0.0:
        return 0
    return max(1, int(rng.poisson(rate * duration)))


def _frame_period(timestamps: tuple[float, ...], fallback_fps: int) -> float:
    return timestamps[1] - timestamps[0] if len(timestamps) > 1 else 1.0 / fallback_fps


def _lifetime_frames(
    frame_count: int,
    lifetime_seconds: float,
    frames_per_second: float,
    rng: np.random.Generator,
) -> tuple[int, int]:
    minimum = (
        _MINIMUM_PERSISTENT_FRAMES
        if frame_count >= _MINIMUM_PERSISTENT_FRAMES
        else 1
    )
    length = min(frame_count, max(minimum, round(lifetime_seconds * frames_per_second)))
    start_limit = frame_count - length + 1
    start = int(rng.integers(0, start_limit))
    return start, start + length - 1


__all__ = [
    "render_artifacts",
    "sample_dust",
    "sample_scratches",
    "translate_bilinear_black",
    "vignette_mask",
]

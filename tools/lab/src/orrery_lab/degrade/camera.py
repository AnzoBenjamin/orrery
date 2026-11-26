"""Timestamp-driven, band-limited 2D camera shake and focus breathing."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from orrery_lab.degrade.types import validate_timestamps
from orrery_lab.render2d.camera import MAX_TILT, Camera

CHANNEL_COUNT = 6
MIN_SHAKE_FREQUENCY_HZ = 0.5
MAX_SHAKE_FREQUENCY_HZ = 8.0


@dataclass(frozen=True)
class CameraDegradeConfig:
    """Limits for a smooth Fourier camera trajectory, expressed in physical units."""

    frequency_min_hz: float = 0.5
    frequency_max_hz: float = 8.0
    component_count: int = 8
    center_amplitude_world: float = 0.004
    tilt_amplitude_radians: float = math.radians(0.8)
    roll_amplitude_radians: float = math.radians(1.0)
    focus_breathing_fraction: float = 0.015

    def __post_init__(self) -> None:
        values = (
            self.frequency_min_hz,
            self.frequency_max_hz,
            self.center_amplitude_world,
            self.tilt_amplitude_radians,
            self.roll_amplitude_radians,
            self.focus_breathing_fraction,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("camera degradation values must be finite")
        if (
            self.frequency_min_hz < MIN_SHAKE_FREQUENCY_HZ
            or self.frequency_max_hz > MAX_SHAKE_FREQUENCY_HZ
        ):
            raise ValueError("camera shake frequencies must remain within 0.5-8 Hz")
        if self.frequency_min_hz > self.frequency_max_hz:
            raise ValueError("camera shake frequency bounds are reversed")
        if self.component_count <= 0:
            raise ValueError("camera shake needs at least one Fourier component")
        if min(values[2:5]) < 0.0:
            raise ValueError("camera shake amplitudes cannot be negative")
        if not 0.0 <= self.focus_breathing_fraction < 1.0:
            raise ValueError("focus breathing must be a fraction below one")


@dataclass(frozen=True)
class CameraFourierTerm:
    """One fully sampled trajectory term; channel order is documented in ``channels``."""

    frequency_hz: float
    phases_radians: tuple[float, float, float, float, float, float]
    amplitudes: tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class CameraSampleMetadata:
    timestamp_seconds: float
    center_world: tuple[float, float]
    tilt_x_radians: float
    tilt_y_radians: float
    roll_radians: float
    focal_px: float


@dataclass(frozen=True)
class CameraDegradeMetadata:
    channels: tuple[str, str, str, str, str, str]
    frequency_band_hz: tuple[float, float]
    terms: tuple[CameraFourierTerm, ...]
    samples: tuple[CameraSampleMetadata, ...]


@dataclass(frozen=True)
class CameraDegradeResult:
    cameras: tuple[Camera, ...]
    metadata: CameraDegradeMetadata


def degrade_camera(
    camera: Camera,
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    *,
    config: CameraDegradeConfig = CameraDegradeConfig(),
) -> CameraDegradeResult:
    """Sample once, then evaluate smooth shake and breathing at absolute timestamps."""
    validate_timestamps(timestamps, len(timestamps))
    frequencies = rng.uniform(
        config.frequency_min_hz,
        config.frequency_max_hz,
        size=config.component_count,
    )
    phases = rng.uniform(0.0, math.tau, size=(config.component_count, CHANNEL_COUNT))
    raw = rng.normal(size=(config.component_count, CHANNEL_COUNT)) / (
        1.0 + frequencies[:, np.newaxis] / config.frequency_min_hz
    )
    tilt_x_room = max(0.0, MAX_TILT - abs(camera.tilt_x))
    tilt_y_room = max(0.0, MAX_TILT - abs(camera.tilt_y))
    limits = (
        config.center_amplitude_world,
        config.center_amplitude_world,
        min(config.tilt_amplitude_radians, tilt_x_room),
        min(config.tilt_amplitude_radians, tilt_y_room),
        config.roll_amplitude_radians,
        config.focus_breathing_fraction,
    )
    amplitudes = np.empty_like(raw)
    for channel, limit in enumerate(limits):
        total = float(np.sum(np.abs(raw[:, channel])))
        amplitudes[:, channel] = 0.0 if total == 0.0 else raw[:, channel] * limit / total

    terms = tuple(
        CameraFourierTerm(
            float(frequencies[index]),
            _six(phases[index]),
            _six(amplitudes[index]),
        )
        for index in range(config.component_count)
    )
    cameras: list[Camera] = []
    samples: list[CameraSampleMetadata] = []
    for timestamp in timestamps:
        signal = np.sum(
            amplitudes * np.sin(math.tau * frequencies[:, np.newaxis] * timestamp + phases),
            axis=0,
        )
        changed = replace(
            camera,
            center_world=(
                camera.center_world[0] + float(signal[0]),
                camera.center_world[1] + float(signal[1]),
            ),
            tilt_x=camera.tilt_x + float(signal[2]),
            tilt_y=camera.tilt_y + float(signal[3]),
            roll=camera.roll + float(signal[4]),
            focal_px=camera.focal_px * (1.0 + float(signal[5])),
        )
        cameras.append(changed)
        samples.append(
            CameraSampleMetadata(
                timestamp,
                changed.center_world,
                changed.tilt_x,
                changed.tilt_y,
                changed.roll,
                changed.focal_px,
            )
        )
    metadata = CameraDegradeMetadata(
        ("center_x_world", "center_y_world", "tilt_x", "tilt_y", "roll", "focal_fraction"),
        (config.frequency_min_hz, config.frequency_max_hz),
        terms,
        tuple(samples),
    )
    return CameraDegradeResult(tuple(cameras), metadata)


def _six(
    values: np.ndarray[tuple[int, ...], np.dtype[np.float64]],
) -> tuple[float, float, float, float, float, float]:
    return (
        float(values[0]),
        float(values[1]),
        float(values[2]),
        float(values[3]),
        float(values[4]),
        float(values[5]),
    )


__all__ = [
    "CameraDegradeConfig",
    "CameraDegradeMetadata",
    "CameraDegradeResult",
    "CameraFourierTerm",
    "CameraSampleMetadata",
    "degrade_camera",
]

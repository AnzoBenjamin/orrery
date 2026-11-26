"""Auto-exposure drift and Poisson-Gaussian sensor noise in linear light."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from orrery_lab.degrade.types import validate_linear_rgb, validate_timestamps

MAX_DRIFT_FREQUENCY_HZ = 0.5


@dataclass(frozen=True)
class SensorDegradeConfig:
    target_luminance: float = 0.35
    minimum_gain: float = 0.25
    maximum_gain: float = 4.0
    drift_frequency_min_hz: float = 0.03
    drift_frequency_max_hz: float = 0.35
    drift_component_count: int = 4
    drift_amplitude_stops: float = 0.2
    full_well_electrons: float = 4000.0
    read_noise_std: float = 0.003

    def __post_init__(self) -> None:
        values = (
            self.target_luminance,
            self.minimum_gain,
            self.maximum_gain,
            self.drift_frequency_min_hz,
            self.drift_frequency_max_hz,
            self.drift_amplitude_stops,
            self.full_well_electrons,
            self.read_noise_std,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("sensor degradation values must be finite")
        if not 0.0 < self.target_luminance <= 1.0:
            raise ValueError("target luminance must be in (0, 1]")
        if self.minimum_gain <= 0.0 or self.maximum_gain < self.minimum_gain:
            raise ValueError("exposure gain bounds are invalid")
        if (
            self.drift_frequency_min_hz <= 0.0
            or self.drift_frequency_max_hz > MAX_DRIFT_FREQUENCY_HZ
        ):
            raise ValueError("exposure drift frequencies must be low-frequency (0, 0.5] Hz")
        if self.drift_frequency_min_hz > self.drift_frequency_max_hz:
            raise ValueError("exposure drift frequency bounds are reversed")
        if self.drift_component_count <= 0:
            raise ValueError("exposure drift needs at least one Fourier component")
        if self.drift_amplitude_stops < 0.0:
            raise ValueError("exposure drift amplitude cannot be negative")
        if self.full_well_electrons <= 0.0 or self.read_noise_std < 0.0:
            raise ValueError("sensor noise scales are invalid")


@dataclass(frozen=True)
class ExposureFourierTerm:
    frequency_hz: float
    phase_radians: float
    amplitude_stops: float


@dataclass(frozen=True)
class SensorFrameMetadata:
    timestamp_seconds: float
    scene_luminance: float
    auto_exposure_gain: float
    drift_stops: float
    applied_gain: float


@dataclass(frozen=True)
class SensorDegradeMetadata:
    operation_order: tuple[str, str, str, str]
    target_luminance: float
    gain_bounds: tuple[float, float]
    full_well_electrons: float
    read_noise_std: float
    exposure_terms: tuple[ExposureFourierTerm, ...]
    frames: tuple[SensorFrameMetadata, ...]
    output_dtype: str
    output_range: tuple[float, float]


@dataclass(frozen=True)
class SensorDegradeResult:
    """Linear float32 RGB clipped to [0, 1], the pipeline's declared output boundary."""

    pixels: npt.NDArray[np.float32]
    metadata: SensorDegradeMetadata


def degrade_sensor(
    frames: npt.NDArray[np.float32],
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    *,
    config: SensorDegradeConfig = SensorDegradeConfig(),
) -> SensorDegradeResult:
    """Apply coherent exposure drift, then shot/read noise, and clip only at output."""
    validate_linear_rgb(frames, sequence=True)
    validate_timestamps(timestamps, frames.shape[0])
    frequencies = rng.uniform(
        config.drift_frequency_min_hz,
        config.drift_frequency_max_hz,
        size=config.drift_component_count,
    )
    phases = rng.uniform(0.0, math.tau, size=config.drift_component_count)
    raw_amplitudes = rng.normal(size=config.drift_component_count) / (
        1.0 + frequencies / config.drift_frequency_min_hz
    )
    magnitude = float(np.sum(np.abs(raw_amplitudes)))
    amplitudes = (
        np.zeros_like(raw_amplitudes)
        if magnitude == 0.0
        else raw_amplitudes * config.drift_amplitude_stops / magnitude
    )
    terms = tuple(
        ExposureFourierTerm(float(frequency), float(phase), float(amplitude))
        for frequency, phase, amplitude in zip(frequencies, phases, amplitudes, strict=True)
    )

    output = np.empty_like(frames)
    frame_metadata: list[SensorFrameMetadata] = []
    for index, timestamp in enumerate(timestamps):
        channel_means = tuple(
            float(np.mean(frames[index, :, :, channel], dtype=np.float64)) for channel in range(3)
        )
        luminance = sum(
            mean * weight
            for mean, weight in zip(channel_means, (0.2126, 0.7152, 0.0722), strict=True)
        )
        auto_gain = min(
            max(
                config.target_luminance / max(luminance, float(np.finfo(np.float32).eps)),
                config.minimum_gain,
            ),
            config.maximum_gain,
        )
        drift_stops = float(
            np.sum(amplitudes * np.sin(math.tau * frequencies * timestamp + phases))
        )
        applied_gain = auto_gain * (2.0**drift_stops)
        exposed = frames[index].astype(np.float64) * applied_gain
        electrons = rng.poisson(exposed * config.full_well_electrons)
        noisy = electrons / config.full_well_electrons
        if config.read_noise_std > 0.0:
            noisy = noisy + rng.normal(0.0, config.read_noise_std, size=noisy.shape)
        output[index] = np.clip(noisy, 0.0, 1.0).astype(np.float32)
        frame_metadata.append(
            SensorFrameMetadata(timestamp, luminance, auto_gain, drift_stops, applied_gain)
        )

    metadata = SensorDegradeMetadata(
        ("auto_exposure", "exposure_drift_linear_gain", "poisson_gaussian_noise", "clip"),
        config.target_luminance,
        (config.minimum_gain, config.maximum_gain),
        config.full_well_electrons,
        config.read_noise_std,
        terms,
        tuple(frame_metadata),
        "float32-linear-rgb",
        (0.0, 1.0),
    )
    return SensorDegradeResult(output, metadata)


__all__ = [
    "ExposureFourierTerm",
    "SensorDegradeConfig",
    "SensorDegradeMetadata",
    "SensorDegradeResult",
    "SensorFrameMetadata",
    "degrade_sensor",
]

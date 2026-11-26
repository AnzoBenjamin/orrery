"""Frozen public types for deterministic archival-film degradation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

type ArchivalTone = Literal["sepia", "monochrome"]
type ArchivalRGBSequence = npt.NDArray[np.float32]
MIN_ARCHIVAL_FPS = 12
MAX_ARCHIVAL_FPS = 24


@dataclass(frozen=True)
class ArchivalDegradeConfig:
    """Bounds and physical parameters for the archival capture profile."""

    fps_range: tuple[int, int] = (12, 24)
    weave_frequency_range_hz: tuple[float, float] = (0.08, 0.45)
    weave_component_count: int = 3
    weave_amplitude_px: tuple[float, float] = (1.2, 0.8)
    flicker_frequency_range_hz: tuple[float, float] = (0.06, 0.35)
    flicker_component_count: int = 3
    flicker_amplitude_fraction: float = 0.12
    grain_std: float = 0.035
    grain_luminance_floor: float = 0.25
    scratch_rate_per_second: float = 1.5
    scratch_lifetime_seconds: tuple[float, float] = (0.25, 1.5)
    scratch_width_px: tuple[float, float] = (0.4, 1.4)
    scratch_opacity: tuple[float, float] = (0.08, 0.3)
    scratch_max_drift_normalized_per_second: float = 0.04
    scratch_max_slant_normalized: float = 0.025
    dust_rate_per_second: float = 5.0
    dust_lifetime_seconds: tuple[float, float] = (0.12, 0.8)
    dust_radius_px: tuple[float, float] = (0.6, 3.0)
    dust_opacity: tuple[float, float] = (0.08, 0.35)
    dust_max_speed_normalized_per_second: float = 0.08
    vignette_strength: tuple[float, float] = (0.15, 0.35)
    vignette_radius_normalized: tuple[float, float] = (0.45, 0.72)
    tone_modes: tuple[ArchivalTone, ...] = ("sepia", "monochrome")

    def __post_init__(self) -> None:
        if self.fps_range[0] < MIN_ARCHIVAL_FPS or self.fps_range[1] > MAX_ARCHIVAL_FPS:
            raise ValueError("archival frame rate must remain within 12-24 fps")
        if self.fps_range[1] < self.fps_range[0]:
            raise ValueError("archival frame-rate range is reversed")
        _validate_frequency_range("weave", self.weave_frequency_range_hz)
        _validate_frequency_range("flicker", self.flicker_frequency_range_hz)
        if self.weave_component_count <= 0 or self.flicker_component_count <= 0:
            raise ValueError("archival trajectories need at least one component")
        _validate_pair("weave amplitude", self.weave_amplitude_px, minimum=0.0)
        _validate_fraction("flicker amplitude", self.flicker_amplitude_fraction, upper=1.0)
        if not math.isfinite(self.grain_std) or self.grain_std < 0.0:
            raise ValueError("grain standard deviation must be finite and non-negative")
        _validate_closed_fraction("grain luminance floor", self.grain_luminance_floor)
        for name, value in (
            ("scratch rate", self.scratch_rate_per_second),
            ("scratch drift", self.scratch_max_drift_normalized_per_second),
            ("scratch slant", self.scratch_max_slant_normalized),
            ("dust rate", self.dust_rate_per_second),
            ("dust speed", self.dust_max_speed_normalized_per_second),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name, bounds, positive in (
            ("scratch lifetime", self.scratch_lifetime_seconds, True),
            ("scratch width", self.scratch_width_px, True),
            ("scratch opacity", self.scratch_opacity, False),
            ("dust lifetime", self.dust_lifetime_seconds, True),
            ("dust radius", self.dust_radius_px, True),
            ("dust opacity", self.dust_opacity, False),
            ("vignette strength", self.vignette_strength, False),
            ("vignette radius", self.vignette_radius_normalized, True),
        ):
            _validate_range(name, bounds, positive=positive)
        if self.scratch_opacity[1] > 1.0 or self.dust_opacity[1] > 1.0:
            raise ValueError("artifact opacity must be at most one")
        if self.vignette_strength[1] > 1.0:
            raise ValueError("vignette strength must be at most one")
        if self.vignette_radius_normalized[1] >= 1.0:
            raise ValueError("vignette radius must be below one")
        if not self.tone_modes or len(set(self.tone_modes)) != len(self.tone_modes):
            raise ValueError("tone modes must be non-empty and unique")
        if any(mode not in ("sepia", "monochrome") for mode in self.tone_modes):
            raise ValueError("unsupported archival tone mode")


@dataclass(frozen=True)
class WeaveFourierTerm:
    frequency_hz: float
    x_phase_radians: float
    y_phase_radians: float
    x_amplitude_px: float
    y_amplitude_px: float


@dataclass(frozen=True)
class FlickerFourierTerm:
    frequency_hz: float
    phase_radians: float
    amplitude_fraction: float


@dataclass(frozen=True)
class ScratchEventMetadata:
    event_id: int
    start_frame: int
    end_frame_inclusive: int
    start_timestamp_seconds: float
    end_timestamp_seconds: float
    sampled_lifetime_seconds: float
    x_start_normalized: float
    x_velocity_normalized_per_second: float
    slant_normalized: float
    y_range_normalized: tuple[float, float]
    width_px: float
    opacity: float
    target_luminance: float


@dataclass(frozen=True)
class DustEventMetadata:
    event_id: int
    start_frame: int
    end_frame_inclusive: int
    start_timestamp_seconds: float
    end_timestamp_seconds: float
    sampled_lifetime_seconds: float
    center_start_normalized: tuple[float, float]
    velocity_normalized_per_second: tuple[float, float]
    radius_px: float
    opacity: float
    target_luminance: float


@dataclass(frozen=True)
class ResampleFrameMetadata:
    output_timestamp_seconds: float
    source_left_index: int
    source_right_index: int
    interpolation_alpha: float


@dataclass(frozen=True)
class ArchivalTimingMetadata:
    source_timestamps_seconds: tuple[float, ...]
    selected_fps: int
    frame_period_seconds: float
    output_timestamps_seconds: tuple[float, ...]
    source_duration_seconds: float
    output_duration_seconds: float
    resample_frames: tuple[ResampleFrameMetadata, ...]


@dataclass(frozen=True)
class ArchivalFrameMetadata:
    frame_index: int
    timestamp_seconds: float
    gate_translation_px: tuple[float, float]
    flicker_gain: float
    grain_seed: int
    active_scratch_ids: tuple[int, ...]
    active_dust_ids: tuple[int, ...]


@dataclass(frozen=True)
class VignetteMetadata:
    strength: float
    radius_normalized: float
    distance_normalization: Literal["center-to-farthest-corner"]
    falloff: Literal["smoothstep"]


@dataclass(frozen=True)
class ToneMetadata:
    mode: ArchivalTone
    working_space: Literal["linear-rgb"]
    luminance_coefficients: tuple[float, float, float]
    sepia_matrix: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


@dataclass(frozen=True)
class ArchivalDegradeMetadata:
    schema_version: Literal[1]
    config: ArchivalDegradeConfig
    dimensions: tuple[int, int]
    input_dtype: Literal["float32-linear-rgb"]
    operation_order: tuple[str, ...]
    timing: ArchivalTimingMetadata
    resample_interpolation: Literal["linear-between-neighboring-source-frames"]
    weave_terms: tuple[WeaveFourierTerm, ...]
    flicker_terms: tuple[FlickerFourierTerm, ...]
    translation_interpolation: Literal["bilinear-pixel-center"]
    translation_border: Literal["constant-black"]
    grain_model: Literal["shared-rgb-gaussian-scaled-by-sqrt-luminance"]
    scratches: tuple[ScratchEventMetadata, ...]
    dust: tuple[DustEventMetadata, ...]
    vignette: VignetteMetadata
    tone: ToneMetadata
    frames: tuple[ArchivalFrameMetadata, ...]
    output_dtype: Literal["float32-linear-rgb"]
    output_range: tuple[float, float]


@dataclass(frozen=True)
class ArchivalDegradeResult:
    pixels: ArchivalRGBSequence
    timestamps: tuple[float, ...]
    metadata: ArchivalDegradeMetadata


def _validate_frequency_range(name: str, bounds: tuple[float, float]) -> None:
    _validate_range(f"{name} frequency", bounds, positive=True)
    if bounds[1] > 1.0:
        raise ValueError(f"{name} frequency must remain low-frequency (at most 1 Hz)")


def _validate_pair(name: str, values: tuple[float, float], *, minimum: float) -> None:
    if not all(math.isfinite(value) and value >= minimum for value in values):
        raise ValueError(f"{name} values must be finite and at least {minimum}")


def _validate_fraction(name: str, value: float, *, upper: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value < upper:
        raise ValueError(f"{name} must be finite and in [0, {upper})")


def _validate_closed_fraction(name: str, value: float) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


def _validate_range(name: str, bounds: tuple[float, float], *, positive: bool) -> None:
    lower, upper = bounds
    minimum_ok = lower > 0.0 if positive else lower >= 0.0
    if not all(math.isfinite(value) for value in bounds) or not minimum_ok or upper < lower:
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} range must be finite, ordered, and {qualifier}")


__all__ = [
    "ArchivalDegradeConfig",
    "ArchivalDegradeMetadata",
    "ArchivalDegradeResult",
    "ArchivalFrameMetadata",
    "ArchivalRGBSequence",
    "ArchivalTimingMetadata",
    "ArchivalTone",
    "DustEventMetadata",
    "FlickerFourierTerm",
    "ResampleFrameMetadata",
    "ScratchEventMetadata",
    "ToneMetadata",
    "VignetteMetadata",
    "WeaveFourierTerm",
]

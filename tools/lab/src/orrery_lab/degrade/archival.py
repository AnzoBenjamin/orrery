"""Deterministic archival-film capture profile in linear RGB."""

from __future__ import annotations

import math
from bisect import bisect_right

import numpy as np

from orrery_lab.degrade.archival_effects import (
    render_artifacts,
    sample_dust,
    sample_scratches,
    translate_bilinear_black,
    vignette_mask,
)
from orrery_lab.degrade.archival_types import (
    ArchivalDegradeConfig,
    ArchivalDegradeMetadata,
    ArchivalDegradeResult,
    ArchivalFrameMetadata,
    ArchivalRGBSequence,
    ArchivalTimingMetadata,
    FlickerFourierTerm,
    ResampleFrameMetadata,
    ToneMetadata,
    VignetteMetadata,
    WeaveFourierTerm,
)
from orrery_lab.degrade.types import validate_linear_rgb, validate_timestamps

_LUMA = (0.2126, 0.7152, 0.0722)
_SEPIA = (
    (0.393, 0.769, 0.189),
    (0.349, 0.686, 0.168),
    (0.272, 0.534, 0.131),
)
_UINT64_HIGH_EXCLUSIVE = 2**63
_DEFAULT_CONFIG = ArchivalDegradeConfig()


def degrade_archival(
    frames: ArchivalRGBSequence,
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    *,
    config: ArchivalDegradeConfig = _DEFAULT_CONFIG,
) -> ArchivalDegradeResult:
    """Resample and render a complete, replayable archival-film degradation profile."""
    validate_linear_rgb(frames, sequence=True)
    validate_timestamps(timestamps, frames.shape[0])
    selected_fps = int(rng.integers(config.fps_range[0], config.fps_range[1] + 1))
    output_timestamps = _output_timestamps(timestamps, selected_fps)
    resampled, records = _resample(frames, timestamps, output_timestamps)

    weave_terms = _sample_weave_terms(rng, config)
    flicker_terms = _sample_flicker_terms(rng, config)
    scratches = sample_scratches(output_timestamps, rng, config)
    dust = sample_dust(output_timestamps, rng, config)
    vignette_strength = float(rng.uniform(*config.vignette_strength))
    vignette_radius = float(rng.uniform(*config.vignette_radius_normalized))
    tone_mode = config.tone_modes[int(rng.integers(0, len(config.tone_modes)))]
    height, width = frames.shape[1:3]
    vignette = vignette_mask(height, width, vignette_strength, vignette_radius)

    output = np.empty_like(resampled, dtype=np.float32)
    frame_records: list[ArchivalFrameMetadata] = []
    for frame_index, timestamp in enumerate(output_timestamps):
        dx = sum(
            term.x_amplitude_px
            * math.sin(math.tau * term.frequency_hz * timestamp + term.x_phase_radians)
            for term in weave_terms
        )
        dy = sum(
            term.y_amplitude_px
            * math.sin(math.tau * term.frequency_hz * timestamp + term.y_phase_radians)
            for term in weave_terms
        )
        flicker_gain = 1.0 + sum(
            term.amplitude_fraction
            * math.sin(math.tau * term.frequency_hz * timestamp + term.phase_radians)
            for term in flicker_terms
        )
        working = translate_bilinear_black(resampled[frame_index], dx, dy)
        working *= flicker_gain

        grain_seed = int(rng.integers(0, _UINT64_HIGH_EXCLUSIVE))
        grain_rng = np.random.default_rng(grain_seed)
        luminance = np.sum(working * np.asarray(_LUMA), axis=2)
        grain_scale = config.grain_std * (
            config.grain_luminance_floor
            + (1.0 - config.grain_luminance_floor) * np.sqrt(np.maximum(luminance, 0.0))
        )
        grain = grain_rng.normal(0.0, 1.0, size=(height, width)) * grain_scale
        working += grain[..., np.newaxis]
        working, active_scratches, active_dust = render_artifacts(
            working, frame_index, timestamp, scratches, dust
        )
        working *= vignette[..., np.newaxis]
        working = _apply_tone(working, tone_mode)
        output[frame_index] = np.clip(working, 0.0, 1.0).astype(np.float32)
        frame_records.append(
            ArchivalFrameMetadata(
                frame_index,
                timestamp,
                (dx, dy),
                flicker_gain,
                grain_seed,
                active_scratches,
                active_dust,
            )
        )

    output_duration = output_timestamps[-1] - output_timestamps[0]
    timing = ArchivalTimingMetadata(
        timestamps,
        selected_fps,
        1.0 / selected_fps,
        output_timestamps,
        timestamps[-1] - timestamps[0],
        output_duration,
        records,
    )
    metadata = ArchivalDegradeMetadata(
        1,
        config,
        (width, height),
        "float32-linear-rgb",
        (
            "linear_timestamp_resample",
            "gate_weave_bilinear_translation",
            "multiplicative_flicker",
            "luminance_aware_film_grain",
            "scratch_and_dust_composite",
            "radial_vignette",
            "linear_light_tone",
            "output_clip",
        ),
        timing,
        "linear-between-neighboring-source-frames",
        weave_terms,
        flicker_terms,
        "bilinear-pixel-center",
        "constant-black",
        "shared-rgb-gaussian-scaled-by-sqrt-luminance",
        scratches,
        dust,
        VignetteMetadata(
            vignette_strength,
            vignette_radius,
            "center-to-farthest-corner",
            "smoothstep",
        ),
        ToneMetadata(tone_mode, "linear-rgb", _LUMA, _SEPIA),
        tuple(frame_records),
        "float32-linear-rgb",
        (0.0, 1.0),
    )
    return ArchivalDegradeResult(output, output_timestamps, metadata)


def _output_timestamps(timestamps: tuple[float, ...], fps: int) -> tuple[float, ...]:
    duration = timestamps[-1] - timestamps[0]
    count = math.floor(duration * fps + 1e-12) + 1
    return tuple(timestamps[0] + index / fps for index in range(count))


def _resample(
    frames: ArchivalRGBSequence,
    source_timestamps: tuple[float, ...],
    output_timestamps: tuple[float, ...],
) -> tuple[np.ndarray, tuple[ResampleFrameMetadata, ...]]:
    output = np.empty((len(output_timestamps), *frames.shape[1:]), dtype=np.float64)
    records: list[ResampleFrameMetadata] = []
    if len(source_timestamps) == 1:
        output[0] = frames[0]
        return output, (ResampleFrameMetadata(output_timestamps[0], 0, 0, 0.0),)
    for output_index, timestamp in enumerate(output_timestamps):
        right = min(max(bisect_right(source_timestamps, timestamp), 1), len(source_timestamps) - 1)
        left = right - 1
        span = source_timestamps[right] - source_timestamps[left]
        alpha = min(max((timestamp - source_timestamps[left]) / span, 0.0), 1.0)
        output[output_index] = frames[left].astype(np.float64) + alpha * (
            frames[right].astype(np.float64) - frames[left].astype(np.float64)
        )
        records.append(ResampleFrameMetadata(timestamp, left, right, alpha))
    return output, tuple(records)


def _sample_weave_terms(
    rng: np.random.Generator, config: ArchivalDegradeConfig
) -> tuple[WeaveFourierTerm, ...]:
    frequencies = rng.uniform(*config.weave_frequency_range_hz, size=config.weave_component_count)
    phases = rng.uniform(0.0, math.tau, size=(config.weave_component_count, 2))
    raw = rng.normal(size=(config.weave_component_count, 2)) / (
        1.0 + frequencies[:, np.newaxis] / config.weave_frequency_range_hz[0]
    )
    amplitudes = _normalize_components(raw, config.weave_amplitude_px)
    return tuple(
        WeaveFourierTerm(
            float(frequencies[index]),
            float(phases[index, 0]),
            float(phases[index, 1]),
            float(amplitudes[index, 0]),
            float(amplitudes[index, 1]),
        )
        for index in range(config.weave_component_count)
    )


def _sample_flicker_terms(
    rng: np.random.Generator, config: ArchivalDegradeConfig
) -> tuple[FlickerFourierTerm, ...]:
    frequencies = rng.uniform(
        *config.flicker_frequency_range_hz, size=config.flicker_component_count
    )
    phases = rng.uniform(0.0, math.tau, size=config.flicker_component_count)
    raw = rng.normal(size=config.flicker_component_count) / (
        1.0 + frequencies / config.flicker_frequency_range_hz[0]
    )
    total = float(np.sum(np.abs(raw)))
    amplitudes = (
        np.zeros_like(raw)
        if total == 0.0
        else raw * config.flicker_amplitude_fraction / total
    )
    return tuple(
        FlickerFourierTerm(float(frequency), float(phase), float(amplitude))
        for frequency, phase, amplitude in zip(frequencies, phases, amplitudes, strict=True)
    )


def _normalize_components(
    raw: np.ndarray, limits: tuple[float, float]
) -> np.ndarray:
    output = np.zeros_like(raw)
    for channel, limit in enumerate(limits):
        total = float(np.sum(np.abs(raw[:, channel])))
        if total != 0.0:
            output[:, channel] = raw[:, channel] * limit / total
    return output


def _apply_tone(image: np.ndarray, mode: str) -> np.ndarray:
    if mode == "monochrome":
        luminance = np.sum(image * np.asarray(_LUMA), axis=2)
        return np.repeat(luminance[..., np.newaxis], 3, axis=2)
    return image @ np.asarray(_SEPIA, dtype=np.float64).T


__all__ = ["degrade_archival"]

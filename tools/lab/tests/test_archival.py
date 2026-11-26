"""Archival-film profile degradation (requirement 4.3)."""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import numpy.typing as npt
import pytest
from orrery_lab.degrade import ArchivalDegradeConfig, degrade_archival


def _frames(
    duration: float = 2.0,
    source_fps: int = 30,
    *,
    height: int = 20,
    width: int = 24,
    value: float = 0.45,
) -> tuple[npt.NDArray[np.float32], tuple[float, ...]]:
    count = round(duration * source_fps) + 1
    timestamps = tuple(index / source_fps for index in range(count))
    pixels = np.full((count, height, width, 3), value, dtype=np.float32)
    return pixels, timestamps


def _isolated_config(**changes: object) -> ArchivalDegradeConfig:
    values: dict[str, object] = {
        "fps_range": (18, 18),
        "weave_amplitude_px": (0.0, 0.0),
        "flicker_amplitude_fraction": 0.0,
        "grain_std": 0.0,
        "scratch_rate_per_second": 0.0,
        "dust_rate_per_second": 0.0,
        "vignette_strength": (0.0, 0.0),
        "vignette_radius_normalized": (0.6, 0.6),
        "tone_modes": ("monochrome",),
    }
    values.update(changes)
    return ArchivalDegradeConfig(**values)  # type: ignore[arg-type] -- typed test builder


@pytest.mark.parametrize("fps", [12, 24])
def test_archival_fps_bounds_and_timestamp_resampling(fps: int) -> None:
    frames = np.empty((4, 4, 5, 3), dtype=np.float32)
    for index, value in enumerate((0.0, 0.2, 0.7, 1.0)):
        frames[index].fill(value)
    source_timestamps = (4.0, 4.11, 4.43, 5.0)
    result = degrade_archival(
        frames,
        source_timestamps,
        np.random.default_rng(2),
        config=_isolated_config(fps_range=(fps, fps)),
    )

    expected = tuple(4.0 + index / fps for index in range(fps + 1))
    assert result.timestamps == expected
    assert result.metadata.timing.source_timestamps_seconds == source_timestamps
    assert result.metadata.timing.output_timestamps_seconds == expected
    assert result.metadata.timing.selected_fps == fps
    assert result.metadata.timing.frame_period_seconds == pytest.approx(1.0 / fps)
    assert all(
        right > left
        for left, right in zip(result.timestamps, result.timestamps[1:], strict=False)
    )
    middle = result.metadata.timing.resample_frames[fps // 2]
    assert middle.source_left_index == 2
    assert middle.source_right_index == 3
    assert 0.0 < middle.interpolation_alpha < 1.0


def test_gate_weave_and_flicker_are_smooth_low_frequency_trajectories() -> None:
    frames, timestamps = _frames(duration=4.0)
    result = degrade_archival(frames, timestamps, np.random.default_rng(8))
    translations = np.asarray(
        [frame.gate_translation_px for frame in result.metadata.frames], dtype=np.float64
    )
    gains = np.asarray([frame.flicker_gain for frame in result.metadata.frames])

    assert all(0.0 < term.frequency_hz <= 1.0 for term in result.metadata.weave_terms)
    assert all(0.0 < term.frequency_hz <= 1.0 for term in result.metadata.flicker_terms)
    assert np.ptp(translations[:, 0]) > 0.05
    assert np.ptp(gains) > 0.005
    assert np.max(np.abs(np.diff(translations, n=2, axis=0))) < 0.05
    assert np.max(np.abs(np.diff(gains, n=2))) < 0.01
    assert result.metadata.translation_interpolation == "bilinear-pixel-center"
    assert result.metadata.translation_border == "constant-black"


def test_film_grain_is_luminance_aware_and_temporally_varying() -> None:
    frames, timestamps = _frames(duration=0.5, height=48, width=64)
    frames[:, :24].fill(0.1)
    frames[:, 24:].fill(0.7)
    result = degrade_archival(
        frames,
        timestamps,
        np.random.default_rng(91),
        config=_isolated_config(grain_std=0.035, grain_luminance_floor=0.1),
    )
    first = result.pixels[0, :, :, 0]

    dark_variance = float(np.var(first[:22] - 0.1))
    bright_variance = float(np.var(first[26:] - 0.7))
    assert dark_variance > 0.0
    assert bright_variance > dark_variance * 2.0
    assert not np.array_equal(result.pixels[0], result.pixels[1])
    assert len({frame.grain_seed for frame in result.metadata.frames}) == len(result.pixels)
    assert result.metadata.grain_model == "shared-rgb-gaussian-scaled-by-sqrt-luminance"


def test_scratches_and_dust_persist_and_are_rendered() -> None:
    frames, timestamps = _frames(duration=1.0, height=24, width=32)
    config = _isolated_config(
        fps_range=(24, 24),
        scratch_rate_per_second=8.0,
        scratch_lifetime_seconds=(0.3, 0.3),
        scratch_width_px=(1.5, 1.5),
        scratch_opacity=(0.5, 0.5),
        dust_rate_per_second=12.0,
        dust_lifetime_seconds=(0.25, 0.25),
        dust_radius_px=(2.0, 2.0),
        dust_opacity=(0.5, 0.5),
    )
    result = degrade_archival(frames, timestamps, np.random.default_rng(17), config=config)

    assert result.metadata.scratches
    assert result.metadata.dust
    assert all(event.end_frame_inclusive > event.start_frame for event in result.metadata.scratches)
    assert all(event.end_frame_inclusive > event.start_frame for event in result.metadata.dust)
    scratch_counts = {
        event.event_id: sum(
            event.event_id in frame.active_scratch_ids for frame in result.metadata.frames
        )
        for event in result.metadata.scratches
    }
    dust_counts = {
        event.event_id: sum(
            event.event_id in frame.active_dust_ids for frame in result.metadata.frames
        )
        for event in result.metadata.dust
    }
    assert min(scratch_counts.values()) >= 2
    assert min(dust_counts.values()) >= 2
    assert np.max(np.abs(result.pixels - 0.45)) > 0.1


def test_radial_vignette_darkens_edges_more_than_center() -> None:
    frames, timestamps = _frames(duration=0.0, source_fps=30, height=31, width=31, value=0.8)
    result = degrade_archival(
        frames,
        timestamps,
        np.random.default_rng(3),
        config=_isolated_config(
            vignette_strength=(0.5, 0.5),
            vignette_radius_normalized=(0.35, 0.35),
        ),
    )
    image = result.pixels[0, :, :, 0]

    assert image[15, 15] == pytest.approx(0.8)
    assert image[0, 0] < image[15, 15] * 0.6
    assert result.metadata.vignette.strength == 0.5
    assert result.metadata.vignette.falloff == "smoothstep"


def test_linear_light_sepia_and_monochrome_tones() -> None:
    frames, timestamps = _frames(duration=0.0, height=3, width=3, value=0.4)
    monochrome = degrade_archival(
        frames,
        timestamps,
        np.random.default_rng(4),
        config=_isolated_config(tone_modes=("monochrome",)),
    )
    sepia = degrade_archival(
        frames,
        timestamps,
        np.random.default_rng(4),
        config=_isolated_config(tone_modes=("sepia",)),
    )

    assert np.array_equal(monochrome.pixels[..., 0], monochrome.pixels[..., 1])
    assert np.array_equal(monochrome.pixels[..., 1], monochrome.pixels[..., 2])
    assert np.all(sepia.pixels[..., 0] > sepia.pixels[..., 1])
    assert np.all(sepia.pixels[..., 1] > sepia.pixels[..., 2])
    assert sepia.metadata.tone.working_space == "linear-rgb"
    assert sepia.metadata.tone.luminance_coefficients == (0.2126, 0.7152, 0.0722)
    assert len(sepia.metadata.tone.sepia_matrix) == 3


def test_archival_metadata_is_complete_and_json_serializable() -> None:
    frames, timestamps = _frames(duration=0.25)
    result = degrade_archival(frames, timestamps, np.random.default_rng(22))
    metadata = json.loads(json.dumps(asdict(result.metadata), sort_keys=True))

    assert metadata["schema_version"] == 1
    assert metadata["config"]["fps_range"] == [12, 24]
    assert metadata["timing"]["source_timestamps_seconds"] == list(timestamps)
    assert metadata["timing"]["output_timestamps_seconds"] == list(result.timestamps)
    assert metadata["resample_interpolation"] == "linear-between-neighboring-source-frames"
    assert metadata["weave_terms"][0]["x_amplitude_px"] is not None
    assert metadata["flicker_terms"][0]["amplitude_fraction"] is not None
    assert metadata["frames"][0]["grain_seed"] is not None
    assert metadata["scratches"][0]["width_px"] > 0.0
    assert metadata["scratches"][0]["sampled_lifetime_seconds"] > 0.0
    assert metadata["dust"][0]["radius_px"] > 0.0
    assert metadata["dust"][0]["sampled_lifetime_seconds"] > 0.0
    assert metadata["vignette"]["radius_normalized"] > 0.0
    assert metadata["tone"]["mode"] in ("sepia", "monochrome")
    assert metadata["operation_order"][-1] == "output_clip"
    assert metadata["output_dtype"] == "float32-linear-rgb"


@pytest.mark.parametrize(
    ("pixels", "timestamps", "message"),
    [
        (np.zeros((2, 3, 3), dtype=np.float32), (0.0, 1.0), "shape"),
        (np.zeros((2, 3, 3, 3), dtype=np.float64), (0.0, 1.0), "float32"),
        (np.full((2, 3, 3, 3), math.nan, dtype=np.float32), (0.0, 1.0), "finite"),
        (np.full((2, 3, 3, 3), 1.1, dtype=np.float32), (0.0, 1.0), "interval"),
        (np.zeros((2, 3, 3, 3), dtype=np.float32), (0.0, 0.0), "increasing"),
    ],
)
def test_invalid_archival_inputs_fail_clearly(
    pixels: npt.NDArray[np.float32], timestamps: tuple[float, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        degrade_archival(pixels, timestamps, np.random.default_rng(0))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"fps_range": (11, 20)}, "12-24"),
        ({"weave_frequency_range_hz": (0.1, 1.1)}, "low-frequency"),
        ({"scratch_opacity": (0.2, 1.1)}, "at most one"),
        ({"tone_modes": ()}, "non-empty"),
    ],
)
def test_invalid_archival_configuration_fails(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _isolated_config(**changes)


def test_archival_degradation_is_exactly_deterministic_for_equal_seeds() -> None:
    frames, timestamps = _frames(duration=1.0)
    first = degrade_archival(frames, timestamps, np.random.default_rng(1234))
    second = degrade_archival(frames, timestamps, np.random.default_rng(1234))

    assert first.timestamps == second.timestamps
    assert first.metadata == second.metadata
    assert first.pixels.dtype == np.float32
    assert np.all((first.pixels >= 0.0) & (first.pixels <= 1.0))
    assert np.array_equal(first.pixels, second.pixels)

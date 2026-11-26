"""Camera, temporal, and sensor degradation for synthetic capture (requirement 4.1)."""

import json
import math
from dataclasses import asdict

import numpy as np
import numpy.typing as npt
import pytest
from orrery_lab.degrade import (
    SensorDegradeConfig,
    TemporalDegradeConfig,
    degrade_camera,
    degrade_sensor,
    degrade_temporal,
)
from orrery_lab.render2d.camera import MAX_TILT, Camera


def _camera() -> Camera:
    return Camera(320, 240, (0.0, 0.0), 180.0, tilt_x=0.1, tilt_y=-0.08)


def test_camera_shake_is_smooth_and_strictly_band_limited() -> None:
    timestamps = tuple(float(value) for value in np.linspace(0.0, 2.0, 401))
    result = degrade_camera(_camera(), timestamps, np.random.default_rng(7))
    centers = np.array([camera.center_world for camera in result.cameras])
    velocity = np.diff(centers, axis=0) / (timestamps[1] - timestamps[0])

    assert all(0.5 <= term.frequency_hz <= 8.0 for term in result.metadata.terms)
    assert np.max(np.linalg.norm(np.diff(velocity, axis=0), axis=1)) < 0.02
    assert np.ptp(centers[:, 0]) > 0.0
    assert result.cameras[1].center_world != result.cameras[2].center_world


def test_camera_shake_preserves_legal_tilt_and_focus_breathes() -> None:
    camera = Camera(320, 240, (0.0, 0.0), 180.0, tilt_x=MAX_TILT, tilt_y=-MAX_TILT)
    timestamps = tuple(float(value) for value in np.linspace(0.0, 1.0, 80))
    result = degrade_camera(camera, timestamps, np.random.default_rng(2))
    focals = np.array([sample.focal_px for sample in result.metadata.samples])

    assert all(abs(changed.tilt_x) <= MAX_TILT for changed in result.cameras)
    assert all(abs(changed.tilt_y) <= MAX_TILT for changed in result.cameras)
    assert np.ptp(focals) > 0.1
    assert np.all(focals > 0.0)


def test_temporal_static_supersamples_are_exactly_unchanged() -> None:
    still = np.random.default_rng(3).random((8, 12, 16, 3), dtype=np.float32)
    still[:] = still[0]
    result = degrade_temporal(
        still,
        tuple(float(value) for value in np.linspace(-0.1, 0.1, len(still))),
        0.0,
        config=TemporalDegradeConfig(
            shutter_seconds=0.08,
            rolling_shutter_seconds=0.06,
            integration_samples=8,
        ),
    )

    assert np.array_equal(result.pixels, still[0])
    assert result.pixels.dtype == np.float32


def test_motion_blur_integrates_a_moving_edge() -> None:
    timestamps = tuple(float(value) for value in np.linspace(-0.5, 0.5, 21))
    frames = np.zeros((len(timestamps), 5, 32, 3), dtype=np.float32)
    for index, timestamp in enumerate(timestamps):
        edge = round(16 + 12 * timestamp)
        frames[index, :, edge:] = 1.0

    sharp = degrade_temporal(
        frames,
        timestamps,
        0.0,
        config=TemporalDegradeConfig(shutter_seconds=0.0),
    ).pixels
    blurred = degrade_temporal(
        frames,
        timestamps,
        0.0,
        config=TemporalDegradeConfig(shutter_seconds=0.5, integration_samples=16),
    ).pixels

    assert set(np.unique(sharp)) <= {0.0, 1.0}
    assert np.any((blurred > 0.0) & (blurred < 1.0))
    assert blurred[:, :, 0].mean() == pytest.approx(sharp[:, :, 0].mean(), abs=0.03)


def test_rolling_shutter_uses_row_specific_exposure_times() -> None:
    timestamps = (-1.0, 0.0, 1.0)
    frames = np.empty((3, 8, 4, 3), dtype=np.float32)
    frames[0].fill(0.0)
    frames[1].fill(0.5)
    frames[2].fill(1.0)
    result = degrade_temporal(
        frames,
        timestamps,
        0.0,
        config=TemporalDegradeConfig(shutter_seconds=0.0, rolling_shutter_seconds=1.0),
    )

    row_means = result.pixels.mean(axis=(1, 2))
    assert np.all(np.diff(row_means) > 0.0)
    assert result.metadata.row_exposure_centers_seconds[0] < 0.0
    assert result.metadata.row_exposure_centers_seconds[-1] > 0.0


def test_exposure_drift_is_low_frequency_and_smooth() -> None:
    timestamps = tuple(float(value) for value in np.linspace(0.0, 8.0, 81))
    frames = np.full((len(timestamps), 2, 2, 3), 0.35, dtype=np.float32)
    config = SensorDegradeConfig(
        drift_amplitude_stops=0.3,
        full_well_electrons=1e9,
        read_noise_std=0.0,
    )
    result = degrade_sensor(frames, timestamps, np.random.default_rng(9), config=config)
    gains = np.array([frame.applied_gain for frame in result.metadata.frames])

    assert all(0.0 < term.frequency_hz <= 0.5 for term in result.metadata.exposure_terms)
    assert np.ptp(gains) > 0.01
    assert np.max(np.abs(np.diff(gains))) < 0.15


def test_poisson_gaussian_noise_has_expected_mean_and_nonzero_variance() -> None:
    frames = np.full((1, 256, 256, 3), 0.25, dtype=np.float32)
    result = degrade_sensor(
        frames,
        (0.0,),
        np.random.default_rng(123),
        config=SensorDegradeConfig(
            target_luminance=0.25,
            drift_amplitude_stops=0.0,
            full_well_electrons=2000.0,
            read_noise_std=0.004,
        ),
    )

    assert float(result.pixels.mean()) == pytest.approx(0.25, abs=0.001)
    assert float(result.pixels.var()) > 0.0001
    assert result.pixels.dtype == np.float32
    assert np.all((result.pixels >= 0.0) & (result.pixels <= 1.0))


def test_all_degradation_metadata_is_json_serializable_and_complete() -> None:
    camera = degrade_camera(_camera(), (0.0, 0.1), np.random.default_rng(1))
    supersamples = np.full((3, 2, 3, 3), 0.2, dtype=np.float32)
    temporal = degrade_temporal(supersamples, (-0.1, 0.0, 0.1), 0.0)
    sensor = degrade_sensor(
        temporal.pixels[np.newaxis],
        (0.0,),
        np.random.default_rng(1),
    )

    encoded = json.dumps(
        {
            "camera": asdict(camera.metadata),
            "temporal": asdict(temporal.metadata),
            "sensor": asdict(sensor.metadata),
        },
        sort_keys=True,
    )
    assert "frequency_hz" in encoded
    assert "row_exposure_centers_seconds" in encoded
    assert "full_well_electrons" in encoded
    assert "float32-linear-rgb" in encoded


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
def test_invalid_linear_inputs_fail_clearly(
    pixels: npt.NDArray[np.float32], timestamps: tuple[float, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        degrade_sensor(pixels, timestamps, np.random.default_rng(0))


def test_temporal_requires_real_supersample_coverage() -> None:
    frames = np.zeros((2, 3, 4, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="cover"):
        degrade_temporal(
            frames,
            (0.0, 0.01),
            0.0,
            config=TemporalDegradeConfig(shutter_seconds=0.1),
        )


def test_degradation_is_exactly_deterministic_for_equal_seeds() -> None:
    timestamps = (0.0, 0.1, 0.2)
    first_camera = degrade_camera(_camera(), timestamps, np.random.default_rng(44))
    second_camera = degrade_camera(_camera(), timestamps, np.random.default_rng(44))
    frames = np.full((3, 24, 20, 3), 0.3, dtype=np.float32)
    first_sensor = degrade_sensor(frames, timestamps, np.random.default_rng(55))
    second_sensor = degrade_sensor(frames, timestamps, np.random.default_rng(55))

    assert first_camera == second_camera
    assert first_sensor.metadata == second_sensor.metadata
    assert np.array_equal(first_sensor.pixels, second_sensor.pixels)

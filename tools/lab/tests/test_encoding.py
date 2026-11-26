"""Real FFmpeg encoding, VFR, and dropped-frame degradation (requirement 4.3)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from orrery_lab.degrade import (
    EncodingConfig,
    EncodingError,
    FFmpegAdapter,
    encode_video,
    select_codec_profile,
)

_CODEC_NAMES = {"h264": "h264", "h265": "hevc", "vp9": "vp9"}


def _frames(count: int = 6) -> np.ndarray:
    height, width = 16, 24
    y, x = np.indices((height, width))
    frames = np.empty((count, height, width, 3), dtype=np.uint8)
    for index in range(count):
        frames[index, :, :, 0] = (x * 9 + index * 19) % 256
        frames[index, :, :, 1] = (y * 13 + index * 11) % 256
        frames[index, :, :, 2] = ((x + y) * 7 + index * 23) % 256
    return frames


def _config(codec: str, **changes: object) -> EncodingConfig:
    values: dict[str, object] = {
        "codecs": (codec,),
        "pixel_formats": ("yuv420p",),
        "variable_frame_rate": False,
        "drop_probability": 0.0,
    }
    values.update(changes)
    return EncodingConfig(**values)  # type: ignore[arg-type] -- test helper builds typed fields


def _decode(encoded: bytes, extension: str, width: int, height: int) -> np.ndarray:
    with tempfile.TemporaryDirectory(prefix="orrery encoding decode ") as directory_name:
        path = Path(directory_name) / f"clip with spaces{extension}"
        path.write_bytes(encoded)
        completed = subprocess.run(
            (
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-fps_mode",
                "passthrough",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ),
            check=True,
            capture_output=True,
        )
    frame_size = width * height * 3
    assert len(completed.stdout) % frame_size == 0
    return np.frombuffer(completed.stdout, dtype=np.uint8).reshape((-1, height, width, 3))


@pytest.mark.parametrize("codec", ["h264", "h265", "vp9"])
def test_all_codecs_are_real_and_decode_at_source_dimensions(codec: str) -> None:
    frames = _frames()
    timestamps = (0.0, 0.04, 0.08, 0.12, 0.16, 0.2)
    result = encode_video(
        frames,
        timestamps,
        np.random.default_rng(10),
        config=_config(codec),
    )

    assert result.metadata.codec.codec == codec
    assert result.metadata.codec.crf_selection_range[0] <= result.metadata.codec.crf
    assert result.metadata.codec.crf <= result.metadata.codec.crf_selection_range[1]
    assert result.metadata.probe.codec_name == _CODEC_NAMES[codec]
    assert result.metadata.probe.frame_count == len(frames)
    assert (result.metadata.probe.width, result.metadata.probe.height) == (24, 16)
    decoded = _decode(
        result.encoded_bytes,
        result.metadata.codec.file_extension,
        result.metadata.probe.width,
        result.metadata.probe.height,
    )
    assert decoded.shape == frames.shape
    assert np.ptp(decoded.mean(axis=(1, 2, 3))) > 1.0


@pytest.mark.parametrize("codec", ["h264", "h265", "vp9"])
def test_seeded_profile_and_encoded_output_are_deterministic(codec: str) -> None:
    profile_config = _config(codec)
    first_profile = select_codec_profile(24, 16, np.random.default_rng(122), config=profile_config)
    second_profile = select_codec_profile(24, 16, np.random.default_rng(122), config=profile_config)
    assert first_profile == second_profile

    config = _config(
        codec,
        variable_frame_rate=True,
        vfr_jitter_fraction=0.18,
        drop_probability=0.25,
    )
    timestamps = tuple(index * 0.04 for index in range(7))
    first = encode_video(_frames(7), timestamps, np.random.default_rng(51), config=config)
    second = encode_video(_frames(7), timestamps, np.random.default_rng(51), config=config)

    assert first.metadata == second.metadata
    assert first.encoded_bytes == second.encoded_bytes


def test_existing_vfr_timestamps_are_preserved_exactly() -> None:
    timestamps = (12.5, 12.54, 12.605, 12.641, 12.73)
    result = encode_video(
        _frames(5),
        timestamps,
        np.random.default_rng(3),
        config=_config("h264"),
    )

    assert result.metadata.timing.source_clock_origin_seconds == 12.5
    assert result.metadata.timing.source_timestamps_seconds == timestamps
    assert result.metadata.timing.encoded_timestamps_ticks == (0, 40, 105, 141, 230)
    assert result.metadata.probe.timestamp_ticks == (0, 40, 105, 141, 230)
    assert result.metadata.timing.variable_frame_rate_output


def test_vfr_jitter_and_dropped_frames_keep_timeline_gaps() -> None:
    timestamps = tuple(index * 0.04 for index in range(8))
    result = encode_video(
        _frames(8),
        timestamps,
        np.random.default_rng(8),
        config=_config(
            "vp9",
            variable_frame_rate=True,
            vfr_jitter_fraction=0.2,
            drop_probability=1.0,
        ),
    )
    timing = result.metadata.timing

    assert timing.vfr_jitter_enabled
    assert timing.kept_source_indices == (0, 7)
    assert timing.dropped_source_indices == (1, 2, 3, 4, 5, 6)
    assert timing.protected_endpoint_indices == (0, 7)
    assert timing.encoded_timestamps_ticks == (0, timing.full_timeline_ticks[-1])
    assert timing.encoded_timestamps_ticks[-1] > 7
    assert result.metadata.probe.timestamp_ticks == timing.encoded_timestamps_ticks
    assert result.metadata.probe.frame_count == 2
    assert _decode(result.encoded_bytes, ".webm", 24, 16).shape[0] == 2


def test_metadata_is_typed_json_serializable_and_complete() -> None:
    result = encode_video(
        _frames(3),
        (0.0, 0.033, 0.071),
        np.random.default_rng(91),
        config=_config("h265"),
    )
    metadata = json.loads(json.dumps(asdict(result.metadata), sort_keys=True))

    assert metadata["schema_version"] == 1
    assert metadata["input_dtype"] == "uint8-rgb"
    assert metadata["codec"]["encoder"] == "libx265"
    assert metadata["codec"]["thread_count"] == 1
    assert metadata["timing"]["time_base"] == "1/1000"
    assert metadata["timing"]["source_timestamps_seconds"] == [0.0, 0.033, 0.071]
    assert metadata["probe"]["timestamp_ticks"] == [0, 33, 71]
    assert metadata["ffmpeg_version"].startswith("ffmpeg version")
    assert metadata["ffprobe_version"].startswith("ffprobe version")


@pytest.mark.parametrize(
    ("frames", "timestamps", "message"),
    [
        (np.zeros((2, 4, 3), dtype=np.uint8), (0.0, 0.04), "shape"),
        (np.zeros((2, 4, 4, 3), dtype=np.float32), (0.0, 0.04), "uint8"),
        (np.zeros((2, 4, 4, 3), dtype=np.uint8), (0.0,), "count"),
        (np.zeros((2, 4, 4, 3), dtype=np.uint8), (0.0, 0.0), "increasing"),
        (np.zeros((2, 4, 4, 3), dtype=np.uint8), (0.0, 0.0004), "at least"),
    ],
)
def test_invalid_inputs_fail_before_ffmpeg(
    frames: np.ndarray, timestamps: tuple[float, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        encode_video(frames, timestamps, np.random.default_rng(0), config=_config("h264"))


@pytest.mark.parametrize(
    "config",
    [
        EncodingConfig(codecs=("h264",), variable_frame_rate_probability=0.0),
        EncodingConfig(codecs=("vp9",), variable_frame_rate_probability=1.0),
    ],
)
def test_optional_vfr_selection_is_seeded(config: EncodingConfig) -> None:
    first = encode_video(_frames(3), (0.0, 0.04, 0.08), np.random.default_rng(4), config=config)
    second = encode_video(_frames(3), (0.0, 0.04, 0.08), np.random.default_rng(4), config=config)
    assert first.metadata.timing == second.metadata.timing
    assert first.metadata.timing.vfr_jitter_enabled == bool(config.variable_frame_rate_probability)


def test_adapter_uses_argv_and_supports_executable_paths_with_spaces(tmp_path: Path) -> None:
    tool_directory = tmp_path / "tools with spaces"
    tool_directory.mkdir()
    ffmpeg_link = tool_directory / "ffmpeg safe"
    ffprobe_link = tool_directory / "ffprobe safe"
    ffmpeg_link.symlink_to(Path(shutil.which("ffmpeg") or "ffmpeg"))
    ffprobe_link.symlink_to(Path(shutil.which("ffprobe") or "ffprobe"))
    adapter = FFmpegAdapter(str(ffmpeg_link), str(ffprobe_link))

    result = encode_video(
        _frames(2),
        (0.0, 0.04),
        np.random.default_rng(2),
        config=_config("h264"),
        adapter=adapter,
    )
    assert result.metadata.probe.frame_count == 2

    marker = tmp_path / "must-not-exist"
    malicious = FFmpegAdapter(f"ffmpeg;touch {marker}", str(ffprobe_link))
    with pytest.raises(EncodingError, match="not found"):
        encode_video(
            _frames(2),
            (0.0, 0.04),
            np.random.default_rng(2),
            config=_config("h264"),
            adapter=malicious,
        )
    assert not marker.exists()

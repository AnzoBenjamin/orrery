"""Public deterministic encoding degradation pipeline."""

from __future__ import annotations

import numpy as np

from orrery_lab.degrade.encoding_profile import select_codec_profile, select_timing
from orrery_lab.degrade.encoding_types import (
    EncodingConfig,
    EncodingError,
    EncodingMetadata,
    EncodingResult,
    RGB8Sequence,
)
from orrery_lab.degrade.ffmpeg import FFmpegAdapter

_DEFAULT_ADAPTER = FFmpegAdapter()
_DEFAULT_CONFIG = EncodingConfig()
_SEQUENCE_DIMENSIONS = 4
_RGB_CHANNELS = 3


def encode_video(
    frames: RGB8Sequence,
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    *,
    config: EncodingConfig = _DEFAULT_CONFIG,
    adapter: FFmpegAdapter = _DEFAULT_ADAPTER,
) -> EncodingResult:
    """Encode validated uint8 RGB through a seeded lossy codec and verified VFR timeline."""
    _validate_rgb8(frames)
    profile = select_codec_profile(frames.shape[2], frames.shape[1], rng, config=config)
    timing = select_timing(timestamps, rng, config=config)
    if len(timestamps) != frames.shape[0]:
        raise ValueError("timestamp count must equal frame count")
    output = adapter.encode(frames, profile, timing)
    probe = output.probe
    expected_dimensions = (frames.shape[2], frames.shape[1])
    if probe.codec_name != profile.probed_codec_name:
        raise EncodingError(
            f"encoded codec {probe.codec_name!r} does not match {profile.probed_codec_name!r}"
        )
    if (probe.width, probe.height) != expected_dimensions:
        raise EncodingError("encoded dimensions do not match input dimensions")
    if probe.frame_count != len(timing.kept_source_indices):
        raise EncodingError("encoded frame count does not match kept-frame metadata")
    if probe.timestamp_ticks != timing.encoded_timestamps_ticks:
        raise EncodingError(
            f"encoded timestamps {probe.timestamp_ticks!r} do not match requested "
            f"timestamps {timing.encoded_timestamps_ticks!r}"
        )
    metadata = EncodingMetadata(
        1,
        expected_dimensions,
        "uint8-rgb",
        "ffmpeg-rgb-to-yuv",
        profile,
        timing,
        probe,
        output.ffmpeg_version,
        output.ffprobe_version,
    )
    return EncodingResult(output.encoded_bytes, metadata)


def _validate_rgb8(frames: RGB8Sequence) -> None:
    if frames.ndim != _SEQUENCE_DIMENSIONS or frames.shape[-1] != _RGB_CHANNELS:
        raise ValueError("uint8 RGB must have shape (frames, height, width, 3)")
    if any(dimension <= 0 for dimension in frames.shape):
        raise ValueError("uint8 RGB dimensions must be positive")
    if frames.dtype != np.uint8:
        raise ValueError("encoding RGB must be uint8")


__all__ = ["encode_video"]

"""Seeded codec/profile and presentation-timeline selection."""

from __future__ import annotations

from itertools import pairwise
from typing import cast

import numpy as np

from orrery_lab.degrade.encoding_types import (
    TIMESCALE,
    CodecName,
    CodecProfile,
    ContainerName,
    EncodingConfig,
    EncodingTimingMetadata,
    PixelFormat,
)
from orrery_lab.degrade.types import validate_timestamps

_ENCODERS: dict[CodecName, tuple[str, str, str, str]] = {
    "h264": ("libx264", "h264", "mp4", ".mp4"),
    "h265": ("libx265", "hevc", "mp4", ".mp4"),
    "vp9": ("libvpx-vp9", "vp9", "webm", ".webm"),
}


_DEFAULT_CONFIG = EncodingConfig()


def select_codec_profile(
    width: int,
    height: int,
    rng: np.random.Generator,
    *,
    config: EncodingConfig = _DEFAULT_CONFIG,
) -> CodecProfile:
    """Select all codec parameters once; the returned profile is replayable metadata."""
    if width <= 0 or height <= 0:
        raise ValueError("encoding dimensions must be positive")
    codec = config.codecs[int(rng.integers(0, len(config.codecs)))]
    crf_range = _crf_range(codec, config)
    crf = int(rng.integers(crf_range[0], crf_range[1] + 1))
    gop_size = int(rng.integers(config.gop_range[0], config.gop_range[1] + 1))
    compatible_formats: tuple[PixelFormat, ...] = tuple(
        pixel_format
        for pixel_format in config.pixel_formats
        if pixel_format == "yuv444p" or (width % 2 == 0 and height % 2 == 0)
    )
    if not compatible_formats:
        raise ValueError("odd encoding dimensions require yuv444p in pixel_formats")
    pixel_format = compatible_formats[int(rng.integers(0, len(compatible_formats)))]
    encoder, probed_name, container, extension = _ENCODERS[codec]
    encoder_options = _encoder_options(codec, gop_size, config.thread_count)
    muxer_options = (
        ("-movflags", "+faststart+disable_chpl", "-video_track_timescale", str(TIMESCALE))
        if container == "mp4"
        else ("-cluster_time_limit", "-1", "-cluster_size_limit", "-1")
    )
    return CodecProfile(
        codec,
        encoder,
        probed_name,
        cast(ContainerName, container),
        extension,
        crf,
        crf_range,
        gop_size,
        config.thread_count,
        pixel_format,
        encoder_options,
        muxer_options,
    )


def select_timing(
    timestamps: tuple[float, ...],
    rng: np.random.Generator,
    *,
    config: EncodingConfig = _DEFAULT_CONFIG,
) -> EncodingTimingMetadata:
    """Build a millisecond presentation timeline and select dropped source frames."""
    validate_timestamps(timestamps, len(timestamps))
    origin = timestamps[0]
    source_ticks = tuple(round((timestamp - origin) * TIMESCALE) for timestamp in timestamps)
    if any(right <= left for left, right in pairwise(source_ticks)):
        raise ValueError(f"timestamps must be at least {1 / TIMESCALE:g} seconds apart")

    jitter_enabled = (
        config.variable_frame_rate
        if config.variable_frame_rate is not None
        else bool(rng.random() < config.variable_frame_rate_probability)
    )
    if jitter_enabled:
        scales = tuple(
            float(value)
            for value in rng.uniform(
                1.0 - config.vfr_jitter_fraction,
                1.0 + config.vfr_jitter_fraction,
                size=max(0, len(timestamps) - 1),
            )
        )
        timeline = [0]
        for (left, right), scale in zip(pairwise(source_ticks), scales, strict=True):
            timeline.append(timeline[-1] + max(1, round((right - left) * scale)))
    else:
        scales = tuple(1.0 for _ in range(max(0, len(timestamps) - 1)))
        timeline = list(source_ticks)

    protected = (0,) if len(timestamps) == 1 else (0, len(timestamps) - 1)
    kept: list[int] = []
    dropped: list[int] = []
    for index in range(len(timestamps)):
        should_drop = index not in protected and rng.random() < config.drop_probability
        (dropped if should_drop else kept).append(index)
    encoded_ticks = tuple(timeline[index] for index in kept)
    intervals = tuple(right - left for left, right in pairwise(encoded_ticks))
    variable_output = len(set(intervals)) > 1
    return EncodingTimingMetadata(
        origin,
        timestamps,
        f"1/{TIMESCALE}",
        TIMESCALE,
        jitter_enabled,
        config.vfr_jitter_fraction if jitter_enabled else 0.0,
        scales,
        tuple(timeline),
        config.drop_probability,
        protected,
        tuple(kept),
        tuple(dropped),
        encoded_ticks,
        tuple(tick / TIMESCALE for tick in encoded_ticks),
        variable_output,
    )


def _crf_range(codec: CodecName, config: EncodingConfig) -> tuple[int, int]:
    if codec == "h264":
        return config.h264_crf_range
    if codec == "h265":
        return config.h265_crf_range
    return config.vp9_crf_range


def _encoder_options(codec: CodecName, gop_size: int, threads: int) -> tuple[str, ...]:
    common = ("-threads", str(threads), "-g", str(gop_size), "-bf", "0")
    if codec == "h264":
        return (
            *common,
            "-preset",
            "medium",
            "-x264-params",
            f"keyint={gop_size}:min-keyint={gop_size}:scenecut=0:threads={threads}",
        )
    if codec == "h265":
        return (
            *common,
            "-preset",
            "medium",
            "-x265-params",
            f"pools=none:frame-threads={threads}:wpp=0:keyint={gop_size}:min-keyint={gop_size}:scenecut=0",
            "-tag:v",
            "hvc1",
        )
    return (*common, "-deadline", "good", "-cpu-used", "4", "-row-mt", "0", "-b:v", "0")


__all__ = ["select_codec_profile", "select_timing"]

"""Frozen public types for deterministic video encoding degradation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

type CodecName = Literal["h264", "h265", "vp9"]
type ContainerName = Literal["mp4", "webm"]
type PixelFormat = Literal["yuv420p", "yuv444p"]
type RGB8Sequence = npt.NDArray[np.uint8]
TIMESCALE = 1000


@dataclass(frozen=True)
class EncodingConfig:
    """Bounds for seeded profile selection and temporal encoding degradation.

    Input timestamps are always retained as the source clock in metadata. With VFR jitter
    enabled, source intervals are scaled on the output timeline. Dropped frames retain their
    timeline positions, so the resulting gap is never collapsed to constant frame rate.
    """

    codecs: tuple[CodecName, ...] = ("h264", "h265", "vp9")
    h264_crf_range: tuple[int, int] = (18, 32)
    h265_crf_range: tuple[int, int] = (20, 34)
    vp9_crf_range: tuple[int, int] = (20, 40)
    gop_range: tuple[int, int] = (12, 60)
    thread_count: int = 1
    pixel_formats: tuple[PixelFormat, ...] = ("yuv420p", "yuv444p")
    variable_frame_rate: bool | None = None
    variable_frame_rate_probability: float = 0.5
    vfr_jitter_fraction: float = 0.12
    drop_probability: float = 0.05

    def __post_init__(self) -> None:
        if not self.codecs or len(set(self.codecs)) != len(self.codecs):
            raise ValueError("codecs must be non-empty and unique")
        if any(codec not in ("h264", "h265", "vp9") for codec in self.codecs):
            raise ValueError("unsupported codec in encoding configuration")
        for name, bounds, limit in (
            ("H.264 CRF", self.h264_crf_range, 51),
            ("H.265 CRF", self.h265_crf_range, 51),
            ("VP9 CRF", self.vp9_crf_range, 63),
        ):
            if bounds[0] < 0 or bounds[1] < bounds[0] or bounds[1] > limit:
                raise ValueError(f"{name} range is invalid")
        if self.gop_range[0] <= 0 or self.gop_range[1] < self.gop_range[0]:
            raise ValueError("GOP range is invalid")
        if self.thread_count <= 0:
            raise ValueError("thread count must be positive")
        if not self.pixel_formats or len(set(self.pixel_formats)) != len(self.pixel_formats):
            raise ValueError("pixel formats must be non-empty and unique")
        if any(pixel_format not in ("yuv420p", "yuv444p") for pixel_format in self.pixel_formats):
            raise ValueError("unsupported encoding pixel format")
        probabilities = (self.variable_frame_rate_probability, self.drop_probability)
        if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("encoding probabilities must be finite values in [0, 1]")
        if not math.isfinite(self.vfr_jitter_fraction) or not 0.0 <= self.vfr_jitter_fraction < 1.0:
            raise ValueError("VFR jitter fraction must be finite and in [0, 1)")


@dataclass(frozen=True)
class CodecProfile:
    codec: CodecName
    encoder: str
    probed_codec_name: str
    container: ContainerName
    file_extension: str
    crf: int
    crf_selection_range: tuple[int, int]
    gop_size: int
    thread_count: int
    pixel_format: PixelFormat
    encoder_options: tuple[str, ...]
    muxer_options: tuple[str, ...]


@dataclass(frozen=True)
class EncodingTimingMetadata:
    source_clock_origin_seconds: float
    source_timestamps_seconds: tuple[float, ...]
    time_base: str
    timescale_ticks_per_second: int
    vfr_jitter_enabled: bool
    requested_jitter_fraction: float
    interval_scale_factors: tuple[float, ...]
    full_timeline_ticks: tuple[int, ...]
    drop_probability: float
    protected_endpoint_indices: tuple[int, ...]
    kept_source_indices: tuple[int, ...]
    dropped_source_indices: tuple[int, ...]
    encoded_timestamps_ticks: tuple[int, ...]
    encoded_timestamps_seconds: tuple[float, ...]
    variable_frame_rate_output: bool


@dataclass(frozen=True)
class ProbeMetadata:
    codec_name: str
    width: int
    height: int
    frame_count: int
    stream_time_base: str
    native_pts: tuple[int, ...]
    timestamp_ticks: tuple[int, ...]
    timestamps_seconds: tuple[float, ...]


@dataclass(frozen=True)
class EncodingMetadata:
    schema_version: Literal[1]
    dimensions: tuple[int, int]
    input_dtype: Literal["uint8-rgb"]
    color_conversion: Literal["ffmpeg-rgb-to-yuv"]
    codec: CodecProfile
    timing: EncodingTimingMetadata
    probe: ProbeMetadata
    ffmpeg_version: str
    ffprobe_version: str


@dataclass(frozen=True)
class EncodingResult:
    encoded_bytes: bytes
    metadata: EncodingMetadata


class EncodingError(RuntimeError):
    """A real FFmpeg invocation or verification failed."""


__all__ = [
    "TIMESCALE",
    "CodecName",
    "CodecProfile",
    "ContainerName",
    "EncodingConfig",
    "EncodingError",
    "EncodingMetadata",
    "EncodingResult",
    "EncodingTimingMetadata",
    "PixelFormat",
    "ProbeMetadata",
    "RGB8Sequence",
]

"""Real video ingestion for reconstruction jobs.

PyAV performs both decoding and encoding. The normalized frame cache is lossless FFV1, while the
browser artifacts are H.264 and WebP. Original display timestamps remain in the manifest.
"""

from __future__ import annotations

import base64
import bisect
import hashlib
import itertools
import math
import statistics
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, cast

import av
from av.container import OutputContainer
from av.error import FFmpegError
from av.filter import Graph
from av.video.stream import VideoStream

from orrery_engine.probe import SUPPORTED_CODECS, SUPPORTED_CONTAINERS

CancelCheck = Callable[[], None]


class IngestError(RuntimeError):
    """Input media could not be decoded into a usable video."""


@dataclass(frozen=True)
class IngestConfig:
    analysis_long_side: int = 960
    proxy_long_side: int = 720
    thumbnail_count: int = 5


@dataclass(frozen=True)
class SourceInfo:
    timestamps: tuple[float, ...]
    width: int
    height: int
    rate: Fraction
    rotation: Literal[0, 1, 2, 3]
    codec: str
    container: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class NormalizedSample:
    frame_index: int
    timestamp_seconds: float
    source_frame_index: int
    original_timestamp_seconds: float


@dataclass(frozen=True)
class IngestResult:
    manifest: dict[str, object]
    source_path: Path
    analysis_path: Path
    proxy_path: Path


def ingest_footage(
    source_path: Path,
    output_dir: Path,
    *,
    footage_id: str,
    source_sha256: str,
    config: IngestConfig,
    check_canceled: CancelCheck,
) -> IngestResult:
    """Decode, orient, normalize, resize, and encode one footage item."""
    output_dir.mkdir(parents=True, exist_ok=True)
    info = inspect_source(source_path, check_canceled)
    samples = _normalized_samples(info.timestamps)
    display_width, display_height = _display_size(info)
    analysis_size = _fit(display_width, display_height, config.analysis_long_side)
    proxy_size = _fit(display_width, display_height, config.proxy_long_side)
    analysis_path = output_dir / "analysis.mkv"
    proxy_path = output_dir / "proxy.mp4"
    thumbnail_indices = _thumbnail_indices(len(samples), config.thumbnail_count)
    thumbnail_paths = _encode_copies(
        source_path,
        info,
        samples,
        analysis_path,
        proxy_path,
        analysis_size,
        proxy_size,
        thumbnail_indices,
        output_dir,
        check_canceled,
    )
    intrinsics = _intrinsics(info.metadata, display_width, display_height)
    manifest: dict[str, object] = {
        "footageId": footage_id,
        "sourceSha256": source_sha256,
        "container": info.container,
        "codec": info.codec,
        "width": info.width,
        "height": info.height,
        "displayWidth": display_width,
        "displayHeight": display_height,
        "rotationQuarterTurns": info.rotation,
        "colorSpace": "bt709-rgb",
        "originalTimestampsSeconds": list(info.timestamps),
        "normalizedFrames": [
            {
                "frameIndex": item.frame_index,
                "timestampSeconds": item.timestamp_seconds,
                "sourceFrameIndex": item.source_frame_index,
                "originalTimestampSeconds": item.original_timestamp_seconds,
            }
            for item in samples
        ],
        "analysisCopy": _embedded(analysis_path, "video/x-matroska"),
        "proxyVideo": _embedded(proxy_path, "video/mp4"),
        "thumbnails": [
            {
                "frameIndex": index,
                "timestampSeconds": samples[index].timestamp_seconds,
                "image": _embedded(path, "image/webp"),
            }
            for index, path in thumbnail_paths.items()
        ],
    }
    if intrinsics is not None:
        manifest["intrinsics"] = intrinsics
    return IngestResult(manifest, source_path, analysis_path, proxy_path)


def inspect_source(path: Path, check_canceled: CancelCheck) -> SourceInfo:
    """Read stream metadata and exact decoded display timestamps."""
    try:
        container = av.open(str(path))
    except FFmpegError as error:
        raise IngestError("The footage is not a readable video.") from error
    with container:
        families = set(container.format.name.split(","))
        if not families & SUPPORTED_CONTAINERS or not container.streams.video:
            raise IngestError("The footage container is not supported.")
        stream = container.streams.video[0]
        codec = str(stream.codec_context.name)
        if codec not in SUPPORTED_CODECS:
            raise IngestError(f"The {codec} video codec is not supported.")
        timestamps: list[float] = []
        rotation = 0
        fallback_rate = stream.average_rate or stream.guessed_rate or Fraction(30, 1)
        for index, frame in enumerate(container.decode(stream)):
            check_canceled()
            if index == 0:
                rotation = round(float(getattr(frame, "rotation", 0) or 0))
            timestamp = (
                float(frame.pts * frame.time_base)
                if frame.pts is not None
                else index / float(fallback_rate)
            )
            timestamps.append(max(0.0, timestamp))
        if not timestamps:
            raise IngestError("The footage contains no decodable video frames.")
        metadata = {**container.metadata, **stream.metadata}
        return SourceInfo(
            tuple(timestamps),
            stream.width,
            stream.height,
            Fraction(float(fallback_rate)).limit_denominator(100_000),
            cast(Literal[0, 1, 2, 3], (rotation // 90) % 4),
            codec,
            sorted(families & SUPPORTED_CONTAINERS)[0],
            {str(key).lower(): str(value) for key, value in metadata.items()},
        )


def full_resolution_frames(path: Path, indices: set[int]) -> Iterator[tuple[int, av.VideoFrame]]:
    """Decode requested oriented source frames on demand for later precision stages."""
    if not indices:
        return
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        for index, frame in enumerate(container.decode(stream)):
            if index in indices:
                yield index, _orient(frame, _frame_rotation(frame))
            if index >= max(indices):
                break


def _normalized_samples(timestamps: tuple[float, ...]) -> tuple[NormalizedSample, ...]:
    if len(timestamps) == 1:
        return (NormalizedSample(0, 0.0, 0, timestamps[0]),)
    intervals = [b - a for a, b in itertools.pairwise(timestamps) if b > a]
    interval = statistics.median(intervals) if intervals else 1 / 30
    interval = max(interval, 1 / 240)
    duration = max(0.0, timestamps[-1] - timestamps[0])
    count = max(1, round(duration / interval) + 1)
    relative = [value - timestamps[0] for value in timestamps]
    result: list[NormalizedSample] = []
    for index in range(count):
        target = index * interval
        position = bisect.bisect_left(relative, target)
        candidates = [min(position, len(relative) - 1), max(0, position - 1)]
        source_index = min(candidates, key=lambda item: abs(relative[item] - target))
        result.append(NormalizedSample(index, target, source_index, timestamps[source_index]))
    return tuple(result)


def _encode_copies(  # noqa: PLR0917 - one cohesive dual-encode operation
    source: Path,
    info: SourceInfo,
    samples: tuple[NormalizedSample, ...],
    analysis_path: Path,
    proxy_path: Path,
    analysis_size: tuple[int, int],
    proxy_size: tuple[int, int],
    thumbnail_indices: set[int],
    output_dir: Path,
    check_canceled: CancelCheck,
) -> dict[int, Path]:
    fps = _normalized_rate(samples, info.rate)
    selected_by_source: dict[int, list[int]] = {}
    for sample in samples:
        selected_by_source.setdefault(sample.source_frame_index, []).append(sample.frame_index)
    thumbnails: dict[int, Path] = {}
    with (
        av.open(str(source)) as input_container,
        av.open(str(analysis_path), "w", format="matroska") as analysis,
        av.open(str(proxy_path), "w", format="mp4") as proxy,
    ):
        source_stream = input_container.streams.video[0]
        analysis_stream = _video_stream(analysis, "ffv1", fps, analysis_size, "bgr0")
        proxy_stream = _video_stream(proxy, "libx264", fps, proxy_size, "yuv420p")
        proxy_stream.options = {
            "bf": "0",
            "crf": "23",
            "g": "6",
            "preset": "medium",
            "threads": "1",
            "tune": "zerolatency",
        }
        for source_index, frame in enumerate(input_container.decode(source_stream)):
            check_canceled()
            output_indices = selected_by_source.get(source_index, ())
            if not output_indices:
                continue
            oriented = _orient(frame, info.rotation)
            for output_index in output_indices:
                analysis_frame = oriented.reformat(
                    width=analysis_size[0], height=analysis_size[1], format="bgr0"
                )
                proxy_frame = oriented.reformat(
                    width=proxy_size[0], height=proxy_size[1], format="rgb24"
                )
                _mux_frame(analysis, analysis_stream, analysis_frame, output_index)
                _mux_frame(proxy, proxy_stream, proxy_frame, output_index)
                if output_index in thumbnail_indices:
                    path = output_dir / f"thumbnail-{output_index:06d}.webp"
                    _encode_still(path, proxy_frame)
                    thumbnails[output_index] = path
        analysis.mux(analysis_stream.encode())  # pyright: ignore[reportUnknownMemberType]
        proxy.mux(proxy_stream.encode())  # pyright: ignore[reportUnknownMemberType]
    if len(thumbnails) != len(thumbnail_indices):
        raise IngestError("The footage ended before thumbnails could be encoded.")
    return thumbnails


def _video_stream(
    container: OutputContainer,
    codec: str,
    rate: Fraction,
    size: tuple[int, int],
    pixel_format: str,
) -> VideoStream:
    stream = cast(
        VideoStream,
        container.add_stream(codec, rate=rate),  # pyright: ignore[reportUnknownMemberType]
    )
    stream.width, stream.height = size
    stream.pix_fmt = pixel_format
    stream.time_base = 1 / rate
    return stream


def _mux_frame(
    container: OutputContainer,
    stream: VideoStream,
    frame: av.VideoFrame,
    index: int,
) -> None:
    frame.pts = index
    frame.time_base = stream.time_base
    frame.color_primaries = 1
    frame.colorspace = 1
    frame.color_trc = 1
    container.mux(stream.encode(frame))  # pyright: ignore[reportUnknownMemberType]


def _encode_still(path: Path, frame: av.VideoFrame) -> None:
    with av.open(str(path), "w", format="webp") as output:
        stream = output.add_stream(  # pyright: ignore[reportUnknownMemberType]
            "libwebp", rate=1
        )
        stream.width, stream.height = frame.width, frame.height
        stream.pix_fmt = "yuv420p"
        output.mux(stream.encode(frame))  # pyright: ignore[reportUnknownMemberType]
        output.mux(stream.encode())  # pyright: ignore[reportUnknownMemberType]


def _orient(frame: av.VideoFrame, quarter_turns: int) -> av.VideoFrame:
    if quarter_turns == 0:
        return frame
    filters = {1: ("transpose", "clock"), 2: ("hflip,vflip", ""), 3: ("transpose", "cclock")}
    name, argument = filters[quarter_turns]
    graph = Graph()
    source = graph.add_buffer(template=frame)
    previous: Any = source
    for filter_name in name.split(","):
        node = graph.add(filter_name, argument if len(name.split(",")) == 1 else None)
        previous.link_to(node)
        previous = node
    sink = graph.add("buffersink")
    previous.link_to(sink)
    graph.configure()
    source.push(frame)
    return cast(av.VideoFrame, sink.pull())


def _frame_rotation(frame: av.VideoFrame) -> Literal[0, 1, 2, 3]:
    degrees = round(float(getattr(frame, "rotation", 0) or 0))
    return cast(Literal[0, 1, 2, 3], (degrees // 90) % 4)


def _display_size(info: SourceInfo) -> tuple[int, int]:
    return (info.height, info.width) if info.rotation % 2 else (info.width, info.height)


def _fit(width: int, height: int, long_side: int) -> tuple[int, int]:
    scale = min(1.0, long_side / max(width, height))
    fitted = (max(2, round(width * scale)), max(2, round(height * scale)))
    return tuple(value if value % 2 == 0 else value - 1 for value in fitted)  # type: ignore[return-value]


def _thumbnail_indices(frame_count: int, count: int) -> set[int]:
    actual = min(frame_count, max(1, count))
    if actual == 1:
        return {0}
    return {round(index * (frame_count - 1) / (actual - 1)) for index in range(actual)}


def _normalized_rate(samples: tuple[NormalizedSample, ...], fallback: Fraction) -> Fraction:
    if len(samples) < 2:  # noqa: PLR2004 - a rate needs two samples
        return fallback
    interval = samples[1].timestamp_seconds - samples[0].timestamp_seconds
    return Fraction(1 / interval).limit_denominator(100_000)


def _embedded(path: Path, media_type: str) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "filename": path.name,
        "mediaType": media_type,
        "encoding": "base64",
        "byteSize": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "data": base64.b64encode(content).decode("ascii"),
    }


def _intrinsics(metadata: dict[str, str], width: int, height: int) -> dict[str, float | str] | None:
    explicit = [_number(metadata.get(key)) for key in ("fx", "fy", "cx", "cy")]
    if all(value is not None for value in explicit):
        fx, fy, cx, cy = cast(list[float], explicit)
        return {
            "fxPixels": fx,
            "fyPixels": fy,
            "cxPixels": cx,
            "cyPixels": cy,
            "source": "metadata",
        }
    keys = (
        "focal_length_35mm",
        "focal_length_in_35mm_format",
        "com.apple.quicktime.camera.focal_length.35mm_equivalent",
    )
    equivalent = next(
        (_number(metadata.get(key)) for key in keys if _number(metadata.get(key))), None
    )
    if equivalent is None or equivalent <= 0:
        return None
    focal_pixels = equivalent * width / 36.0
    return {
        "fxPixels": focal_pixels,
        "fyPixels": focal_pixels,
        "cxPixels": width / 2,
        "cyPixels": height / 2,
        "source": "35mm_equivalent_metadata",
    }


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value.split()[0])
    except ValueError:
        return None
    return number if math.isfinite(number) else None

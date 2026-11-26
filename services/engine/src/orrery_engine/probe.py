"""Footage inspection: is this file a video we can analyse, and what are its properties.

The verdict depends only on what the file contains, never on its name or declared type
(platform-foundation requirement 6.3).
"""

import hashlib
import itertools
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, SupportsFloat

import av
import av.error
import httpx

SUPPORTED_CODECS = frozenset(
    {"h264", "hevc", "vp8", "vp9", "av1", "mpeg4", "prores", "mjpeg", "dnxhd"},
)
"""Video codecs the pipeline decodes. Phones and cameras record nearly all footage in these."""

SUPPORTED_CONTAINERS = frozenset({"mov", "mp4", "matroska", "webm", "avi"})
"""Container families, matched against FFmpeg's comma-separated demuxer names."""

VFR_SPREAD = 0.1
"""Frame intervals varying by more than this fraction of the median mark variable frame rate."""

DOWNLOAD_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class ProbeResult:
    sha256: str
    byte_size: int
    duration_s: float
    width: int
    height: int
    fps_nominal: float
    is_vfr: bool
    codec: str
    rotation_quarter_turns: Literal[0, 1, 2, 3]


RejectionCode = Literal[
    "too_large", "too_long", "not_video", "unsupported_codec", "unsupported_container", "empty"
]


@dataclass(frozen=True)
class Rejection:
    code: RejectionCode
    reason: str
    """What happened and what to do next, shown to the user as written."""


class SourceUnavailableError(Exception):
    """The input could not be fetched. The caller should retry later."""


class TooLargeError(Exception):
    pass


def download(
    url: str,
    dest: Path,
    max_bytes: int,
    client: httpx.Client,
    *,
    check_canceled: Callable[[], None] | None = None,
) -> tuple[str, int]:
    """Streams `url` to `dest`, hashing as it goes. Stops once `max_bytes` is exceeded."""
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:  # noqa: PLR2004
                msg = f"source returned HTTP {response.status_code}"
                raise SourceUnavailableError(msg)
            with dest.open("wb") as out:
                for chunk in response.iter_bytes(DOWNLOAD_CHUNK):
                    if check_canceled is not None:
                        check_canceled()
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLargeError
                    digest.update(chunk)
                    out.write(chunk)
    except httpx.HTTPError as error:
        msg = f"source unreachable: {type(error).__name__}"
        raise SourceUnavailableError(msg) from error
    return digest.hexdigest(), size


def _rate(value: SupportsFloat | None) -> float | None:
    """A positive frame rate as a float; None when the container does not state one."""
    if value is None:
        return None
    rate = float(value)
    return rate if rate > 0 else None


def _is_vfr(pts: list[int]) -> bool:
    """True when frame intervals vary beyond rounding: a phone's variable frame rate."""
    ordered = sorted(set(pts))
    intervals = [b - a for a, b in itertools.pairwise(ordered)]
    # The first and last intervals are often irregular even in constant-rate files.
    core = intervals[1:-1]
    if len(core) < 3:  # noqa: PLR2004 - too few frames to judge
        return False
    median = statistics.median(core)
    if median <= 0:
        return False
    return (max(core) - min(core)) / median > VFR_SPREAD


def inspect(  # noqa: PLR0911, PLR0912 - one guard clause per rejection reason reads best
    path: Path, *, sha256: str, byte_size: int, max_duration_s: float
) -> ProbeResult | Rejection:
    """Reads the container and first video stream of a downloaded file."""
    if byte_size == 0:
        return Rejection("empty", "The file is empty. Export the clip again and re-upload it.")
    try:
        container = av.open(str(path))
    except (av.error.InvalidDataError, av.error.FFmpegError, UnicodeDecodeError):
        return Rejection(
            "not_video",
            "This file is not a video we can read. Upload an MP4, MOV, MKV, WebM, or AVI file "
            "straight from your camera or phone.",
        )
    with container:
        families = set(container.format.name.split(","))
        if not families & SUPPORTED_CONTAINERS:
            return Rejection(
                "unsupported_container",
                f"Files in the {container.format.long_name} format are not supported. "
                "Convert it to MP4 (H.264) and upload it again.",
            )
        if not container.streams.video:
            return Rejection(
                "not_video",
                "This file has no video track. Upload the footage itself, not an audio "
                "recording or an image.",
            )
        stream = container.streams.video[0]
        codec = str(stream.codec_context.name)
        if codec not in SUPPORTED_CODECS:
            return Rejection(
                "unsupported_codec",
                f"Video encoded with {codec} is not supported. Export it as H.264 MP4 and "
                "upload it again.",
            )

        duration_s: float | None = None
        if container.duration is not None:
            duration_s = container.duration / av.time_base
        elif stream.duration is not None:
            duration_s = float(stream.duration * stream.time_base)

        pts: list[int] = []
        first_rotation = 0
        decoded_first = False
        for packet in container.demux(stream):
            if packet.pts is not None:
                pts.append(packet.pts)
            if not decoded_first and packet.size > 0:
                for frame in packet.decode():
                    first_rotation = round(float(getattr(frame, "rotation", 0) or 0))
                    decoded_first = True
                    break

        if not pts:
            return Rejection("not_video", "The video track contains no frames. Film it again.")
        if stream.width <= 0 or stream.height <= 0:
            return Rejection("not_video", "The video has no picture size. Export it again.")
        if duration_s is None or duration_s <= 0:
            duration_s = float((max(pts) - min(pts)) * stream.time_base)
        if duration_s <= 0:
            return Rejection("not_video", "The video has no timing information. Export it again.")
        if duration_s > max_duration_s:
            return Rejection(
                "too_long",
                f"This clip is {duration_s / 60:.1f} minutes long; the limit is "
                f"{max_duration_s / 60:.0f} minutes. Trim it to a few cycles of the mechanism.",
            )

        fps = _rate(stream.average_rate) or _rate(stream.guessed_rate) or len(pts) / duration_s
        quarter_turns = (first_rotation // 90) % 4
        return ProbeResult(
            sha256=sha256,
            byte_size=byte_size,
            duration_s=duration_s,
            width=stream.width,
            height=stream.height,
            fps_nominal=fps,
            is_vfr=_is_vfr(pts),
            codec=codec,
            rotation_quarter_turns=quarter_turns,  # pyright: ignore[reportArgumentType] - modulo 4
        )

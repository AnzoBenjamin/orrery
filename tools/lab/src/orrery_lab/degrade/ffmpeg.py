"""Real, path-safe FFmpeg/ffprobe subprocess adapter for deterministic VFR encoding."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import cast

import numpy as np

from orrery_lab.degrade.encoding_types import (
    TIMESCALE,
    CodecProfile,
    EncodingError,
    EncodingTimingMetadata,
    ProbeMetadata,
    RGB8Sequence,
)


@dataclass(frozen=True)
class FFmpegOutput:
    encoded_bytes: bytes
    probe: ProbeMetadata
    ffmpeg_version: str
    ffprobe_version: str


@dataclass(frozen=True)
class FFmpegAdapter:
    """Subprocess boundary. Executables resolve without a shell and inputs use generated paths."""

    ffmpeg_executable: str = "ffmpeg"
    ffprobe_executable: str = "ffprobe"
    timeout_seconds: float = 120.0

    def encode(
        self,
        frames: RGB8Sequence,
        profile: CodecProfile,
        timing: EncodingTimingMetadata,
    ) -> FFmpegOutput:
        ffmpeg = _resolve_executable(self.ffmpeg_executable)
        ffprobe = _resolve_executable(self.ffprobe_executable)
        with tempfile.TemporaryDirectory(prefix="orrery-encode-") as directory_name:
            directory = Path(directory_name)
            manifest = _write_inputs(directory, frames, timing)
            output_path = directory / f"encoded{profile.file_extension}"
            command = _encode_command(ffmpeg, manifest, output_path, profile)
            _run(command, self.timeout_seconds, "FFmpeg encoding")
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise EncodingError("FFmpeg produced no encoded bytes")
            probe = self._probe(ffprobe, output_path)
            encoded_bytes = output_path.read_bytes()
        return FFmpegOutput(
            encoded_bytes,
            probe,
            _version_line(ffmpeg, self.timeout_seconds),
            _version_line(ffprobe, self.timeout_seconds),
        )

    def _probe(self, executable: Path, path: Path) -> ProbeMetadata:
        command = (
            str(executable),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,width,height,time_base,nb_read_frames:frame=best_effort_timestamp",
            "-show_streams",
            "-show_frames",
            "-of",
            "json",
            str(path),
        )
        completed = _run(command, self.timeout_seconds, "ffprobe verification")
        return _parse_probe(completed.stdout)


def _write_inputs(
    directory: Path,
    frames: RGB8Sequence,
    timing: EncodingTimingMetadata,
) -> Path:
    lines = ["ffconcat version 1.0"]
    kept = timing.kept_source_indices
    for output_index, source_index in enumerate(kept):
        name = f"frame-{output_index:06d}.ppm"
        frame = np.ascontiguousarray(frames[source_index])
        header = f"P6\n{frame.shape[1]} {frame.shape[0]}\n255\n".encode("ascii")
        (directory / name).write_bytes(header + frame.tobytes())
        lines.extend((f"file '{name}'", f"option framerate {TIMESCALE}/1"))
        if output_index + 1 < len(kept):
            duration_ticks = (
                timing.encoded_timestamps_ticks[output_index + 1]
                - timing.encoded_timestamps_ticks[output_index]
            )
            lines.append(f"duration {duration_ticks / TIMESCALE:.3f}")
    manifest = directory / "frames.ffconcat"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def _encode_command(
    executable: Path,
    manifest: Path,
    output: Path,
    profile: CodecProfile,
) -> tuple[str, ...]:
    return (
        str(executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-fflags",
        "+bitexact",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-bitexact",
        "-fps_mode",
        "passthrough",
        "-enc_time_base",
        f"1:{TIMESCALE}",
        "-c:v",
        profile.encoder,
        "-crf",
        str(profile.crf),
        *profile.encoder_options,
        "-pix_fmt",
        profile.pixel_format,
        "-flags:v",
        "+bitexact",
        *profile.muxer_options,
        "-y",
        str(output),
    )


def _parse_probe(text: str) -> ProbeMetadata:
    try:
        document = cast(object, json.loads(text))
    except json.JSONDecodeError as error:
        raise EncodingError("ffprobe returned invalid JSON") from error
    if not isinstance(document, dict):
        raise EncodingError("ffprobe JSON root is not an object")
    root = cast(dict[str, object], document)
    streams_object = root.get("streams")
    frames_object = root.get("frames")
    if not isinstance(streams_object, list):
        raise EncodingError("ffprobe video streams are malformed")
    if not isinstance(frames_object, list):
        raise EncodingError("ffprobe frame records are malformed")
    streams = cast(list[object], streams_object)
    frames = cast(list[object], frames_object)
    if len(streams) != 1:
        raise EncodingError("ffprobe did not report exactly one video stream")
    if not frames:
        raise EncodingError("ffprobe did not report encoded frames")
    stream = _object_record(streams[0], "ffprobe video stream is malformed")
    codec_name = _string_field(stream, "codec_name")
    width = _integer_field(stream, "width")
    height = _integer_field(stream, "height")
    time_base = _string_field(stream, "time_base")
    fraction = Fraction(time_base)
    native_pts: list[int] = []
    timestamp_ticks: list[int] = []
    for value in frames:
        frame = _object_record(value, "ffprobe frame record is malformed")
        pts = _integer_field(frame, "best_effort_timestamp")
        scaled = Fraction(pts) * fraction * TIMESCALE
        if scaled.denominator != 1:
            raise EncodingError("encoded frame timestamp is not on the declared millisecond clock")
        native_pts.append(pts)
        timestamp_ticks.append(scaled.numerator)
    reported_count = _integer_field(stream, "nb_read_frames")
    if reported_count != len(native_pts):
        raise EncodingError("ffprobe frame count disagrees with frame records")
    return ProbeMetadata(
        codec_name,
        width,
        height,
        reported_count,
        time_base,
        tuple(native_pts),
        tuple(timestamp_ticks),
        tuple(tick / TIMESCALE for tick in timestamp_ticks),
    )


def _object_record(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EncodingError(message)
    return cast(dict[str, object], value)


def _string_field(record: dict[str, object], name: str) -> str:
    value = record.get(name)
    if not isinstance(value, str):
        raise EncodingError(f"ffprobe field {name!r} is missing or not a string")
    return value


def _integer_field(record: dict[str, object], name: str) -> int:
    value = record.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise EncodingError(f"ffprobe field {name!r} is missing or not an integer")
    try:
        return int(value)
    except ValueError as error:
        raise EncodingError(f"ffprobe field {name!r} is not an integer") from error


def _resolve_executable(name: str) -> Path:
    resolved = shutil.which(name)
    if resolved is None:
        raise EncodingError(f"required executable {name!r} was not found")
    return Path(resolved).resolve()


def _version_line(executable: Path, timeout: float) -> str:
    completed = _run((str(executable), "-version"), timeout, f"{executable.name} version check")
    lines = completed.stdout.splitlines()
    if not lines:
        raise EncodingError(f"{executable.name} returned no version information")
    return lines[0]


def _run(
    command: tuple[str, ...], timeout: float, operation: str
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(  # noqa: S603 -- absolute executable and argv, never a shell
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EncodingError(f"{operation} could not run: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise EncodingError(f"{operation} failed: {detail}")
    return completed


__all__ = ["FFmpegAdapter", "FFmpegOutput"]

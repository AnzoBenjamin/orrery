"""Content hashes over decoded video frames rather than container bytes."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DecodedFrameHash:
    schema_version: int
    algorithm: str
    pixel_format: str
    width: int
    height: int
    frame_count: int
    digest: str

    def record(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "algorithm": self.algorithm,
            "pixelFormat": self.pixel_format,
            "width": self.width,
            "height": self.height,
            "frameCount": self.frame_count,
            "digest": self.digest,
        }


def decoded_frame_hash(
    encoded: bytes,
    *,
    extension: str,
    width: int,
    height: int,
    ffmpeg: str = "ffmpeg",
) -> DecodedFrameHash:
    """Decode the first video stream to RGB24 and hash frames in presentation order."""
    if not encoded:
        raise ValueError("encoded video cannot be empty")
    if not extension.startswith(".") or "/" in extension or "\\" in extension:
        raise ValueError("video extension must be a simple suffix beginning with a dot")
    if width <= 0 or height <= 0:
        raise ValueError("decoded dimensions must be positive")
    executable = shutil.which(ffmpeg) if Path(ffmpeg).name == ffmpeg else ffmpeg
    if executable is None or not Path(executable).exists():
        raise RuntimeError(f"FFmpeg executable not found: {ffmpeg}")
    with tempfile.TemporaryDirectory(prefix="orrery-suite-decode-") as directory_name:
        path = Path(directory_name) / f"clip{extension}"
        path.write_bytes(encoded)
        completed = subprocess.run(  # noqa: S603 -- argv only; executable is resolved above
            (
                executable,
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-fps_mode",
                "passthrough",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ),
            check=False,
            capture_output=True,
        )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg could not decode generated clip: {message}")
    frame_size = width * height * 3
    if not completed.stdout or len(completed.stdout) % frame_size:
        raise RuntimeError("decoded RGB byte count is not a whole number of frames")
    return DecodedFrameHash(
        1,
        "sha256",
        "rgb24",
        width,
        height,
        len(completed.stdout) // frame_size,
        hashlib.sha256(completed.stdout).hexdigest(),
    )


__all__ = ["DecodedFrameHash", "decoded_frame_hash"]

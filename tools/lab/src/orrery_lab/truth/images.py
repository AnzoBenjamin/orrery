"""Deterministic 16-bit instance PNG and float32 OpenEXR writers."""

from __future__ import annotations

import struct
import zlib

import numpy as np
import numpy.typing as npt

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXR_MAGIC = 20_000_630


IMAGE_DIMENSIONS = 2
MAX_INSTANCE_ID = 0xFFFF


def png16(instance_id: npt.NDArray[np.int32]) -> bytes:
    """Encode one two-dimensional instance map as deterministic grayscale PNG."""
    if instance_id.ndim != IMAGE_DIMENSIONS or instance_id.dtype != np.int32:
        raise ValueError("instance mask must be a two-dimensional int32 array")
    if (
        instance_id.size == 0
        or np.any(instance_id < 0)
        or np.any(instance_id > MAX_INSTANCE_ID)
    ):
        raise ValueError("instance mask IDs must be in the 16-bit unsigned range")
    height, width = instance_id.shape
    rows = np.asarray(instance_id, dtype=">u2").reshape(height, width)
    raw = b"".join(b"\x00" + rows[row].tobytes() for row in range(height))
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 16, 0, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(raw, level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def depth_exr(depth: npt.NDArray[np.float32]) -> bytes:
    """Encode one top-to-bottom float32 Z plane as uncompressed scanline OpenEXR."""
    if depth.ndim != IMAGE_DIMENSIONS or depth.dtype != np.float32 or np.any(np.isnan(depth)):
        raise ValueError("depth must be a two-dimensional float32 array without NaNs")
    height, width = depth.shape
    if width <= 0 or height <= 0:
        raise ValueError("depth dimensions must be positive")
    channels = b"Z\0" + struct.pack("<iB3xii", 2, 0, 1, 1) + b"\0"
    window = struct.pack("<iiii", 0, 0, width - 1, height - 1)
    header = b"".join(
        (
            struct.pack("<II", EXR_MAGIC, 2),
            _exr_attribute("channels", "chlist", channels),
            _exr_attribute("compression", "compression", b"\x00"),
            _exr_attribute("dataWindow", "box2i", window),
            _exr_attribute("displayWindow", "box2i", window),
            _exr_attribute("lineOrder", "lineOrder", b"\x00"),
            _exr_attribute("pixelAspectRatio", "float", struct.pack("<f", 1.0)),
            _exr_attribute("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0)),
            _exr_attribute("screenWindowWidth", "float", struct.pack("<f", 1.0)),
            b"\0",
        )
    )
    scanline_size = 8 + 4 * width
    first_scanline = len(header) + 8 * height
    offsets = b"".join(
        struct.pack("<Q", first_scanline + row * scanline_size) for row in range(height)
    )
    rows = np.asarray(depth, dtype="<f4")
    scanlines = b"".join(
        struct.pack("<iI", row, 4 * width) + rows[row].tobytes() for row in range(height)
    )
    return header + offsets + scanlines


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFF_FFFF)


def _exr_attribute(name: str, kind: str, value: bytes) -> bytes:
    return (
        name.encode("ascii")
        + b"\0"
        + kind.encode("ascii")
        + b"\0"
        + struct.pack("<I", len(value))
        + value
    )


__all__ = ["depth_exr", "png16"]

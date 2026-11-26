"""Small reader for uncompressed scanline EXR files emitted by Blender's compositor."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from orrery_lab.render3d.types import CyclesRenderError

EXR_MAGIC = 20_000_630
PIXEL_DTYPES: dict[int, str] = {0: "<u4", 1: "<f2", 2: "<f4"}


@dataclass(frozen=True)
class ExrImage:
    width: int
    height: int
    channels: dict[str, npt.NDArray[np.float32]]


@dataclass(frozen=True)
class _Channel:
    name: str
    pixel_type: int
    x_sampling: int
    y_sampling: int


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.position = 0

    def take(self, size: int) -> bytes:
        end = self.position + size
        if end > len(self.data):
            raise CyclesRenderError("truncated OpenEXR render-pass output")
        value = self.data[self.position : end]
        self.position = end
        return value

    def unpack(self, pattern: str) -> tuple[int, ...]:
        size = struct.calcsize(pattern)
        return struct.unpack(pattern, self.take(size))

    def cstring(self) -> str:
        end = self.data.find(b"\0", self.position)
        if end < 0:
            raise CyclesRenderError("unterminated OpenEXR string")
        value = self.data[self.position : end]
        self.position = end + 1
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError as error:
            raise CyclesRenderError("invalid OpenEXR header text") from error


def read_exr(path: Path) -> ExrImage:
    reader = _Reader(path.read_bytes())
    magic, version = reader.unpack("<II")
    if magic != EXR_MAGIC:
        raise CyclesRenderError(f"{path.name} is not an OpenEXR image")
    if version & 0x0000_FF00:
        raise CyclesRenderError(f"unsupported tiled, deep, or multipart OpenEXR {path.name}")
    attributes: dict[str, tuple[str, bytes]] = {}
    while True:
        name = reader.cstring()
        if not name:
            break
        kind = reader.cstring()
        (size,) = reader.unpack("<I")
        attributes[name] = (kind, reader.take(size))
    compression = attributes.get("compression")
    if compression is None or compression[1] != b"\x00":
        raise CyclesRenderError(f"{path.name} is not an uncompressed scanline OpenEXR")
    window = attributes.get("dataWindow")
    if window is None or window[0] != "box2i":
        raise CyclesRenderError(f"{path.name} has no integer data window")
    x_min, y_min, x_max, y_max = struct.unpack("<iiii", window[1])
    width, height = x_max - x_min + 1, y_max - y_min + 1
    channels = _channels(attributes.get("channels"), path)
    offsets = [reader.unpack("<Q")[0] for _ in range(height)]
    arrays = {channel.name: np.empty((height, width), dtype=np.float32) for channel in channels}
    for offset in offsets:
        reader.position = offset
        y, packed_size = reader.unpack("<iI")
        if not y_min <= y <= y_max:
            raise CyclesRenderError(f"{path.name} has an out-of-range scanline")
        packed = _Reader(reader.take(packed_size))
        row = y - y_min
        for channel in channels:
            if channel.x_sampling != 1 or channel.y_sampling != 1:
                raise CyclesRenderError(f"{path.name} uses unsupported channel sampling")
            dtype = PIXEL_DTYPES.get(channel.pixel_type)
            if dtype is None:
                raise CyclesRenderError(f"{path.name} uses unknown EXR pixel type")
            size = width * np.dtype(dtype).itemsize
            values = np.frombuffer(packed.take(size), dtype=dtype).astype(np.float32)
            arrays[channel.name][row] = values
        if packed.position != len(packed.data):
            raise CyclesRenderError(f"{path.name} scanline has trailing data")
    return ExrImage(width, height, arrays)


def _channels(attribute: tuple[str, bytes] | None, path: Path) -> tuple[_Channel, ...]:
    if attribute is None or attribute[0] != "chlist":
        raise CyclesRenderError(f"{path.name} has no channel list")
    reader = _Reader(attribute[1])
    result: list[_Channel] = []
    while True:
        name = reader.cstring()
        if not name:
            break
        pixel_type = reader.unpack("<i")[0]
        reader.take(4)  # pLinear and three reserved bytes
        x_sampling, y_sampling = reader.unpack("<ii")
        result.append(_Channel(name, pixel_type, x_sampling, y_sampling))
    if not result:
        raise CyclesRenderError(f"{path.name} has no channels")
    return tuple(result)


__all__ = ["ExrImage", "read_exr"]

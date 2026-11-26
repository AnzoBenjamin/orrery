"""Deterministic vector hand and tool silhouettes animated along cubic image paths."""

from __future__ import annotations

# skia-python has no type information; this module is its narrow drawing adapter.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
import math
from dataclasses import dataclass
from typing import Literal

import skia

from orrery_lab.geometry import Point2

OccluderKind = Literal["hand", "tool"]


@dataclass(frozen=True)
class AnimatedOccluder:
    kind: OccluderKind
    start: float
    end: float
    control_points: tuple[Point2, Point2, Point2, Point2]
    scale: float
    angle: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.start,
            self.end,
            self.scale,
            self.angle,
            *(v for p in self.control_points for v in p),
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("occluder values must be finite")
        if self.start < 0.0 or self.end <= self.start:
            raise ValueError("occluder interval must have positive duration")
        if self.scale <= 0.0:
            raise ValueError("occluder scale must be positive")

    def active(self, time: float) -> bool:
        return self.start <= time <= self.end

    def position(self, time: float) -> Point2:
        progress = min(1.0, max(0.0, (time - self.start) / (self.end - self.start)))
        reverse = 1.0 - progress
        weights = (
            reverse**3,
            3.0 * reverse * reverse * progress,
            3.0 * reverse * progress * progress,
            progress**3,
        )
        return tuple(
            sum(
                weight * point[axis]
                for weight, point in zip(weights, self.control_points, strict=True)
            )
            for axis in range(2)
        )  # type: ignore[return-value]

    def covers(self, point_image: Point2, time: float) -> bool:
        if not self.active(time):
            return False
        center = self.position(time)
        c, s = math.cos(-self.angle), math.sin(-self.angle)
        dx, dy = point_image[0] - center[0], point_image[1] - center[1]
        x, y = c * dx - s * dy, s * dx + c * dy
        if self.kind == "hand":
            return (x / (0.9 * self.scale)) ** 2 + (y / (0.7 * self.scale)) ** 2 <= 1.0
        half_length = 1.7 * self.scale
        clamped = min(half_length, max(-half_length, x))
        return math.hypot(x - clamped, y) <= 0.22 * self.scale


def _paint(color: int) -> skia.Paint:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setColor(color)
    return paint


def _draw_hand(canvas: skia.Canvas, occluder: AnimatedOccluder, time: float) -> None:
    x, y = occluder.position(time)
    scale = occluder.scale
    canvas.save()
    canvas.translate(x, y)
    canvas.rotate(math.degrees(occluder.angle))
    shadow = _paint(skia.ColorSetARGB(90, 0, 0, 0))
    skin = _paint(skia.ColorSetARGB(255, 173, 119, 82))
    highlight = _paint(skia.ColorSetARGB(100, 232, 190, 145))
    canvas.drawOval(skia.Rect.MakeXYWH(-0.62 * scale, -0.45 * scale, 1.25 * scale, scale), shadow)
    canvas.drawOval(skia.Rect.MakeXYWH(-0.67 * scale, -0.5 * scale, 1.25 * scale, scale), skin)
    for index, length in enumerate((0.9, 1.08, 1.0, 0.78)):
        left = (-0.58 + 0.29 * index) * scale
        rect = skia.Rect.MakeXYWH(left, (-0.45 - length) * scale, 0.23 * scale, length * scale)
        canvas.drawRoundRect(rect, 0.11 * scale, 0.11 * scale, skin)
    canvas.save()
    canvas.rotate(-38.0, -0.5 * scale, 0.1 * scale)
    thumb = skia.Rect.MakeXYWH(-0.83 * scale, -0.02 * scale, 0.55 * scale, 0.25 * scale)
    canvas.drawRoundRect(thumb, 0.12 * scale, 0.12 * scale, skin)
    canvas.restore()
    canvas.drawOval(
        skia.Rect.MakeXYWH(-0.35 * scale, -0.25 * scale, 0.5 * scale, 0.28 * scale), highlight
    )
    canvas.restore()


def _draw_tool(canvas: skia.Canvas, occluder: AnimatedOccluder, time: float) -> None:
    x, y = occluder.position(time)
    scale = occluder.scale
    canvas.save()
    canvas.translate(x, y)
    canvas.rotate(math.degrees(occluder.angle))
    shadow = _paint(skia.ColorSetARGB(100, 0, 0, 0))
    metal = _paint(skia.ColorSetARGB(255, 126, 132, 130))
    handle = _paint(skia.ColorSetARGB(255, 116, 45, 34))
    canvas.drawRoundRect(
        skia.Rect.MakeXYWH(-1.75 * scale, -0.16 * scale, 3.5 * scale, 0.44 * scale),
        0.2 * scale,
        0.2 * scale,
        shadow,
    )
    canvas.drawRoundRect(
        skia.Rect.MakeXYWH(-1.7 * scale, -0.22 * scale, 1.15 * scale, 0.44 * scale),
        0.2 * scale,
        0.2 * scale,
        handle,
    )
    canvas.drawRect(
        skia.Rect.MakeXYWH(-0.65 * scale, -0.08 * scale, 2.0 * scale, 0.16 * scale), metal
    )
    path = skia.Path()
    path.moveTo(1.25 * scale, -0.08 * scale)
    path.lineTo(1.7 * scale, -0.45 * scale)
    path.lineTo(1.48 * scale, 0.0)
    path.lineTo(1.7 * scale, 0.45 * scale)
    path.close()
    canvas.drawPath(path, metal)
    canvas.restore()


def draw_occluders(
    canvas: skia.Canvas, occluders: tuple[AnimatedOccluder, ...], time: float
) -> None:
    for occluder in occluders:
        if not occluder.active(time):
            continue
        if occluder.kind == "hand":
            _draw_hand(canvas, occluder, time)
        else:
            _draw_tool(canvas, occluder, time)


__all__ = ["AnimatedOccluder", "OccluderKind", "draw_occluders"]

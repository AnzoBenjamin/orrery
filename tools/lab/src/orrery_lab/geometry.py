"""Planar construction helpers, in meters and radians (counter-clockwise positive)."""

from __future__ import annotations

import math

type Point2 = tuple[float, float]


def polar(origin: Point2, length: float, angle: float) -> Point2:
    return (origin[0] + length * math.cos(angle), origin[1] + length * math.sin(angle))


def unit(dx: float, dy: float) -> Point2:
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def distance(a: Point2, b: Point2) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def angle_of(a: Point2, b: Point2) -> float:
    """Direction from `a` to `b`."""
    return math.atan2(b[1] - a[1], b[0] - a[0])


def lerp(a: Point2, b: Point2, t: float) -> Point2:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def offset(a: Point2, b: Point2, along: float, across: float) -> Point2:
    """The point `along` of the way from `a` to `b`, then `across` times |ab| to the left."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    return (a[0] + along * dx - across * dy, a[1] + along * dy + across * dx)


def circle_intersection(c0: Point2, r0: float, c1: Point2, r1: float, left: bool) -> Point2 | None:
    """Where circles about `c0` and `c1` meet, on the left of `c0 → c1` or on its right.

    None when they do not meet (or meet only tangentially, where a loop would be at a toggle).
    """
    d = distance(c0, c1)
    if d <= 0.0 or d >= r0 + r1 or d <= abs(r0 - r1):
        return None
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(max(r0 * r0 - a * a, 0.0))
    ux, uy = (c1[0] - c0[0]) / d, (c1[1] - c0[1]) / d
    sign = 1.0 if left else -1.0
    return (c0[0] + a * ux - sign * h * uy, c0[1] + a * uy + sign * h * ux)


def acos_range(low: float, high: float) -> tuple[float, float] | None:
    """Angles in `[0, π]` whose cosine lies in `[low, high]`, or None when there are none."""
    low, high = max(low, -1.0), min(high, 1.0)
    if low > high:
        return None
    return (math.acos(high), math.acos(low))

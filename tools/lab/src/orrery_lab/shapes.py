"""Part outlines as polygons in a body's local frame (meters): rounded links from the convex hull
of circles around their points, involute spur gears, racks, Fourier cams, and stadium slots.

Polygons are counter-clockwise and simple, as the solver's collision check expects.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

from orrery_lab.geometry import Point2

#: Standard pressure angle of the involute gears drawn here.
PRESSURE_ANGLE = math.radians(20)
#: Addendum and dedendum in modules.
ADDENDUM, DEDENDUM = 1.0, 1.25


def circle(center: Point2, radius: float, segments: int = 24, start: float = 0.0) -> list[Point2]:
    return [
        (
            center[0] + radius * math.cos(start + math.tau * k / segments),
            center[1] + radius * math.sin(start + math.tau * k / segments),
        )
        for k in range(segments)
    ]


def convex_hull(points: Sequence[Point2]) -> list[Point2]:
    """Andrew's monotone chain, counter-clockwise, without collinear points."""
    pts = sorted(set(points))
    if len(pts) < 3:  # noqa: PLR2004 (a polygon needs three points)
        return list(pts)

    def cross(o: Point2, a: Point2, b: Point2) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point2] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:  # noqa: PLR2004
            lower.pop()
        lower.append(p)
    upper: list[Point2] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:  # noqa: PLR2004
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def rounded_hull(points: Sequence[Point2], radius: float, segments: int = 16) -> list[Point2]:
    """The convex hull of circles of `radius` around `points`: a capsule for two points, a
    rounded triangle for three."""
    return convex_hull([p for c in points for p in circle(c, radius, segments)])


def stadium(a: Point2, b: Point2, radius: float, segments: int = 12) -> list[Point2]:
    """A slot of half-width `radius` from `a` to `b`."""
    return rounded_hull([a, b], radius, 2 * segments)


def area(polygon: Sequence[Point2]) -> float:
    """Signed area (positive when counter-clockwise)."""
    return 0.5 * sum(
        polygon[i][0] * polygon[(i + 1) % len(polygon)][1]
        - polygon[(i + 1) % len(polygon)][0] * polygon[i][1]
        for i in range(len(polygon))
    )


def _involute(angle: float) -> float:
    return math.tan(angle) - angle


def spur_gear(
    center: Point2, teeth: int, module: float, phase: float = 0.0, flank_points: int = 4
) -> list[Point2]:
    """An external involute spur gear: tooth centers at `phase + 2πk/teeth`, 20° pressure angle,
    standard addendum and dedendum."""
    pitch = module * teeth / 2
    base = pitch * math.cos(PRESSURE_ANGLE)
    tip, root = pitch + ADDENDUM * module, pitch - DEDENDUM * module

    def half_width(r: float) -> float:
        """Half the tooth's angular width at radius `r` (on or outside the base circle)."""
        phi = math.acos(min(1.0, base / r))
        return math.pi / (2 * teeth) + _involute(PRESSURE_ANGLE) - _involute(phi)

    def at(r: float, a: float) -> Point2:
        return (center[0] + r * math.cos(a), center[1] + r * math.sin(a))

    start = max(base, root)
    radii = [start + (tip - start) * k / flank_points for k in range(flank_points + 1)]
    polygon: list[Point2] = []
    for k in range(teeth):
        c = phase + math.tau * k / teeth
        if root < base:
            polygon.append(at(root, c - half_width(base)))
        polygon.extend(at(r, c - half_width(r)) for r in radii)
        polygon.extend(at(r, c + half_width(r)) for r in reversed(radii))
        if root < base:
            polygon.append(at(root, c + half_width(base)))
    return polygon


def rack(
    pitch_start: Point2,
    along: Point2,
    toward_teeth: Point2,
    *,
    teeth: int,
    module: float,
    depth: float,
) -> list[Point2]:
    """A rack whose pitch line starts at `pitch_start` and runs `teeth` pitches along `along`, its
    teeth on the `toward_teeth` side, with a back `depth` behind the roots."""
    pitch = math.pi * module
    lean = math.tan(PRESSURE_ANGLE)

    def at(s: float, h: float) -> Point2:
        return (
            pitch_start[0] + s * along[0] + h * toward_teeth[0],
            pitch_start[1] + s * along[1] + h * toward_teeth[1],
        )

    top, bottom = ADDENDUM * module, -DEDENDUM * module
    teeth_side: list[Point2] = []
    for k in range(teeth):
        s = (k + 0.5) * pitch
        # A trapezoid tooth centered at s: half its pitch wide on the pitch line.
        teeth_side.extend(
            [
                at(s - 0.25 * pitch - (bottom * -lean), bottom),
                at(s - 0.25 * pitch + top * lean, top),
                at(s + 0.25 * pitch - top * lean, top),
                at(s + 0.25 * pitch + (bottom * -lean), bottom),
            ]
        )
    length = teeth * pitch
    back = [at(length, bottom - depth), at(0.0, bottom - depth)]
    polygon = [at(0.0, bottom), *teeth_side, at(length, bottom), *back]
    return polygon if area(polygon) > 0 else polygon[::-1]


def profile(radius: Callable[[float], float], samples: int = 180) -> list[Point2]:
    """A closed curve in polar form `r(φ)` about the local origin."""
    return [
        (radius(phi) * math.cos(phi), radius(phi) * math.sin(phi))
        for phi in (math.tau * k / samples for k in range(samples))
    ]


def geneva_wheel(
    center: Point2,
    radius: float,
    *,
    slots: int,
    slot_width: float,
    slot_depth: float,
    phase: float,
) -> list[Point2]:
    """A Geneva wheel: a disk with `slots` radial slots, one centered at `phase`."""
    polygon: list[Point2] = []
    half = math.asin(min(0.99, 0.5 * slot_width / radius))
    inner = radius - slot_depth
    arc_points = 6
    for k in range(slots):
        c = phase + math.tau * k / slots
        nxt = c + math.tau / slots
        # Slot walls: down one side, across the bottom, up the other.
        for r, a in (
            (radius, c - half),
            (inner, c - half * radius / inner),
            (inner, c + half * radius / inner),
            (radius, c + half),
        ):
            polygon.append((center[0] + r * math.cos(a), center[1] + r * math.sin(a)))
        # The rim between this slot and the next.
        for j in range(1, arc_points):
            a = c + half + (nxt - half - c - half) * j / arc_points
            polygon.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    return polygon

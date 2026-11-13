"""Drawing pin-jointed linkages from their joint locations.

A linkage is a set of named locations (world coordinates at driver zero) and bodies that each pin
some of them. Every location two or more bodies share becomes revolute joints from the first body
listed to each of the others, so a location shared by three bodies is two joints, as in a real
machine with one pin through three parts.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import combinations

from orrery_lab.family import Infeasible
from orrery_lab.geometry import Point2, circle_intersection, distance
from orrery_lab.graph import BodyKind, Graph, PointRole

FRAME = "frame"


@dataclass(frozen=True)
class Part:
    """A body: the locations it is pinned at, and points that only it carries."""

    id: str
    label: str
    pins: tuple[str, ...]
    kind: BodyKind = "link"
    own: dict[str, tuple[Point2, PointRole]] = field(
        default_factory=dict[str, tuple[Point2, PointRole]]
    )


def joint_id(location: str, body: str, first: bool) -> str:
    return f"j-{location}" if first else f"j-{location}-{body}"


def draw(
    graph: Graph,
    locations: dict[str, Point2],
    parts: list[Part],
    driven: tuple[str, str],
    min_spacing: float,
) -> None:
    """Adds the parts and their pins to `graph`, and drives the pin of `driven = (location, body)`
    on the frame.

    Raises `Infeasible` when two pins of one part are closer than `min_spacing` (a link too short
    to make).
    """
    for part in parts:
        for a, b in combinations(part.pins, 2):
            if distance(locations[a], locations[b]) < min_spacing:
                raise Infeasible(f"pins {a} and {b} of {part.id} nearly coincide")
        body = graph.body(part.id, part.label, part.kind)
        for pin in part.pins:
            body.point(pin, locations[pin])
        for point, (at, role) in part.own.items():
            body.point(point, at, role)

    holders: dict[str, list[str]] = {}
    for part in parts:
        for pin in part.pins:
            holders.setdefault(pin, []).append(part.id)
    drive_joint: str | None = None
    for location, bodies in holders.items():
        first = bodies[0]
        for i, other in enumerate(bodies[1:]):
            jid = joint_id(location, other, i == 0)
            graph.revolute(jid, first, location, other, location)
            if (location, other) == driven and first == FRAME:
                drive_joint = jid
    if drive_joint is None:
        raise ValueError(f"no frame pin {driven} to drive")
    graph.drive(drive_joint)


def dyad_by(a: Point2, ra: float, b: Point2, rb: float, key: Callable[[Point2], float]) -> Point2:
    """The dyad joint whose `key` is least (for branches named by where they sit, such as
    "the lower one")."""
    return min((dyad(a, ra, b, rb, True), dyad(a, ra, b, rb, False)), key=key)


@dataclass(frozen=True)
class Rotation:
    """Turns a canonical drawing by `angle` about the world origin."""

    angle: float

    def __call__(self, p: Point2) -> Point2:
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def dyad(a: Point2, ra: float, b: Point2, rb: float, left: bool) -> Point2:
    """The joint of two links of lengths `ra` (from `a`) and `rb` (from `b`), on the left of
    `a → b` or its right."""
    p = circle_intersection(a, ra, b, rb, left)
    if p is None:
        raise Infeasible("a dyad does not close")
    return p

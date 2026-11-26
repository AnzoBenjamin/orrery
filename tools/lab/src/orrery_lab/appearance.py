"""Appearance: what makes a sample look like a machine of real parts (requirement 1.3).

`dress` gives every planar moving body an outline (written into the graph, with thickness and
layer, for the solver's collision check) and a record the renderers draw from: holes at its pins,
slots, lightening cut-outs, rivets, a printed pattern, and its specimen-tag letter. Spatial bodies
are drawn as rods. The frame becomes a base plate with bosses under its pivots.
Parts are stacked in layers on their pins, as in a real machine. Parts pinned or sliding on each
other take different layers; gears that mesh, belted pulleys, and a cam and its follower share one.
Layers are assigned greedily, then any parts that the solver finds colliding over the driver range
are moved apart, until nothing collides. Pins that pass through layers between the two they join
are not checked against the parts in those layers.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

from orrery_lab.decoration import Circle, WearKind, WearMark
from orrery_lab.family import Built, Requirements
from orrery_lab.geometry import Point2, distance
from orrery_lab.graph import Json, checked
from orrery_lab.shapes import (
    circle,
    geneva_wheel,
    profile,
    rack,
    rounded_hull,
    spur_gear,
    stadium,
)

Pattern = Literal["plain", "stripes", "dots", "checker", "numerals", "filigree"]
PATTERNS: tuple[Pattern, ...] = ("plain", "stripes", "dots", "checker", "numerals", "filigree")
#: Gap between layers, as a share of the plate thickness.
LAYER_GAP = 0.25
MAX_RELAYERS = 12
LIGHTENING_PROBABILITY = 0.45
RIVET_PROBABILITY = 0.5


class AppearanceInfeasible(Exception):  # noqa: N818 (a rejected generated appearance)
    """The sampled dimensions cannot be dressed without physical overlap."""


@dataclass
class BodyAppearance:
    body_id: str
    #: The specimen-tag letter (the body's label).
    tag: str
    #: Plate outline in the body's local frame; empty for spatial bodies.
    outline: list[Point2] = field(default_factory=list[Point2])
    thickness: float = 0.0
    #: Layer index; the plate's mid-plane is at `offset` along the plane normal.
    layer: int = 0
    offset: float = 0.0
    holes: list[Circle] = field(default_factory=list[Circle])
    cutouts: list[list[Point2]] = field(default_factory=list[list[Point2]])
    rivets: list[Circle] = field(default_factory=list[Circle])
    wear_marks: list[WearMark] = field(default_factory=list[WearMark])
    #: Internal gear teeth (a ring's tooth spaces), drawn inside the outline.
    inner_teeth: list[Point2] = field(default_factory=list[Point2])
    pattern: Pattern = "plain"
    #: Rod radius for spatial bodies, drawn between their points.
    rod_radius: float = 0.0


@dataclass
class Appearance:
    width: float
    thickness: float
    pin_radius: float
    bodies: dict[str, BodyAppearance]
    #: The frame's base plate (plane coordinates of the main plane) and bosses under its pivots.
    base_plate: list[Point2]
    bosses: list[Circle]

    def record(self) -> Json:
        """A JSON record for `truth.json`."""
        return asdict(self)


@dataclass(frozen=True)
class Dressed:
    document: Json
    appearance: Appearance


def _vec2(p: Json) -> Point2:
    return (float(p["x"]), float(p["y"]))


def _wrap(angle: float, period: float) -> float:
    """`angle` folded into [-period/2, period/2)."""
    return (angle + 0.5 * period) % period - 0.5 * period


class _Mechanism:
    """Lookups on a graph document."""

    def __init__(self, document: Json) -> None:
        self.doc = document
        self.bodies: dict[str, Json] = {b["id"]: b for b in document["bodies"]}
        self.ground = next(b["id"] for b in document["bodies"] if b["kind"] == "ground")
        self.points: dict[str, dict[str, Point2]] = {
            b["id"]: {p["id"]: _vec2(p["local"]) for p in b["points"]} for b in document["bodies"]
        }

    def joints(self, *kinds: str) -> list[Json]:
        return [j for j in self.doc["joints"] if j["kind"] in kinds]

    def axle(self, body: str) -> Point2 | None:
        """The point where a body turns on a revolute joint to the frame (or any revolute)."""
        fallback: Point2 | None = None
        for j in self.joints("revolute"):
            for side, other in (("A", "B"), ("B", "A")):
                if j[f"body{side}"] == body:
                    at = self.points[body][j[f"anchor{side}"]["pointId"]]
                    if j[f"body{other}"] == self.ground:
                        return at
                    fallback = fallback or at
        return fallback

    def pin_points(self, body: str) -> list[Point2]:
        out = [
            self.points[body][j[f"anchor{side}"]["pointId"]]
            for j in self.joints("revolute", "spherical", "universal")
            for side in ("A", "B")
            if j[f"body{side}"] == body
        ]
        out.extend(
            self.points[body][j["pin"]["pointId"]]
            for j in self.joints("pin_in_slot")
            if j["pin"]["bodyId"] == body
        )
        return out

    def size(self) -> float:
        """Diagonal of the drawn bounding box, in meters."""
        pts = np.array([p for b in self.points.values() for p in b.values()])
        return float(np.hypot(*np.ptp(pts, axis=0))) or 1.0


def _gear_phases(m: _Mechanism) -> dict[str, float]:
    """Tooth phases that interleave meshing teeth in the drawn pose, walked out from the first
    gear of each meshing chain (its phase is zero)."""
    phase: dict[str, float] = {}
    meshes = [j for j in m.joints("gear_mesh") if "rack" not in j]
    for start in (j["bodyA"] for j in meshes):
        if start in phase:
            continue
        phase[start] = 0.0
        frontier = [start]
        while frontier:
            a = frontier.pop()
            for j in meshes:
                if a not in (j["bodyA"], j["bodyB"]):
                    continue
                b = j["bodyB"] if j["bodyA"] == a else j["bodyA"]
                if b in phase:
                    continue
                ga, gb = m.bodies[a]["gear"], m.bodies[b]["gear"]
                ca, cb = m.axle(a), m.axle(b)
                if ca is None or cb is None:
                    continue
                za, zb = int(ga["teeth"]), int(gb["teeth"])
                if gb["internal"] or ga["internal"]:
                    # The pinion's tooth at the contact sits in a tooth space of the ring.
                    pinion, ring = (a, b) if gb["internal"] else (b, a)
                    zp = za if pinion == a else zb
                    zr = zb if pinion == a else za
                    cp, cr = (ca, cb) if pinion == a else (cb, ca)
                    toward = math.atan2(cp[1] - cr[1], cp[0] - cr[0])
                    if pinion in phase:
                        e = _wrap(phase[pinion] - toward, math.tau / zp)
                        phase[ring] = toward + e * zp / zr
                    else:
                        e = _wrap(phase[ring] - toward, math.tau / zr)
                        phase[pinion] = toward + e * zr / zp
                else:
                    toward = math.atan2(cb[1] - ca[1], cb[0] - ca[0])
                    e = _wrap(phase[a] - toward, math.tau / za)
                    # Aligned, b has a tooth space facing a; it turns the other way, za/zb as far.
                    phase[b] = toward + math.pi + math.pi / zb - e * za / zb
                frontier.append(b)
    return phase


def _gear_outline(
    m: _Mechanism,
    body: Json,
    look: BodyAppearance,
    axle: Point2,
    phases: dict[str, float],
) -> list[Point2]:
    body_id = str(body["id"])
    gear = body["gear"]
    rack_mesh = next(
        (
            joint
            for joint in m.joints("gear_mesh")
            if joint.get("rack") and joint["bodyB"] == body_id
        ),
        None,
    )
    if rack_mesh is not None:
        return _rack_outline(
            m,
            body_id,
            rack_mesh,
            teeth=int(gear["teeth"]),
            module=float(gear["module"]),
        )
    teeth, module = int(gear["teeth"]), float(gear["module"])
    if gear["internal"]:
        pitch = module * teeth / 2
        look.inner_teeth = spur_gear(axle, teeth, module, phases.get(body_id, 0.0))
        return circle(axle, pitch + 3.0 * module, 96)
    return spur_gear(axle, teeth, module, phases.get(body_id, 0.0))


def _body_outline(
    m: _Mechanism,
    body: Json,
    look: BodyAppearance,
    *,
    width: float,
    phases: dict[str, float],
    geneva_slots: int | None,
) -> list[Point2]:
    body_id, kind = body["id"], body["kind"]
    points = list(m.points[body_id].values())
    axle = m.axle(body_id) or (0.0, 0.0)
    if kind == "gear" and "gear" in body:
        return _gear_outline(m, body, look, axle, phases)
    if kind == "pulley" and "pulley" in body:
        return circle(axle, float(body["pulley"]["radius"]) * 1.06, 72)
    if kind == "cam" and "cam" in body:
        cam = body["cam"]
        a, b = cam["fourier"]["a"], cam["fourier"]["b"]

        def cam_radius(phi: float) -> float:
            value = float(cam["baseRadius"])
            for k in range(len(a)):
                bk = b[k] if k and k < len(b) else 0.0
                value += a[k] * math.cos(k * phi) + bk * math.sin(k * phi)
            return value

        return profile(cam_radius, 180)
    if geneva_slots is not None:
        reach = max(distance(axle, point) for point in points)
        slot = next(joint for joint in m.joints("pin_in_slot") if joint["bodyB"] == body_id)
        start = _vec2(slot["slot"]["start"])
        phase = math.atan2(start[1] - axle[1], start[0] - axle[0])
        depth = reach - distance(axle, start)
        return geneva_wheel(
            axle,
            reach / 0.9,
            slots=geneva_slots,
            slot_width=2.6 * look_pin(width),
            slot_depth=depth + 0.1 * reach,
            phase=phase,
        )
    hull_points = [*points]
    for joint in m.joints("pin_in_slot"):
        if body_id in (joint["bodyA"], joint["bodyB"]) and joint["pin"]["bodyId"] != body_id:
            hull_points += [_vec2(joint["slot"]["start"]), _vec2(joint["slot"]["end"])]
    for joint in m.joints("cam_follower"):
        if joint["bodyB"] == body_id and joint.get("rollerRadius"):
            hull_points += circle(
                m.points[body_id][joint["followerPoint"]["pointId"]],
                joint["rollerRadius"],
                16,
            )
    plate_radius = 0.8 * width if kind == "slider_block" else 0.5 * width
    return rounded_hull(hull_points, plate_radius)


def look_pin(width: float) -> float:
    return 0.22 * width


def _rack_outline(
    m: _Mechanism,
    body_id: str,
    mesh: Json,
    *,
    teeth: int,
    module: float,
) -> list[Point2]:
    pinion_axle = m.axle(mesh["bodyA"]) or (0.0, 0.0)
    guide = next(j for j in m.joints("prismatic") if j["bodyB"] == body_id)
    pitch_point = m.points[body_id][guide["anchorB"]["pointId"]]
    axis = (mesh["rack"]["axisLocalB"]["x"], mesh["rack"]["axisLocalB"]["y"])
    lo, hi = guide.get("limits", [-0.0, 0.0])
    length = math.pi * module * teeth
    # Contact points on the rack as it moves from lo to hi run from pitch - hi to pitch - lo.
    back = hi + 0.5 * (length - (hi - lo))
    start = (pitch_point[0] - back * axis[0], pitch_point[1] - back * axis[1])
    toward = (pinion_axle[0] - pitch_point[0], pinion_axle[1] - pitch_point[1])
    n = math.hypot(*toward) or 1.0
    return rack(
        start,
        axis,
        (toward[0] / n, toward[1] / n),
        teeth=teeth,
        module=module,
        depth=2.5 * module,
    )


def _decorate(
    look: BodyAppearance,
    points: list[Point2],
    pins: list[Point2],
    width: float,
    rng: np.random.Generator,
) -> None:
    pin = look_pin(width)
    look.holes = [Circle(p, pin) for p in pins]
    look.pattern = PATTERNS[int(rng.integers(len(PATTERNS)))]
    if len(pins) == 2:  # noqa: PLR2004 (a binary link)
        a, b = pins
        length = distance(a, b)
        if length > 5 * width and rng.random() < LIGHTENING_PROBABILITY:
            # A lightening slot along the middle of a long link.
            t0, t1 = 0.3, 0.7
            look.cutouts.append(
                stadium(
                    (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1])),
                    (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1])),
                    0.18 * width,
                )
            )
        if rng.random() < RIVET_PROBABILITY:
            for t in (0.15, 0.85):
                look.rivets.append(
                    Circle((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), 0.09 * width)
                )
    del points


def _layer_constraints(
    m: _Mechanism, outlined: set[str]
) -> tuple[dict[str, str], set[frozenset[str]]]:
    """Groups of bodies that must share a layer (each body's group root), and pairs that must
    not."""
    root = {b: b for b in outlined}

    def find(x: str) -> str:
        while root[x] != x:
            root[x] = root[root[x]]
            x = root[x]
        return x

    for j in m.joints("gear_mesh", "belt", "cam_follower"):
        a, b = j["bodyA"], j["bodyB"]
        if a in outlined and b in outlined:
            root[find(a)] = find(b)
    conflicts: set[frozenset[str]] = set()
    for j in m.joints("revolute", "prismatic", "pin_in_slot"):
        a, b = j["bodyA"], j["bodyB"]
        if a in outlined and b in outlined and find(a) != find(b):
            conflicts.add(frozenset((find(a), find(b))))
    return {b: find(b) for b in outlined}, conflicts


def _color(order: list[str], conflicts: set[frozenset[str]]) -> dict[str, int]:
    layer: dict[str, int] = {}
    for g in order:
        taken = {layer[h] for h in layer if frozenset((g, h)) in conflicts}
        layer[g] = next(k for k in range(len(order) + 1) if k not in taken)
    return layer


def dress(
    built: Built,
    requirements: Requirements,
    rng: np.random.Generator,
    geneva_slots: int | None = None,
) -> Dressed:
    """Outlines, layers, and decorations for an accepted sample."""
    document = copy.deepcopy(built.document)
    m = _Mechanism(document)
    size = m.size()
    width = size * float(rng.uniform(0.035, 0.065))
    thickness = width * float(rng.uniform(0.15, 0.45))
    phases = _gear_phases(m)
    looks: dict[str, BodyAppearance] = {}
    outlined: set[str] = set()
    for body in document["bodies"]:
        body_id = body["id"]
        look = BodyAppearance(body_id, body["label"])
        looks[body_id] = look
        if body["kind"] == "ground":
            continue
        if body["planeId"] is None:
            look.rod_radius = 0.3 * width
            continue
        pins = m.pin_points(body_id)
        is_geneva = geneva_slots is not None and any(
            j["bodyB"] == body_id for j in m.joints("pin_in_slot")
        )
        look.outline = _body_outline(
            m,
            body,
            look,
            width=width,
            phases=phases,
            geneva_slots=geneva_slots if is_geneva else None,
        )
        look.thickness = thickness
        _decorate(look, list(m.points[body_id].values()), pins, width, rng)
        for j in m.joints("pin_in_slot"):
            if j["bodyB"] == body_id and j["pin"]["bodyId"] != body_id and not is_geneva:
                look.cutouts.append(
                    stadium(
                        _vec2(j["slot"]["start"]),
                        _vec2(j["slot"]["end"]),
                        1.15 * look_pin(width),
                    )
                )
        outlined.add(body_id)

    groups, conflicts = _layer_constraints(m, outlined)
    driven = next(
        (
            joint["bodyB"]
            for joint in m.joints("revolute", "prismatic")
            if joint["id"] == document["drivers"][0]["jointId"]
        ),
        None,
    )
    roots = {groups[body] for body in outlined}
    order = sorted(roots, key=lambda group: (group != groups.get(driven or "", ""), group))
    spacing = thickness * (1.0 + LAYER_GAP)
    for _ in range(MAX_RELAYERS):
        layer = _color(order, conflicts)
        for body_id in outlined:
            look = looks[body_id]
            look.layer = layer[groups[body_id]]
            look.offset = look.layer * spacing
            target = next(b for b in document["bodies"] if b["id"] == body_id)
            target["outline"] = {
                "polygonLocal": [{"x": x, "y": y} for x, y in look.outline],
                "thickness": thickness,
                "offset": look.offset,
            }
        found = _collisions(document, built, requirements)
        new = {frozenset((groups[a], groups[b])) for a, b in found if groups[a] != groups[b]}
        if not found:
            break
        if new <= conflicts:
            raise AppearanceInfeasible(f"layering cannot separate {sorted(found)}")
        conflicts |= new
    else:
        raise AppearanceInfeasible("layering did not converge")

    plate, bosses = _base_plate(m, width)
    return Dressed(document, Appearance(width, thickness, look_pin(width), looks, plate, bosses))


def _collisions(document: Json, built: Built, requirements: Requirements) -> list[tuple[str, str]]:
    _, solver = checked(document)
    drive = np.zeros(solver.driver_count)
    drawn = solver.assemble(drive)
    found: list[tuple[str, str]] = []
    for end in (e for e in built.drive_range if e != 0.0):
        report = solver.plausibility(0, drive, 0.0, end, requirements.step, seed=drawn)
        found += [c.bodies for c in report.collisions]
    return found


def _base_plate(m: _Mechanism, width: float) -> tuple[list[Point2], list[Circle]]:
    ground = m.bodies[m.ground]
    if ground["planeId"] is None and len(m.doc["planes"]) != 1:
        return [], []
    pts = np.array([p for b in m.points.values() for p in b.values()])
    lo, hi = pts.min(axis=0) - 3 * width, pts.max(axis=0) + 3 * width
    plate = [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]
    bosses = [Circle(p, 0.7 * width) for p in m.points[m.ground].values()]
    return [(float(x), float(y)) for x, y in plate], bosses


__all__: list[str] = [
    "Appearance",
    "AppearanceInfeasible",
    "BodyAppearance",
    "Circle",
    "Dressed",
    "WearKind",
    "WearMark",
    "dress",
]

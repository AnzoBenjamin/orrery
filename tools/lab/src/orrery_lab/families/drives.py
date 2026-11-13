"""Gear, belt, intermittent, and cam families, and the sewing machine (requirement 1.1).

Gears are drawn so their pitch circles touch at the drawn pose (center distance = module × the sum
of the teeth over two, or the difference for an internal ring). Mesh phases are zero: the drawn
pose is where the teeth engage, which the renderer reproduces from the gear data.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from orrery_lab.families.four_bar import rocking_profile
from orrery_lab.families.linkages import BRANCH, FRAME_ANGLE, grashof_crank, is_left
from orrery_lab.families.pinned import FRAME, Part, Rotation, draw, dyad
from orrery_lab.family import Built, Infeasible, PartRef, Requirements
from orrery_lab.geometry import Point2, distance, lerp, polar
from orrery_lab.graph import Graph, Json
from orrery_lab.space import Choice, Integer, LogUniform, ParameterSpace, Params, Uniform

FULL_TURN = (0.0, math.tau)
DEFAULT_REQUIREMENTS = Requirements()
TRANSMISSION_15 = Requirements(min_transmission=math.radians(15))
MAX_GEARS = 4


def gear_data(teeth: int, module: float, internal: bool = False) -> Json:
    return {"gear": {"teeth": teeth, "module": module, "internal": internal}}


@dataclass(frozen=True)
class GearTrain:
    """Two to four spur gears on fixed axles, each meshing with the next; the last may be an
    internal ring around its pinion."""

    name: str = "gear-train"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                # Module in meters: watch and clock wheels to small machine gearing.
                "module": LogUniform(0.0004, 0.004),
                "frame_angle": FRAME_ANGLE,
                "gears": Integer(2, MAX_GEARS),
                **{f"teeth_{i}": Integer(12, 60) for i in range(MAX_GEARS)},
                **{f"direction_{i}": Uniform(-1.2, 1.2) for i in range(MAX_GEARS)},
                "ring": Choice(("no", "yes")),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        count = int(params["gears"])
        module = params["module"]
        teeth = [int(params[f"teeth_{i}"]) for i in range(count)]
        ring = Choice(("no", "yes")).pick(params["ring"]) == "yes"
        if ring and teeth[-1] < teeth[-2] + 8:
            # A ring needs clearly more teeth than the pinion inside it.
            teeth[-1] = teeth[-2] + 8 + teeth[-1] % 12
        turn = Rotation(params["frame_angle"])
        centers: list[Point2] = [(0.0, 0.0)]
        heading = 0.0
        for i in range(1, count):
            internal = ring and i == count - 1
            gap = module * (teeth[i] - teeth[i - 1] if internal else teeth[i] + teeth[i - 1]) / 2
            heading += params[f"direction_{i}"]
            centers.append(polar(centers[-1], gap, heading))
        for i in range(count):
            for j in range(i + 2, count):
                # Gears that do not mesh must not overlap.
                reach = module * (teeth[i] + teeth[j]) / 2 + 2 * module
                if not (ring and j == count - 1) and distance(centers[i], centers[j]) < reach:
                    raise Infeasible("two gears that do not mesh overlap")
        loc = {f"axle-{i}": turn(c) for i, c in enumerate(centers)}
        parts = [Part(FRAME, "Frame", tuple(loc), "ground")]
        for i in range(count):
            internal = ring and i == count - 1
            pitch = module * teeth[i] / 2
            parts.append(
                Part(
                    f"gear-{i}",
                    "ABCD"[i],
                    (f"axle-{i}",),
                    "gear",
                    {
                        "mark": (
                            turn(polar(centers[i], 0.7 * pitch, 0.4 * i)),
                            "output" if i == count - 1 else "tracked",
                        )
                    },
                )
            )
        graph = Graph(sample_id, "Gear train")
        draw(graph, loc, parts, driven=("axle-0", "gear-0"), min_spacing=0.0)
        for i in range(count):
            graph.bodies[f"gear-{i}"].extra.update(
                gear_data(teeth[i], module, internal=ring and i == count - 1)
            )
        for i in range(1, count):
            internal = ring and i == count - 1
            # θA = ratio·θB with ratio = teeth B / teeth A, negative for an external mesh.
            ratio = teeth[i] / teeth[i - 1] * (1.0 if internal else -1.0)
            graph.gear_mesh(f"mesh-{i}", f"gear-{i - 1}", f"gear-{i}", ratio)
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=tuple(PartRef("gear", bodies=(f"gear-{i}",)) for i in range(1, count)),
        )


@dataclass(frozen=True)
class RackAndPinion:
    """A pinion on a fixed axle rocks a rack along a guide."""

    name: str = "rack-and-pinion"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "module": LogUniform(0.0005, 0.004),
                "frame_angle": FRAME_ANGLE,
                "pinion_teeth": Integer(12, 40),
                "rack_teeth": Integer(20, 60),
                "travel": Uniform(0.5, 0.85),
                "start": Uniform(-0.5, 0.5),
                "side": Choice(("below", "above")),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        module = params["module"]
        teeth, rack_teeth = int(params["pinion_teeth"]), int(params["rack_teeth"])
        pitch = module * teeth / 2
        length = math.pi * module * rack_teeth
        below = Choice(("below", "above")).pick(params["side"]) == "below"
        turn = Rotation(params["frame_angle"])
        # The rack's pitch line touches the pinion's pitch circle. Below the pinion it runs +x
        # when the pinion turns counter-clockwise; above, -x.
        line_y = -pitch if below else pitch
        ratio = pitch if below else -pitch
        half_travel = 0.5 * length * params["travel"]
        # Drawn with the pinion partway along the rack; the limits are the rack's ends.
        offset = params["start"] * (0.5 * length - half_travel)
        lo, hi = -half_travel - offset, half_travel - offset
        axis = turn((1.0, 0.0))
        loc = {"axle": turn((0.0, 0.0))}
        depth = 2.5 * module * (-1.0 if below else 1.0)
        graph = Graph(sample_id, "Rack and pinion")
        draw(
            graph,
            loc,
            [
                Part(
                    FRAME,
                    "Frame",
                    ("axle",),
                    "ground",
                    {"guide": (turn((0.0, line_y)), "joint_anchor")},
                ),
                Part(
                    "pinion",
                    "A",
                    ("axle",),
                    "gear",
                    {"mark": (turn(polar((0.0, 0.0), 0.7 * pitch, 0.3)), "tracked")},
                ),
                Part(
                    "rack",
                    "B",
                    (),
                    "gear",
                    {
                        "pitch": (turn((0.0, line_y)), "joint_anchor"),
                        "end": (turn((0.5 * length - offset, line_y + depth)), "output"),
                    },
                ),
            ],
            driven=("axle", "pinion"),
            min_spacing=0.0,
        )
        graph.bodies["pinion"].extra.update(gear_data(teeth, module))
        graph.bodies["rack"].extra.update(gear_data(rack_teeth, module))
        margin = 0.02 * length
        graph.prismatic(
            "j-guide", FRAME, "guide", "rack", "pitch", axis=axis, limits=(lo - margin, hi + margin)
        )
        graph.joints.append(
            {
                "id": "mesh-rack",
                "kind": "gear_mesh",
                "bodyA": "pinion",
                "bodyB": "rack",
                "ratio": ratio,
                "phase": 0.0,
                "rack": {"axisLocalB": {"x": axis[0], "y": axis[1], "z": 0.0}},
                "status": "observed",
                "confidence": 1.0,
            }
        )
        drive_range = (lo / ratio, hi / ratio) if ratio > 0 else (hi / ratio, lo / ratio)
        document = graph.document()
        document["drivers"][0]["profile"] = rocking_profile(*drive_range)
        return Built(
            document,
            drive_range,
            cyclic=False,
            breakable=(PartRef("gear", bodies=("rack",)), PartRef("gear", bodies=("pinion",))),
        )


@dataclass(frozen=True)
class BeltDrive:
    """A driving pulley turns one or two others by open or crossed belts."""

    name: str = "belt-drive"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": LogUniform(0.05, 0.5),
                "frame_angle": FRAME_ANGLE,
                "pulleys": Integer(2, 3),
                **{f"radius_{i}": Uniform(0.06, 0.25) for i in range(3)},
                **{f"span_{i}": Uniform(0.5, 1.0) for i in range(1, 3)},
                **{f"direction_{i}": Uniform(-math.pi, math.pi) for i in range(1, 3)},
                **{f"crossed_{i}": Choice(("open", "crossed")) for i in range(1, 3)},
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        count = int(params["pulleys"])
        unit = params["scale"]
        radii = [params[f"radius_{i}"] * unit for i in range(count)]
        turn = Rotation(params["frame_angle"])
        centers: list[Point2] = [
            (0.0, 0.0),
            *(
                polar((0.0, 0.0), params[f"span_{i}"] * unit, params[f"direction_{i}"])
                for i in range(1, count)
            ),
        ]
        for i in range(count):
            for j in range(i + 1, count):
                if distance(centers[i], centers[j]) < 1.3 * (radii[i] + radii[j]):
                    raise Infeasible("two pulleys overlap")
        loc = {f"axle-{i}": turn(c) for i, c in enumerate(centers)}
        parts = [
            Part(FRAME, "Frame", tuple(loc), "ground"),
            *(
                Part(
                    f"pulley-{i}",
                    "ABC"[i],
                    (f"axle-{i}",),
                    "pulley",
                    {
                        "mark": (
                            turn(polar(centers[i], 0.8 * radii[i], 0.5 * i)),
                            "output" if i == count - 1 else "tracked",
                        )
                    },
                )
                for i in range(count)
            ),
        ]
        graph = Graph(sample_id, "Belt drive")
        draw(graph, loc, parts, driven=("axle-0", "pulley-0"), min_spacing=0.0)
        belts: list[str] = []
        for i in range(count):
            graph.bodies[f"pulley-{i}"].extra["pulley"] = {"radius": radii[i]}
        for i in range(1, count):
            crossed = Choice(("open", "crossed")).pick(params[f"crossed_{i}"]) == "crossed"
            # The driver turns radius B / radius A times as far as pulley B.
            belts.append(
                graph.belt(f"belt-{i}", "pulley-0", f"pulley-{i}", radii[i] / radii[0], crossed)
            )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=tuple(PartRef("belt", joints=(b,)) for b in belts),
        )


@dataclass(frozen=True)
class GenevaDrive:
    """A Geneva drive over one indexing motion: the driver's pin enters a radial slot of the
    wheel, turns it by one slot pitch (2π/n), and leaves. Between indexings the wheel is held by
    the locking disk, a contact the schema does not describe, so a sample covers the engaged arc
    from just after the pin enters to just before it leaves."""

    name: str = "geneva-drive"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": LogUniform(0.03, 0.3),
                "frame_angle": FRAME_ANGLE,
                "slots": Integer(4, 8),
                "engagement": Uniform(0.85, 0.95),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        n = int(params["slots"])
        center = params["scale"]
        # The pin enters and leaves tangentially: crank radius = center distance · sin(π/n).
        crank = center * math.sin(math.pi / n)
        wheel = center * math.cos(math.pi / n)
        half_arc = (0.5 * math.pi - math.pi / n) * params["engagement"]
        turn = Rotation(params["frame_angle"])
        g = (center, 0.0)
        pin = (crank, 0.0)
        loc = {"o": turn((0.0, 0.0)), "g": turn(g), "pin": turn(pin)}
        # The slot runs along the wheel's radius toward the driver, from just inside the pin's
        # deepest point to the rim.
        start = turn((center - 0.9 * (center - crank), 0.0))
        end = turn((center - 1.02 * wheel, 0.0))
        graph = Graph(sample_id, f"Geneva drive ({n} slots)")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o", "g"), "ground"),
                Part("driver", "A", ("o", "pin")),
                Part(
                    "wheel",
                    "B",
                    ("g",),
                    own={"rim": (turn(polar(g, 0.9 * wheel, math.pi + math.pi / n)), "output")},
                ),
            ],
            driven=("o", "driver"),
            min_spacing=0.01 * center,
        )
        graph.pin_in_slot("j-slot", "driver", "pin", "wheel", start=start, end=end)
        document = graph.document()
        # One indexing at one turn per second of the driver.
        document["drivers"][0]["profile"] = {
            "type": "samples",
            "t": [0.0, 2 * half_arc / math.tau],
            "q": [-half_arc, half_arc],
        }
        return Built(
            document,
            (-half_arc, half_arc),
            cyclic=True,
            breakable=(PartRef("binary_link", bodies=("wheel",)),),
        )


FollowerKind = Literal["knife", "roller", "flat"]


@dataclass(frozen=True)
class CamProfile:
    base: float
    a: tuple[float, ...]
    b: tuple[float, ...]

    def radius(self, phi: float) -> tuple[float, float, float]:
        """r, dr/dφ, d²r/dφ² at profile angle φ (in the cam's frame)."""
        r, d1, d2 = self.base, 0.0, 0.0
        for k, (ak, bk) in enumerate(zip(self.a, self.b, strict=True)):
            if k == 0:
                r += ak
                continue
            c, s = math.cos(k * phi), math.sin(k * phi)
            r += ak * c + bk * s
            d1 += k * (-ak * s + bk * c)
            d2 += -k * k * (ak * c + bk * s)
        return r, d1, d2

    def point(self, phi: float) -> Point2:
        r = self.radius(phi)[0]
        return (r * math.cos(phi), r * math.sin(phi))

    def normal(self, phi: float) -> Point2:
        """Outward unit normal of the profile at φ."""
        r, d1, _ = self.radius(phi)
        tx = d1 * math.cos(phi) - r * math.sin(phi)
        ty = d1 * math.sin(phi) + r * math.cos(phi)
        n = math.hypot(tx, ty)
        return (ty / n, -tx / n)

    def turned(self, angle: float) -> CamProfile:
        """The same profile turned by `angle` (counter-clockwise) in the cam's frame."""
        a, b = [self.a[0]], [self.b[0]]
        for k in range(1, len(self.a)):
            c, s = math.cos(k * angle), math.sin(k * angle)
            a.append(self.a[k] * c - self.b[k] * s)
            b.append(self.a[k] * s + self.b[k] * c)
        return CamProfile(self.base, tuple(a), tuple(b))

    def least_curvature_radius(self) -> float:
        """The least radius of curvature over the profile (negative where it is concave)."""
        least = math.inf
        for phi in np.linspace(0.0, math.tau, 720, endpoint=False):
            r, d1, d2 = self.radius(float(phi))
            curvature = (r * r + 2 * d1 * d1 - r * d2) / (r * r + d1 * d1) ** 1.5
            least = min(least, 1.0 / curvature if curvature > 0 else -math.inf)
        return least


def solve_angle(f: Callable[[float], float], lo: float, hi: float) -> float:
    """A root of `f` between `lo` and `hi` by bisection; `f(lo)` and `f(hi)` differ in sign."""
    flo = f(lo)
    if flo * f(hi) > 0:
        raise Infeasible("the follower line misses the cam")
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class CamFollower:
    """A disk cam turns under a translating follower held to it: a knife edge, a roller, or a
    flat face. The profile is a short Fourier series kept convex, so every follower stays in
    contact at one point; a return spring loads the follower as in a real machine."""

    kind: FollowerKind

    @property
    def name(self) -> str:
        return f"cam-follower-{self.kind}"

    @property
    def requirements(self) -> Requirements:
        return DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "base": LogUniform(0.01, 0.08),
                "frame_angle": FRAME_ANGLE,
                **{f"a_{k}": Uniform(-0.18, 0.18) for k in range(1, 4)},
                **{f"b_{k}": Uniform(-0.18, 0.18) for k in range(1, 4)},
                "offset": Uniform(-0.3, 0.3),
                "roller": Uniform(0.15, 0.4),
                "stiffness": LogUniform(50.0, 2000.0),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        base = params["base"]
        harmonics = range(1, 4)
        # Higher harmonics are damped so the profile stays smooth.
        cam = CamProfile(
            base,
            (0.0, *(params[f"a_{k}"] * base / k for k in harmonics)),
            (0.0, *(params[f"b_{k}"] * base / k for k in harmonics)),
        )
        roller = params["roller"] * base if self.kind == "roller" else 0.0
        if cam.least_curvature_radius() < max(0.1 * base, 1.2 * roller):
            raise Infeasible("the cam profile is not convex enough for the follower")
        e = params["offset"] * base if self.kind != "flat" else 0.0
        if self.kind == "knife":
            phi = solve_angle(lambda p: cam.point(p)[0] - e, 0.05, math.pi - 0.05)
            contact = cam.point(phi)
        elif self.kind == "roller":

            def center_x(p: float) -> float:
                return cam.point(p)[0] + roller * cam.normal(p)[0] - e

            phi = solve_angle(center_x, 0.05, math.pi - 0.05)
            px, py = cam.point(phi)
            nx, ny = cam.normal(phi)
            contact = (px + roller * nx, py + roller * ny)
        else:
            # The highest point of the profile, where dy/dφ = ρ' sin φ + ρ cos φ changes sign.
            grid = np.linspace(0.0, math.pi, 2001)
            k = int(np.argmax([cam.point(float(p))[1] for p in grid]))

            def rise(p: float) -> float:
                r, d1, _ = cam.radius(p)
                return d1 * math.sin(p) + r * math.cos(p)

            phi = solve_angle(rise, float(grid[max(k - 1, 0)]), float(grid[min(k + 1, 2000)]))
            contact = (0.0, cam.point(phi)[1])
        # A flat face lies along the follower's local x axis, which is the world x axis in the
        # drawn pose, so a flat-faced follower is drawn moving along world y.
        angle = 0.0 if self.kind == "flat" else params["frame_angle"]
        turn = Rotation(angle)
        up = turn((0.0, 1.0))
        rest = contact[1] + 0.5 * base
        loc = {"shaft": turn((0.0, 0.0))}
        graph = Graph(sample_id, f"Cam with {self.kind} follower")
        draw(
            graph,
            loc,
            [
                Part(
                    FRAME,
                    "Frame",
                    ("shaft",),
                    "ground",
                    {
                        "guide": (turn((e, 0.0)), "joint_anchor"),
                        "seat": (turn((e, rest + 1.5 * base)), "joint_anchor"),
                    },
                ),
                Part("cam", "A", ("shaft",), "cam"),
                Part(
                    "follower",
                    "B",
                    (),
                    "slider_block",
                    {
                        "contact": (turn(contact), "joint_anchor"),
                        "stem": (turn((e, rest)), "joint_anchor"),
                        "top": (turn((e, rest + 0.5 * base)), "output"),
                    },
                ),
            ],
            driven=("shaft", "cam"),
            min_spacing=0.0,
        )
        # The profile turns with the drawing (its frame is the world frame in the drawn pose).
        drawn = cam.turned(angle)
        graph.bodies["cam"].extra["cam"] = {
            "baseRadius": base,
            "fourier": {"a": list(drawn.a), "b": list(drawn.b)},
        }
        graph.prismatic("j-guide", FRAME, "guide", "follower", "stem", axis=up)
        graph.cam_follower(
            "j-contact",
            "cam",
            "follower",
            "contact",
            kind=self.kind,
            roller_radius=roller if self.kind == "roller" else None,
        )
        graph.spring(
            "spring",
            FRAME,
            "seat",
            "follower",
            "top",
            stiffness=params["stiffness"],
            free_length=2.5 * base,
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(PartRef("slider_block", bodies=("follower",)),),
        )


@dataclass(frozen=True)
class SewingMachine:
    """A household sewing machine's head: the main shaft's crank drives the needle bar up and down
    through a connecting link (a slider-crank), and the same crank pin carries the take-up lever,
    steadied by a short rocker link, whose eye pulls the thread through each stitch."""

    name: str = "sewing-machine"
    requirements: Requirements = TRANSMISSION_15

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": LogUniform(0.06, 0.25),
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                "crank": Uniform(0.12, 0.2),
                "needle_link": Uniform(0.5, 0.8),
                "lever": Uniform(0.4, 0.8),
                "rocker": Uniform(0.3, 0.6),
                "rocker_pivot_x": Uniform(0.3, 0.7),
                "rocker_pivot_y": Uniform(-0.2, 0.3),
                "branch": BRANCH,
                "eye_reach": Uniform(1.2, 1.8),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"]
        crank, link = params["crank"] * unit, params["needle_link"] * unit
        lever, rocker = params["lever"] * unit, params["rocker"] * unit
        o = (0.0, 0.0)
        o3 = (params["rocker_pivot_x"] * unit, params["rocker_pivot_y"] * unit)
        pa = polar(o, crank, params["input_angle"])
        # The needle bar slides vertically below the shaft.
        needle = (0.0, pa[1] - math.sqrt(link * link - pa[0] ** 2))
        grashof_crank((distance(o, o3), crank, lever, rocker))
        pb = dyad(pa, lever, o3, rocker, is_left(params))
        eye = lerp(pa, pb, params["eye_reach"])
        turn = Rotation(params["frame_angle"])
        canonical = {"o": o, "o3": o3, "a": pa, "n": needle, "b": pb}
        loc = {k: turn(v) for k, v in canonical.items()}
        graph = Graph(sample_id, "Sewing machine needle bar and take-up lever")
        draw(
            graph,
            loc,
            [
                Part(
                    FRAME, "Frame", ("o", "o3"), "ground", {"bar-guide": (loc["o"], "joint_anchor")}
                ),
                Part("crank", "A", ("o", "a")),
                Part("needle-link", "B", ("a", "n")),
                Part(
                    "needle-bar",
                    "C",
                    ("n",),
                    "slider_block",
                    {"needle": (turn((0.0, needle[1] - 0.6 * unit)), "output")},
                ),
                Part("take-up", "D", ("a", "b"), own={"eye": (turn(eye), "output")}),
                Part("rocker", "E", ("b", "o3")),
            ],
            driven=("o", "crank"),
            min_spacing=0.03 * unit,
        )
        graph.prismatic("j-bar", FRAME, "bar-guide", "needle-bar", "n", axis=turn((0.0, 1.0)))
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("needle-link",)),
                PartRef("binary_link", bodies=("rocker",)),
                PartRef("binary_link", bodies=("take-up",)),
                PartRef("slider_block", bodies=("needle-bar",)),
            ),
        )


FAMILIES = (
    GearTrain(),
    RackAndPinion(),
    BeltDrive(),
    GenevaDrive(),
    *(CamFollower(k) for k in ("knife", "roller", "flat")),
    SewingMachine(),
)

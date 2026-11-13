"""Pin-jointed linkage families beyond the four-bar (requirement 1.1).

Six-bar names follow McCarthy and Soh, *Geometric Design of Linkages* (2nd ed., 2010): starting
from a four-bar (frame, input, coupler, output), two more links are added as a dyad between

- Watt I: the coupler and the output (the two ternary links share a joint);
- Watt II: the output and the frame (two four-bars in series);
- Stephenson I: the input and the output (the frame is a binary link of the four-bar loop);
- Stephenson II: the frame is a binary link of the five-bar loop (drawn directly from that chain);
- Stephenson III: the coupler and the frame (the frame is ternary).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from orrery_lab.families.four_bar import rocking_profile
from orrery_lab.families.pinned import FRAME, Part, Rotation, draw, dyad, dyad_by
from orrery_lab.family import Built, Infeasible, PartRef, Requirements
from orrery_lab.geometry import Point2, distance, lerp, offset, polar
from orrery_lab.graph import Graph
from orrery_lab.space import Choice, LogUniform, ParameterSpace, Params, Uniform

FULL_TURN = (0.0, math.tau)
SCALE = LogUniform(0.04, 0.4)
FRAME_ANGLE = Uniform(-math.pi, math.pi)
BRANCH = Choice(("left", "right"))


TRANSMISSION_15 = Requirements(min_transmission=math.radians(15))
TRANSMISSION_10 = Requirements(min_transmission=math.radians(10))
ANY_TRANSMISSION = Requirements(min_transmission=0.0)
DEFAULT_REQUIREMENTS = Requirements()


def is_left(params: Params, key: str = "branch") -> bool:
    return BRANCH.pick(params[key]) == "left"


def grashof_crank(lengths: tuple[float, float, float, float], margin: float = 0.05) -> None:
    """Raises unless the second length (the input) is the shortest and the loop is Grashof."""
    s = sorted(lengths)
    if lengths[1] != s[0] or s[0] + s[3] > s[1] + s[2] - margin * s[3]:
        raise Infeasible("the input cannot turn fully")


SixBarKind = Literal["watt-1", "watt-2", "stephenson-1", "stephenson-2", "stephenson-3"]


@dataclass(frozen=True)
class SixBar:
    kind: SixBarKind

    @property
    def name(self) -> str:
        return f"six-bar-{self.kind}"

    @property
    def requirements(self) -> Requirements:
        return Requirements(min_transmission=math.radians(15))

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                "frame": Uniform(0.6, 1.2),
                "input": Uniform(0.15, 0.4),
                "coupler": Uniform(0.6, 1.3),
                "output": Uniform(0.5, 1.2),
                "branch": BRANCH,
                "attach_along": Uniform(0.2, 0.9),
                "attach_across": Uniform(-0.7, 0.7),
                "far_along": Uniform(0.2, 1.4),
                "far_across": Uniform(-0.8, 0.8),
                "dyad_first": Uniform(0.6, 1.4),
                "dyad_second": Uniform(0.6, 1.4),
                "dyad_branch": BRANCH,
                "output_extension": Uniform(1.0, 1.3),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"] / 2.5
        g, a, c, o = (params[k] * unit for k in ("frame", "input", "coupler", "output"))
        turn = Rotation(params["frame_angle"])
        o2, o4 = (0.0, 0.0), (g, 0.0)
        pa = polar(o2, a, params["input_angle"])

        if self.kind == "stephenson-2":
            return self._stephenson_2(params, unit, turn, pa, sample_id)

        grashof_crank((g, a, c, o))
        pb = dyad(pa, c, o4, o, is_left(params))
        along, across = params["attach_along"], params["attach_across"]
        far_along, far_across = params["far_along"], params["far_across"]
        # Where the dyad attaches at each end, by kind.
        start_on, end_on = {
            "watt-1": ("coupler", "output"),
            "watt-2": ("output", FRAME),
            "stephenson-1": ("input", "output"),
            "stephenson-3": ("coupler", FRAME),
        }[self.kind]
        segment = {"input": (o2, pa), "coupler": (pa, pb), "output": (o4, pb), FRAME: (o2, o4)}
        pc = offset(*segment[start_on], along, across)
        pd = offset(*segment[end_on], far_along, far_across)
        span = distance(pc, pd)
        pe = dyad(
            pc,
            span * params["dyad_first"],
            pd,
            span * params["dyad_second"],
            is_left(params, "dyad_branch"),
        )
        tip = lerp(pd, pe, params["output_extension"])
        end_pin = "o6" if end_on == FRAME else "d"
        canonical = {"o2": o2, "o4": o4, "a": pa, "b": pb, "c": pc, end_pin: pd, "e": pe}
        loc = {k: turn(v) for k, v in canonical.items()}

        def pins(body: str, *base: str) -> tuple[str, ...]:
            return (
                base + (("c",) if start_on == body else ()) + ((end_pin,) if end_on == body else ())
            )

        parts = [
            Part(FRAME, "Frame", pins(FRAME, "o2", "o4"), "ground"),
            Part("input", "A", pins("input", "o2", "a")),
            Part(
                "coupler",
                "B",
                pins("coupler", "a", "b"),
                own={"trace": (turn(offset(pa, pb, 0.5, 0.3)), "tracked")},
            ),
            Part("output", "C", pins("output", "b", "o4")),
            Part("dyad-near", "D", ("c", "e")),
            Part("dyad-far", "E", ("e", end_pin), own={"tip": (turn(tip), "output")}),
        ]
        return self._finish(sample_id, loc, parts, unit)

    def _stephenson_2(
        self,
        params: Params,
        unit: float,
        turn: Rotation,
        pa: Point2,
        sample_id: str,
    ) -> Built:
        # Input (ternary: o2, a, c) and the floating ternary (b, d, e) are joined by two binary
        # links (a-b, c-d): a four-bar loop off the frame. The floating ternary drives a rocker
        # (e-o6) on the frame, which closes the five-bar loop through the binary frame (o2, o6).
        o2 = (0.0, 0.0)
        pc = offset(o2, pa, params["attach_along"], params["attach_across"])
        pb = polar(pa, params["coupler"] * unit, params["input_angle"] + 0.5 * math.pi)
        pd = dyad(pc, params["output"] * unit, pb, distance(pa, pb), is_left(params))
        pe = offset(pb, pd, params["far_along"], params["far_across"])
        o6 = polar(pe, params["frame"] * unit, params["input_angle"] - 0.5 * math.pi)
        tip = lerp(o6, pe, params["output_extension"])
        canonical = {"o2": o2, "a": pa, "c": pc, "b": pb, "d": pd, "e": pe, "o6": o6}
        loc = {k: turn(v) for k, v in canonical.items()}
        parts = [
            Part(FRAME, "Frame", ("o2", "o6"), "ground"),
            Part("input", "A", ("o2", "a", "c")),
            Part("link-ab", "B", ("a", "b")),
            Part("link-cd", "C", ("c", "d")),
            Part(
                "floating",
                "D",
                ("b", "d", "e"),
                own={"trace": (turn(lerp(pb, pd, 0.5)), "tracked")},
            ),
            Part("rocker", "E", ("e", "o6"), own={"tip": (turn(tip), "output")}),
        ]
        return self._finish(sample_id, loc, parts, unit)

    def _finish(
        self, sample_id: str, loc: dict[str, Point2], parts: list[Part], unit: float
    ) -> Built:
        graph = Graph(sample_id, f"Six-bar ({self.kind.replace('-', ' ')})")
        draw(graph, loc, parts, driven=("o2", "input"), min_spacing=0.05 * unit)
        binaries = tuple(
            p.id
            for p in parts
            if len(p.pins) == 2 and p.id not in {FRAME, "input"}  # noqa: PLR2004
        )
        last_two = (parts[-2].id, parts[-1].id)
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                *(PartRef("binary_link", bodies=(b,)) for b in binaries),
                PartRef("adjacent_links", bodies=last_two),
            ),
        )


@dataclass(frozen=True)
class ChebyshevLambda:
    """Chebyshev's lambda linkage: frame 2, crank 1, coupler and rocker 2.5, with the tracing
    point at the end of the coupler extended to 5. Over part of the turn the point moves on a
    nearly straight line. The lengths vary by up to 2% around those proportions."""

    name: str = "chebyshev-lambda"
    #: The proportions give a least transmission angle near 23 degrees.
    requirements: Requirements = TRANSMISSION_15

    def parameter_space(self) -> ParameterSpace:
        tolerance = Uniform(0.98, 1.02)
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                "frame": tolerance,
                "crank": tolerance,
                "coupler": tolerance,
                "rocker": tolerance,
                "extension": tolerance,
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"] / 5.0
        g, a = 2.0 * unit * params["frame"], unit * params["crank"]
        c, r = 2.5 * unit * params["coupler"], 2.5 * unit * params["rocker"]
        turn = Rotation(params["frame_angle"])
        o2, o4 = (0.0, 0.0), (g, 0.0)
        pb = polar(o2, a, params["input_angle"])
        pc = dyad(pb, c, o4, r, True)
        pen = lerp(pb, pc, 2.0 * params["extension"])
        loc = {k: turn(v) for k, v in {"o2": o2, "o4": o4, "b": pb, "c": pc}.items()}
        graph = Graph(sample_id, "Chebyshev lambda")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o2", "o4"), "ground"),
                Part("crank", "A", ("o2", "b")),
                Part("lambda", "B", ("b", "c"), own={"pen": (turn(pen), "output")}),
                Part("rocker", "C", ("c", "o4")),
            ],
            driven=("o2", "crank"),
            min_spacing=0.1 * unit,
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("rocker",)),
                PartRef("binary_link", bodies=("lambda",)),
                PartRef("adjacent_links", bodies=("lambda", "rocker")),
            ),
        )


@dataclass(frozen=True)
class PeaucellierLipkin:
    """Peaucellier–Lipkin inversor: a rhombus of side `s` held at opposite corners by two arms of
    length `l` from a fixed pivot O. Its other two corners A and P stay inverse points about O
    (|OA|·|OP| = l² − s²), so with A on a circle through O, P draws an exact straight line. The
    input arm carrying A rocks."""

    name: str = "peaucellier-lipkin"
    requirements: Requirements = TRANSMISSION_10

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "side": Uniform(0.3, 0.6),
                "arm": Uniform(0.3, 0.6),
                "input_angle": Uniform(0.0, 1.0),
                "branch": BRANCH,
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        long = params["scale"]
        s, r = params["side"] * long, params["arm"] * long
        # |OA| = 2r·cos(α/2) must stay inside (l − s, l + s), with a margin at each end.
        margin = 0.08
        if 2 * r >= (long + s) * (1 - margin) or 2 * r <= (long - s) * (1 + margin):
            raise Infeasible("the arm circle does not fit the rhombus's reach")
        alpha_max = 2 * math.acos((long - s) * (1 + margin) / (2 * r)) * (1 - margin)
        alpha0 = (2 * params["input_angle"] - 1) * 0.5 * alpha_max
        turn = Rotation(params["frame_angle"])
        o, q = (0.0, 0.0), (r, 0.0)
        pa = polar(q, r, alpha0)
        left = is_left(params)
        pb = dyad(o, long, pa, s, left)
        pd = dyad(o, long, pa, s, not left)
        pp = (pb[0] + pd[0] - pa[0], pb[1] + pd[1] - pa[1])
        canonical = {"o": o, "q": q, "a": pa, "b": pb, "d": pd, "p": pp}
        loc = {k: turn(v) for k, v in canonical.items()}
        graph = Graph(sample_id, "Peaucellier–Lipkin inversor")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o", "q"), "ground"),
                Part("arm", "A", ("q", "a")),
                Part("long-b", "B", ("o", "b")),
                Part("long-d", "C", ("o", "d")),
                Part("side-ab", "D", ("a", "b")),
                Part("side-ad", "E", ("a", "d")),
                Part("side-bp", "F", ("b", "p"), own={"pen": (loc["p"], "output")}),
                Part("side-dp", "G", ("d", "p")),
            ],
            driven=("q", "arm"),
            min_spacing=0.03 * long,
        )
        drive_range = (-alpha_max / 2 - alpha0, alpha_max / 2 - alpha0)
        document = graph.document()
        document["drivers"][0]["profile"] = rocking_profile(*drive_range)
        return Built(
            document,
            drive_range,
            cyclic=False,
            breakable=(
                PartRef("binary_link", bodies=("side-bp",)),
                PartRef("binary_link", bodies=("long-b",)),
                PartRef("adjacent_links", bodies=("side-bp", "side-dp")),
            ),
        )


@dataclass(frozen=True)
class Pantograph:
    """A pantograph copying a crank pin's circle at scale `k` about its fixed pivot O. The
    parallelogram C-A-D-T keeps O, the tracer T, and the pen P in line with |OP| = k·|OT|."""

    name: str = "pantograph"
    requirements: Requirements = ANY_TRANSMISSION

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                "ratio": Uniform(1.5, 3.0),
                "crank": Uniform(0.08, 0.2),
                "tracer_distance": Uniform(0.35, 0.6),
                "elbow_angle": Uniform(0.5, 1.2),
                "elbow_reach": Uniform(0.7, 1.1),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        k = params["ratio"]
        reach = params["scale"]
        o = (0.0, 0.0)
        q = (params["tracer_distance"] * reach / k, 0.0)
        pt = polar(q, params["crank"] * reach / k, params["input_angle"])
        pp = (k * pt[0], k * pt[1])
        # The elbow A sits off the line O-P, so the arms meet at an angle.
        pa = polar(o, params["elbow_reach"] * distance(o, pp), params["elbow_angle"])
        pc = (pa[0] / k, pa[1] / k)
        pd = (pa[0] + (pp[0] - pa[0]) / k, pa[1] + (pp[1] - pa[1]) / k)
        turn = Rotation(params["frame_angle"])
        canonical = {"o": o, "q": q, "t": pt, "a": pa, "c": pc, "d": pd}
        loc = {k_: turn(v) for k_, v in canonical.items()}
        graph = Graph(sample_id, "Pantograph")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o", "q"), "ground"),
                Part("crank", "A", ("q", "t")),
                Part("arm-oa", "B", ("o", "c", "a")),
                Part("arm-ap", "C", ("a", "d"), own={"pen": (turn(pp), "output")}),
                Part("link-ct", "D", ("c", "t")),
                Part("link-dt", "E", ("d", "t")),
            ],
            driven=("q", "crank"),
            min_spacing=0.02 * reach,
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("link-ct",)),
                PartRef("binary_link", bodies=("link-dt",)),
                PartRef("adjacent_links", bodies=("link-dt", "arm-ap")),
            ),
        )


#: Theo Jansen's "holy numbers" for the Strandbeest leg, in his units.
HOLY = {
    "a": 38.0,
    "b": 41.5,
    "c": 39.3,
    "d": 40.1,
    "e": 55.8,
    "f": 39.4,
    "g": 36.7,
    "h": 65.7,
    "i": 49.0,
    "j": 50.0,
    "k": 61.9,
    "l": 7.8,
    "m": 15.0,
}


@dataclass(frozen=True)
class JansenLeg:
    """One Strandbeest leg (Theo Jansen): a crank and seven links whose foot traces a flat
    walking stride. The lengths vary by up to 2% around the holy numbers."""

    name: str = "jansen-leg"
    requirements: Requirements = TRANSMISSION_10

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                **{f"len_{k}": Uniform(0.98, 1.02) for k in HOLY},
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"] / 120.0
        n = {k: v * params[f"len_{k}"] * unit for k, v in HOLY.items()}
        o = (0.0, 0.0)
        z = (-n["a"], -n["l"])
        pa = polar(o, n["m"], params["input_angle"])

        def below(p: Point2) -> float:
            return p[1]

        def left(p: Point2) -> float:
            return p[0]

        p3 = dyad_by(pa, n["j"], z, n["b"], lambda p: -p[1])  # above
        p4 = dyad_by(z, n["d"], p3, n["e"], left)
        p5 = dyad_by(pa, n["k"], z, n["c"], below)
        p6 = dyad_by(p4, n["f"], p5, n["g"], left)
        p7 = dyad_by(p6, n["h"], p5, n["i"], below)
        turn = Rotation(params["frame_angle"])
        canonical = {"o": o, "z": z, "a": pa, "p3": p3, "p4": p4, "p5": p5, "p6": p6}
        loc = {k: turn(v) for k, v in canonical.items()}
        graph = Graph(sample_id, "Jansen leg")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o", "z"), "ground"),
                Part("crank", "A", ("o", "a")),
                Part("link-j", "B", ("a", "p3")),
                Part("upper", "C", ("z", "p3", "p4")),
                Part("link-k", "D", ("a", "p5")),
                Part("link-c", "E", ("z", "p5")),
                Part("link-f", "F", ("p4", "p6")),
                Part("foot", "G", ("p5", "p6"), own={"toe": (turn(p7), "output")}),
            ],
            driven=("o", "crank"),
            min_spacing=2.0 * unit,
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("link-j",)),
                PartRef("binary_link", bodies=("link-k",)),
                PartRef("binary_link", bodies=("link-f",)),
                PartRef("adjacent_links", bodies=("link-f", "foot")),
            ),
        )


@dataclass(frozen=True)
class FlappingWing:
    """A flapping-wing automaton: one crank drives two wing levers through two rods, as in tin
    birds and butterfly toys. Each side is a crank-rocker four-bar sharing the crank."""

    name: str = "flapping-wing"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return ParameterSpace(
            {
                "scale": SCALE,
                "frame_angle": FRAME_ANGLE,
                "input_angle": Uniform(0.0, math.tau),
                "crank": Uniform(0.08, 0.2),
                "pivot_spread": Uniform(0.2, 0.5),
                "pivot_height": Uniform(0.5, 1.0),
                "short_arm": Uniform(0.15, 0.35),
                "arm_angle": Uniform(-0.6, 0.6),
                "wing": Uniform(1.5, 3.0),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        unit = params["scale"] / (params["pivot_spread"] + params["wing"] * params["short_arm"])
        crank = params["crank"] * unit
        spread, height = params["pivot_spread"] * unit, params["pivot_height"] * unit
        arm = params["short_arm"] * unit
        o = (0.0, 0.0)
        pa = polar(o, crank, params["input_angle"])
        sides: dict[str, tuple[Point2, Point2, Point2]] = {}
        for side, sign in (("l", -1.0), ("r", 1.0)):
            pivot = (sign * spread, height)
            # The short arm points down and inward, toward the crank; the wing continues past the
            # pivot, out and up.
            joint = polar(pivot, arm, -0.5 * math.pi - sign * (0.4 + params["arm_angle"]))
            tip = lerp(joint, pivot, 1.0 + params["wing"])
            grashof_crank((distance(o, pivot), crank, distance(pa, joint), arm))
            sides[side] = (pivot, joint, tip)
        turn = Rotation(params["frame_angle"])
        canonical = {
            "o": o,
            "a": pa,
            "wl": sides["l"][0],
            "sl": sides["l"][1],
            "wr": sides["r"][0],
            "sr": sides["r"][1],
        }
        loc = {k: turn(v) for k, v in canonical.items()}
        graph = Graph(sample_id, "Flapping-wing automaton")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o", "wl", "wr"), "ground"),
                Part("crank", "A", ("o", "a")),
                Part("rod-left", "B", ("a", "sl")),
                Part("rod-right", "C", ("a", "sr")),
                Part("wing-left", "D", ("wl", "sl"), own={"tip": (turn(sides["l"][2]), "output")}),
                Part("wing-right", "E", ("wr", "sr"), own={"tip": (turn(sides["r"][2]), "output")}),
            ],
            driven=("o", "crank"),
            min_spacing=0.03 * unit,
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("rod-left",)),
                PartRef("binary_link", bodies=("rod-right",)),
                PartRef("binary_link", bodies=("wing-left",)),
                PartRef("adjacent_links", bodies=("rod-right", "wing-right")),
            ),
        )


FAMILIES = (
    *(SixBar(k) for k in ("watt-1", "watt-2", "stephenson-1", "stephenson-2", "stephenson-3")),
    ChebyshevLambda(),
    PeaucellierLipkin(),
    Pantograph(),
    JansenLeg(),
    FlappingWing(),
)

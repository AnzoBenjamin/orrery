"""Four-bar linkages by Grashof class (requirement 1.1): crank-rocker, double-crank,
double-rocker, and change-point.

With `s` the shortest and `l` the longest of the four lengths and `p`, `q` the others, a Grashof
loop (`s + l < p + q`) has a link that turns fully: the input when it is the shortest
(crank-rocker), the input and output when the frame is shortest (double-crank), the coupler when
it is shortest (double-rocker, whose input rocks). A change-point loop (`s + l = p + q`) folds flat
twice a turn and can change branch there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from orrery_lab.family import Built, Infeasible, PartRef, Requirements
from orrery_lab.geometry import (
    acos_range,
    circle_intersection,
    distance,
    lerp,
    offset,
    polar,
)
from orrery_lab.graph import Graph, Json
from orrery_lab.space import Choice, LogUniform, ParameterSpace, Params, Uniform

FourBarClass = Literal["crank-rocker", "double-crank", "double-rocker", "change-point"]

#: How far inside the Grashof inequality a non-change-point loop must be, as a share of `l`, so
#: that it is not a change-point loop to within rounding.
GRASHOF_MARGIN = 0.05
#: Share of a rocking input's range kept clear at each end.
ROCKING_MARGIN = 0.05
ROCKING_SAMPLES = 33
#: Shortest output a change-point loop may be given, as a share of the scale.
MIN_CHANGE_POINT_OUTPUT = 0.2


def rocking_profile(low: float, high: float) -> Json:
    """One period (2 s) from zero out to `high`, back through zero to `low`, and back."""
    t = np.linspace(0.0, 2.0, ROCKING_SAMPLES)
    q = np.where(t <= 1.0, high * np.sin(math.pi * t), -low * np.sin(math.pi * t))
    return {"type": "samples", "t": t.tolist(), "q": q.tolist()}


@dataclass(frozen=True)
class FourBar:
    kind: FourBarClass

    @property
    def name(self) -> str:
        return f"four-bar-{self.kind}"

    @property
    def requirements(self) -> Requirements:
        if self.kind == "change-point":
            # Folding flat is what the class is: toggles and branch points are expected.
            return Requirements(min_transmission=0.0, allow_bifurcation=True)
        return Requirements()

    def parameter_space(self) -> ParameterSpace:
        short, long = Uniform(0.15, 0.45), Uniform(0.5, 1.2)
        ratios = {
            "crank-rocker": {"frame": long, "input": short, "coupler": long, "output": long},
            "double-crank": {"frame": short, "input": long, "coupler": long, "output": long},
            "double-rocker": {"frame": long, "input": long, "coupler": short, "output": long},
            # The output is solved for from the other three.
            "change-point": {"frame": long, "input": Uniform(0.3, 1.2), "coupler": long},
        }[self.kind]
        return ParameterSpace(
            {
                # Characteristic length in meters: a toy automaton to a loom's treadle linkage.
                "scale": LogUniform(0.04, 0.4),
                **ratios,
                "frame_angle": Uniform(-math.pi, math.pi),
                "input_angle": Uniform(0.0, 1.0),
                "branch": Choice(("open", "crossed")),
                "coupler_along": Uniform(-0.2, 1.2),
                "coupler_across": Uniform(-0.6, 0.6),
                "output_extension": Uniform(1.0, 1.35),
            }
        )

    def _lengths(self, p: Params) -> tuple[float, float, float, float]:
        frame, a, b = p["frame"], p["input"], p["coupler"]
        if self.kind != "change-point":
            return (frame, a, b, p["output"])
        # The output length that makes s + l = p + q, from the candidates that keep it positive
        # and distinct enough from the others to be drawn.
        for c in sorted((frame + b - a, a + b - frame, frame + a - b)):
            if c <= MIN_CHANGE_POINT_OUTPUT:
                continue
            s = sorted((frame, a, b, c))
            if math.isclose(s[0] + s[3], s[1] + s[2], rel_tol=1e-12):
                return (frame, a, b, c)
        raise Infeasible("no output length makes a change-point loop")

    def _classify(self, lengths: tuple[float, float, float, float]) -> None:
        if self.kind == "change-point":
            return
        s = sorted(lengths)
        if s[0] + s[3] > s[1] + s[2] - GRASHOF_MARGIN * s[3]:
            raise Infeasible("not Grashof by the margin")
        shortest = {"crank-rocker": 1, "double-crank": 0, "double-rocker": 2}[self.kind]
        if min(range(4), key=lambda i: lengths[i]) != shortest:
            raise Infeasible("the wrong link is shortest")

    def _input(
        self, params: Params, lengths: tuple[float, float, float, float], cyclic: bool
    ) -> tuple[float, tuple[float, float]]:
        """The drawn input angle from the frame line, and the driver range around it."""
        if cyclic:
            return params["input_angle"] * math.tau, (0.0, math.tau)
        g, a, b, c = lengths
        # The input rocks where the coupler and output can close the loop with a transmission
        # angle of at least the family minimum: |B - O4| between d(μ) and d(π - μ).
        mu = self.requirements.min_transmission
        d_min = math.sqrt(b * b + c * c - 2 * b * c * math.cos(mu))
        d_max = math.sqrt(b * b + c * c + 2 * b * c * math.cos(mu))
        span = acos_range(
            (a * a + g * g - d_max * d_max) / (2 * a * g),
            (a * a + g * g - d_min * d_min) / (2 * a * g),
        )
        if span is None:
            raise Infeasible("the input cannot rock")
        margin = ROCKING_MARGIN * (span[1] - span[0])
        low, high = span[0] + margin, span[1] - margin
        # Drawn somewhere in the middle half of the swing.
        theta0 = low + (0.25 + 0.5 * params["input_angle"]) * (high - low)
        return theta0, (low - theta0, high - theta0)

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng  # every choice is a parameter
        unit = params["scale"]
        g, a, b, c = (x * unit for x in self._lengths(params))
        self._classify((g, a, b, c))
        psi = params["frame_angle"]
        left = Choice(("open", "crossed")).pick(params["branch"]) == "open"

        cyclic = self.kind != "double-rocker"
        theta0, drive_range = self._input(params, (g, a, b, c), cyclic)

        o2 = (0.0, 0.0)
        o4 = polar(o2, g, psi)
        pb = polar(o2, a, psi + theta0)
        pc = circle_intersection(pb, b, o4, c, left)
        if pc is None:
            raise Infeasible("the loop does not close at the drawn input angle")
        trace = offset(pb, pc, params["coupler_along"], params["coupler_across"])
        tip = lerp(o4, pc, params["output_extension"])
        if distance(trace, pb) < 1e-3 * unit or distance(trace, pc) < 1e-3 * unit:
            raise Infeasible("the coupler point sits on a joint")

        graph = Graph(sample_id, f"Four-bar ({self.kind})")
        frame = graph.body("frame", "Frame", "ground")
        frame.point("o2", o2)
        frame.point("o4", o4)
        crank = graph.body("input", "A")
        crank.point("o2", o2)
        crank.point("b", pb)
        coupler = graph.body("coupler", "B")
        coupler.point("b", pb)
        coupler.point("c", pc)
        coupler.point("trace", trace, "tracked")
        output = graph.body("output", "C")
        output.point("o4", o4)
        output.point("c", pc)
        output.point("tip", tip, "output")
        graph.revolute("j-o2", "frame", "o2", "input", "o2")
        graph.revolute("j-b", "input", "b", "coupler", "b")
        graph.revolute("j-c", "coupler", "c", "output", "c")
        graph.revolute("j-o4", "frame", "o4", "output", "o4")
        graph.drive("j-o2")
        document = graph.document()
        if not cyclic:
            document["drivers"][0]["profile"] = rocking_profile(*drive_range)
        return Built(
            document=document,
            drive_range=drive_range,
            cyclic=cyclic,
            breakable=(
                PartRef("binary_link", bodies=("coupler",)),
                PartRef("binary_link", bodies=("output",)),
                PartRef("adjacent_links", bodies=("coupler", "output")),
            ),
        )


FAMILIES = tuple(
    FourBar(kind) for kind in ("crank-rocker", "double-crank", "double-rocker", "change-point")
)

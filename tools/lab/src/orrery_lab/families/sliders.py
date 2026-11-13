"""Families with sliding joints (requirement 1.1): offset slider-crank, inverted slider-crank,
Whitworth quick-return, and Scotch yoke.

Each is drawn in a canonical frame (crank pivot at the origin, slide along +x) and turned by the
sampled frame angle. Sliders keep the orientation of the body they slide on, which in the drawn
pose is the world frame, as the solver's prismatic joint requires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from orrery_lab.families.pinned import FRAME, Part, Rotation, draw
from orrery_lab.family import Built, Infeasible, PartRef, Requirements
from orrery_lab.geometry import Point2, offset, polar, unit
from orrery_lab.graph import Graph
from orrery_lab.space import LogUniform, ParameterSpace, Params, Uniform

FULL_TURN = (0.0, math.tau)


DEFAULT_REQUIREMENTS = Requirements()


def common(extra: dict[str, Uniform | LogUniform]) -> ParameterSpace:
    return ParameterSpace(
        {
            # The longest moving part, in meters.
            "scale": LogUniform(0.04, 0.4),
            "frame_angle": Uniform(-math.pi, math.pi),
            "input_angle": Uniform(0.0, math.tau),
            **extra,
        }
    )


def slide_point(origin: Point2, axis: Point2, length: float) -> Point2:
    return (origin[0] + length * axis[0], origin[1] + length * axis[1])


@dataclass(frozen=True)
class SliderCrank:
    """A crank drives a block along a straight guide through a connecting rod. The guide may be
    offset from the crank pivot (a quick-return effect)."""

    name: str = "slider-crank"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return common(
            {
                "crank": Uniform(0.2, 0.45),
                "offset": Uniform(-0.3, 0.3),
                "rod_along": Uniform(0.2, 0.8),
                "rod_across": Uniform(-0.15, 0.15),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        rod = params["scale"]
        crank, e = params["crank"] * rod, params["offset"] * rod
        turn = Rotation(params["frame_angle"])
        b = polar((0.0, 0.0), crank, params["input_angle"])
        # The slider pin is on the guide line y = e, ahead of the crank.
        c = (b[0] + math.sqrt(rod * rod - (e - b[1]) ** 2), e)
        axis = turn((1.0, 0.0))
        loc = {k: turn(v) for k, v in {"o": (0.0, 0.0), "b": b, "c": c}.items()}
        graph = Graph(sample_id, "Slider-crank")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o",), "ground", {"rail": (turn((0.0, e)), "joint_anchor")}),
                Part("crank", "A", ("o", "b")),
                Part(
                    "rod",
                    "B",
                    ("b", "c"),
                    own={
                        "trace": (
                            offset(loc["b"], loc["c"], params["rod_along"], params["rod_across"]),
                            "tracked",
                        )
                    },
                ),
                Part(
                    "slider",
                    "C",
                    ("c",),
                    "slider_block",
                    {"face": (slide_point(loc["c"], axis, 0.15 * rod), "output")},
                ),
            ],
            driven=("o", "crank"),
            min_spacing=0.02 * rod,
        )
        graph.prismatic("j-guide", FRAME, "rail", "slider", "c", axis=axis)
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("rod",)),
                PartRef("slider_block", bodies=("slider",)),
                PartRef("adjacent_links", bodies=("rod", "slider")),
            ),
        )


@dataclass(frozen=True)
class InvertedSliderCrank:
    """The crank pin carries a block that slides along a lever pivoted on the frame, so the
    lever rocks (the oscillating-cylinder and crank-shaper inversion)."""

    name: str = "inverted-slider-crank"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return common({"pivot_distance": Uniform(1.3, 2.6), "lever_reach": Uniform(1.05, 1.3)})

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        g = params["scale"] / (params["pivot_distance"] + 1.0)
        crank, distance_o4 = g, g * params["pivot_distance"]
        turn = Rotation(params["frame_angle"])
        o4 = (distance_o4, 0.0)
        b = polar((0.0, 0.0), crank, params["input_angle"])
        reach = (distance_o4 + crank) * params["lever_reach"]
        loc = {k: turn(v) for k, v in {"o2": (0.0, 0.0), "o4": o4, "b": b}.items()}
        along = unit(loc["b"][0] - loc["o4"][0], loc["b"][1] - loc["o4"][1])
        graph = Graph(sample_id, "Inverted slider-crank")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o2", "o4"), "ground"),
                Part("crank", "A", ("o2", "b")),
                Part("block", "B", ("b",), "slider_block"),
                Part(
                    "lever",
                    "C",
                    ("o4",),
                    own={"tip": (slide_point(loc["o4"], along, reach), "output")},
                ),
            ],
            driven=("o2", "crank"),
            min_spacing=0.02 * params["scale"],
        )
        graph.prismatic("j-slide", "lever", "o4", "block", "b", axis=along)
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("slider_block", bodies=("block",)),
                PartRef("binary_link", bodies=("lever",)),
            ),
        )


@dataclass(frozen=True)
class Whitworth:
    """Whitworth quick-return: the slotted lever's pivot is inside the crank circle, so the
    lever turns fully but unevenly, and drives a ram through a rod: a slow cutting stroke and a
    quick return."""

    name: str = "whitworth-quick-return"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return common(
            {
                "pivot_distance": Uniform(0.3, 0.7),
                "lever_arm": Uniform(0.6, 1.2),
                "rod": Uniform(2.2, 3.5),
                "ram_height": Uniform(-0.5, 0.5),
            }
        )

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        crank = params["scale"] / 4.0
        g = crank * params["pivot_distance"]
        arm, rod = crank * params["lever_arm"], crank * params["rod"]
        height = crank * params["ram_height"]
        if rod <= arm + abs(height) + 0.05 * crank:
            raise Infeasible("the rod cannot follow the lever's whole turn")
        turn = Rotation(params["frame_angle"])
        o4 = (0.0, g)
        b = polar((0.0, 0.0), crank, params["input_angle"])
        away = unit(o4[0] - b[0], o4[1] - b[1])
        r = (o4[0] + arm * away[0], o4[1] + arm * away[1])
        ram_y = o4[1] + height
        s = (r[0] + math.sqrt(rod * rod - (ram_y - r[1]) ** 2), ram_y)
        canonical = {"o2": (0.0, 0.0), "o4": o4, "b": b, "r": r, "s": s}
        loc = {k: turn(v) for k, v in canonical.items()}
        along = unit(loc["b"][0] - loc["o4"][0], loc["b"][1] - loc["o4"][1])
        axis = turn((1.0, 0.0))
        graph = Graph(sample_id, "Whitworth quick-return")
        draw(
            graph,
            loc,
            [
                Part(
                    FRAME,
                    "Frame",
                    ("o2", "o4"),
                    "ground",
                    {"ram-guide": (turn((0.0, ram_y)), "joint_anchor")},
                ),
                Part("crank", "A", ("o2", "b")),
                Part("block", "B", ("b",), "slider_block"),
                Part("lever", "C", ("o4", "r")),
                Part("rod", "D", ("r", "s")),
                Part(
                    "ram",
                    "E",
                    ("s",),
                    "slider_block",
                    {"tool": (slide_point(loc["s"], axis, 0.5 * crank), "output")},
                ),
            ],
            driven=("o2", "crank"),
            min_spacing=0.05 * crank,
        )
        graph.prismatic("j-slot", "lever", "o4", "block", "b", axis=along)
        graph.prismatic("j-ram", FRAME, "ram-guide", "ram", "s", axis=axis)
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(
                PartRef("binary_link", bodies=("rod",)),
                PartRef("slider_block", bodies=("block",)),
                PartRef("slider_block", bodies=("ram",)),
                PartRef("adjacent_links", bodies=("rod", "ram")),
            ),
        )


@dataclass(frozen=True)
class ScotchYoke:
    """The crank pin runs in a straight slot across a yoke that slides on a guide, giving the
    yoke simple harmonic motion."""

    name: str = "scotch-yoke"
    requirements: Requirements = DEFAULT_REQUIREMENTS

    def parameter_space(self) -> ParameterSpace:
        return common({"slot_margin": Uniform(1.15, 1.5), "rod_reach": Uniform(1.5, 3.0)})

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        del rng
        crank = params["scale"] / (1.0 + params["rod_reach"])
        turn = Rotation(params["frame_angle"])
        b = polar((0.0, 0.0), crank, params["input_angle"])
        half = crank * params["slot_margin"]
        loc = {k: turn(v) for k, v in {"o": (0.0, 0.0), "b": b}.items()}
        guide = turn((b[0], 0.0))
        graph = Graph(sample_id, "Scotch yoke")
        draw(
            graph,
            loc,
            [
                Part(FRAME, "Frame", ("o",), "ground", {"rail": (loc["o"], "joint_anchor")}),
                Part("crank", "A", ("o", "b")),
                Part(
                    "yoke",
                    "B",
                    (),
                    "slider_block",
                    {
                        "guide": (guide, "joint_anchor"),
                        "rod-end": (turn((b[0] + crank * params["rod_reach"], 0.0)), "output"),
                    },
                ),
            ],
            driven=("o", "crank"),
            min_spacing=0.02 * crank,
        )
        axis = turn((1.0, 0.0))
        graph.prismatic("j-guide", FRAME, "rail", "yoke", "guide", axis=axis)
        graph.pin_in_slot(
            "j-slot",
            "crank",
            "b",
            "yoke",
            start=turn((b[0], -half)),
            end=turn((b[0], half)),
        )
        return Built(
            graph.document(),
            FULL_TURN,
            cyclic=True,
            breakable=(PartRef("slider_block", bodies=("yoke",)),),
        )


FAMILIES = (SliderCrank(), InvertedSliderCrank(), Whitworth(), ScotchYoke())

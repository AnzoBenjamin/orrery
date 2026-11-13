"""The `Family` protocol (synthetic-lab design, "Families").

A family samples parameters from its space and draws a mechanism from them. Drawing can fail for
geometric reasons (a loop that does not close at the chosen input angle, a class condition that the
sampled lengths miss): it raises `Infeasible`, and the sampler draws again. Everything that can only
be known by simulating (the driver range is reachable, transmission angles, collisions) is checked
by `orrery_lab.feasibility` with the solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np

from orrery_lab.graph import Json
from orrery_lab.space import ParameterSpace, Params

PartKind = Literal["binary_link", "slider_block", "gear", "belt", "adjacent_links"]


class Infeasible(Exception):  # noqa: N818 (a rejection, not a program error)
    """The parameters do not describe a mechanism of this family."""


@dataclass(frozen=True)
class PartRef:
    """A part a breakage may remove (requirement 2.1): its bodies, or a belt joint."""

    kind: PartKind
    bodies: tuple[str, ...] = ()
    joints: tuple[str, ...] = ()


@dataclass(frozen=True)
class Built:
    """A drawn mechanism and the range its first driver is meant to cover.

    `drive_range` is relative to the drawn pose (driver value zero) and contains zero. A `cyclic`
    driver turns through the whole range continuously (a crank: `(0, 2π)`); otherwise it rocks
    between the ends.
    """

    document: Json
    drive_range: tuple[float, float]
    cyclic: bool
    breakable: tuple[PartRef, ...]


@dataclass(frozen=True)
class Requirements:
    """What the solver must confirm before a sample is accepted."""

    #: Least transmission angle allowed in any four-bar loop, in radians. Zero accepts toggles.
    min_transmission: float = math.radians(20)
    #: Whether branch points (a change-point four-bar folding flat) are part of the family.
    allow_bifurcation: bool = False
    #: Sweep step for the check, in radians or meters.
    step: float = math.tau / 120


class Family(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def requirements(self) -> Requirements: ...

    def parameter_space(self) -> ParameterSpace: ...

    def build(self, params: Params, rng: np.random.Generator, sample_id: str) -> Built:
        """Draws the mechanism; raises `Infeasible` when the parameters cannot be drawn."""
        ...

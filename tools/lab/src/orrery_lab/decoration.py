"""Small serializable appearance primitives shared by dressing and breakage."""

from dataclasses import dataclass
from typing import Literal

from orrery_lab.geometry import Point2

WearKind = Literal["ring", "scuff", "belt", "mesh"]


@dataclass
class Circle:
    center: Point2
    radius: float


@dataclass
class WearMark:
    center: Point2
    radius: float
    kind: WearKind


__all__ = ["Circle", "WearKind", "WearMark"]

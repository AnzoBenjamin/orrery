"""Parameter spaces: the bounded distributions a family samples from (requirement 1.2).

Lengths are meters and angles radians. A space is part of the lab's versioned behavior: the same
space, seed, and lab version give the same parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

type Params = dict[str, float]


@dataclass(frozen=True)
class Uniform:
    low: float
    high: float

    def __post_init__(self) -> None:
        if not self.low <= self.high:
            raise ValueError(f"empty range [{self.low}, {self.high}]")

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.uniform(self.low, self.high))

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high


@dataclass(frozen=True)
class LogUniform:
    """Uniform in the logarithm: for scales and stiffnesses that span orders of magnitude."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if not 0 < self.low <= self.high:
            raise ValueError(f"log-uniform needs 0 < low <= high, got [{self.low}, {self.high}]")

    def sample(self, rng: np.random.Generator) -> float:
        return float(np.exp(rng.uniform(np.log(self.low), np.log(self.high))))

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high


@dataclass(frozen=True)
class Integer:
    """Integers from `low` to `high` inclusive, sampled as floats (tooth counts, link counts)."""

    low: int
    high: int

    def __post_init__(self) -> None:
        if not self.low <= self.high:
            raise ValueError(f"empty range [{self.low}, {self.high}]")

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.integers(self.low, self.high, endpoint=True))

    def contains(self, value: float) -> bool:
        return value.is_integer() and self.low <= value <= self.high


@dataclass(frozen=True)
class Choice:
    """One of a few options, sampled as its index."""

    options: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("a choice needs at least one option")

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.integers(0, len(self.options)))

    def contains(self, value: float) -> bool:
        return value.is_integer() and 0 <= value < len(self.options)

    def pick(self, value: float) -> str:
        return self.options[int(value)]


type Distribution = Uniform | LogUniform | Integer | Choice


@dataclass(frozen=True)
class ParameterSpace:
    """Named distributions, sampled in name order so adding a parameter is visible in review."""

    parameters: dict[str, Distribution]

    def sample(self, rng: np.random.Generator) -> Params:
        return {name: self.parameters[name].sample(rng) for name in sorted(self.parameters)}

    def contains(self, params: Params) -> bool:
        return params.keys() == self.parameters.keys() and all(
            self.parameters[k].contains(v) for k, v in params.items()
        )

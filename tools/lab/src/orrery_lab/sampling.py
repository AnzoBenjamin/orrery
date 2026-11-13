"""Rejection sampling of specimen samples from a family (requirement 1.2).

Each sample has its own NumPy generator from `(seed,)`, so a sample depends only on the family,
the seed, and the lab version.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from orrery_lab.family import Built, Family, Infeasible
from orrery_lab.feasibility import Verdict, check
from orrery_lab.generated.mechanism import Mechanism
from orrery_lab.space import Params

DEFAULT_ATTEMPTS = 400


class NoFeasibleSample(Exception):  # noqa: N818 (named for what happened)
    """No attempt within the budget passed the checks."""

    def __init__(self, family: str, seed: int, rejections: Counter[str]) -> None:
        common = ", ".join(f"{reason} ({n})" for reason, n in rejections.most_common(3))
        super().__init__(f"{family} seed {seed}: no feasible sample; most common: {common}")
        self.rejections = rejections


@dataclass(frozen=True)
class Sample:
    family: str
    seed: int
    #: Which attempt was accepted (zero-based).
    attempt: int
    params: Params
    built: Built
    mechanism: Mechanism
    min_transmission: float
    rejections: Counter[str] = field(default_factory=Counter[str])

    @property
    def id(self) -> str:
        return sample_id(self.family, self.seed)

    def graph_json(self) -> str:
        """The mechanism graph document, as stored and sent to the solver."""
        return json.dumps(self.built.document, sort_keys=True)


def sample_id(family: str, seed: int) -> str:
    return f"{family}-{seed}"


def generate(family: Family, seed: int, attempts: int = DEFAULT_ATTEMPTS) -> Sample:
    rng = np.random.default_rng((seed,))
    space = family.parameter_space()
    rejections: Counter[str] = Counter()
    for attempt in range(attempts):
        params = space.sample(rng)
        try:
            built = family.build(params, rng, sample_id(family.name, seed))
        except Infeasible as e:
            rejections[str(e)] += 1
            continue
        verdict: Verdict = check(built, family.requirements)
        if verdict.reason is not None or verdict.mechanism is None:
            rejections[verdict.reason or "unchecked"] += 1
            continue
        return Sample(
            family=family.name,
            seed=seed,
            attempt=attempt,
            params=params,
            built=built,
            mechanism=verdict.mechanism,
            min_transmission=verdict.min_transmission,
            rejections=rejections,
        )
    raise NoFeasibleSample(family.name, seed, rejections)

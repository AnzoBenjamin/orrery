"""Deterministic physically based material specifications for Cycles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

MaterialKind = Literal["cardboard", "plywood", "brass", "steel", "painted_tin", "aged_iron"]
MATERIAL_KINDS: tuple[MaterialKind, ...] = (
    "cardboard",
    "plywood",
    "brass",
    "steel",
    "painted_tin",
    "aged_iron",
)


@dataclass(frozen=True)
class PbrMaterial:
    kind: MaterialKind
    base_color: tuple[float, float, float, float]
    metallic: float
    roughness: float


_SPECS: dict[MaterialKind, PbrMaterial] = {
    "cardboard": PbrMaterial("cardboard", (0.48, 0.29, 0.12, 1.0), 0.0, 0.86),
    "plywood": PbrMaterial("plywood", (0.62, 0.38, 0.16, 1.0), 0.0, 0.64),
    "brass": PbrMaterial("brass", (0.63, 0.39, 0.11, 1.0), 0.9, 0.25),
    "steel": PbrMaterial("steel", (0.34, 0.39, 0.42, 1.0), 0.92, 0.2),
    "painted_tin": PbrMaterial("painted_tin", (0.5, 0.045, 0.025, 1.0), 0.35, 0.3),
    "aged_iron": PbrMaterial("aged_iron", (0.12, 0.09, 0.055, 1.0), 0.78, 0.66),
}


def assign_pbr(body_ids: tuple[str, ...], seed: int) -> dict[str, PbrMaterial]:
    rng = np.random.default_rng(seed)
    order: list[MaterialKind] = []
    while len(order) < len(body_ids):
        order.extend(MATERIAL_KINDS[int(index)] for index in rng.permutation(len(MATERIAL_KINDS)))
    return {body_id: _SPECS[kind] for body_id, kind in zip(body_ids, order, strict=False)}


__all__ = ["MATERIAL_KINDS", "MaterialKind", "PbrMaterial", "assign_pbr"]

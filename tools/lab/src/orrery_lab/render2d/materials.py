"""Deterministic real-world material families for synthetic machine parts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
ASSET_ROOT = Path(__file__).parents[1] / "assets" / "materials"
CC0_TEXTURES: dict[MaterialKind, Path] = {
    "plywood": ASSET_ROOT / "wood_planks_grey_diff_1k.jpg",
}

PALETTES: dict[MaterialKind, tuple[tuple[int, int, int, int], tuple[int, int, int, int]]] = {
    "cardboard": ((157, 125, 82, 255), (103, 76, 48, 255)),
    "plywood": ((194, 151, 91, 255), (111, 73, 38, 255)),
    "brass": ((180, 143, 72, 255), (89, 65, 29, 255)),
    "steel": ((142, 151, 151, 255), (61, 68, 70, 255)),
    "painted_tin": ((116, 45, 35, 255), (55, 28, 24, 255)),
    "aged_iron": ((72, 68, 59, 255), (31, 29, 25, 255)),
}


@dataclass(frozen=True)
class Material:
    kind: MaterialKind
    base: tuple[int, int, int, int]
    accent: tuple[int, int, int, int]
    texture_phase: float
    texture_path: str | None = None


def assign_materials(body_ids: tuple[str, ...], rng: np.random.Generator) -> dict[str, Material]:
    order: list[MaterialKind] = []
    while len(order) < len(body_ids):
        permutation = rng.permutation(len(MATERIAL_KINDS))
        order.extend(MATERIAL_KINDS[int(index)] for index in permutation)
    return {
        body_id: Material(
            kind,
            *PALETTES[kind],
            float(rng.uniform(0.0, 1.0)),
            str(CC0_TEXTURES[kind]) if kind in CC0_TEXTURES else None,
        )
        for body_id, kind in zip(body_ids, order[: len(body_ids)], strict=True)
    }


__all__ = [
    "CC0_TEXTURES",
    "MATERIAL_KINDS",
    "Material",
    "MaterialKind",
    "assign_materials",
]

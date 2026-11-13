"""Every mechanism family, by name."""

from orrery_lab.families import four_bar, linkages, sliders
from orrery_lab.family import Family

FAMILIES: dict[str, Family] = {
    f.name: f for f in (*four_bar.FAMILIES, *sliders.FAMILIES, *linkages.FAMILIES)
}


def family(name: str) -> Family:
    try:
        return FAMILIES[name]
    except KeyError:
        known = ", ".join(sorted(FAMILIES))
        raise KeyError(f"unknown family {name!r}; known: {known}") from None

"""The `orrery-lab` command line."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated

import typer

from orrery_lab import LAB_VERSION
from orrery_lab.families import FAMILIES, family
from orrery_lab.sampling import NoFeasibleSample, generate

app = typer.Typer(
    name="orrery-lab",
    help="Generate mechanisms with known ground truth, break and render them, score the engine.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("version")
def show_version() -> None:
    """Print the lab version (part of every suite's manifest hash)."""
    typer.echo(LAB_VERSION)


@app.command("families")
def list_families() -> None:
    """List the mechanism families."""
    for name in sorted(FAMILIES):
        typer.echo(name)


@app.command("sample")
def sample(
    name: Annotated[str, typer.Argument(help="Family name (see `orrery-lab families`).")],
    seed: Annotated[int, typer.Option(min=0, help="Sample seed.")] = 0,
    out: Annotated[
        Path | None, typer.Option(help="Write the mechanism graph here instead of stdout.")
    ] = None,
) -> None:
    """Generate one feasible sample and print its mechanism graph (JSON)."""
    try:
        chosen = family(name)
    except KeyError as e:
        raise typer.BadParameter(str(e.args[0]), param_hint="NAME") from None
    try:
        result = generate(chosen, seed)
    except NoFeasibleSample as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None
    text = result.graph_json()
    if out is None:
        typer.echo(text)
    else:
        out.write_text(text + "\n")
    low, high = result.built.drive_range
    typer.echo(
        f"{result.id}: accepted on attempt {result.attempt + 1}, driver range "
        f"[{low:.4f}, {high:.4f}], least transmission angle "
        f"{math.degrees(result.min_transmission):.1f}°",
        err=True,
    )

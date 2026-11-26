"""Render and extract actual Blender Render Result passes.

All ``bpy`` interaction stays at this adapter boundary because Blender has no useful type stubs.
"""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
import numpy as np
import numpy.typing as npt

from orrery_lab.appearance import Appearance
from orrery_lab.graph import Json
from orrery_lab.render3d.exr import read_exr
from orrery_lab.render3d.scene import build_scene
from orrery_lab.render3d.types import CyclesRenderError, RenderConfig, RenderedPasses

_DEFAULT_CONFIG = RenderConfig()


def render(
    document: Json,
    appearance: Appearance,
    config: RenderConfig = _DEFAULT_CONFIG,
) -> RenderedPasses:
    """Build and render a scene using deterministic single-device CPU Cycles.

    Blender 5 no longer exposes ``Render Result.layers`` to Python. A compositor Render Layers
    node therefore writes its actual Combined, Depth (Z), and IndexOB sockets to lossless float
    EXR files. The arrays below are loaded from those real render-pass outputs, not synthesized.
    """
    built = build_scene(document, appearance, config)
    with tempfile.TemporaryDirectory(prefix="orrery-cycles-") as directory:
        paths = _pass_outputs(Path(directory))
        try:
            bpy.ops.render.render(write_still=False)
        except RuntimeError as error:
            raise CyclesRenderError(f"Cycles render failed: {error}") from error
        combined = read_exr(_find_output(paths["Combined"]))
        depth_image = read_exr(_find_output(paths["Depth"]))
        index_image = read_exr(_find_output(paths["IndexOB"]))
    _check_dimensions(combined.width, combined.height, config, "Combined")
    _check_dimensions(depth_image.width, depth_image.height, config, "Depth")
    _check_dimensions(index_image.width, index_image.height, config, "IndexOB")
    rgb = np.stack(
        tuple(_named_channel(combined.channels, suffix) for suffix in ("R", "G", "B")),
        axis=-1,
    ).astype(np.float32, copy=False)
    depth = _scalar_channel(depth_image.channels).astype(np.float32, copy=True)
    instance_id = np.rint(_scalar_channel(index_image.channels)).astype(np.int32, copy=True)
    depth[instance_id == 0] = np.inf
    if not np.all(np.isfinite(rgb)):
        raise CyclesRenderError("Combined pass contains non-finite RGB values")
    expected = set(built.object_ids.values())
    observed = {int(value) for value in np.unique(instance_id) if value != 0}
    if not observed <= expected:
        unexpected = sorted(observed - expected)
        raise CyclesRenderError(f"IndexOB contains unexpected object IDs {unexpected}")
    return RenderedPasses(rgb, depth, instance_id, built.object_ids, built.camera)


def _pass_outputs(directory: Path) -> dict[str, Path]:
    scene = bpy.context.scene
    previous = scene.compositing_node_group
    if previous is not None:
        scene.compositing_node_group = None
        bpy.data.node_groups.remove(previous)
    tree = bpy.data.node_groups.new("OrreryRenderPasses", "CompositorNodeTree")
    scene.compositing_node_group = tree
    scene.use_nodes = True
    render_layers = tree.nodes.new("CompositorNodeRLayers")
    render_layers.scene = scene
    render_layers.layer = "ViewLayer"
    prefixes: dict[str, Path] = {}
    for pass_name, socket_names, prefix, socket_type in (
        ("Combined", ("Image",), "combined-", "RGBA"),
        ("Depth", ("Depth",), "depth-", "FLOAT"),
        # Blender 5 renamed this compositor socket while retaining the IndexOB render pass.
        ("IndexOB", ("IndexOB", "Object Index"), "index-ob-", "FLOAT"),
    ):
        outputs = tree.nodes.new("CompositorNodeOutputFile")
        outputs.directory = str(directory)
        outputs.file_name = prefix
        outputs.format.file_format = "OPEN_EXR_MULTILAYER"
        outputs.format.color_depth = "32"
        outputs.format.exr_codec = "NONE"
        item = outputs.file_output_items.new(socket_type, pass_name)
        source = next(
            (
                render_layers.outputs.get(socket_name)
                for socket_name in socket_names
                if render_layers.outputs.get(socket_name)
            ),
            None,
        )
        if source is None:
            raise CyclesRenderError(f"Render Layers has no {pass_name} socket")
        tree.links.new(source, outputs.inputs[item.name])
        prefixes[pass_name] = directory / prefix
    return prefixes


def _find_output(prefix: Path) -> Path:
    matches = sorted(prefix.parent.glob(f"{prefix.name}*.exr"))
    if len(matches) != 1:
        raise CyclesRenderError(
            f"expected one EXR render-pass output for {prefix.name}, found {len(matches)}"
        )
    return matches[0]


def _check_dimensions(width: int, height: int, config: RenderConfig, pass_name: str) -> None:
    if (width, height) != (config.width, config.height):
        raise CyclesRenderError(
            f"pass {pass_name} has dimensions {(width, height)}, "
            f"expected {(config.width, config.height)}"
        )


def _named_channel(
    channels: dict[str, npt.NDArray[np.float32]], suffix: str
) -> npt.NDArray[np.float32]:
    matches = [
        value for name, value in channels.items() if name == suffix or name.endswith(f".{suffix}")
    ]
    if len(matches) != 1:
        raise CyclesRenderError(f"expected one EXR {suffix} channel, found {len(matches)}")
    return matches[0]


def _scalar_channel(
    channels: dict[str, npt.NDArray[np.float32]],
) -> npt.NDArray[np.float32]:
    if len(channels) != 1:
        raise CyclesRenderError(f"expected one scalar EXR channel, found {sorted(channels)}")
    return next(iter(channels.values()))


__all__ = ["render"]

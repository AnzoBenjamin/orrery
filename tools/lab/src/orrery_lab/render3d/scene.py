"""Blender scene adapter for dressed mechanisms.

All ``bpy`` interaction stays in this module because Blender does not publish useful type stubs.
"""

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportAttributeAccessIssue=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Vector

from orrery_lab.appearance import Appearance, BodyAppearance
from orrery_lab.graph import Json
from orrery_lab.render3d.camera import camera_pose
from orrery_lab.render3d.geometry import (
    MeshData,
    PlaneFrame,
    extruded_outline,
    plane_frames,
    rod_mesh,
    scene_points,
    spatial_body_points,
)
from orrery_lab.render3d.materials import PbrMaterial, assign_pbr
from orrery_lab.render3d.types import CameraMetadata, RenderConfig, SceneBuild, SceneBuildError

SCENE_NAME = "OrrerySyntheticLab"
TINY = 1e-12
_DEFAULT_CONFIG = RenderConfig()


def build_scene(
    document: Json, appearance: Appearance, config: RenderConfig = _DEFAULT_CONFIG
) -> SceneBuild:
    """Replace Blender's active scene contents with a deterministic CPU-Cycles scene."""
    _clear_scene()
    scene = bpy.context.scene
    scene.name = SCENE_NAME
    _configure_cycles(scene, config)
    frames = plane_frames(document)
    body_ids = tuple(str(body["id"]) for body in document["bodies"] if body["kind"] != "ground")
    materials = assign_pbr(body_ids, config.seed)
    object_ids: dict[str, int] = {}
    for index, body in enumerate(document["bodies"], start=1):
        if body["kind"] == "ground":
            continue
        body_id = str(body["id"])
        look = appearance.bodies.get(body_id)
        if look is None:
            raise SceneBuildError(f"appearance is missing body {body_id}")
        plane_id = body["planeId"]
        if plane_id is None:
            mesh_data = rod_mesh(spatial_body_points(body), look.rod_radius, config.rod_sides)
        else:
            plane = frames.get(str(plane_id))
            if plane is None:
                raise SceneBuildError(f"body {body_id} references missing plane {plane_id}")
            mesh_data = extruded_outline(look, plane)
        pass_index = index
        _mesh_object(body_id, mesh_data, materials[body_id], pass_index, look)
        object_ids[body_id] = pass_index
    _base_plate(document, appearance, frames)
    points = scene_points(document, appearance)
    camera = _camera(scene, points, config)
    _lights(scene, points)
    scene.render.image_settings.file_format = "OPEN_EXR"
    return SceneBuild(scene.name, object_ids, camera)


def _clear_scene() -> None:
    for obj in tuple(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    collections = (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    )
    for collection in collections:
        for block in tuple(collection):
            collection.remove(block)


def _configure_cycles(scene: object, config: RenderConfig) -> None:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = config.samples
    scene.cycles.use_denoising = False
    scene.cycles.use_animated_seed = False
    scene.cycles.seed = config.seed
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.render.resolution_x = config.width
    scene.render.resolution_y = config.height
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0
    scene.render.threads_mode = "FIXED"
    scene.render.threads = config.threads
    scene.render.film_transparent = False
    scene.render.use_file_extension = False
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    scene.render.image_settings.color_mode = "RGBA"
    view_layer = scene.view_layers[0]
    view_layer.name = "ViewLayer"
    view_layer.use_pass_z = True
    view_layer.use_pass_object_index = True
    world = scene.world or bpy.data.worlds.new("OrreryWorld")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is None:
        raise SceneBuildError("Blender world has no Background shader")
    background.inputs["Color"].default_value = (0.025, 0.018, 0.012, 1.0)
    background.inputs["Strength"].default_value = 0.15


def _mesh_object(
    body_id: str,
    mesh_data: MeshData,
    material: PbrMaterial,
    pass_index: int,
    look: BodyAppearance,
) -> object:
    mesh = bpy.data.meshes.new(f"mesh:{body_id}")
    mesh.from_pydata(mesh_data.vertices, (), mesh_data.faces)
    mesh.validate(verbose=False)
    mesh.update()
    obj = bpy.data.objects.new(f"body:{body_id}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.pass_index = pass_index
    obj.data.materials.append(_material(material))
    bevel_width = max(0.0, min(0.12 * max(look.thickness, look.rod_radius), 0.04 * look.thickness))
    if bevel_width > 0.0:
        modifier = obj.modifiers.new("physical edge bevel", "BEVEL")
        modifier.width = bevel_width
        modifier.segments = 2
    return obj


def _material(spec: PbrMaterial) -> object:
    material = bpy.data.materials.new(f"material:{spec.kind}:{len(bpy.data.materials)}")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is None:
        raise SceneBuildError("Blender material has no Principled BSDF shader")
    principled.inputs["Base Color"].default_value = spec.base_color
    principled.inputs["Metallic"].default_value = spec.metallic
    principled.inputs["Roughness"].default_value = spec.roughness
    return material


def _base_plate(document: Json, appearance: Appearance, frames: dict[str, PlaneFrame]) -> None:
    if not appearance.base_plate or not document["planes"]:
        return
    plane = frames[str(document["planes"][0]["id"])]
    thickness = max(appearance.thickness, 1e-5)
    look = BodyAppearance(
        "__base__",
        "Base",
        outline=appearance.base_plate,
        thickness=thickness,
        offset=-1.1 * thickness,
    )
    material = PbrMaterial("plywood", (0.32, 0.17, 0.065, 1.0), 0.0, 0.72)
    base = _mesh_object("__base__", extruded_outline(look, plane), material, 0, look)
    base.name = "ground:base-plate"
    base.pass_index = 0


def _camera(
    scene: object, points: tuple[tuple[float, float, float], ...], config: RenderConfig
) -> CameraMetadata:
    pose = camera_pose(points, config)
    data = bpy.data.cameras.new("camera:synthetic")
    data.type = "PERSP"
    data.lens_unit = "FOV"
    data.angle = math.radians(config.field_of_view_degrees)
    data.sensor_fit = "HORIZONTAL"
    data.clip_start = pose.near_clip
    data.clip_end = pose.far_clip
    obj = bpy.data.objects.new("camera:synthetic", data)
    scene.collection.objects.link(obj)
    obj.location = pose.location
    direction = Vector(pose.target) - obj.location
    if direction.length <= TINY:
        raise SceneBuildError("camera location coincides with its target")
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = obj
    bpy.context.view_layer.update()
    view = obj.matrix_world.inverted()
    matrix = tuple(float(view[row][column]) for row in range(4) for column in range(4))
    return CameraMetadata(
        config.camera_path,
        config.frame_index,
        config.frame_count,
        pose.location,
        pose.target,
        config.field_of_view_degrees,
        pose.near_clip,
        pose.far_clip,
        matrix,
    )


def _lights(scene: object, points: tuple[tuple[float, float, float], ...]) -> None:
    cloud = np.asarray(points, dtype=np.float64)
    center = 0.5 * (cloud.min(axis=0) + cloud.max(axis=0))
    extent = max(float(np.ptp(cloud, axis=0).max()), 0.05)
    for name, direction, energy, size in (
        ("key", (1.5, -1.2, 2.0), 650.0, 2.5),
        ("fill", (-1.4, 0.8, 1.1), 260.0, 1.8),
    ):
        data = bpy.data.lights.new(f"light:{name}", "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size * extent
        obj = bpy.data.objects.new(f"light:{name}", data)
        scene.collection.objects.link(obj)
        obj.location = center + extent * np.asarray(direction)
        obj.rotation_euler = (Vector(center) - obj.location).to_track_quat("-Z", "Y").to_euler()


__all__ = ["build_scene"]

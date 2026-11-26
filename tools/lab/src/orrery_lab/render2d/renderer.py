"""Skia rendering of dressed planar mechanism samples (synthetic-lab requirement 3.1)."""

# skia-python ships no type information; keep the suppression at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import skia

from orrery_lab.appearance import Appearance, BodyAppearance
from orrery_lab.dynamics import BodyPose
from orrery_lab.geometry import Point2
from orrery_lab.graph import Json
from orrery_lab.render2d.camera import Camera, fit_camera
from orrery_lab.render2d.materials import Material, assign_materials
from orrery_lab.render2d.occluders import AnimatedOccluder, draw_occluders

RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class RenderConfig:
    width: int = 640
    height: int = 480
    clutter_count: int = 8
    shadows: bool = True
    shadow_offset: Point2 = (7.0, 9.0)
    background: RGBA = (34, 29, 23, 255)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("render dimensions must be positive")
        if self.clutter_count < 0:
            raise ValueError("clutter count cannot be negative")


@dataclass(frozen=True)
class RenderedFrame:
    pixels: npt.NDArray[np.uint8]
    png: bytes
    point_projections: dict[tuple[str, str], Point2]
    point_visibility: dict[tuple[str, str], bool]
    materials: dict[str, Material]
    camera: Camera


def _color(rgba: RGBA) -> int:
    return skia.ColorSetARGB(rgba[3], rgba[0], rgba[1], rgba[2])


def _paint(rgba: RGBA, *, style: skia.Paint.Style = skia.Paint.kFill_Style) -> skia.Paint:
    paint = skia.Paint()
    paint.setAntiAlias(True)
    paint.setColor(_color(rgba))
    paint.setStyle(style)
    return paint


def _world(local: Point2, pose: BodyPose | None) -> Point2:
    if pose is None:
        return local
    c, s = math.cos(pose.angle), math.sin(pose.angle)
    return (
        pose.x + c * local[0] - s * local[1],
        pose.y + s * local[0] + c * local[1],
    )


def _projected(
    points: list[Point2] | tuple[Point2, ...], camera: Camera, pose: BodyPose | None
) -> list[Point2]:
    return [camera.project(_world(point, pose)) for point in points]


def _path(points: list[Point2]) -> skia.Path:
    path = skia.Path()
    if not points:
        return path
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    path.close()
    return path


def _circle_points(center: Point2, radius: float, count: int = 24) -> list[Point2]:
    return [
        (
            center[0] + radius * math.cos(math.tau * index / count),
            center[1] + radius * math.sin(math.tau * index / count),
        )
        for index in range(count)
    ]


def _scene_points(
    document: Json, appearance: Appearance, poses: dict[str, BodyPose]
) -> list[Point2]:
    points = list(appearance.base_plate)
    for body in document["bodies"]:
        body_id = str(body["id"])
        if body["planeId"] is None and body["kind"] != "ground":
            raise ValueError(f"the Skia renderer cannot draw spatial body {body_id}")
        pose = poses.get(body_id)
        look = appearance.bodies[body_id]
        points.extend(_world(point, pose) for point in look.outline)
        points.extend(
            _world((point["local"]["x"], point["local"]["y"]), pose) for point in body["points"]
        )
    if not points:
        raise ValueError("the scene has no planar geometry")
    return points


def _draw_background(canvas: skia.Canvas, config: RenderConfig, rng: np.random.Generator) -> None:
    canvas.clear(_color(config.background))
    grain = _paint((232, 223, 201, 18))
    for _ in range(max(80, config.width * config.height // 3500)):
        x, y = float(rng.uniform(0, config.width)), float(rng.uniform(0, config.height))
        radius = float(rng.uniform(0.3, 1.4))
        canvas.drawCircle(x, y, radius, grain)
    vignette = skia.GradientShader.MakeRadial(
        (0.5 * config.width, 0.45 * config.height),
        0.75 * max(config.width, config.height),
        [_color((0, 0, 0, 0)), _color((0, 0, 0, 145))],
    )
    paint = skia.Paint(Shader=vignette)
    canvas.drawRect(skia.Rect.MakeWH(config.width, config.height), paint)


def _draw_base_plate(canvas: skia.Canvas, appearance: Appearance, camera: Camera) -> None:
    if not appearance.base_plate:
        return
    path = _path([camera.project(point) for point in appearance.base_plate])
    canvas.drawPath(path, _paint((205, 191, 159, 255)))
    canvas.drawPath(path, _paint((74, 61, 43, 255), style=skia.Paint.kStroke_Style))
    for boss in appearance.bosses:
        center = camera.project(boss.center)
        edge = camera.project((boss.center[0] + boss.radius, boss.center[1]))
        radius = math.dist(center, edge)
        canvas.drawCircle(*center, radius, _paint((157, 125, 72, 255)))


def _draw_clutter(canvas: skia.Canvas, config: RenderConfig, rng: np.random.Generator) -> None:
    for index in range(config.clutter_count):
        x = float(rng.uniform(10.0, config.width - 10.0))
        y = float(rng.uniform(10.0, config.height - 10.0))
        radius = float(rng.uniform(3.0, 10.0))
        if index % 3 == 0:
            canvas.drawCircle(x, y, radius, _paint((103, 91, 71, 255)))
            canvas.drawCircle(
                x,
                y,
                0.45 * radius,
                _paint(config.background),
            )
        elif index % 3 == 1:
            paint = _paint((128, 111, 77, 210))
            canvas.save()
            canvas.rotate(float(rng.uniform(-45, 45)), x, y)
            canvas.drawRect(
                skia.Rect.MakeXYWH(x - 3 * radius, y - radius, 6 * radius, 2 * radius), paint
            )
            canvas.restore()
        else:
            stroke = _paint((177, 154, 105, 220), style=skia.Paint.kStroke_Style)
            stroke.setStrokeWidth(2.0)
            canvas.drawLine(x - radius, y - radius, x + radius, y + radius, stroke)
            canvas.drawLine(x - radius, y + radius, x + radius, y - radius, stroke)


def _draw_texture(
    canvas: skia.Canvas,
    path: skia.Path,
    material: Material,
    rng: np.random.Generator,
) -> None:
    bounds = path.getBounds()
    accent = _paint(material.accent, style=skia.Paint.kStroke_Style)
    accent.setStrokeWidth(0.7 if material.kind in {"steel", "brass"} else 1.2)
    canvas.save()
    canvas.clipPath(path, doAntiAlias=True)
    if material.texture_path is not None:
        data = skia.Data.MakeFromFileName(material.texture_path)
        image = skia.Image.MakeFromEncoded(data) if data is not None else None
        if image is None:
            raise RuntimeError(f"cannot decode CC0 material texture {material.texture_path}")
        canvas.drawImageRect(image, bounds)
    if material.kind in {"plywood", "cardboard"}:
        spacing = 7.0 if material.kind == "plywood" else 11.0
        y = bounds.top() - spacing + material.texture_phase * spacing
        while y < bounds.bottom() + spacing:
            wobble = 2.0 * math.sin(0.05 * y + material.texture_phase * math.tau)
            canvas.drawLine(bounds.left(), y, bounds.right(), y + wobble, accent)
            y += spacing
    elif material.kind in {"steel", "brass"}:
        x = bounds.left() + 3.0 * material.texture_phase
        while x < bounds.right():
            canvas.drawLine(x, bounds.top(), x + 0.15 * bounds.height(), bounds.bottom(), accent)
            x += 4.0
    else:
        for _ in range(18):
            x = float(rng.uniform(bounds.left(), bounds.right()))
            y = float(rng.uniform(bounds.top(), bounds.bottom()))
            canvas.drawCircle(x, y, float(rng.uniform(0.4, 1.6)), accent)
    canvas.restore()


def _body_path(look: BodyAppearance, camera: Camera, pose: BodyPose | None) -> skia.Path:
    path = _path(_projected(look.outline, camera, pose))
    path.setFillType(skia.PathFillType.kEvenOdd)
    for cutout in look.cutouts:
        subpath = _path(_projected(cutout, camera, pose))
        path.addPath(subpath)
    for hole in look.holes:
        subpath = _path(_projected(_circle_points(hole.center, hole.radius), camera, pose))
        path.addPath(subpath)
    return path


def _draw_body(
    canvas: skia.Canvas,
    look: BodyAppearance,
    material: Material,
    *,
    camera: Camera,
    pose: BodyPose | None,
    config: RenderConfig,
    rng: np.random.Generator,
) -> None:
    path = _body_path(look, camera, pose)
    if config.shadows:
        shadow = skia.Path(path)
        shadow.transform(skia.Matrix.Translate(*config.shadow_offset))
        shadow_paint = _paint((0, 0, 0, 115))
        shadow_paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.BlurStyle.kNormal_BlurStyle, 4.0))
        canvas.drawPath(shadow, shadow_paint)
    canvas.drawPath(path, _paint(material.base))
    _draw_texture(canvas, path, material, rng)
    edge = _paint(material.accent, style=skia.Paint.kStroke_Style)
    edge.setStrokeWidth(1.2)
    canvas.drawPath(path, edge)
    for rivet in look.rivets:
        center = camera.project(_world(rivet.center, pose))
        side = camera.project(_world((rivet.center[0] + rivet.radius, rivet.center[1]), pose))
        canvas.drawCircle(*center, math.dist(center, side), _paint((215, 190, 132, 255)))
    for wear in look.wear_marks:
        center = camera.project(_world(wear.center, pose))
        side = camera.project(_world((wear.center[0] + wear.radius, wear.center[1]), pose))
        wear_paint = _paint((52, 38, 27, 150), style=skia.Paint.kStroke_Style)
        wear_paint.setStrokeWidth(1.5)
        canvas.drawCircle(*center, math.dist(center, side), wear_paint)


def render_frame(
    document: Json,
    appearance: Appearance,
    rng: np.random.Generator,
    *,
    camera: Camera | None = None,
    poses: dict[str, BodyPose] | None = None,
    time: float = 0.0,
    occluders: tuple[AnimatedOccluder, ...] = (),
    config: RenderConfig = RenderConfig(),
) -> RenderedFrame:
    """Render one RGBA frame and named-point projections from the same camera."""
    poses = poses or {}
    if not math.isfinite(time) or time < 0.0:
        raise ValueError("render time must be finite and nonnegative")
    scene_points = _scene_points(document, appearance, poses)
    chosen_camera = camera or fit_camera(scene_points, config.width, config.height, rng)
    if (chosen_camera.width, chosen_camera.height) != (config.width, config.height):
        raise ValueError("camera and render dimensions differ")
    surface = skia.Surface(config.width, config.height)
    canvas = surface.getCanvas()
    _draw_background(canvas, config, rng)
    _draw_base_plate(canvas, appearance, chosen_camera)
    _draw_clutter(canvas, config, rng)
    body_ids = tuple(
        str(body["id"])
        for body in document["bodies"]
        if body["kind"] != "ground" and appearance.bodies[body["id"]].outline
    )
    materials = assign_materials(body_ids, rng)
    ordered = sorted(body_ids, key=lambda body_id: appearance.bodies[body_id].offset)
    for body_id in ordered:
        _draw_body(
            canvas,
            appearance.bodies[body_id],
            materials[body_id],
            camera=chosen_camera,
            pose=poses.get(body_id),
            config=config,
            rng=rng,
        )
    projections = {
        (str(body["id"]), str(point["id"])): chosen_camera.project(
            _world(
                (float(point["local"]["x"]), float(point["local"]["y"])),
                poses.get(str(body["id"])),
            )
        )
        for body in document["bodies"]
        for point in body["points"]
    }
    visibility = {
        name: not any(occluder.covers(point, time) for occluder in occluders)
        for name, point in projections.items()
    }
    draw_occluders(canvas, occluders, time)
    image = surface.makeImageSnapshot()
    pixels = np.asarray(
        image.toarray(colorType=skia.ColorType.kRGBA_8888_ColorType), dtype=np.uint8
    ).copy()
    encoded = image.encodeToData(skia.EncodedImageFormat.kPNG, 100)
    if encoded is None:
        raise RuntimeError("Skia failed to encode the frame")
    return RenderedFrame(
        pixels,
        bytes(encoded),
        projections,
        visibility,
        materials,
        chosen_camera,
    )


__all__ = ["RenderConfig", "RenderedFrame", "render_frame"]

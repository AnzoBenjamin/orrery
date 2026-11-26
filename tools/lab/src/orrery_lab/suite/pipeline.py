"""Build actual ClipTruth inputs for one deterministic suite clip."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import cast

import numpy as np
from orrery_kinematics import Solver

from orrery_lab import LAB_VERSION
from orrery_lab.appearance import Appearance
from orrery_lab.breakage import Broken, apply_breakage
from orrery_lab.degrade import EncodingConfig, encode_video
from orrery_lab.dynamics import BodyPose
from orrery_lab.families import family
from orrery_lab.graph import Json
from orrery_lab.render2d import RenderConfig, RenderedFrame, render_frame
from orrery_lab.render3d import RenderConfig as Render3DConfig
from orrery_lab.render3d import RenderedPasses
from orrery_lab.render3d import render as render_3d
from orrery_lab.sampling import Sample, generate
from orrery_lab.suite.manifest import CaptureProfile, ClipPlan, part_kind
from orrery_lab.truth import ClipTruth, TruthFrame
from orrery_lab.truth.types import BodyPoseTruth

_CAMERA_RANDOM_DRAWS = 7


@dataclass(frozen=True)
class BuiltClip:
    truth: ClipTruth
    selected_breakage: str


def build_clip(plan: ClipPlan) -> BuiltClip:
    """Sample, optionally break, render, and encode one planned clip."""
    sample = generate(family(plan.spec.family), plan.seed)
    rng = np.random.default_rng((plan.seed, plan.index))
    broken = _break(sample, plan, rng)
    document = broken.document if broken is not None else sample.built.document
    appearance = broken.appearance if broken is not None else sample.appearance
    render_seed = int(rng.integers(0, np.iinfo(np.uint64).max, dtype=np.uint64))
    encoding_seed = int(rng.integers(0, np.iinfo(np.uint64).max, dtype=np.uint64))
    timestamps = tuple(index / plan.profile.frame_rate for index in range(plan.profile.frame_count))

    if plan.profile.render_mode == "2d":
        poses, driver_values = _planar_motion(sample, document, plan.profile.frame_count, broken)
        rendered = _render_planar(
            document,
            appearance,
            plan.profile,
            poses=poses,
            timestamps=timestamps,
            seed=render_seed,
        )
        rgb = np.stack([frame.pixels[:, :, :3] for frame in rendered])
    else:
        poses, driver_values = _static_motion(document, plan.profile.frame_count)
        rendered = _render_spatial(document, appearance, plan.profile, render_seed)
        rgb = np.stack(
            [np.clip(frame.rgb * 255.0, 0.0, 255.0).astype(np.uint8) for frame in rendered]
        )

    encoding = encode_video(
        rgb,
        timestamps,
        np.random.default_rng(encoding_seed),
        config=EncodingConfig(
            codecs=(plan.profile.codec,),
            pixel_formats=("yuv420p",),
            variable_frame_rate=plan.profile.variable_frame_rate,
            drop_probability=plan.profile.drop_probability,
        ),
    )
    frames = tuple(
        TruthFrame(timestamp, drivers, cast(dict[str, BodyPoseTruth], body_pose), frame)
        for timestamp, drivers, body_pose, frame in zip(
            timestamps, driver_values, poses, rendered, strict=True
        )
    )
    selected = broken.record.kind if broken is not None else "none"
    return BuiltClip(
        ClipTruth(
            plan.spec.id,
            LAB_VERSION,
            plan.profile.name,
            sample,
            frames,
            encoding,
            breakage=broken,
            include_depth=plan.profile.render_mode == "3d",
        ),
        selected,
    )


def _break(sample: Sample, plan: ClipPlan, rng: np.random.Generator) -> Broken | None:
    selection = plan.spec.breakage
    if selection == "none":
        return None
    expected = part_kind(selection)
    choices = tuple(
        candidate
        for candidate in sample.built.breakable
        if expected is None or candidate.kind == expected
    )
    if not choices:
        raise ValueError(
            f"clip {plan.spec.id!r} requests breakage {selection!r}, "
            f"but family {sample.family!r} has no such breakable part"
        )
    chosen = choices[int(rng.integers(0, len(choices)))]
    return apply_breakage(sample, chosen, f"{plan.spec.id}-breakage")


def _driver_trajectory(sample: Sample, count: int) -> tuple[float, ...]:
    low, high = sample.built.drive_range
    if sample.built.cyclic:
        return tuple(low + (high - low) * index / count for index in range(count))
    values: list[float] = []
    for index in range(count):
        phase = 2.0 * index / count
        value = (
            high * math.sin(math.pi * phase) if phase <= 1.0 else -low * math.sin(math.pi * phase)
        )
        values.append(value)
    return tuple(values)


def _planar_motion(
    sample: Sample,
    document: Json,
    count: int,
    broken: Broken | None,
) -> tuple[tuple[dict[str, BodyPose], ...], tuple[dict[str, float], ...]]:
    if broken is not None or not document["drivers"]:
        return _static_motion(document, count)
    solver = Solver(json.dumps(document, sort_keys=True))
    drive = np.zeros(solver.driver_count, dtype=np.float64)
    state = solver.assemble(drive)
    poses: list[dict[str, BodyPose]] = []
    drivers: list[dict[str, float]] = []
    driver_ids = tuple(str(item["id"]) for item in document["drivers"])
    for value in _driver_trajectory(sample, count):
        drive[0] = value
        state = solver.assemble(drive, seed=state)
        poses.append(_poses_from_state(document, state))
        drivers.append(
            {driver_id: float(drive[index]) for index, driver_id in enumerate(driver_ids)}
        )
    return tuple(poses), tuple(drivers)


def _static_motion(
    document: Json, count: int
) -> tuple[tuple[dict[str, BodyPose], ...], tuple[dict[str, float], ...]]:
    pose = {str(body["id"]): BodyPose(0.0, 0.0, 0.0) for body in document["bodies"]}
    drivers = {str(driver["id"]): 0.0 for driver in document["drivers"]}
    return (
        tuple(dict(pose) for _ in range(count)),
        tuple(dict(drivers) for _ in range(count)),
    )


def _poses_from_state(document: Json, state: np.ndarray) -> dict[str, BodyPose]:
    offset = 0
    poses: dict[str, BodyPose] = {}
    for body in document["bodies"]:
        body_id = str(body["id"])
        if body["kind"] == "ground":
            poses[body_id] = BodyPose(0.0, 0.0, 0.0)
        elif body["planeId"] is not None:
            poses[body_id] = BodyPose(
                float(state[offset]), float(state[offset + 1]), float(state[offset + 2])
            )
            offset += 3
        else:
            raise ValueError("the planar suite renderer cannot consume a spatial solver state")
    return poses


def _render_planar(
    document: Json,
    appearance: object,
    profile: CaptureProfile,
    *,
    poses: tuple[dict[str, BodyPose], ...],
    timestamps: tuple[float, ...],
    seed: int,
) -> tuple[RenderedFrame, ...]:
    if not isinstance(appearance, Appearance):
        raise TypeError("planar rendering requires an Appearance")
    config = RenderConfig(
        width=profile.width,
        height=profile.height,
        clutter_count=profile.clutter_count,
        shadows=profile.shadows,
    )
    frames: list[RenderedFrame] = []
    camera = None
    for index, (timestamp, frame_poses) in enumerate(zip(timestamps, poses, strict=True)):
        frame_rng = np.random.default_rng(seed)
        if index:
            for _ in range(_CAMERA_RANDOM_DRAWS):
                frame_rng.random()
        frame = render_frame(
            document,
            appearance,
            frame_rng,
            camera=camera,
            poses=frame_poses,
            time=timestamp,
            config=config,
        )
        camera = frame.camera
        frames.append(frame)
    return tuple(frames)


def _render_spatial(
    document: Json,
    appearance: object,
    profile: CaptureProfile,
    seed: int,
) -> tuple[RenderedPasses, ...]:
    if not isinstance(appearance, Appearance):
        raise TypeError("3D rendering requires an Appearance")
    return tuple(
        render_3d(
            document,
            appearance,
            Render3DConfig(
                width=profile.width,
                height=profile.height,
                samples=profile.cycles_samples,
                seed=seed,
                camera_path=profile.camera_path,
                frame_index=frame_index,
                frame_count=profile.frame_count,
                threads=1,
                rod_sides=6,
            ),
        )
        for frame_index in range(profile.frame_count)
    )


__all__ = ["BuiltClip", "build_clip"]

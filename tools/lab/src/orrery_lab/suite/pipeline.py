"""Build actual ClipTruth inputs for one deterministic suite clip."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from typing import cast

import numpy as np
from orrery_kinematics import Solver

from orrery_lab import LAB_VERSION
from orrery_lab.appearance import Appearance
from orrery_lab.breakage import Broken, apply_breakage
from orrery_lab.degrade import (
    CameraDegradeConfig,
    EncodingConfig,
    SensorDegradeConfig,
    degrade_camera,
    degrade_sensor,
    encode_video,
)
from orrery_lab.dynamics import BodyPose, DynamicsConfig, Trajectory, simulate
from orrery_lab.families import family
from orrery_lab.graph import Json
from orrery_lab.render2d import RenderConfig, RenderedFrame, render_frame
from orrery_lab.render3d import RenderConfig as Render3DConfig
from orrery_lab.render3d import RenderedPasses
from orrery_lab.render3d import render as render_3d
from orrery_lab.sampling import Sample, generate
from orrery_lab.suite.manifest import CaptureProfile, CaptureTier, ClipPlan, part_kind
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
    degradation_seed = int(rng.integers(0, np.iinfo(np.uint64).max, dtype=np.uint64))
    encoding_seed = int(rng.integers(0, np.iinfo(np.uint64).max, dtype=np.uint64))
    timestamps = tuple(index / plan.profile.frame_rate for index in range(plan.profile.frame_count))
    dynamics = None
    degradations: dict[str, object] = {}

    if plan.profile.render_mode == "2d":
        poses, driver_values, dynamics = _planar_motion(sample, document, timestamps, broken)
        rendered, camera_degradation = _render_planar(
            document,
            appearance,
            plan.profile,
            poses=poses,
            timestamps=timestamps,
            render_seed=render_seed,
            degradation_seed=degradation_seed,
        )
        if camera_degradation is not None:
            degradations["camera"] = camera_degradation
        rgb = np.stack([frame.pixels[:, :, :3] for frame in rendered])
        rgb, sensor_degradation = _degrade_capture(
            rgb, timestamps, plan.profile.tier, degradation_seed
        )
        if sensor_degradation is not None:
            degradations["sensor"] = sensor_degradation
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
            dynamics=dynamics,
            degradations=degradations,
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
    index = plan.spec.breakage_index
    if index is None:
        index = int(rng.integers(0, len(choices)))
    if index >= len(choices):
        raise ValueError(
            f"clip {plan.spec.id!r} breakage index {index} exceeds {len(choices)} matching choices"
        )
    chosen = choices[index]
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
    timestamps: tuple[float, ...],
    broken: Broken | None,
) -> tuple[
    tuple[dict[str, BodyPose], ...],
    tuple[dict[str, float], ...],
    Trajectory | None,
]:
    if broken is not None:
        return _dynamic_motion(document, broken, timestamps)
    if not document["drivers"]:
        static_poses, static_drivers = _static_motion(document, len(timestamps))
        return static_poses, static_drivers, None
    solver = Solver(json.dumps(document, sort_keys=True))
    drive = np.zeros(solver.driver_count, dtype=np.float64)
    state = solver.assemble(drive)
    poses: list[dict[str, BodyPose]] = []
    drivers: list[dict[str, float]] = []
    driver_ids = tuple(str(item["id"]) for item in document["drivers"])
    for value in _driver_trajectory(sample, len(timestamps)):
        drive[0] = value
        state = solver.assemble(drive, seed=state)
        poses.append(_poses_from_state(document, state))
        drivers.append(
            {driver_id: float(drive[index]) for index, driver_id in enumerate(driver_ids)}
        )
    return tuple(poses), tuple(drivers), None


def _dynamic_motion(
    document: Json,
    broken: Broken,
    timestamps: tuple[float, ...],
) -> tuple[tuple[dict[str, BodyPose], ...], tuple[dict[str, float], ...], Trajectory]:
    period = timestamps[1] - timestamps[0]
    substeps = 80
    config = DynamicsConfig(step=period / substeps)
    simulated = simulate(broken, timestamps[-1], config=config)
    indices = tuple(round(timestamp / config.step) for timestamp in timestamps)
    dynamic_frames = tuple(
        replace(simulated.frames[index], time=timestamp)
        for index, timestamp in zip(indices, timestamps, strict=True)
    )
    dynamics = Trajectory(
        simulated.active_body_ids,
        dynamic_frames,
        tuple(simulated.energies[index] for index in indices),
    )
    base = {str(body["id"]): BodyPose(0.0, 0.0, 0.0) for body in document["bodies"]}
    poses: list[dict[str, BodyPose]] = []
    for frame in dynamic_frames:
        current = dict(base)
        current.update(frame.poses)
        poses.append(current)
    drivers = {str(driver["id"]): 0.0 for driver in document["drivers"]}
    return tuple(poses), tuple(dict(drivers) for _ in timestamps), dynamics


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
    render_seed: int,
    degradation_seed: int,
) -> tuple[tuple[RenderedFrame, ...], object | None]:
    if not isinstance(appearance, Appearance):
        raise TypeError("planar rendering requires an Appearance")
    config = RenderConfig(
        width=profile.width,
        height=profile.height,
        clutter_count=profile.clutter_count,
        shadows=profile.shadows,
    )
    base_rng = np.random.default_rng(render_seed)
    base = render_frame(
        document,
        appearance,
        base_rng,
        poses=poses[0],
        time=timestamps[0],
        config=config,
    )
    camera_metadata = None
    cameras = tuple(base.camera for _ in timestamps)
    if profile.tier in {"phone", "hostile"}:
        camera_config = (
            CameraDegradeConfig()
            if profile.tier == "phone"
            else CameraDegradeConfig(
                center_amplitude_world=0.009,
                tilt_amplitude_radians=math.radians(1.6),
                roll_amplitude_radians=math.radians(2.0),
                focus_breathing_fraction=0.03,
            )
        )
        changed = degrade_camera(
            base.camera,
            timestamps,
            np.random.default_rng((degradation_seed, 0)),
            config=camera_config,
        )
        cameras = changed.cameras
        camera_metadata = changed.metadata
    frames: list[RenderedFrame] = []
    for timestamp, frame_poses, camera in zip(timestamps, poses, cameras, strict=True):
        frame_rng = np.random.default_rng(render_seed)
        for _ in range(_CAMERA_RANDOM_DRAWS):
            frame_rng.random()
        frames.append(
            render_frame(
                document,
                appearance,
                frame_rng,
                camera=camera,
                poses=frame_poses,
                time=timestamp,
                config=config,
            )
        )
    return tuple(frames), camera_metadata


def _degrade_capture(
    rgb: np.ndarray,
    timestamps: tuple[float, ...],
    tier: CaptureTier,
    seed: int,
) -> tuple[np.ndarray, object | None]:
    if tier not in {"phone", "hostile"}:
        return rgb, None
    linear = np.power(rgb.astype(np.float32) / 255.0, 2.2).astype(np.float32)
    config = (
        SensorDegradeConfig(full_well_electrons=3000.0, read_noise_std=0.004)
        if tier == "phone"
        else SensorDegradeConfig(
            drift_amplitude_stops=0.4,
            full_well_electrons=1200.0,
            read_noise_std=0.009,
        )
    )
    result = degrade_sensor(
        linear,
        timestamps,
        np.random.default_rng((seed, 1)),
        config=config,
    )
    encoded = np.clip(np.power(result.pixels, 1.0 / 2.2) * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    metadata = {
        "inputTransfer": "srgb-approximate-gamma-2.2",
        "workingSpace": "linear-rgb",
        "outputTransfer": "srgb-approximate-gamma-2.2",
        "sensor": result.metadata,
    }
    return encoded, metadata


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

"""Versioned MP4/JSON/Arrow/mask/depth truth export (requirements 6.1-6.2)."""

# pyarrow has no complete stubs; Arrow inspection in this test module is its adapter boundary.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

import json
import math
import shutil
import struct
import zlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from orrery_lab.breakage import Broken, apply_breakage
from orrery_lab.degrade import EncodingConfig, encode_video
from orrery_lab.dynamics import BodyPose, simulate
from orrery_lab.families import family
from orrery_lab.render2d import RenderConfig, render_frame
from orrery_lab.render3d import RenderConfig as Render3DConfig
from orrery_lab.render3d import render as render_3d
from orrery_lab.render3d.exr import read_exr
from orrery_lab.sampling import Sample, generate
from orrery_lab.truth import ClipTruth, TruthFrame, export_clip
from orrery_lab.truth.images import depth_exr
from orrery_lab.truth.types import BodyPoseTruth

PLANAR_FAMILIES = (
    "four-bar-crank-rocker",
    "slider-crank",
    "whitworth-quick-return",
    "six-bar-watt-1",
    "gear-train",
    "rack-and-pinion",
    "geneva-drive",
    "cam-follower-roller",
    "sewing-machine",
)


def _encoding_config(*, drop_probability: float = 0.0) -> EncodingConfig:
    return EncodingConfig(
        codecs=("h264",),
        pixel_formats=("yuv420p",),
        variable_frame_rate=False,
        drop_probability=drop_probability,
    )


def _identity_poses(document: dict[str, object]) -> dict[str, BodyPose]:
    bodies = document["bodies"]
    assert isinstance(bodies, list)
    return {str(body["id"]): BodyPose(0.0, 0.0, 0.0) for body in bodies}


def _driver_values(document: dict[str, object]) -> dict[str, float]:
    drivers = document["drivers"]
    assert isinstance(drivers, list)
    return {str(driver["id"]): 0.0 for driver in drivers}


def _clip(
    sample: Sample,
    *,
    frame_count: int = 3,
    breakage: Broken | None = None,
    drop_probability: float = 0.0,
    width: int = 160,
    height: int = 120,
) -> ClipTruth:
    document = breakage.document if breakage is not None else sample.built.document
    appearance = breakage.appearance if breakage is not None else sample.appearance
    timestamps = tuple(0.04 * index for index in range(frame_count))
    config = RenderConfig(width=width, height=height, clutter_count=0, shadows=False)
    rendered = []
    camera = None
    for index, timestamp in enumerate(timestamps):
        frame = render_frame(
            document,
            appearance,
            np.random.default_rng(100 + index),
            camera=camera,
            time=timestamp,
            config=config,
        )
        camera = frame.camera
        rendered.append(frame)
    rgb = np.stack([frame.pixels[:, :, :3] for frame in rendered])
    encoding = encode_video(
        rgb,
        timestamps,
        np.random.default_rng(77),
        config=_encoding_config(drop_probability=drop_probability),
    )
    poses = _identity_poses(document)
    drivers = _driver_values(document)
    frames = tuple(
        TruthFrame(timestamp, dict(drivers), dict(poses), frame)
        for timestamp, frame in zip(timestamps, rendered, strict=True)
    )
    return ClipTruth(
        f"{sample.id}-truth",
        "0.1.0",
        "clean",
        sample,
        frames,
        encoding,
        breakage=breakage,
    )


def _read_arrow(path: Path) -> pa.Table:
    with pa.ipc.open_file(path) as reader:
        return reader.read_all()


def _read_png16(path: Path) -> np.ndarray:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    width = height = 0
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _compression, _filter, _interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            assert (depth, color) == (16, 0)
        elif kind == b"IDAT":
            compressed.extend(payload)
        offset += 12 + length
    raw = zlib.decompress(compressed)
    stride = 1 + 2 * width
    rows = []
    for row in range(height):
        scanline = raw[row * stride : (row + 1) * stride]
        assert scanline[0] == 0
        rows.append(scanline[1:])
    return np.frombuffer(b"".join(rows), dtype=">u2").astype(np.int32).reshape(height, width)


def test_export_writes_versioned_complete_round_trippable_truth(tmp_path: Path) -> None:
    sample = generate(family("four-bar-crank-rocker"), 2)
    truth = _clip(sample)
    result = export_clip(truth, tmp_path / "clip")

    assert result.clip_mp4.read_bytes() == truth.encoding.encoded_bytes
    manifest = json.loads(result.truth_json.read_text())
    assert manifest["format"] == "orrery.synthetic.truth"
    assert manifest["schemaVersion"] == 1
    assert manifest["mechanismGraph"] == sample.built.document
    assert manifest["appearance"] == json.loads(json.dumps(sample.appearance.record()))
    assert manifest["breakage"] is None
    assert manifest["encoding"]["codec"]["container"] == "mp4"
    assert manifest["depthFormat"] is None
    assert len(manifest["files"]) == 6

    frames = _read_arrow(result.frames_arrow)
    points = _read_arrow(result.points_arrow)
    assert frames.num_rows == 3
    assert points.num_rows == 3 * sum(
        len(body["points"]) for body in sample.built.document["bodies"]
    )
    assert frames.schema.metadata[b"orrery.schema_version"] == b"1"
    assert points.schema.metadata[b"orrery.table"] == b"points"
    assert any(point["visible"] for point in points.to_pylist())
    first = frames.to_pylist()[0]
    assert first["drivers"] == [
        {"driver_id": sample.built.document["drivers"][0]["id"], "value": 0.0}
    ]
    assert {pose["body_id"] for pose in first["body_poses"]} == {
        body["id"] for body in sample.built.document["bodies"]
    }
    assert first["camera"]["model"] == "pinhole-brown-conrady-planar"
    assert len(result.mask_paths) == 3
    assert np.array_equal(_read_png16(result.mask_paths[0]), truth.frames[0].rendered.instance_id)


def test_export_is_byte_deterministic_and_preserves_dropped_frame_indices(tmp_path: Path) -> None:
    truth = _clip(generate(family("slider-crank"), 4), frame_count=5, drop_probability=1.0)
    first = export_clip(truth, tmp_path / "first")
    second = export_clip(truth, tmp_path / "second")

    first_files = {
        path.relative_to(first.directory): path.read_bytes()
        for path in first.directory.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second.directory): path.read_bytes()
        for path in second.directory.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    rows = _read_arrow(first.frames_arrow).to_pylist()
    assert [row["source_frame_index"] for row in rows] == [0, 4]
    assert [row["frame_index"] for row in rows] == [0, 1]
    assert len(first.mask_paths) == 2


@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(family_name=st.sampled_from(PLANAR_FAMILIES), seed=st.integers(0, 100))
def test_every_visible_projected_point_is_inside_its_instance_mask_away_from_boundaries(
    family_name: str, seed: int, tmp_path: Path
) -> None:
    """Property 3: visibility implies a 3x3 interior neighborhood of the owning instance."""
    truth = _clip(generate(family(family_name), seed), frame_count=2, width=240, height=180)
    target = tmp_path / f"clip-{family_name}-{seed}"
    shutil.rmtree(target, ignore_errors=True)
    result = export_clip(truth, target)
    manifest = json.loads(result.truth_json.read_text())
    instance_ids = manifest["instanceIds"]
    masks = [_read_png16(path) for path in result.mask_paths]
    for point in _read_arrow(result.points_arrow).to_pylist():
        if not point["visible"]:
            continue
        row, column = math.floor(point["y_px"]), math.floor(point["x_px"])
        neighborhood = masks[point["frame_index"]][row - 1 : row + 2, column - 1 : column + 2]
        assert neighborhood.shape == (3, 3)
        assert np.all(neighborhood == instance_ids[point["body_id"]])
        assert point["occluded_by"] is None


def test_breakage_and_real_degradation_metadata_are_exported_without_substitution(
    tmp_path: Path,
) -> None:
    sample = generate(family("four-bar-crank-rocker"), 3)
    broken = apply_breakage(sample, sample.built.breakable[0], "truth-break")
    truth = _clip(sample, breakage=broken)
    truth = replace(truth, degradations={"encoding-stage": truth.encoding.metadata})
    result = export_clip(truth, tmp_path / "broken")
    manifest = json.loads(result.truth_json.read_text())

    assert manifest["mechanismGraph"] == broken.document
    assert manifest["appearance"] == json.loads(json.dumps(broken.appearance.record()))
    assert manifest["breakage"] == json.loads(json.dumps(broken.record.record()))
    assert manifest["degradations"]["encoding-stage"] == manifest["encoding"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("timestamp", "timestamps"),
        ("pose", "exactly one pose"),
        ("driver", "exactly one value"),
        ("codec", "MP4"),
    ],
)
def test_export_rejects_incomplete_or_mismatched_truth(
    tmp_path: Path, change: str, message: str
) -> None:
    truth = _clip(generate(family("four-bar-crank-rocker"), 1))
    if change == "timestamp":
        frames = (replace(truth.frames[0], timestamp=0.001), *truth.frames[1:])
        truth = replace(truth, frames=frames)
    elif change == "pose":
        poses = dict(truth.frames[0].body_poses)
        poses.pop(next(iter(poses)))
        truth = replace(
            truth,
            frames=(replace(truth.frames[0], body_poses=poses), *truth.frames[1:]),
        )
    elif change == "driver":
        truth = replace(
            truth,
            frames=(replace(truth.frames[0], driver_values={}), *truth.frames[1:]),
        )
    else:
        metadata = replace(
            truth.encoding.metadata,
            codec=replace(
                truth.encoding.metadata.codec,
                codec="vp9",
                encoder="libvpx-vp9",
                probed_codec_name="vp9",
                container="webm",
                file_extension=".webm",
            ),
        )
        truth = replace(truth, encoding=replace(truth.encoding, metadata=metadata))
    with pytest.raises(ValueError, match=message):
        export_clip(truth, tmp_path / change)


def test_actual_dynamics_frames_and_poses_are_cross_validated_and_exported(tmp_path: Path) -> None:
    sample = generate(family("four-bar-crank-rocker"), 3)
    broken = apply_breakage(sample, sample.built.breakable[0], "dynamic-truth")
    trajectory = simulate(broken, 2.0 / 480.0)
    timestamps = tuple(frame.time for frame in trajectory.frames)
    config = RenderConfig(width=160, height=120, clutter_count=0, shadows=False)
    rendered = []
    truth_frames = []
    camera = None
    for dynamic in trajectory.frames:
        poses = _identity_poses(broken.document)
        poses.update(dynamic.poses)
        image = render_frame(
            broken.document,
            broken.appearance,
            np.random.default_rng(14),
            camera=camera,
            poses=poses,
            time=dynamic.time,
            config=config,
        )
        camera = image.camera
        rendered.append(image)
        body_poses: dict[str, BodyPoseTruth] = dict(poses)
        truth_frames.append(
            TruthFrame(dynamic.time, _driver_values(broken.document), body_poses, image)
        )
    encoding = encode_video(
        np.stack([frame.pixels[:, :, :3] for frame in rendered]),
        timestamps,
        np.random.default_rng(15),
        config=_encoding_config(),
    )
    truth = ClipTruth(
        "dynamic-truth",
        "0.1.0",
        "broken-dynamics",
        sample,
        tuple(truth_frames),
        encoding,
        breakage=broken,
        dynamics=trajectory,
    )
    result = export_clip(truth, tmp_path / "dynamic")
    manifest = json.loads(result.truth_json.read_text())

    assert manifest["dynamics"]["active_body_ids"] == list(trajectory.active_body_ids)
    assert manifest["dynamics"]["energies"] == list(trajectory.energies)
    frame_rows = _read_arrow(result.frames_arrow).to_pylist()
    active = trajectory.active_body_ids[0]
    exported = next(
        pose for pose in frame_rows[-1]["body_poses"] if pose["body_id"] == active
    )
    expected = trajectory.frames[-1].poses[active]
    assert exported["translation"][:2] == pytest.approx([expected.x, expected.y])


def test_real_3d_render_exports_optional_depth_and_camera_extrinsics(tmp_path: Path) -> None:
    sample = generate(family("four-bar-crank-rocker"), 2)
    rendered = render_3d(
        sample.built.document,
        sample.appearance,
        Render3DConfig(
            width=32,
            height=24,
            samples=1,
            seed=13,
            threads=1,
            rod_sides=6,
            frame_count=2,
        ),
    )
    timestamps = (0.0, 0.04)
    rgb8 = np.repeat(
        np.clip(rendered.rgb * 255.0, 0.0, 255.0).astype(np.uint8)[np.newaxis],
        2,
        axis=0,
    )
    encoding = encode_video(
        rgb8,
        timestamps,
        np.random.default_rng(8),
        config=_encoding_config(),
    )
    poses = _identity_poses(sample.built.document)
    drivers = _driver_values(sample.built.document)
    truth = ClipTruth(
        "real-3d-depth",
        "0.1.0",
        "clean-3d",
        sample,
        tuple(
            TruthFrame(timestamp, dict(drivers), dict(poses), rendered)
            for timestamp in timestamps
        ),
        encoding,
    )
    result = export_clip(truth, tmp_path / "three-dimensional")

    manifest = json.loads(result.truth_json.read_text())
    assert manifest["renderMode"] == "3d"
    assert manifest["depthFormat"].startswith("image/x-exr")
    assert len(result.depth_paths) == 2
    assert np.array_equal(read_exr(result.depth_paths[0]).channels["Z"], rendered.depth)
    camera = _read_arrow(result.frames_arrow).to_pylist()[0]["camera"]
    assert camera["model"] == "blender-perspective"
    assert camera["worldToCamera"] == list(rendered.camera.world_to_camera)


def test_depth_writer_round_trips_float32_infinity_convention(tmp_path: Path) -> None:
    depth = np.array([[np.inf, 1.25], [2.5, 4.0]], dtype=np.float32)
    path = tmp_path / "depth.exr"
    path.write_bytes(depth_exr(depth))
    image = read_exr(path)
    assert set(image.channels) == {"Z"}
    assert np.array_equal(image.channels["Z"], depth)

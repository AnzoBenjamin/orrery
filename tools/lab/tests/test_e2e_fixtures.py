"""Committed real-pipeline clips for end-to-end consumers (requirement 6.3)."""

# pyarrow has no complete stubs; Arrow inspection in this test module is its adapter boundary.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import cast

import pyarrow as pa
from orrery_lab.graph import Json
from orrery_lab.suite import decoded_frame_hash
from orrery_lab.suite.fixtures import (
    FIXTURE_FORMAT,
    GENERATION_COMMAND,
    materialize_fixture_suite,
    read_fixture_suite,
)

REPOSITORY = Path(__file__).parents[3]
FIXTURES = REPOSITORY / "e2e/fixtures/synthetic-lab"
MANIFEST = REPOSITORY / "tools/lab/fixtures/e2e.toml"
SCRIPT = REPOSITORY / "tools/lab/scripts/generate_e2e_fixtures.py"
EXPECTED = {
    "clean-four-bar": ("four-bar-crank-rocker", "clean-fixture", "none"),
    "broken-flapping-wing": ("flapping-wing", "clean-fixture", "binary_link"),
    "repaired-flapping-wing": ("flapping-wing", "clean-fixture", "none"),
    "phone-slider-crank": ("slider-crank", "phone-fixture", "none"),
}


def _truth(clip_id: str) -> Json:
    path = FIXTURES / "suite" / clip_id / "truth.json"
    return cast(Json, json.loads(path.read_text(encoding="utf-8")))


def _arrow_rows(clip_id: str) -> list[dict[str, object]]:
    path = FIXTURES / "suite" / clip_id / "frames.arrow"
    with pa.ipc.open_file(path) as reader:
        return cast(list[dict[str, object]], reader.read_all().to_pylist())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_committed_fixture_index_and_all_truth_assets_are_valid() -> None:
    result = read_fixture_suite(FIXTURES)

    assert result.index["format"] == FIXTURE_FORMAT
    assert result.index["generator"] == {
        "command": GENERATION_COMMAND,
        "manifestPath": "tools/lab/fixtures/e2e.toml",
        "pipeline": [
            "suite-manifest",
            "seeded-family-sampler",
            "kinematics-or-loose-part-dynamics",
            "skia-renderer",
            "capture-degradation",
            "ffmpeg-encoding",
            "versioned-truth-export",
        ],
    }
    assert SCRIPT.is_file()
    assert {clip.id for clip in result.suite.clips} == set(EXPECTED)
    assert sum(path.stat().st_size for path in FIXTURES.rglob("*") if path.is_file()) < 1024**2

    for clip in result.suite.clips:
        family_name, profile, breakage = EXPECTED[clip.id]
        assert (clip.family, clip.profile, clip.breakage) == (family_name, profile, breakage)
        truth = _truth(clip.id)
        assert truth["format"] == "orrery.synthetic.truth"
        assert truth["schemaVersion"] == 1
        assert truth["family"] == family_name
        assert truth["captureProfile"] == profile
        assert truth["sourceFrameCount"] == 8
        assert truth["encodedFrameCount"] == 8
        assert truth["renderMode"] == "2d"
        assert truth["depthFormat"] is None
        files = cast(list[Json], truth["files"])
        for item in files:
            path = clip.directory / cast(str, item["path"])
            assert path.stat().st_size == item["bytes"]
            assert _sha256(path) == item["sha256"]
        decoded = decoded_frame_hash(
            (clip.directory / "clip.mp4").read_bytes(),
            extension=".mp4",
            width=96,
            height=64,
        )
        assert decoded == clip.decoded_frames


def test_broken_wing_uses_real_dynamics_and_repaired_wing_is_its_intact_specimen() -> None:
    broken = _truth("broken-flapping-wing")
    repaired = _truth("repaired-flapping-wing")
    breakage = cast(Json, broken["breakage"])
    dynamics = cast(Json, broken["dynamics"])
    relation = next(
        cast(Json, record["relationship"])
        for record in cast(list[Json], read_fixture_suite(FIXTURES).index["clips"])
        if record["id"] == "repaired-flapping-wing"
    )

    assert breakage["kind"] == "binary_link"
    assert [body["id"] for body in cast(list[Json], breakage["removedBodies"])] == ["rod-left"]
    assert dynamics["active_body_ids"] == ["wing-left"]
    frames = cast(list[Json], dynamics["frames"])
    angles = [cast(Json, cast(Json, frame["poses"])["wing-left"])["angle"] for frame in frames]
    assert all(math.isfinite(cast(float, angle)) for angle in angles)
    assert abs(cast(float, angles[-1]) - cast(float, angles[0])) > 0.02
    assert all(
        math.isfinite(cast(float, value)) for value in cast(list[object], dynamics["energies"])
    )

    for field in ("sampleId", "seed", "acceptedAttempt", "params", "sourceMechanismSha256"):
        assert repaired[field] == broken[field]
    assert repaired["breakage"] is None
    repaired_bodies = {
        body["id"] for body in cast(list[Json], repaired["mechanismGraph"]["bodies"])
    }
    assert "rod-left" in repaired_bodies
    assert relation == {
        "kind": "repair-of",
        "sourceClipId": "broken-flapping-wing",
        "sourceBreakageId": breakage["id"],
        "removedBodyIds": ["rod-left"],
    }
    repaired_drives = [
        cast(list[Json], row["drivers"])[0]["value"]
        for row in _arrow_rows("repaired-flapping-wing")
    ]
    assert len(set(repaired_drives)) > 1


def test_phone_slider_uses_recorded_camera_sensor_and_vfr_degradation() -> None:
    truth = _truth("phone-slider-crank")
    degradations = cast(Json, truth["degradations"])
    timing = cast(Json, cast(Json, truth["encoding"])["timing"])
    rows = _arrow_rows("phone-slider-crank")

    assert set(degradations) == {"camera", "sensor"}
    assert cast(Json, degradations["sensor"])["workingSpace"] == "linear-rgb"
    assert timing["vfr_jitter_enabled"] is True
    cameras = [cast(Json, row["camera"])["centerWorld"] for row in rows]
    assert len({tuple(cast(list[float], camera)) for camera in cameras}) > 1


def test_committed_fixtures_match_deterministic_real_pipeline_regeneration() -> None:
    regenerated = materialize_fixture_suite(MANIFEST, FIXTURES, check=True)
    assert regenerated.suite.manifest_hash == regenerated.index["suiteManifestHash"]

"""Versioned suite manifests and deterministic generation (requirement 7)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from orrery_lab import LAB_VERSION
from orrery_lab.degrade import EncodingConfig, encode_video
from orrery_lab.families import FAMILIES
from orrery_lab.suite import (
    CaptureProfile,
    ClipSpec,
    LocalSuiteCache,
    S3SuiteCache,
    SuiteManifest,
    canonical_manifest_bytes,
    decoded_frame_hash,
    derive_clip_seed,
    generate_suite,
    load_manifest,
    manifest_hash,
    plan_clips,
    read_suite,
)

SUITES = Path(__file__).parents[1] / "suites"


def _manifest(seed: int, family_name: str = "four-bar-crank-rocker") -> SuiteManifest:
    return SuiteManifest(
        schema_version=1,
        name="property",
        seed=seed,
        runtime_budget_seconds=60,
        profiles=(
            CaptureProfile(
                name="tiny",
                tier="clean",
                width=64,
                height=48,
                frame_rate=4,
                frame_count=2,
                codec="h264",
                clutter_count=0,
                shadows=False,
            ),
        ),
        clips=(ClipSpec(id="property-clip", family=family_name, profile="tiny"),),
    )


def _files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_real_manifests_load_and_declare_composition_and_budget_intent() -> None:
    smoke = load_manifest(SUITES / "smoke.toml")
    core = load_manifest(SUITES / "core.toml")
    full = load_manifest(SUITES / "full.toml")

    assert smoke.runtime_budget_seconds == 180
    assert core.runtime_budget_seconds == 45 * 60
    assert full.runtime_budget_seconds == 8 * 60 * 60
    assert {clip.family for clip in core.clips} == set(FAMILIES)
    assert {profile.tier for profile in full.profiles} == {
        "clean",
        "phone",
        "hostile",
        "archival",
    }
    assert {clip.breakage for clip in full.clips} >= {
        "any",
        "slider_block",
        "gear",
        "belt",
        "adjacent_links",
    }
    assert all(
        core.profile(clip.profile).render_mode == "3d"
        for clip in core.clips
        if clip.family in {"spatial-rssr", "two-plane-cardan"}
    )


def test_manifest_hash_uses_canonical_semantics_and_lab_version(tmp_path: Path) -> None:
    first = _manifest(12)
    path = tmp_path / "reformatted.toml"
    path.write_text(
        """name = "property"
runtime_budget_seconds = 60
seed = 12
schema_version = 1
[[clips]]
profile = "tiny"
family = "four-bar-crank-rocker"
id = "property-clip"
[[profiles]]
frame_count = 2
frame_rate = 4
height = 48
width = 64
tier = "clean"
name = "tiny"
codec = "h264"
clutter_count = 0
shadows = false
"""
    )
    second = load_manifest(path)

    assert canonical_manifest_bytes(first) == canonical_manifest_bytes(second)
    assert manifest_hash(first, LAB_VERSION) == manifest_hash(second, LAB_VERSION)
    assert manifest_hash(first, LAB_VERSION) != manifest_hash(first, f"{LAB_VERSION}+changed")
    assert len(manifest_hash(first, LAB_VERSION)) == 64


def test_clip_seeds_are_stable_unique_and_manifest_ordered() -> None:
    manifest = SuiteManifest(
        schema_version=1,
        name="seeds",
        seed=42,
        runtime_budget_seconds=60,
        profiles=(_manifest(0).profiles[0],),
        clips=tuple(
            ClipSpec(id=f"clip-{name}", family=name, profile="tiny")
            for name in ("slider-crank", "gear-train", "belt-drive")
        ),
    )
    first = plan_clips(manifest)
    second = plan_clips(manifest)

    assert first == second
    assert [plan.index for plan in first] == [0, 1, 2]
    assert len({plan.seed for plan in first}) == 3
    assert first[2].seed == derive_clip_seed(42, 2)


def test_decoded_hash_is_over_real_decoded_frames_and_not_container_metadata() -> None:
    frames = np.zeros((3, 16, 24, 3), dtype=np.uint8)
    frames[1, :, :, 0] = 170
    frames[2, :, :, 1] = 90
    config = EncodingConfig(
        codecs=("h264",),
        pixel_formats=("yuv420p",),
        variable_frame_rate=False,
        drop_probability=0.0,
    )
    first = encode_video(frames, (0.0, 0.04, 0.08), np.random.default_rng(4), config=config)
    second = encode_video(frames, (0.0, 0.04, 0.08), np.random.default_rng(4), config=config)
    hashes = [
        decoded_frame_hash(result.encoded_bytes, extension=".mp4", width=24, height=16)
        for result in (first, second)
    ]

    assert hashes[0] == hashes[1]
    assert hashes[0].frame_count == 3
    assert len(hashes[0].digest) == 64


@settings(
    max_examples=3,
    deadline=None,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(
    seed=st.integers(min_value=0, max_value=10_000),
    family_name=st.sampled_from(("four-bar-crank-rocker", "slider-crank", "gear-train")),
)
def test_repeated_generation_has_byte_identical_truth_and_decoded_hashes(
    seed: int, family_name: str, tmp_path: Path
) -> None:
    """Property 2: the canonical manifest and lab version completely determine suite content."""
    manifest = _manifest(seed, family_name)
    first_root = tmp_path / f"first-{seed}-{family_name}"
    second_root = tmp_path / f"second-{seed}-{family_name}"
    shutil.rmtree(first_root, ignore_errors=True)
    shutil.rmtree(second_root, ignore_errors=True)

    first = generate_suite(manifest, first_root)
    second = generate_suite(manifest, second_root)

    assert first.manifest_hash == second.manifest_hash
    assert first.clips[0].decoded_frames == second.clips[0].decoded_frames
    assert first.clips[0].truth_sha256 == second.clips[0].truth_sha256
    assert (first.clips[0].directory / "truth.json").read_bytes() == (
        second.clips[0].directory / "truth.json"
    ).read_bytes()
    assert _files(first.directory) == _files(second.directory)


def test_local_cache_reuses_valid_suite_by_manifest_hash(tmp_path: Path) -> None:
    cache = LocalSuiteCache(tmp_path / "object-cache")
    first = generate_suite(_manifest(71), tmp_path / "first-output", cache=cache)
    restored = generate_suite(_manifest(71), tmp_path / "second-output", cache=cache)

    assert not first.cache_hit
    assert restored.cache_hit
    assert restored.manifest_hash == first.manifest_hash
    assert _files(restored.directory) == _files(first.directory)
    assert (tmp_path / "object-cache" / first.manifest_hash / "suite.json").is_file()


def test_cache_and_suite_reader_reject_tampering(tmp_path: Path) -> None:
    result = generate_suite(_manifest(73), tmp_path / "output")
    (result.clips[0].directory / "truth.json").write_bytes(b"{}\n")

    with pytest.raises(ValueError, match=r"integrity|truth hash"):
        read_suite(result.directory, expected_hash=result.manifest_hash)


def test_real_garage_cache_round_trip_when_integration_environment_is_available(
    tmp_path: Path,
) -> None:
    names = (
        "ORRERY_TEST_S3_ENDPOINT",
        "ORRERY_TEST_S3_BUCKET",
        "ORRERY_TEST_S3_REGION",
        "ORRERY_TEST_S3_ACCESS_KEY_ID",
        "ORRERY_TEST_S3_SECRET_ACCESS_KEY",
    )
    values = [os.environ.get(name) for name in names]
    if not all(values):
        pytest.skip("real Garage integration environment is not configured")
    endpoint, bucket, region, access_key, secret_key = values
    assert all(value is not None for value in values)
    generated = generate_suite(_manifest(91), tmp_path / "source")
    cache = S3SuiteCache(
        endpoint_url=endpoint or "",
        bucket=bucket or "",
        region=region or "",
        access_key_id=access_key or "",
        secret_access_key=secret_key or "",
        prefix="synthetic-lab/integration-tests",
    )
    cache.store(generated.manifest_hash, generated.directory)
    destination = tmp_path / "garage-restored"

    assert cache.restore(generated.manifest_hash, destination)
    restored = read_suite(destination, expected_hash=generated.manifest_hash, cache_hit=True)
    assert restored.clips[0].decoded_frames == generated.clips[0].decoded_frames
    assert _files(destination) == _files(generated.directory)


@pytest.mark.parametrize(
    "change",
    ["unknown-profile", "duplicate-id", "spatial-in-2d", "odd-dimensions"],
)
def test_manifest_validation_rejects_ambiguous_or_unencodable_suites(change: str) -> None:
    base = _manifest(0).model_dump(mode="python")
    clips = list(base["clips"])
    profiles = list(base["profiles"])
    base["clips"] = clips
    base["profiles"] = profiles
    if change == "unknown-profile":
        clips[0]["profile"] = "missing"
    elif change == "duplicate-id":
        clips.append(dict(clips[0]))
    elif change == "spatial-in-2d":
        clips[0]["family"] = "spatial-rssr"
    else:
        profiles[0]["width"] = 63
    with pytest.raises(ValueError, match=r"profile|unique|3d|even"):
        SuiteManifest.model_validate(base)

"""Deterministic materialization and validation of committed end-to-end fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from orrery_lab import LAB_VERSION
from orrery_lab.graph import Json
from orrery_lab.suite.generator import SuiteResult, generate_suite, read_suite
from orrery_lab.suite.manifest import load_manifest

FIXTURE_FORMAT = "orrery.e2e.synthetic-fixtures"
FIXTURE_VERSION = 1
FIXTURE_INDEX = "index.json"
SUITE_DIRECTORY = "suite"
GENERATION_COMMAND = "uv run --frozen python tools/lab/scripts/generate_e2e_fixtures.py"
GENERATION_MANIFEST = "tools/lab/fixtures/e2e.toml"
PIPELINE = (
    "suite-manifest",
    "seeded-family-sampler",
    "kinematics-or-loose-part-dynamics",
    "skia-renderer",
    "capture-degradation",
    "ffmpeg-encoding",
    "versioned-truth-export",
)


@dataclass(frozen=True)
class FixtureSuite:
    directory: Path
    index: Json
    suite: SuiteResult


def materialize_fixture_suite(
    manifest_path: Path,
    destination: Path,
    *,
    check: bool = False,
) -> FixtureSuite:
    """Generate all fixture bytes from the real suite pipeline, then atomically install or check."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".synthetic-fixtures-", dir=destination.parent))
    candidate = temporary / "candidate"
    try:
        generated = generate_suite(load_manifest(manifest_path), temporary / "generated")
        shutil.copytree(generated.directory, candidate / SUITE_DIRECTORY)
        index = _build_index(candidate, generated)
        (candidate / FIXTURE_INDEX).write_bytes(_canonical_json(index))
        if check:
            if not destination.is_dir() or _file_bytes(candidate) != _file_bytes(destination):
                raise RuntimeError(
                    f"committed fixtures differ from deterministic regeneration: {destination}"
                )
        else:
            _replace_directory(candidate, destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return read_fixture_suite(destination)


def read_fixture_suite(directory: Path) -> FixtureSuite:
    """Validate the fixture index, every byte hash, suite integrity, and repair provenance."""
    index_path = directory / FIXTURE_INDEX
    try:
        index = cast(Json, json.loads(index_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid fixture index {index_path}: {error}") from error
    if index.get("format") != FIXTURE_FORMAT or index.get("schemaVersion") != FIXTURE_VERSION:
        raise ValueError("fixture index format or schema version is unsupported")
    if index.get("labVersion") != LAB_VERSION:
        raise ValueError("fixture index lab version differs from the installed lab")
    expected_files = _validate_inventory(directory, index.get("files"))
    observed_files = {
        path.relative_to(directory)
        for path in directory.rglob("*")
        if path.is_file() and path.name != FIXTURE_INDEX
    }
    if expected_files != observed_files:
        raise ValueError("fixture files differ from the indexed inventory")
    manifest_hash = _string(index, "suiteManifestHash")
    suite = read_suite(directory / SUITE_DIRECTORY, expected_hash=manifest_hash)
    records_value = index.get("clips")
    if not isinstance(records_value, list):
        raise ValueError("fixture clip index must be a list")
    records = cast(list[object], records_value)
    if len(records) != len(suite.clips):
        raise ValueError("fixture clip index differs from the generated suite")
    by_id = {clip.id: clip for clip in suite.clips}
    for value in records:
        record = _object(value, "fixture clip")
        clip = by_id.get(_string(record, "id"))
        if clip is None or _string(record, "truthSha256") != clip.truth_sha256:
            raise ValueError("fixture clip provenance differs from suite truth")
        if record.get("sourceClip") != clip.source_clip:
            raise ValueError("fixture source relation differs from suite manifest")
        _validate_relationship(directory, record)
    return FixtureSuite(directory, index, suite)


def _build_index(root: Path, generated: SuiteResult) -> Json:
    suite_index_path = root / SUITE_DIRECTORY / "suite.json"
    suite_index = cast(Json, json.loads(suite_index_path.read_text(encoding="utf-8")))
    clips: list[Json] = []
    truths: dict[str, Json] = {}
    for clip in generated.clips:
        truth_path = root / SUITE_DIRECTORY / clip.id / "truth.json"
        truths[clip.id] = cast(Json, json.loads(truth_path.read_text(encoding="utf-8")))
    for clip in generated.clips:
        truth = truths[clip.id]
        relationship: Json | None = None
        if clip.source_clip is not None:
            source = truths[clip.source_clip]
            _assert_repair_pair(source, truth)
            breakage = _object(source.get("breakage"), "source breakage")
            removed = cast(list[object], breakage["removedBodies"])
            relationship = {
                "kind": "repair-of",
                "sourceClipId": clip.source_clip,
                "sourceBreakageId": breakage["id"],
                "removedBodyIds": [
                    _string(_object(body, "removed body"), "id") for body in removed
                ],
            }
        clips.append(
            {
                "id": clip.id,
                "family": clip.family,
                "profile": clip.profile,
                "sampleId": truth["sampleId"],
                "sampleSeed": clip.seed,
                "sourceMechanismSha256": truth["sourceMechanismSha256"],
                "selectedBreakage": clip.breakage,
                "sourceClip": clip.source_clip,
                "relationship": relationship,
                "truthSha256": clip.truth_sha256,
                "decodedFrames": clip.decoded_frames.record(),
            }
        )
    return {
        "format": FIXTURE_FORMAT,
        "schemaVersion": FIXTURE_VERSION,
        "labVersion": LAB_VERSION,
        "generator": {
            "command": GENERATION_COMMAND,
            "manifestPath": GENERATION_MANIFEST,
            "pipeline": list(PIPELINE),
        },
        "suiteManifestHash": generated.manifest_hash,
        "suiteManifestCanonicalSha256": suite_index["manifestCanonicalSha256"],
        "suiteIndexSha256": _sha256(suite_index_path),
        "clips": clips,
        "files": [_file_record(path, root) for path in _files(root)],
    }


def _validate_relationship(directory: Path, record: Json) -> None:
    source_id = record.get("sourceClip")
    relation = record.get("relationship")
    if source_id is None:
        if relation is not None:
            raise ValueError("an unrelated fixture clip has relationship metadata")
        return
    if not isinstance(source_id, str):
        raise ValueError("fixture source clip must be a string or null")
    source = _read_truth(directory, source_id)
    repaired = _read_truth(directory, _string(record, "id"))
    _assert_repair_pair(source, repaired)
    relationship = _object(relation, "fixture relationship")
    breakage = _object(source.get("breakage"), "source breakage")
    if relationship.get("kind") != "repair-of" or relationship.get("sourceClipId") != source_id:
        raise ValueError("fixture repair relationship is invalid")
    if relationship.get("sourceBreakageId") != breakage.get("id"):
        raise ValueError("fixture repair relationship names the wrong breakage")


def _assert_repair_pair(source: Json, repaired: Json) -> None:
    fields = ("family", "sampleId", "seed", "acceptedAttempt", "params", "sourceMechanismSha256")
    if any(source.get(field) != repaired.get(field) for field in fields):
        raise ValueError("repaired fixture is not the same sampled specimen as its broken source")
    if source.get("breakage") is None or repaired.get("breakage") is not None:
        raise ValueError("repair relation must connect a broken clip to an intact clip")


def _read_truth(directory: Path, clip_id: str) -> Json:
    path = directory / SUITE_DIRECTORY / clip_id / "truth.json"
    return cast(Json, json.loads(path.read_text(encoding="utf-8")))


def _validate_inventory(directory: Path, value: object) -> set[Path]:
    if not isinstance(value, list):
        raise ValueError("fixture file inventory must be a list")
    values = cast(list[object], value)
    expected: set[Path] = set()
    for value_item in values:
        item = _object(value_item, "fixture file")
        relative = Path(_string(item, "path"))
        if relative.is_absolute() or ".." in relative.parts or relative in expected:
            raise ValueError("fixture inventory contains an unsafe or duplicate path")
        path = directory / relative
        size = item.get("bytes")
        if not isinstance(size, int) or isinstance(size, bool):
            raise ValueError("fixture file byte size must be an integer")
        if not path.is_file() or path.stat().st_size != size or _sha256(path) != item.get("sha256"):
            raise ValueError(f"fixture file failed integrity validation: {relative}")
        expected.add(relative)
    return expected


def _replace_directory(candidate: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}-backup")
    shutil.rmtree(backup, ignore_errors=True)
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(candidate, destination)
    except BaseException:
        if backup.exists():
            os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def _file_bytes(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in _files(root)}


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _file_record(path: Path, root: Path) -> Json:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _object(value: object, label: str) -> Json:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Json, value)


def _string(record: Json, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"fixture field {field!r} must be a string")
    return value


def _canonical_json(value: Json) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


__all__ = [
    "FIXTURE_FORMAT",
    "FIXTURE_INDEX",
    "FIXTURE_VERSION",
    "GENERATION_COMMAND",
    "FixtureSuite",
    "materialize_fixture_suite",
    "read_fixture_suite",
]

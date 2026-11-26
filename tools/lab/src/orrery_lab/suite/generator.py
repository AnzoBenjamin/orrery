"""Atomic deterministic orchestration of complete generated suites."""

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
from orrery_lab.suite.cache import SuiteCache
from orrery_lab.suite.content import DecodedFrameHash, decoded_frame_hash
from orrery_lab.suite.manifest import (
    MANIFEST_FORMAT,
    MANIFEST_VERSION,
    SuiteManifest,
    canonical_manifest_bytes,
    load_manifest,
    manifest_hash,
    plan_clips,
)
from orrery_lab.suite.pipeline import build_clip
from orrery_lab.truth import export_clip

SUITE_INDEX = "suite.json"


@dataclass(frozen=True)
class GeneratedClip:
    id: str
    family: str
    profile: str
    seed: int
    breakage: str
    directory: Path
    truth_sha256: str
    decoded_frames: DecodedFrameHash


@dataclass(frozen=True)
class SuiteResult:
    directory: Path
    manifest_hash: str
    clips: tuple[GeneratedClip, ...]
    cache_hit: bool = False


def generate_suite(
    manifest_or_path: SuiteManifest | Path,
    output_root: Path,
    *,
    cache: SuiteCache | None = None,
) -> SuiteResult:
    """Generate a suite once under ``output_root/<manifest hash>`` and reuse valid caches."""
    manifest = (
        load_manifest(manifest_or_path) if isinstance(manifest_or_path, Path) else manifest_or_path
    )
    identity = manifest_hash(manifest, LAB_VERSION)
    destination = output_root / identity
    if destination.exists():
        return read_suite(destination, expected_hash=identity, cache_hit=True)
    if cache is not None and cache.restore(identity, destination):
        return read_suite(destination, expected_hash=identity, cache_hit=True)
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{identity}-", dir=output_root))
    try:
        clips: list[dict[str, object]] = []
        for plan in plan_clips(manifest):
            built = build_clip(plan)
            clip_directory = temporary / plan.spec.id
            exported = export_clip(built.truth, clip_directory)
            content_hash = decoded_frame_hash(
                built.truth.encoding.encoded_bytes,
                extension=built.truth.encoding.metadata.codec.file_extension,
                width=plan.profile.width,
                height=plan.profile.height,
            )
            expected_count = built.truth.encoding.metadata.probe.frame_count
            if content_hash.frame_count != expected_count:
                raise RuntimeError("decoded frame hash count differs from verified encoding probe")
            clips.append(
                {
                    "id": plan.spec.id,
                    "family": plan.spec.family,
                    "profile": plan.spec.profile,
                    "seed": plan.seed,
                    "requestedBreakage": plan.spec.breakage,
                    "selectedBreakage": built.selected_breakage,
                    "path": plan.spec.id,
                    "truthSha256": _sha256(exported.truth_json),
                    "decodedFrames": content_hash.record(),
                }
            )
        files = [_file_record(path, temporary) for path in _files(temporary)]
        index = {
            "format": MANIFEST_FORMAT,
            "schemaVersion": MANIFEST_VERSION,
            "labVersion": LAB_VERSION,
            "manifestHash": identity,
            "manifestCanonicalSha256": hashlib.sha256(
                canonical_manifest_bytes(manifest)
            ).hexdigest(),
            "manifest": manifest.canonical_record(),
            "runtimeBudgetSeconds": manifest.runtime_budget_seconds,
            "clips": clips,
            "files": files,
        }
        (temporary / SUITE_INDEX).write_bytes(_canonical_json(index))
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    result = read_suite(destination, expected_hash=identity)
    if cache is not None:
        cache.store(identity, destination)
    return result


def read_suite(
    directory: Path, *, expected_hash: str | None = None, cache_hit: bool = False
) -> SuiteResult:
    """Validate every cached byte before exposing a generated suite."""
    index_path = directory / SUITE_INDEX
    try:
        raw = cast(dict[str, object], json.loads(index_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid generated suite index {index_path}: {error}") from error
    if raw.get("format") != MANIFEST_FORMAT or raw.get("schemaVersion") != MANIFEST_VERSION:
        raise ValueError("generated suite format or schema version is unsupported")
    identity = raw.get("manifestHash")
    if not isinstance(identity, str) or (expected_hash is not None and identity != expected_hash):
        raise ValueError("generated suite manifest hash does not match its cache key")
    manifest_raw = raw.get("manifest")
    manifest = SuiteManifest.model_validate(manifest_raw)
    if manifest_hash(manifest, str(raw.get("labVersion"))) != identity:
        raise ValueError("generated suite canonical manifest/lab-version hash is invalid")
    _validate_files(directory, raw.get("files"))
    clips_raw = raw.get("clips")
    if not isinstance(clips_raw, list):
        raise ValueError("generated suite clips must be a list")
    clips = tuple(_read_clip(directory, item) for item in cast(list[object], clips_raw))
    if tuple(clip.id for clip in clips) != tuple(spec.id for spec in manifest.clips):
        raise ValueError("generated suite clips differ from manifest order")
    return SuiteResult(directory, identity, clips, cache_hit)


def _read_clip(directory: Path, value: object) -> GeneratedClip:
    if not isinstance(value, dict):
        raise ValueError("generated clip record must be an object")
    record = cast(dict[str, object], value)
    clip_id = _string(record, "id")
    relative = Path(_string(record, "path"))
    if relative != Path(clip_id) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("generated clip path is not its safe clip id")
    truth_sha = _string(record, "truthSha256")
    if _sha256(directory / relative / "truth.json") != truth_sha:
        raise ValueError(f"generated clip {clip_id!r} truth hash is invalid")
    decoded = record.get("decodedFrames")
    if not isinstance(decoded, dict):
        raise ValueError("decoded frame hash record must be an object")
    decoded_record = cast(dict[str, object], decoded)
    content_hash = DecodedFrameHash(
        _integer(decoded_record, "schemaVersion"),
        _string(decoded_record, "algorithm"),
        _string(decoded_record, "pixelFormat"),
        _integer(decoded_record, "width"),
        _integer(decoded_record, "height"),
        _integer(decoded_record, "frameCount"),
        _string(decoded_record, "digest"),
    )
    if content_hash.schema_version != 1 or content_hash.algorithm != "sha256":
        raise ValueError("decoded frame hash format is unsupported")
    return GeneratedClip(
        clip_id,
        _string(record, "family"),
        _string(record, "profile"),
        _integer(record, "seed"),
        _string(record, "selectedBreakage"),
        directory / relative,
        truth_sha,
        content_hash,
    )


def _validate_files(directory: Path, value: object) -> None:
    if not isinstance(value, list):
        raise ValueError("generated suite file inventory must be a list")
    expected: set[Path] = set()
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise ValueError("generated suite file record must be an object")
        record = cast(dict[str, object], item)
        relative = Path(_string(record, "path"))
        if relative.is_absolute() or ".." in relative.parts or relative == Path(SUITE_INDEX):
            raise ValueError("generated suite inventory contains an unsafe path")
        path = directory / relative
        if relative in expected or not path.is_file():
            raise ValueError("generated suite inventory contains a duplicate or missing file")
        expected.add(relative)
        if path.stat().st_size != _integer(record, "bytes") or _sha256(path) != _string(
            record, "sha256"
        ):
            raise ValueError(f"cached suite file failed integrity check: {relative}")
    observed = {
        path.relative_to(directory)
        for path in directory.rglob("*")
        if path.is_file() and path.name != SUITE_INDEX
    }
    if observed != expected:
        raise ValueError("generated suite files differ from the indexed inventory")


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _file_record(path: Path, root: Path) -> dict[str, object]:
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


def _string(record: dict[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"generated suite field {field!r} must be a string")
    return value


def _integer(record: dict[str, object], field: str) -> int:
    value = record.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"generated suite field {field!r} must be an integer")
    return value


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


__all__ = [
    "SUITE_INDEX",
    "GeneratedClip",
    "SuiteResult",
    "generate_suite",
    "read_suite",
]

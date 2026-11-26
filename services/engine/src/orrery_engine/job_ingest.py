"""Ingest-stage orchestration independent of lifecycle and callback delivery."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx

from orrery_engine.generated.contract import ReconstructJobRequest
from orrery_engine.ingest import IngestConfig, ingest_footage
from orrery_engine.job_support import sha256_file
from orrery_engine.probe import download
from orrery_engine.settings import Settings

CancelCheck = Callable[[], None]
ProgressCallback = Callable[[float, str], None]


class IngestChecksumError(RuntimeError):
    """Downloaded bytes differ from the checksum in the reconstruction request."""


@dataclass(frozen=True)
class IngestStageOutput:
    manifests: tuple[dict[str, object], ...]
    runtime_ms: float


def run_ingest_stage(
    request: ReconstructJobRequest,
    job_dir: Path,
    settings: Settings,
    http: httpx.Client,
    *,
    check_canceled: CancelCheck,
    progress: ProgressCallback,
) -> IngestStageOutput:
    """Download and normalize every requested footage item, then persist its manifest."""
    started = time.monotonic()
    manifests: list[dict[str, object]] = []
    footage_count = len(request.inputs.footage)
    for index, footage in enumerate(request.inputs.footage):
        check_canceled()
        footage_dir = job_dir / "ingest" / f"{index:02d}"
        footage_dir.mkdir(parents=True, exist_ok=True)
        source = footage_dir / "source"
        if source.exists():
            digest = sha256_file(source)
        else:
            partial = source.with_suffix(".part")
            partial.unlink(missing_ok=True)
            digest, _ = download(
                footage.source_url,
                partial,
                settings.max_source_bytes,
                http,
                check_canceled=check_canceled,
            )
            os.replace(partial, source)
        if footage.sha256 is not None and digest != footage.sha256:
            raise IngestChecksumError("Downloaded footage did not match its expected SHA-256.")
        progress(
            0.1 + 0.75 * index / footage_count,
            f"Decoding and normalizing footage {index + 1} of {footage_count}.",
        )
        result = ingest_footage(
            source,
            footage_dir,
            footage_id=footage.footage_id,
            source_sha256=digest,
            config=IngestConfig(
                settings.analysis_long_side,
                settings.proxy_long_side,
                settings.thumbnail_count,
            ),
            check_canceled=check_canceled,
        )
        manifests.append(result.manifest)
    output = IngestStageOutput(tuple(manifests), (time.monotonic() - started) * 1000)
    _write_json(job_dir / "ingest" / "manifest.json", list(output.manifests))
    return output


def load_ingest_manifests(job_dir: Path) -> tuple[dict[str, object], ...]:
    value: object = json.loads((job_dir / "ingest" / "manifest.json").read_text())
    if not isinstance(value, list):
        raise ValueError("the ingest checkpoint manifest is invalid")
    items = cast(list[object], value)
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("the ingest checkpoint manifest is invalid")
    return tuple(cast(dict[str, object], item) for item in items)


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    os.replace(temporary, path)


__all__ = [
    "IngestChecksumError",
    "IngestStageOutput",
    "load_ingest_manifests",
    "run_ingest_stage",
]

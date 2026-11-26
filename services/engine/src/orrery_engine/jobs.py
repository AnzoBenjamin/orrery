from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx

from orrery_engine.generated.contract import (
    AnalysisArtifacts,
    EngineEvent,
    JobAccepted,
    JobArtifact,
    JobError,
    JobStatus1,
    JobStatus3,
    ReconstructJobRequest,
)
from orrery_engine.ingest import IngestConfig, IngestError, ingest_footage
from orrery_engine.job_support import (
    job_error as _error,
)
from orrery_engine.job_support import (
    peak_rss_bytes as _peak_rss_bytes,
)
from orrery_engine.job_support import (
    request_fingerprint as _request_fingerprint,
)
from orrery_engine.job_support import (
    sha256_file as _sha256_file,
)
from orrery_engine.probe import SourceUnavailableError, TooLargeError, download
from orrery_engine.settings import Settings

MEDIA_TYPE = "application/vnd.orrery.analysis-artifacts+json"
STAGE_GRAPH = {"ingest": (), "camera_motion": ("ingest",)}


class JobCanceledError(RuntimeError):
    pass


class JobFailureError(RuntimeError):
    def __init__(self, error: JobError) -> None:
        super().__init__(error.message)
        self.error = error


@dataclass
class JobRecord:
    request: ReconstructJobRequest
    callback_secret: str | None
    status_url: str
    status: Literal["queued", "running", "failed", "canceled"] = "queued"
    current_stage: str | None = None
    progress: float = 0.0
    artifacts: list[JobArtifact] = field(default_factory=list[JobArtifact])
    error: JobError | None = None
    completed_stages: set[str] = field(default_factory=set[str])
    stage_runtimes: dict[str, float] = field(default_factory=dict[str, float])
    seq: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def job_id(self) -> UUID:
        return self.request.job_id


class JobManager:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self._settings = settings
        self._http = http
        self._records: dict[UUID, JobRecord] = {}
        self._records_lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.concurrency, thread_name_prefix="engine-job"
        )
        self._jobs_dir = settings.work_dir / "jobs"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._load_checkpoints()

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def submit(
        self,
        request: ReconstructJobRequest,
        callback_secret: str,
        status_url: str,
    ) -> JobAccepted:
        with self._records_lock:
            existing = self._records.get(request.job_id)
            if existing is not None:
                if _request_fingerprint(existing.request) != _request_fingerprint(request):
                    raise JobFailureError(
                        _error(
                            "invalid_input",
                            "The job ID already belongs to a different reconstruction request.",
                        )
                    )
                with existing.lock:
                    if existing.status in {"queued", "running"}:
                        return _accepted(existing)
                    existing.request = request
                    existing.callback_secret = callback_secret
                    existing.status_url = status_url
                    existing.status = "queued"
                    existing.current_stage = None
                    existing.progress = 0.0
                    existing.error = None
                    existing.cancel.clear()
                    self._checkpoint(existing)
                    self._executor.submit(self._run, existing)
                    return _accepted(existing)
            record = JobRecord(request, callback_secret, status_url)
            self._records[request.job_id] = record
            self._checkpoint(record)
            self._executor.submit(self._run, record)
            return _accepted(record)

    def status(self, job_id: UUID) -> JobStatus1 | JobStatus3 | None:
        with self._records_lock:
            record = self._records.get(job_id)
        if record is None:
            return None
        with record.lock:
            if record.status in {"failed", "canceled"}:
                error = record.error or _error(
                    "internal_error", "The terminal job has no recorded error."
                )
                terminal_status: Literal["failed", "canceled"] = (
                    "canceled" if record.status == "canceled" else "failed"
                )
                return JobStatus3(
                    contract_version="1",
                    job_id=job_id,
                    status=terminal_status,
                    artifacts=list(record.artifacts),
                    error=error,
                )
            active_status: Literal["queued", "running"] = (
                "running" if record.status == "running" else "queued"
            )
            return JobStatus1(
                contract_version="1",
                job_id=job_id,
                status=active_status,
                current_stage=record.current_stage,
                progress=record.progress,
                artifacts=list(record.artifacts),
            )

    def cancel(self, job_id: UUID) -> JobStatus1 | JobStatus3 | None:
        with self._records_lock:
            record = self._records.get(job_id)
        if record is None:
            return None
        record.cancel.set()
        return self.status(job_id)

    def _run(self, record: JobRecord) -> None:
        with record.lock:
            record.status = "running"
            self._checkpoint(record)
        try:
            if "ingest" not in record.completed_stages:
                self._run_ingest(record)
            self._check_canceled(record)
            self._emit(record, "stage_started", {"stage": "camera_motion"})
            raise JobFailureError(
                _error(
                    "capability_unavailable",
                    "Ingest completed, but camera-motion reconstruction is not implemented yet.",
                    stage="camera_motion",
                    prerequisites=("vision-pipeline:3.1",),
                )
            )
        except JobCanceledError:
            self._finish_failure(record, _error("canceled", "The reconstruction job was canceled."))
        except JobFailureError as failure:
            self._finish_failure(record, failure.error)
        except (IngestError, SourceUnavailableError, TooLargeError) as failure:
            self._finish_failure(
                record,
                _error(
                    "source_unavailable",
                    str(failure) or "The footage could not be ingested.",
                    retryable=True,
                    stage="ingest",
                ),
            )
        except Exception:  # noqa: BLE001 - service boundary converts faults to typed state
            self._finish_failure(
                record,
                _error(
                    "internal_error",
                    "The engine failed while processing the reconstruction job.",
                    retryable=True,
                    stage=record.current_stage,
                ),
            )

    def _run_ingest(self, record: JobRecord) -> None:
        started = time.monotonic()
        with record.lock:
            record.current_stage = "ingest"
            record.progress = 0.0
            self._checkpoint(record)
        self._emit(record, "stage_started", {"stage": "ingest"})
        self._progress(record, 0.02, "Downloading source footage.")
        ingest_items: list[dict[str, object]] = []
        job_dir = self._job_dir(record.job_id)
        for index, footage in enumerate(record.request.inputs.footage):
            self._check_canceled(record)
            footage_dir = job_dir / "ingest" / f"{index:02d}"
            footage_dir.mkdir(parents=True, exist_ok=True)
            source = footage_dir / "source"
            if source.exists():
                digest = _sha256_file(source)
            else:
                partial = source.with_suffix(".part")
                partial.unlink(missing_ok=True)
                digest, _ = download(
                    footage.source_url,
                    partial,
                    self._settings.max_source_bytes,
                    self._http,
                    check_canceled=lambda: self._check_canceled(record),
                )
                os.replace(partial, source)
            if footage.sha256 is not None and digest != footage.sha256:
                raise JobFailureError(
                    _error(
                        "source_unavailable",
                        "Downloaded footage did not match its expected SHA-256.",
                        retryable=True,
                        stage="ingest",
                    )
                )
            self._progress(
                record,
                0.1 + 0.75 * index / len(record.request.inputs.footage),
                f"Decoding and normalizing footage {index + 1} of "
                f"{len(record.request.inputs.footage)}.",
            )
            result = ingest_footage(
                source,
                footage_dir,
                footage_id=footage.footage_id,
                source_sha256=digest,
                config=IngestConfig(
                    self._settings.analysis_long_side,
                    self._settings.proxy_long_side,
                    self._settings.thumbnail_count,
                ),
                check_canceled=lambda: self._check_canceled(record),
            )
            ingest_items.append(result.manifest)
        runtime_ms = (time.monotonic() - started) * 1000
        artifact = AnalysisArtifacts.model_validate(
            {
                "format": "orrery.engine.analysis-artifacts",
                "schemaVersion": 1,
                "engineVersion": self._settings.engine_version,
                "tracks": [],
                "cameraMotion": [],
                "bodies": [],
                "joints": [],
                "parameters": [],
                "diagnosis": [],
                "resurrection": [],
                "stageRuntimes": [{"stage": "ingest", "runtimeMs": runtime_ms}],
                "ingest": ingest_items,
            }
        )
        descriptor = self._upload_artifact(record, artifact)
        with record.lock:
            record.artifacts = [descriptor]
            record.completed_stages.add("ingest")
            record.stage_runtimes["ingest"] = runtime_ms
            record.progress = 1.0
            self._checkpoint(record)
        self._emit(
            record,
            "stage_completed",
            {
                "stage": "ingest",
                "runtimeMs": runtime_ms,
                "peakRssBytes": _peak_rss_bytes(),
            },
        )
        self._emit(record, "artifact_written", descriptor.model_dump(by_alias=True, mode="json"))

    def _upload_artifact(self, record: JobRecord, artifact: AnalysisArtifacts) -> JobArtifact:
        content = artifact.model_dump_json(by_alias=True, exclude_none=True).encode()
        grant = record.request.artifact_grant.analysis_artifacts
        try:
            response = self._http.put(
                grant.upload_url,
                content=content,
                headers={"Content-Type": MEDIA_TYPE},
            )
            response.raise_for_status()
        except httpx.HTTPError as failure:
            raise JobFailureError(
                _error(
                    "artifact_upload_failed",
                    "The ingest artifact upload grant failed.",
                    retryable=True,
                    stage="ingest",
                )
            ) from failure
        return JobArtifact(
            slot="analysis_artifacts",
            media_type=MEDIA_TYPE,
            byte_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            download_url=grant.download_url,
        )

    def _progress(self, record: JobRecord, fraction: float, description: str) -> None:
        with record.lock:
            record.progress = fraction
            self._checkpoint(record)
        self._emit(
            record,
            "progress",
            {"stage": "ingest", "fraction": fraction, "description": description},
        )

    def _emit(
        self,
        record: JobRecord,
        event_type: str,
        payload: object,
        *,
        allow_canceled: bool = False,
    ) -> None:
        if not allow_canceled:
            self._check_canceled(record)
        with record.lock:
            secret = record.callback_secret
            if secret is None:
                raise JobFailureError(
                    _error("callback_failed", "The callback secret is unavailable.", retryable=True)
                )
            event = {
                "contractVersion": "1",
                "jobId": str(record.job_id),
                "seq": record.seq,
                "at": datetime.now(UTC).isoformat(),
                "type": event_type,
                "payload": payload,
            }
            record.seq += 1
            self._checkpoint(record)
        validated = EngineEvent.model_validate(event)
        body = validated.model_dump_json(by_alias=True, exclude_none=True).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "Orrery-Callback-Timestamp": timestamp,
            "Orrery-Callback-Signature": f"sha256={signature}",
        }
        for attempt in range(self._settings.callback_attempts):
            try:
                response = self._http.post(
                    record.request.callback.url,
                    content=body,
                    headers=headers,
                    timeout=self._settings.callback_timeout_seconds,
                )
                response.raise_for_status()
                return
            except httpx.HTTPError as failure:
                if attempt + 1 == self._settings.callback_attempts:
                    raise JobFailureError(
                        _error(
                            "callback_failed",
                            "The signed lifecycle callback could not be delivered.",
                            retryable=True,
                            stage=record.current_stage,
                        )
                    ) from failure
                time.sleep(0.05 * (attempt + 1))

    def _finish_failure(self, record: JobRecord, error: JobError) -> None:
        with record.lock:
            record.status = "canceled" if error.code == "canceled" else "failed"
            record.error = error
            record.progress = min(record.progress, 1.0)
            self._checkpoint(record)
        if error.code == "callback_failed":
            return
        with contextlib.suppress(JobCanceledError, JobFailureError):
            self._emit(
                record,
                "failed",
                error.model_dump(by_alias=True, mode="json", exclude_none=True),
                allow_canceled=True,
            )

    @staticmethod
    def _check_canceled(record: JobRecord) -> None:
        if record.cancel.is_set():
            raise JobCanceledError

    def _checkpoint(self, record: JobRecord) -> None:
        path = self._job_dir(record.job_id) / "checkpoint.json"
        payload = {
            "request": record.request.model_dump(by_alias=True, mode="json"),
            "statusUrl": record.status_url,
            "status": record.status,
            "currentStage": record.current_stage,
            "progress": record.progress,
            "artifacts": [item.model_dump(by_alias=True, mode="json") for item in record.artifacts],
            "error": (
                record.error.model_dump(by_alias=True, mode="json", exclude_none=True)
                if record.error
                else None
            ),
            "completedStages": sorted(record.completed_stages),
            "stageRuntimes": record.stage_runtimes,
            "seq": record.seq,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        os.replace(temporary, path)

    def _load_checkpoints(self) -> None:
        for path in self._jobs_dir.glob("*/checkpoint.json"):
            try:
                raw = json.loads(path.read_text())
                request = ReconstructJobRequest.model_validate(raw["request"])
                record = JobRecord(request, None, str(raw["statusUrl"]))
                record.status = (
                    "canceled" if raw["status"] in {"queued", "running"} else raw["status"]
                )
                record.current_stage = raw.get("currentStage")
                record.progress = float(raw.get("progress", 0.0))
                record.artifacts = [
                    JobArtifact.model_validate(item) for item in raw.get("artifacts", [])
                ]
                record.error = JobError.model_validate(raw["error"]) if raw.get("error") else None
                if record.status == "canceled" and record.error is None:
                    record.error = _error(
                        "canceled", "The engine restarted before the job completed."
                    )
                record.completed_stages = set(raw.get("completedStages", []))
                record.stage_runtimes = {
                    str(key): float(value) for key, value in raw.get("stageRuntimes", {}).items()
                }
                record.seq = int(raw.get("seq", 0))
                self._records[request.job_id] = record
            except (OSError, ValueError, TypeError, KeyError):
                continue

    def _job_dir(self, job_id: UUID) -> Path:
        path = self._jobs_dir / str(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


def _accepted(record: JobRecord) -> JobAccepted:
    return JobAccepted(
        contract_version="1",
        job_id=record.job_id,
        accepted=True,
        status="running" if record.status == "running" else "queued",
        status_url=record.status_url,
    )

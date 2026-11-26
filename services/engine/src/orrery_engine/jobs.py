from __future__ import annotations

import contextlib
import hashlib
import hmac
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx

from orrery_engine.camera_motion import CameraMotionError
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
from orrery_engine.job_artifacts import build_analysis_artifact
from orrery_engine.job_camera_motion import (
    CameraMotionStageOutput,
    load_camera_motion_stage,
    run_camera_motion_stage,
)
from orrery_engine.job_checkpoint import load_checkpoints, write_checkpoint
from orrery_engine.job_ingest import (
    IngestChecksumError,
    load_ingest_manifests,
    run_ingest_stage,
)
from orrery_engine.job_models import JobCanceledError, JobFailureError, JobRecord
from orrery_engine.job_seeding import (
    SeedingError,
    SeedingStageOutput,
    load_seeding_stage,
    run_seeding_stage,
)
from orrery_engine.job_support import (
    job_error as _error,
)
from orrery_engine.job_support import (
    peak_rss_bytes as _peak_rss_bytes,
)
from orrery_engine.job_support import (
    request_fingerprint as _request_fingerprint,
)
from orrery_engine.job_tracking import TrackingError, load_tracking_stage
from orrery_engine.job_tracking_lifecycle import TrackingLifecycleMixin
from orrery_engine.probe import SourceUnavailableError, TooLargeError
from orrery_engine.settings import Settings

MEDIA_TYPE = "application/vnd.orrery.analysis-artifacts+json"


class JobManager(TrackingLifecycleMixin):
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
            if "camera_motion" not in record.completed_stages:
                camera = self._run_camera_motion(record)
            else:
                camera = load_camera_motion_stage(self._job_dir(record.job_id))
            self._route_spatial_if_needed(record, camera)
            if "seeding" not in record.completed_stages:
                seeding = self._run_seeding(record, camera)
            else:
                seeding = load_seeding_stage(self._job_dir(record.job_id))
            if "tracking" not in record.completed_stages:
                self._run_tracking(record, camera, seeding)
            else:
                load_tracking_stage(self._job_dir(record.job_id))
            with record.lock:
                record.current_stage = "body_grouping"
                record.progress = 0.0
                self._checkpoint(record)
            self._emit(record, "stage_started", {"stage": "body_grouping"})
            raise JobFailureError(
                _error(
                    "capability_unavailable",
                    "Point tracking completed, but body grouping is not implemented yet.",
                    stage="body_grouping",
                    prerequisites=("vision-pipeline:5.1",),
                )
            )
        except JobCanceledError:
            self._finish_failure(record, _error("canceled", "The reconstruction job was canceled."))
        except JobFailureError as failure:
            self._finish_failure(record, failure.error)
        except (IngestChecksumError, CameraMotionError, SeedingError, TrackingError) as failure:
            self._finish_failure(
                record,
                _error(
                    "invalid_input",
                    str(failure),
                    stage=record.current_stage,
                ),
            )
        except (SourceUnavailableError, TooLargeError) as failure:
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
        with record.lock:
            record.current_stage = "ingest"
            record.progress = 0.0
            self._checkpoint(record)
        self._emit(record, "stage_started", {"stage": "ingest"})
        self._progress(record, 0.02, "Downloading source footage.")
        output = run_ingest_stage(
            record.request,
            self._job_dir(record.job_id),
            self._settings,
            self._http,
            check_canceled=lambda: self._check_canceled(record),
            progress=lambda fraction, description: self._progress(record, fraction, description),
        )
        artifact = build_analysis_artifact(
            self._settings.engine_version,
            record,
            ingest=list(output.manifests),
            pending_runtime=("ingest", output.runtime_ms),
        )
        descriptor = self._upload_artifact(record, artifact)
        self._complete_stage(record, "ingest", output.runtime_ms, descriptor)

    def _run_camera_motion(self, record: JobRecord) -> CameraMotionStageOutput:
        with record.lock:
            record.current_stage = "camera_motion"
            record.progress = 0.0
            self._checkpoint(record)
        self._emit(record, "stage_started", {"stage": "camera_motion"})
        output = run_camera_motion_stage(
            record.request,
            self._job_dir(record.job_id),
            self._settings,
            check_canceled=lambda: self._check_canceled(record),
            progress=lambda fraction, description: self._progress(record, fraction, description),
        )
        artifact = build_analysis_artifact(
            self._settings.engine_version,
            record,
            ingest=list(load_ingest_manifests(self._job_dir(record.job_id))),
            camera=output,
            pending_runtime=("camera_motion", output.runtime_ms),
        )
        descriptor = self._upload_artifact(record, artifact)
        self._complete_stage(record, "camera_motion", output.runtime_ms, descriptor)
        return output

    def _run_seeding(
        self, record: JobRecord, camera: CameraMotionStageOutput
    ) -> SeedingStageOutput:
        with record.lock:
            record.current_stage = "seeding"
            record.progress = 0.0
            self._checkpoint(record)
        self._emit(record, "stage_started", {"stage": "seeding"})
        ingest = load_ingest_manifests(self._job_dir(record.job_id))
        output = run_seeding_stage(
            record.request,
            self._job_dir(record.job_id),
            self._settings,
            camera,
            ingest_manifests=ingest,
            check_canceled=lambda: self._check_canceled(record),
            progress=lambda fraction, description: self._progress(record, fraction, description),
        )
        artifact = build_analysis_artifact(
            self._settings.engine_version,
            record,
            ingest=list(ingest),
            camera=camera,
            seeding=output,
            pending_runtime=("seeding", output.runtime_ms),
        )
        descriptor = self._upload_artifact(record, artifact)
        self._complete_stage(record, "seeding", output.runtime_ms, descriptor)
        return output

    def _complete_stage(
        self,
        record: JobRecord,
        stage: str,
        runtime_ms: float,
        descriptor: JobArtifact,
    ) -> None:
        with record.lock:
            record.artifacts = [descriptor]
            record.completed_stages.add(stage)
            record.stage_runtimes[stage] = runtime_ms
            record.progress = 1.0
            self._checkpoint(record)
        self._emit(
            record,
            "stage_completed",
            {
                "stage": stage,
                "runtimeMs": runtime_ms,
                "peakRssBytes": _peak_rss_bytes(),
            },
        )
        self._emit(record, "artifact_written", descriptor.model_dump(by_alias=True, mode="json"))

    def _route_spatial_if_needed(self, record: JobRecord, output: CameraMotionStageOutput) -> None:
        if not output.requires_spatial:
            return
        reason = " ".join(output.routing_reasons)
        self._emit(
            record,
            "routing",
            {
                "stage": "camera_motion",
                "destination": "spatial_reconstruction",
                "reason": reason,
            },
        )
        raise JobFailureError(
            _error(
                "requires_spatial",
                f"This clip has significant parallax. {reason} Record a steadier, more frontal "
                "clip or use spatial reconstruction when it becomes available.",
                stage="camera_motion",
                prerequisites=("spatial-reconstruction",),
            )
        )

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
                    "The analysis artifact upload grant failed.",
                    retryable=True,
                    stage=record.current_stage,
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
            stage = record.current_stage or "ingest"
            self._checkpoint(record)
        self._emit(
            record,
            "progress",
            {"stage": stage, "fraction": fraction, "description": description},
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
        if error.code != "callback_failed":
            with contextlib.suppress(JobCanceledError, JobFailureError):
                self._emit(
                    record,
                    "failed",
                    error.model_dump(by_alias=True, mode="json", exclude_none=True),
                    allow_canceled=True,
                )
        with record.lock:
            record.status = "canceled" if error.code == "canceled" else "failed"
            record.error = error
            record.progress = min(record.progress, 1.0)
            self._checkpoint(record)

    @staticmethod
    def _check_canceled(record: JobRecord) -> None:
        if record.cancel.is_set():
            raise JobCanceledError

    def _checkpoint(self, record: JobRecord) -> None:
        write_checkpoint(record, self._job_dir(record.job_id))

    def _load_checkpoints(self) -> None:
        for item in load_checkpoints(self._jobs_dir):
            record = JobRecord(item.request, None, item.status_url)
            record.status = item.status
            record.current_stage = item.current_stage
            record.progress = item.progress
            record.artifacts = item.artifacts
            record.error = item.error
            record.completed_stages = item.completed_stages
            record.stage_runtimes = item.stage_runtimes
            record.seq = item.seq
            self._records[record.job_id] = record

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

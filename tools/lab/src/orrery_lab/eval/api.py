"""HTTP adapter for production reconstruction jobs.

The adapter sends only clip URLs and job-control metadata. Ground truth remains local to the lab.
It validates every response against the generated worker-engine contract, verifies downloaded
artifact hashes, and refuses to score failed or incomplete jobs.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from orrery_lab.eval.types import AnalysisArtifacts
from orrery_lab.generated.contract import AnalysisArtifacts as ContractAnalysisArtifacts
from orrery_lab.generated.contract import (
    ContractErrorResponse,
    JobAccepted,
    JobArtifact,
    JobError,
    JobRejected,
    JobStatus,
    JobStatus2,
    JobStatus3,
    JobSubmissionResponse,
    ReconstructJobRequest,
)

CONTRACT_VERSION = "1"
UNAVAILABLE = "capability_unavailable"


class EngineJobError(RuntimeError):
    """A typed engine job failure that evaluation cannot turn into metrics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        job_id: UUID | None = None,
        stage: str | None = None,
        prerequisites: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.job_id = job_id
        self.stage = stage
        self.prerequisites = prerequisites


class ReconstructionUnavailableError(EngineJobError):
    """The job API exists, but required production reconstruction stages do not."""


class ArtifactIntegrityError(EngineJobError):
    """A completed job's artifact did not match its contracted metadata."""


@dataclass(frozen=True)
class ArtifactGrant:
    """Scoped object-store URLs supplied by the evaluation environment."""

    upload_url: str
    download_url: str


@dataclass(frozen=True)
class ProbeResult:
    sha256: str
    width: int
    height: int
    duration_seconds: float


class EngineJobClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_seconds: float = 120.0,
        poll_seconds: float = 0.1,
    ) -> None:
        if not base_url or not service_token:
            raise ValueError("engine base URL and service token are required")
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("timeouts must be positive")
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_token}"}
        self._timeout = timeout_seconds
        self._poll_seconds = poll_seconds

    def probe_clip(
        self, source_url: str, *, max_bytes: int = 2_000_000_000, max_duration_s: float = 3600
    ) -> ProbeResult:
        """Execute the synchronous production probe contract."""
        response = httpx.post(
            f"{self._base_url}/v1/probe",
            json={"sourceUrl": source_url, "maxBytes": max_bytes, "maxDurationS": max_duration_s},
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("outcome") != "accepted":
            raise ValueError(f"engine rejected evaluation clip: {body.get('code', 'unknown')}")
        return ProbeResult(
            str(body["sha256"]),
            int(body["width"]),
            int(body["height"]),
            float(body["durationS"]),
        )

    def run_clip(
        self,
        source_url: str,
        *,
        artifact_grant: ArtifactGrant,
        callback_url: str,
        callback_secret: str,
        broken: bool = False,
        tracker_backend: Literal["klt"] = "klt",
        job_id: UUID | None = None,
    ) -> AnalysisArtifacts:
        """Submit one ground-truth-free clip and return its verified analysis artifact."""
        actual_job_id = job_id or uuid4()
        request = ReconstructJobRequest.model_validate(
            {
                "contractVersion": CONTRACT_VERSION,
                "jobId": str(actual_job_id),
                "kind": "reconstruct",
                "inputs": {"footage": [{"footageId": "evaluation-clip", "sourceUrl": source_url}]},
                "params": {"broken": broken, "trackerBackend": tracker_backend},
                "artifactGrant": {
                    "analysisArtifacts": {
                        "uploadUrl": artifact_grant.upload_url,
                        "downloadUrl": artifact_grant.download_url,
                    }
                },
                "callback": {
                    "url": callback_url,
                    "secretRef": f"synthetic-lab:{actual_job_id}",
                },
                "traceparent": f"00-{secrets.token_hex(16)}-{secrets.token_hex(8)}-01",
            }
        )
        response = httpx.post(
            f"{self._base_url}/v1/jobs",
            json=request.model_dump(by_alias=True, mode="json"),
            headers={**self._headers, "Orrery-Callback-Secret": callback_secret},
            timeout=self._timeout,
        )
        if response.status_code >= 500:  # noqa: PLR2004 - retryable server boundary
            response.raise_for_status()
        if response.status_code == 422:  # noqa: PLR2004
            error = ContractErrorResponse.model_validate(response.json()).error
            raise EngineJobError(error.code, error.message)
        submission = JobSubmissionResponse.model_validate(response.json()).root
        if isinstance(submission, JobRejected):
            self._raise_job_error(submission.error, actual_job_id)
        if not isinstance(submission, JobAccepted):
            raise AssertionError("unreachable job submission variant")
        status_url = submission.status_url
        deadline = time.monotonic() + self._timeout
        while True:
            if time.monotonic() >= deadline:
                raise EngineJobError(
                    "source_unavailable",
                    "Timed out waiting for reconstruction to complete.",
                    job_id=actual_job_id,
                )
            status_response = httpx.get(
                status_url,
                headers=self._headers,
                timeout=min(self._timeout, max(1.0, deadline - time.monotonic())),
            )
            status_response.raise_for_status()
            current = JobStatus.model_validate(status_response.json()).root
            if isinstance(current, JobStatus2):
                return self._download_artifacts(current.artifacts, actual_job_id)
            if isinstance(current, JobStatus3):
                self._raise_job_error(current.error, actual_job_id)
            time.sleep(self._poll_seconds)

    def _download_artifacts(self, artifacts: list[JobArtifact], job_id: UUID) -> AnalysisArtifacts:
        descriptor = next(
            (item for item in artifacts if item.slot == "analysis_artifacts"),
            None,
        )
        if descriptor is None:
            raise ArtifactIntegrityError(
                "artifact_upload_failed",
                "The completed job did not publish analysis artifacts.",
                job_id=job_id,
            )
        response = httpx.get(descriptor.download_url, timeout=self._timeout)
        response.raise_for_status()
        content = response.content
        digest = hashlib.sha256(content).hexdigest()
        if len(content) != descriptor.byte_size or digest != descriptor.sha256:
            raise ArtifactIntegrityError(
                "artifact_upload_failed",
                "The downloaded analysis artifact does not match its size or SHA-256.",
                job_id=job_id,
            )
        try:
            wire = ContractAnalysisArtifacts.model_validate_json(content)
            return AnalysisArtifacts.model_validate(wire.model_dump(by_alias=True, mode="json"))
        except ValidationError as error:
            raise ArtifactIntegrityError(
                "artifact_upload_failed",
                "The downloaded analysis artifact does not match contract version 1.",
                job_id=job_id,
            ) from error

    @staticmethod
    def _raise_job_error(error: JobError, job_id: UUID) -> None:
        code = error.code
        prerequisites = tuple(item.root for item in error.prerequisites or ())
        if code == UNAVAILABLE:
            raise ReconstructionUnavailableError(
                code,
                error.message,
                job_id=job_id,
                stage=error.stage,
                prerequisites=prerequisites,
            )
        raise EngineJobError(
            code,
            error.message,
            job_id=job_id,
            stage=error.stage,
            prerequisites=prerequisites,
        )


__all__ = [
    "ArtifactGrant",
    "ArtifactIntegrityError",
    "EngineJobClient",
    "EngineJobError",
    "ProbeResult",
    "ReconstructionUnavailableError",
]

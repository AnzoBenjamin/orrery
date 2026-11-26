"""Small deterministic helpers shared by the reconstruction job runner."""

import hashlib
import resource
from pathlib import Path

from orrery_engine.generated.contract import JobError, ReconstructJobRequest


def job_error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    stage: str | None = None,
    prerequisites: tuple[str, ...] | None = None,
) -> JobError:
    return JobError.model_validate(
        {
            "code": code,
            "message": message,
            "retryable": retryable,
            "stage": stage,
            "prerequisites": prerequisites,
        }
    )


def request_fingerprint(request: ReconstructJobRequest) -> str:
    content = request.model_dump_json(by_alias=True, exclude_none=True)
    return hashlib.sha256(content.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def peak_rss_bytes() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

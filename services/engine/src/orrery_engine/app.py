"""HTTP interface of the engine. Only the worker calls it, with the service token."""

import hmac
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import structlog
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from orrery_engine.generated.contract import (
    ContractErrorResponse,
    JobError,
    JobRejected,
    ProbeAccepted,
    ProbeRejected,
    ProbeRequest,
    ReconstructJobRequest,
)
from orrery_engine.job_models import JobFailureError
from orrery_engine.jobs import JobManager
from orrery_engine.probe import (
    ProbeResult,
    Rejection,
    SourceUnavailableError,
    TooLargeError,
    download,
    inspect,
)
from orrery_engine.settings import Settings

log = structlog.get_logger()


def create_app(settings: Settings) -> FastAPI:  # noqa: PLR0915 - route wiring is kept together
    http = httpx.Client(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=False)
    jobs = JobManager(settings, http)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
        jobs.close()
        http.close()

    app = FastAPI(
        title="Orrery engine", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    expected = settings.service_token.get_secret_value().encode()

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        presented = (authorization or "").removeprefix("Bearer ").encode()
        if not hmac.compare_digest(presented, expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid service token")

    def allowed_source(url: str) -> bool:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}" in settings.allowed_source_origins

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/jobs",
        dependencies=[Depends(authorize)],
        status_code=status.HTTP_202_ACCEPTED,
    )
    def submit_job(
        http_request: Request,
        payload: Annotated[object, Body()],
        callback_secret: Annotated[str | None, Header(alias="Orrery-Callback-Secret")] = None,
    ) -> JSONResponse:
        try:
            request = ReconstructJobRequest.model_validate(payload)
        except ValidationError:
            return _contract_error(
                "invalid_input",
                "The reconstruction job does not match contract version 1.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if request.contract_version != "1":
            return _job_rejected(
                request.job_id,
                "incompatible_contract",
                f"Contract version {request.contract_version} is not supported; use version 1.",
            )
        if callback_secret is None or len(callback_secret) < 32:  # noqa: PLR2004
            return _contract_error(
                "invalid_input",
                "Orrery-Callback-Secret must contain at least 32 characters.",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        artifact_grant = request.artifact_grant.analysis_artifacts
        protected_urls = [
            *(item.source_url for item in request.inputs.footage),
            artifact_grant.upload_url,
            artifact_grant.download_url,
        ]
        if any(not allowed_source(url) for url in protected_urls):
            return _job_rejected(
                request.job_id,
                "invalid_input",
                "A footage or artifact URL has an origin outside the engine allowlist.",
                http_status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        try:
            accepted = jobs.submit(
                request,
                callback_secret,
                str(http_request.url_for("job_status", job_id=str(request.job_id))),
            )
        except JobFailureError as failure:
            return _job_rejected(
                request.job_id,
                failure.error.code,
                failure.error.message,
                http_status=status.HTTP_409_CONFLICT,
                stage=failure.error.stage,
                prerequisites=tuple(item.root for item in failure.error.prerequisites or ()),
            )
        return _json_response(accepted, status.HTTP_202_ACCEPTED)

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(authorize)], name="job_status")
    def job_status(job_id: UUID) -> JSONResponse:
        current = jobs.status(job_id)
        if current is None:
            return _job_rejected(
                job_id,
                "job_not_found",
                "No reconstruction job with this ID exists.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        return _json_response(current, status.HTTP_200_OK)

    @app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(authorize)])
    def cancel_job(job_id: UUID) -> JSONResponse:
        current = jobs.cancel(job_id)
        if current is None:
            return _job_rejected(
                job_id,
                "job_not_found",
                "No reconstruction job with this ID exists.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        return _json_response(current, status.HTTP_202_ACCEPTED)

    @app.post("/v1/probe", dependencies=[Depends(authorize)], response_model_by_alias=True)
    def probe(request: ProbeRequest) -> ProbeAccepted | ProbeRejected:
        if not allowed_source(request.source_url):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "source origin not allowed")
        settings.work_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.work_dir, prefix="probe-") as tmp:
            path = Path(tmp) / "source"
            try:
                sha256, size = download(request.source_url, path, request.max_bytes, http)
            except TooLargeError:
                limit_gb = request.max_bytes / 1e9
                return ProbeRejected(
                    outcome="rejected",
                    code="too_large",
                    reason=f"The file is larger than {limit_gb:.0f} GB. Trim the clip or export "
                    "it at a lower bitrate.",
                )
            except SourceUnavailableError as error:
                log.warning("probe source unavailable", error=str(error))
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, "source unavailable") from error
            result = inspect(
                path, sha256=sha256, byte_size=size, max_duration_s=request.max_duration_s
            )
        if isinstance(result, Rejection):
            log.info("probe rejected", code=result.code)
            return ProbeRejected(outcome="rejected", code=result.code, reason=result.reason)
        log.info("probe accepted", codec=result.codec, duration_s=round(result.duration_s, 2))
        return _accepted(result)

    return app


def _contract_error(code: str, message: str, http_status: int) -> JSONResponse:
    response = ContractErrorResponse(
        contract_version="1",
        error=_job_error(code, message),
    )
    return _json_response(response, http_status)


def _job_rejected(
    job_id: UUID,
    code: str,
    message: str,
    *,
    http_status: int = status.HTTP_409_CONFLICT,
    stage: str | None = None,
    prerequisites: tuple[str, ...] | None = None,
) -> JSONResponse:
    response = JobRejected(
        contract_version="1",
        job_id=job_id,
        accepted=False,
        status="rejected",
        error=_job_error(
            code,
            message,
            stage=stage,
            prerequisites=prerequisites,
        ),
    )
    return _json_response(response, http_status)


def _job_error(
    code: str,
    message: str,
    *,
    stage: str | None = None,
    prerequisites: tuple[str, ...] | None = None,
) -> JobError:
    return JobError.model_validate(
        {
            "code": code,
            "message": message,
            "retryable": False,
            "stage": stage,
            "prerequisites": prerequisites,
        }
    )


def _json_response(model: BaseModel, http_status: int) -> JSONResponse:
    content = model.model_dump(by_alias=True, mode="json", exclude_none=True)
    return JSONResponse(content, http_status)


def _accepted(result: ProbeResult) -> ProbeAccepted:
    return ProbeAccepted(
        outcome="accepted",
        sha256=result.sha256,
        byte_size=result.byte_size,
        duration_s=result.duration_s,
        width=result.width,
        height=result.height,
        fps_nominal=result.fps_nominal,
        is_vfr=result.is_vfr,
        codec=result.codec,
        rotation_quarter_turns=result.rotation_quarter_turns,
    )

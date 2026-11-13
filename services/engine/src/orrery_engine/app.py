"""HTTP interface of the engine. Only the worker calls it, with the service token."""

import hmac
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status

from orrery_engine.generated.contract import ProbeAccepted, ProbeRejected, ProbeRequest
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


def create_app(settings: Settings) -> FastAPI:
    http = httpx.Client(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        yield
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

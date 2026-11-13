"""HTTP interface of the engine. Only the worker calls it, with the service token."""

import hmac
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

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

MAX_BYTES_CEILING = 2_000_000_000
MAX_DURATION_CEILING_S = 3600.0


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ProbeRequest(Model):
    source_url: str = Field(max_length=8192)
    """Presigned GET URL of the uploaded object."""
    max_bytes: int = Field(gt=0, le=MAX_BYTES_CEILING)
    max_duration_s: float = Field(gt=0, le=MAX_DURATION_CEILING_S)


class ProbeAccepted(Model):
    outcome: Literal["accepted"] = "accepted"
    sha256: str
    byte_size: int
    duration_s: float
    width: int
    height: int
    fps_nominal: float
    is_vfr: bool
    codec: str
    rotation_quarter_turns: int


class ProbeRejected(Model):
    outcome: Literal["rejected"] = "rejected"
    code: str
    reason: str


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

    @app.post("/v1/probe", dependencies=[Depends(authorize)])
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
            return ProbeRejected(code=result.code, reason=result.reason)
        log.info("probe accepted", codec=result.codec, duration_s=round(result.duration_s, 2))
        return _accepted(result)

    return app


def _accepted(result: ProbeResult) -> ProbeAccepted:
    return ProbeAccepted(
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

"""Validated engine configuration (platform-foundation requirement 2).

Values come from the environment. A missing or invalid value stops the process with a message
naming the variable and the rule it broke, never the value itself, so secrets stay out of logs.
"""

import sys
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENGINE_", frozen=True, extra="ignore")

    service_token: SecretStr = Field(min_length=32)
    """Bearer token the worker presents. Shared only between worker and engine."""

    allowed_source_origins: Annotated[tuple[str, ...], NoDecode] = Field(min_length=1)
    """Origins (scheme://host:port) the engine may download inputs from: the object store."""

    work_dir: Path = Path("/tmp")  # noqa: S108 - the container's private, size-limited tmpfs
    """Where downloads, stage caches, and persistent checkpoints are stored."""

    concurrency: int = Field(default=1, ge=1, le=32)
    """Maximum reconstruction jobs executing at once."""

    analysis_long_side: int = Field(default=960, ge=160, le=4096)
    proxy_long_side: int = Field(default=720, ge=160, le=2160)
    thumbnail_count: int = Field(default=5, ge=1, le=20)
    camera_motion_ransac_threshold_px: float = Field(default=1.5, gt=0, le=20)
    camera_motion_parallax_threshold_px: float = Field(default=2.5, gt=0, le=50)
    camera_motion_min_matches: int = Field(default=8, ge=4, le=1000)
    seeding_max_points: int = Field(default=3000, ge=1, le=10000)
    seeding_grid_size_px: int = Field(default=48, ge=4, le=512)
    seeding_per_cell_cap: int = Field(default=6, ge=1, le=100)
    seeding_min_region_pixels: int = Field(default=64, ge=1, le=1_000_000)
    seeding_reseed_interval_frames: int = Field(default=15, ge=1, le=1000)
    seeding_coverage_threshold: float = Field(default=0.5, gt=0, le=1)
    max_source_bytes: int = Field(default=2_000_000_000, gt=0)
    callback_attempts: int = Field(default=3, ge=1, le=10)
    callback_timeout_seconds: float = Field(default=3.0, gt=0, le=8.0)
    engine_version: str = Field(default="development", min_length=1, max_length=200)

    port: int = Field(default=8000, ge=1, le=65535)

    log_level: str = "info"

    environment: str = "development"
    """Deployment environment tag for traces and error reports."""

    release: str | None = None
    """The deployed commit, for traces and error reports."""

    otlp_endpoint: str | None = None
    """OTLP/HTTP collector base URL. Tracing is off without it."""

    sentry_dsn: SecretStr | None = None
    """GlitchTip DSN. Error reporting is off without it."""

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        return _production_requires_telemetry(self)

    @field_validator("allowed_source_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip().rstrip("/") for part in value.split(",") if part.strip())
        return value

    @field_validator("allowed_source_origins")
    @classmethod
    def _check_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for origin in value:
            if not origin.startswith(("http://", "https://")) or origin.count("/") != 2:  # noqa: PLR2004
                msg = "each origin must look like https://host[:port] with no path"
                raise ValueError(msg)
        return value


def _production_requires_telemetry(settings: "Settings") -> "Settings":
    if settings.environment == "production":
        missing = [
            name
            for name, value in (
                ("otlp_endpoint", settings.otlp_endpoint),
                ("sentry_dsn", settings.sentry_dsn),
            )
            if value is None
        ]
        if missing:
            msg = f"required in production: {', '.join('ENGINE_' + m.upper() for m in missing)}"
            raise ValueError(msg)
    return settings


def describe_errors(error: ValidationError) -> str:
    """The variables that failed and why, without their values."""
    lines = ["engine: invalid environment"]
    for issue in error.errors(include_input=False, include_url=False):
        name = "ENGINE_" + "_".join(str(part) for part in issue["loc"]).upper()
        lines.append(f"  {name}: {issue['msg']}")
    return "\n".join(lines)


def load_settings() -> Settings:
    try:
        return Settings()  # pyright: ignore[reportCallIssue] - fields come from the environment
    except ValidationError as error:
        sys.stderr.write(describe_errors(error) + "\n")
        raise SystemExit(1) from None

"""Validated engine configuration (platform-foundation requirement 2).

Values come from the environment. A missing or invalid value stops the process with a message
naming the variable and the rule it broke, never the value itself, so secrets stay out of logs.
"""

import sys
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENGINE_", frozen=True, extra="ignore")

    service_token: SecretStr = Field(min_length=32)
    """Bearer token the worker presents. Shared only between worker and engine."""

    allowed_source_origins: Annotated[tuple[str, ...], NoDecode] = Field(min_length=1)
    """Origins (scheme://host:port) the engine may download inputs from: the object store."""

    work_dir: Path = Path("/tmp")  # noqa: S108 - the container's private, size-limited tmpfs
    """Where downloads are staged while they are inspected."""

    port: int = Field(default=8000, ge=1, le=65535)

    log_level: str = "info"

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

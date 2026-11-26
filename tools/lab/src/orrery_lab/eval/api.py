"""HTTP adapter for the production worker-engine API.

The current shared engine contract only publishes ``/v1/probe``. Job submission is deliberately
not emulated here: callers get a typed blocker until packages/engine-contract publishes the job
request/response and the engine serves it.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

UNPROCESSABLE_CONTENT = 422


class JobApiUnavailableError(RuntimeError):
    """The deployed/current engine does not expose the contracted asynchronous job endpoint."""


@dataclass(frozen=True)
class ProbeResult:
    sha256: str
    width: int
    height: int
    duration_seconds: float


class EngineJobClient:
    def __init__(
        self, base_url: str, service_token: str, *, timeout_seconds: float = 120.0
    ) -> None:
        if not base_url or not service_token:
            raise ValueError("engine base URL and service token are required")
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_token}"}
        self._timeout = timeout_seconds

    def probe_clip(
        self, source_url: str, *, max_bytes: int = 2_000_000_000, max_duration_s: float = 3600
    ) -> ProbeResult:
        """Execute the real current ProbeRequest/ProbeResponse contract."""
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

    def require_job_api(self) -> None:
        """Check availability without fabricating a request outside the shared contract."""
        response = httpx.get(
            f"{self._base_url}/v1/jobs",
            headers=self._headers,
            timeout=self._timeout,
        )
        if response.status_code in {404, 405}:
            raise JobApiUnavailableError(
                "engine job API is unavailable: vision-pipeline task 1.1 and the shared job "
                "contract are not implemented"
            )
        if response.status_code == UNPROCESSABLE_CONTENT:
            raise JobApiUnavailableError(
                "engine has /v1/jobs but packages/engine-contract does not publish its request "
                "schema; refusing to invent or fake a job payload"
            )
        response.raise_for_status()
        raise JobApiUnavailableError(
            "engine accepted an empty uncontracted job request unexpectedly"
        )

    def run_clip(self, source_url: str) -> ProbeResult:
        """Probe a real clip, then require the real job contract before execution."""
        result = self.probe_clip(source_url)
        self.require_job_api()
        return result


__all__ = ["EngineJobClient", "JobApiUnavailableError", "ProbeResult"]

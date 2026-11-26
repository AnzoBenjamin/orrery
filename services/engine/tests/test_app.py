import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import httpx
import pytest
import uvicorn
from opentelemetry.sdk.trace import TracerProvider
from orrery_engine.app import create_app
from orrery_engine.settings import Settings, describe_errors
from orrery_engine.telemetry import add_trace_ids
from pydantic import ValidationError

TOKEN = "t" * 40
GOLDEN = Path(__file__).resolve().parents[3] / "fixtures/golden/engine-contract"


def reconstruction_request(file_server: str) -> dict[str, object]:
    request = json.loads((GOLDEN / "reconstruct-job-request.json").read_text())
    footage = request["inputs"]["footage"][0]
    footage["sourceUrl"] = f"{file_server}/h264.mp4"
    grant = request["artifactGrant"]["analysisArtifacts"]
    grant["uploadUrl"] = f"{file_server}/analysis.json?upload=1"
    grant["downloadUrl"] = f"{file_server}/analysis.json?download=1"
    return request


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def client(file_server: str, tmp_path: Path) -> Iterator[httpx.Client]:
    """The engine served by uvicorn on a real socket, as the worker reaches it."""
    settings = Settings(
        service_token=TOKEN,  # pyright: ignore[reportArgumentType] - coerced to SecretStr
        allowed_source_origins=(file_server,),
        work_dir=tmp_path,
    )
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("engine did not start")
        time.sleep(0.02)
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as http:
        yield http
    server.should_exit = True
    thread.join()


def probe(client: httpx.Client, url: str, *, token: str = TOKEN, max_bytes: int = 10**9):
    return client.post(
        "/v1/probe",
        json={"sourceUrl": url, "maxBytes": max_bytes, "maxDurationS": 300},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_probes_a_real_download(client: httpx.Client, file_server: str) -> None:
    response = probe(client, f"{file_server}/h264.mp4")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "accepted"
    assert body["codec"] == "h264"
    assert body["rotationQuarterTurns"] == 0
    assert len(body["sha256"]) == 64


def test_rejects_a_disguised_file_with_guidance(client: httpx.Client, file_server: str) -> None:
    body = probe(client, f"{file_server}/notes.mp4").json()
    assert body == {"outcome": "rejected", "code": "not_video", "reason": body["reason"]}
    assert "MP4" in body["reason"]


def test_stops_downloading_past_the_size_limit(client: httpx.Client, file_server: str) -> None:
    body = probe(client, f"{file_server}/h264.mp4", max_bytes=1000).json()
    assert body["code"] == "too_large"


def test_requires_the_service_token(client: httpx.Client, file_server: str) -> None:
    assert probe(client, f"{file_server}/h264.mp4", token="wrong").status_code == 401
    assert client.post("/v1/probe", json={}).status_code == 401


def test_downloads_only_from_allowed_origins(client: httpx.Client) -> None:
    response = probe(client, "http://169.254.169.254/latest/meta-data")
    assert response.status_code == 422


def test_missing_sources_are_retryable_errors(client: httpx.Client, file_server: str) -> None:
    assert probe(client, f"{file_server}/missing.mp4").status_code == 502


def test_reconstruction_job_is_contract_validated_and_truthfully_blocked(
    client: httpx.Client, file_server: str
) -> None:
    response = client.post(
        "/v1/jobs",
        json=reconstruction_request(file_server),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    assert response.status_code == 409
    assert response.json() == {
        "contractVersion": "1",
        "jobId": "0195e7c3-24a0-7a72-8c4e-f57a34537c29",
        "accepted": False,
        "status": "rejected",
        "error": {
            "code": "capability_unavailable",
            "message": (
                "Reconstruction cannot run because the production stage runner and ingest "
                "artifacts are not implemented."
            ),
            "retryable": False,
            "stage": "ingest",
            "prerequisites": ["vision-pipeline:1.1", "vision-pipeline:2.1"],
        },
    }


def test_reconstruction_job_rejects_incompatible_versions_and_invalid_payloads(
    client: httpx.Client, file_server: str
) -> None:
    request = reconstruction_request(file_server)
    request["contractVersion"] = "2"
    incompatible = client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    assert incompatible.status_code == 409
    assert incompatible.json()["error"]["code"] == "incompatible_contract"

    invalid = client.post(
        "/v1/jobs",
        json={"truth": "must never be accepted"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert invalid.status_code == 422
    assert invalid.json() == {
        "contractVersion": "1",
        "error": {
            "code": "invalid_input",
            "message": "The reconstruction job does not match contract version 1.",
            "retryable": False,
        },
    }


def test_reconstruction_job_requires_callback_secret_and_allowed_artifact_origins(
    client: httpx.Client, file_server: str
) -> None:
    request = reconstruction_request(file_server)
    missing_secret = client.post(
        "/v1/jobs",
        json=request,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert missing_secret.status_code == 422
    assert missing_secret.json()["error"]["code"] == "invalid_input"

    artifact_grant = cast(dict[str, object], request["artifactGrant"])
    analysis_artifacts = cast(dict[str, object], artifact_grant["analysisArtifacts"])
    analysis_artifacts["uploadUrl"] = "http://other.test/a"
    disallowed = client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    assert disallowed.status_code == 422
    assert "allowlist" in disallowed.json()["error"]["message"]


def test_unknown_reconstruction_job_has_typed_error(client: httpx.Client) -> None:
    response = client.get(
        "/v1/jobs/0195e7c3-24a0-7a72-8c4e-f57a34537c29",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_settings_errors_name_variables_but_never_values() -> None:
    secret = "short-secret-value"
    with pytest.raises(ValidationError) as caught:
        Settings(
            service_token=secret,  # pyright: ignore[reportArgumentType]
            allowed_source_origins=("ftp://nope/path",),
        )
    text = describe_errors(caught.value)
    assert "ENGINE_SERVICE_TOKEN" in text
    assert "ENGINE_ALLOWED_SOURCE_ORIGINS" in text
    assert secret not in text


def test_log_lines_carry_the_active_trace_ids() -> None:

    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("probe") as span:
        event = add_trace_ids(None, "info", {"event": "probe accepted"})
    assert event["trace_id"] == format(span.get_span_context().trace_id, "032x")
    assert add_trace_ids(None, "info", {"event": "outside"}) == {"event": "outside"}


def test_production_requires_tracing_and_error_reporting(file_server: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(
            service_token=TOKEN,  # pyright: ignore[reportArgumentType]
            allowed_source_origins=(file_server,),
            environment="production",
        )
    assert "ENGINE_OTLP_ENDPOINT" in str(caught.value)

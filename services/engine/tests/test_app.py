import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from opentelemetry.sdk.trace import TracerProvider
from orrery_engine.app import create_app
from orrery_engine.settings import Settings, describe_errors
from orrery_engine.telemetry import add_trace_ids
from pydantic import ValidationError

TOKEN = "t" * 40


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

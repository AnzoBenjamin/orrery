import base64
import io
import itertools
import json
import socket
import threading
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

import av
import httpx
import pytest
import uvicorn
from av.container import InputContainer
from opentelemetry.sdk.trace import TracerProvider
from orrery_engine.app import create_app
from orrery_engine.generated.contract import AnalysisArtifacts, EngineEvent
from orrery_engine.settings import Settings, describe_errors
from orrery_engine.telemetry import add_trace_ids
from pydantic import ValidationError

TOKEN = "t" * 40
GOLDEN = Path(__file__).resolve().parents[3] / "fixtures/golden/engine-contract"


class JobServer(Protocol):
    origin: str
    artifact: bytes | None
    events: list[dict[str, object]]
    put_count: int
    signatures_verified: int
    lock: threading.Lock


def reconstruction_request(
    source_origin: str,
    job_origin: str | None = None,
    *,
    filename: str = "h264.mp4",
) -> dict[str, Any]:
    target = job_origin or source_origin
    request = json.loads((GOLDEN / "reconstruct-job-request.json").read_text())
    footage = request["inputs"]["footage"][0]
    footage["sourceUrl"] = f"{source_origin}/{filename}"
    grant = request["artifactGrant"]["analysisArtifacts"]
    grant["uploadUrl"] = f"{target}/analysis.json?upload=1"
    grant["downloadUrl"] = f"{target}/analysis.json?download=1"
    request["callback"]["url"] = f"{target}/callbacks"
    return request


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def running_engine(settings: Settings) -> Generator[httpx.Client]:
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


@pytest.fixture
def client(file_server: str, job_server: JobServer, tmp_path: Path) -> Iterator[httpx.Client]:
    """The engine served by uvicorn on a real socket, as the worker reaches it."""
    settings = Settings(
        service_token=TOKEN,  # pyright: ignore[reportArgumentType] - coerced to SecretStr
        allowed_source_origins=(file_server, job_server.origin),
        work_dir=tmp_path,
    )
    with running_engine(settings) as http:
        yield http


def probe(client: httpx.Client, url: str, *, token: str = TOKEN, max_bytes: int = 10**9):
    return client.post(
        "/v1/probe",
        json={"sourceUrl": url, "maxBytes": max_bytes, "maxDurationS": 300},
        headers={"Authorization": f"Bearer {token}"},
    )


def wait_terminal(client: httpx.Client, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = client.get(f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {TOKEN}"})
        body = response.json()
        if body["status"] in {"failed", "canceled", "completed"}:
            return body
        time.sleep(0.02)
    raise AssertionError("job did not reach a terminal state")


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


def test_reconstruction_job_runs_real_ingest_camera_motion_seeding_and_tracking_then_reports_grouping_limit(  # noqa: E501, PLR0915
    client: httpx.Client, file_server: str, job_server: JobServer
) -> None:
    with job_server.lock:
        job_server.artifact = None
        job_server.events.clear()
        job_server.put_count = 0
        job_server.signatures_verified = 0
    request = reconstruction_request(file_server, job_server.origin)
    request["inputs"]["annotations"] = [
        {
            "annotationId": "user-joint-1",
            "footageId": "fixture-clean-four-bar",
            "frameIndex": 3,
            "kind": "joint",
            "point": {"xPx": 160, "yPx": 120},
            "coordinateSpace": "full_resolution_pixels",
        }
    ]
    job_id = str(request["jobId"])
    response = client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    assert response.status_code == 202
    assert response.json()["accepted"] is True
    assert client.get(response.json()["statusUrl"]).status_code == 401

    terminal = wait_terminal(client, job_id)
    assert terminal["status"] == "failed"
    assert terminal["error"] == {
        "code": "capability_unavailable",
        "message": "Point tracking completed, but body grouping is not implemented yet.",
        "retryable": False,
        "stage": "body_grouping",
        "prerequisites": ["vision-pipeline:5.1"],
    }
    assert len(cast(list[object], terminal["artifacts"])) == 1

    artifact_bytes = job_server.artifact
    assert artifact_bytes is not None
    artifact = AnalysisArtifacts.model_validate_json(artifact_bytes)
    assert artifact.tracks
    assert all(track.body_id is None for track in artifact.tracks)
    assert artifact.tracking_analysis is not None
    tracking_stage = artifact.tracking_analysis[0]
    assert tracking_stage.format == "orrery.engine.tracking"
    assert tracking_stage.schema_version == 1
    assert tracking_stage.backend == "klt"
    assert tracking_stage.metrics.output_track_count == len(artifact.tracks)
    assert tracking_stage.metrics.observed_sample_count > 0
    assert len(tracking_stage.reseeding) == 3
    assert tracking_stage.tracks_arrow.byte_size > 0
    assert len(artifact.camera_motion) == 60
    assert artifact.camera_motion_analysis is not None
    camera_stage = artifact.camera_motion_analysis[0]
    assert camera_stage.footage_id == "fixture-clean-four-bar"
    assert camera_stage.quality.valid_frame_fraction > 0.9
    assert camera_stage.stabilized_preview.byte_size > 0
    assert artifact.seeding_analysis is not None
    seeding_stage = artifact.seeding_analysis[0]
    assert seeding_stage.format == "orrery.engine.seeding"
    assert seeding_stage.schema_version == 1
    assert seeding_stage.coverage
    assert any(point.source == "user_joint" for point in seeding_stage.points)
    user_point = next(point for point in seeding_stage.points if point.source == "user_joint")
    assert (user_point.x_px, user_point.y_px) == (160, 120)
    assert user_point.frame_index == 3
    assert seeding_stage.moving_mask.byte_size > 0
    assert seeding_stage.reseeding_policy.interval_frames == 15
    with av.open(io.BytesIO(base64.b64decode(camera_stage.stabilized_preview.data))) as preview:
        assert preview.streams.video[0].codec_context.name == "h264"
        assert preview.streams.video[0].frames == 60
    assert [stage.stage for stage in artifact.stage_runtimes] == [
        "ingest",
        "camera_motion",
        "seeding",
        "tracking",
    ]
    assert artifact.ingest is not None
    footage = artifact.ingest[0]
    assert (footage.width, footage.height) == (320, 240)
    assert (footage.display_width, footage.display_height) == (320, 240)
    assert footage.color_space == "bt709-rgb"
    assert len(footage.original_timestamps_seconds) == 60
    assert len(footage.normalized_frames) == 60
    assert footage.analysis_copy.byte_size > 0
    assert footage.proxy_video.byte_size > 0
    assert len(footage.thumbnails) == 5
    with av.open(io.BytesIO(base64.b64decode(footage.proxy_video.data))) as proxy:
        assert proxy.streams.video[0].codec_context.name == "h264"
        assert proxy.streams.video[0].frames == 60

    with job_server.lock:
        events = [event for event in job_server.events if event["jobId"] == job_id]
        assert job_server.signatures_verified >= len(events)
    validated = [EngineEvent.model_validate(event).root for event in events]
    assert [event.seq for event in validated] == list(range(len(validated)))
    assert [event.type for event in validated] == [
        "stage_started",
        "progress",
        "progress",
        "stage_completed",
        "artifact_written",
        "stage_started",
        "progress",
        "progress",
        "progress",
        "stage_completed",
        "artifact_written",
        "stage_started",
        "progress",
        "progress",
        "progress",
        "stage_completed",
        "artifact_written",
        "stage_started",
        "progress",
        "progress",
        "stage_completed",
        "artifact_written",
        "stage_started",
        "failed",
    ]


def test_real_handheld_fixture_runs_ingest_then_camera_motion(
    client: httpx.Client, file_server: str, job_server: JobServer
) -> None:
    request = reconstruction_request(
        file_server, job_server.origin, filename="phone-slider-crank.mp4"
    )
    request["jobId"] = str(uuid4())
    response = client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    terminal = wait_terminal(client, str(request["jobId"]))
    assert response.status_code == 202
    assert terminal["error"]["stage"] == "body_grouping"
    artifact_bytes = job_server.artifact
    assert artifact_bytes is not None
    artifact = AnalysisArtifacts.model_validate_json(artifact_bytes)
    assert len(artifact.camera_motion) == 8
    assert artifact.camera_motion_analysis is not None
    stage = artifact.camera_motion_analysis[0]
    assert stage.quality.stabilized_rms_px < 1.0
    assert stage.quality.valid_frame_fraction == 1.0
    assert not stage.requires_spatial
    preview_container = cast(
        InputContainer,
        av.open(io.BytesIO(base64.b64decode(stage.stabilized_preview.data))),
    )
    with preview_container:
        assert len(list(preview_container.decode(video=0))) == 8


def test_parallax_uploads_evidence_then_emits_spatial_routing_event(
    client: httpx.Client, file_server: str, job_server: JobServer
) -> None:
    request = reconstruction_request(file_server, job_server.origin, filename="parallax.mp4")
    request["jobId"] = str(uuid4())
    job_id = str(request["jobId"])
    response = client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    terminal = wait_terminal(client, job_id)
    assert response.status_code == 202
    assert terminal["error"]["code"] == "requires_spatial"
    assert terminal["error"]["stage"] == "camera_motion"
    assert terminal["error"]["prerequisites"] == ["spatial-reconstruction"]
    assert "steadier, more frontal" in terminal["error"]["message"]
    artifact_bytes = job_server.artifact
    assert artifact_bytes is not None
    artifact = AnalysisArtifacts.model_validate_json(artifact_bytes)
    assert artifact.camera_motion_analysis is not None
    stage = artifact.camera_motion_analysis[0]
    assert stage.requires_spatial
    assert stage.routing_reason is not None
    assert stage.quality.parallax_evidence_frames >= 2
    with job_server.lock:
        events = [event for event in job_server.events if event["jobId"] == job_id]
    assert [event["type"] for event in events[-2:]] == ["routing", "failed"]
    routing = cast(dict[str, object], events[-2]["payload"])
    assert routing["destination"] == "spatial_reconstruction"


def test_reconstruction_ingest_applies_rotation_and_normalizes_vfr(
    client: httpx.Client, file_server: str, job_server: JobServer
) -> None:
    rotated = reconstruction_request(file_server, job_server.origin, filename="rotated.mp4")
    rotated["jobId"] = str(uuid4())
    response = client.post(
        "/v1/jobs",
        json=rotated,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    terminal = wait_terminal(client, str(rotated["jobId"]))
    assert response.status_code == 202
    assert terminal["error"]["code"] == "capability_unavailable"
    assert terminal["error"]["stage"] == "body_grouping"
    rotated_bytes = job_server.artifact
    assert rotated_bytes is not None
    rotated_artifact = AnalysisArtifacts.model_validate_json(rotated_bytes)
    assert rotated_artifact.ingest is not None
    rotated_ingest = rotated_artifact.ingest[0]
    assert rotated_ingest.rotation_quarter_turns == 1
    assert (rotated_ingest.display_width, rotated_ingest.display_height) == (240, 320)

    vfr = reconstruction_request(file_server, job_server.origin, filename="vfr.mp4")
    vfr["jobId"] = str(uuid4())
    client.post(
        "/v1/jobs",
        json=vfr,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    wait_terminal(client, str(vfr["jobId"]))
    vfr_bytes = job_server.artifact
    assert vfr_bytes is not None
    vfr_artifact = AnalysisArtifacts.model_validate_json(vfr_bytes)
    assert vfr_artifact.ingest is not None
    vfr_ingest = vfr_artifact.ingest[0]
    original_deltas = [
        float(after.root - before.root)
        for before, after in itertools.pairwise(vfr_ingest.original_timestamps_seconds)
    ]
    normalized_deltas = [
        after.timestamp_seconds - before.timestamp_seconds
        for before, after in itertools.pairwise(vfr_ingest.normalized_frames)
    ]
    assert max(original_deltas) > min(original_deltas) * 1.5
    assert max(normalized_deltas) - min(normalized_deltas) < 1e-9


def test_reconstruction_job_can_be_canceled_within_ten_seconds(
    client: httpx.Client, job_server: JobServer
) -> None:
    request = reconstruction_request(job_server.origin, job_server.origin, filename="slow.mp4")
    request["jobId"] = str(uuid4())
    job_id = str(request["jobId"])
    client.post(
        "/v1/jobs",
        json=request,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Orrery-Callback-Secret": "s" * 40,
        },
    )
    started = time.monotonic()
    canceled = client.post(
        f"/v1/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert canceled.status_code == 202
    terminal = wait_terminal(client, job_id)
    assert time.monotonic() - started < 10
    assert terminal["status"] == "canceled"
    assert terminal["error"]["code"] == "canceled"


def test_reconstruction_resumes_from_the_tracking_checkpoint_after_restart(
    file_server: str, job_server: JobServer, tmp_path: Path
) -> None:
    request = reconstruction_request(file_server, job_server.origin)
    request["jobId"] = str(uuid4())
    job_id = str(request["jobId"])
    settings = Settings(
        service_token=TOKEN,  # pyright: ignore[reportArgumentType] - coerced to SecretStr
        allowed_source_origins=(file_server, job_server.origin),
        work_dir=tmp_path,
    )
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Orrery-Callback-Secret": "s" * 40,
    }
    with job_server.lock:
        initial_puts = job_server.put_count
    with running_engine(settings) as first:
        assert first.post("/v1/jobs", json=request, headers=headers).status_code == 202
        assert wait_terminal(first, job_id)["error"]["code"] == "capability_unavailable"
    with job_server.lock:
        after_tracking_puts = job_server.put_count
    assert after_tracking_puts == initial_puts + 4

    with running_engine(settings) as resumed:
        assert resumed.post("/v1/jobs", json=request, headers=headers).status_code == 202
        terminal = wait_terminal(resumed, job_id)
    assert terminal["error"]["stage"] == "body_grouping"
    with job_server.lock:
        assert job_server.put_count == after_tracking_puts
        job_events = [event for event in job_server.events if event["jobId"] == job_id]
    assert [event["type"] for event in job_events[-2:]] == ["stage_started", "failed"]


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

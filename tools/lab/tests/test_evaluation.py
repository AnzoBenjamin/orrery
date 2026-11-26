"""Task 7.1 evaluation metrics over real versioned truth and contract-shaped artifacts."""

import json
import math
import socket
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

import numpy as np
import pytest
import uvicorn
from orrery_kinematics import Solver
from orrery_lab.eval import (
    AnalysisArtifacts,
    BodyArtifact,
    BodyPoseArtifact,
    CameraMotionArtifact,
    DiagnosisFinding,
    EngineJobClient,
    JobApiUnavailableError,
    JointArtifact,
    ParameterEstimate,
    ResurrectionCandidate,
    StageRuntime,
    TrackArtifact,
    TrackSample,
    evaluate,
    evaluate_paths,
    load_truth,
)
from orrery_lab.eval.model import truth_repair_key
from orrery_lab.eval.truth import LoadedTruth
from orrery_lab.graph import Json

ROOT = Path(__file__).parents[3]
FIXTURES = ROOT / "e2e/fixtures/synthetic-lab/suite"
TOKEN = "e" * 40


def _lengths(truth: LoadedTruth) -> dict[str, float]:
    result: dict[str, float] = {}
    for body in cast(list[Json], truth.graph["bodies"]):
        points = [
            (
                float(cast(Json, point["local"])["x"]),
                float(cast(Json, point["local"])["y"]),
            )
            for point in cast(list[Json], body["points"])
            if point.get("role") == "joint_anchor"
        ]
        distances = [
            math.dist(left, right) for i, left in enumerate(points) for right in points[i + 1 :]
        ]
        if distances and max(distances) > 0:
            result[str(body["id"])] = max(distances)
    return result


def _joint_location(truth: LoadedTruth, joint: Json) -> tuple[float, float]:
    first = truth.frames[0].frame_index
    points = {
        (point.body_id, point.point_id): point
        for point in truth.points
        if point.frame_index == first
    }
    refs = [
        cast(Json, joint[key])
        for key in ("anchorA", "anchorB", "pin", "followerPoint")
        if isinstance(joint.get(key), dict)
    ]
    locations = [points[(str(ref["bodyId"]), str(ref["pointId"]))] for ref in refs]
    return (
        sum(point.x_px for point in locations) / len(locations),
        sum(point.y_px for point in locations) / len(locations),
    )


def _expected_mobility(truth: LoadedTruth) -> int:
    solver = Solver(json.dumps(truth.graph))
    driver_ids = [str(driver["id"]) for driver in cast(list[Json], truth.graph["drivers"])]
    drive = np.asarray([truth.frames[0].drivers[item] for item in driver_ids])
    state = solver.assemble(drive)
    return int(solver.mobility(state, drive).numerical)


def _expected_diagnosis(truth: LoadedTruth) -> tuple[DiagnosisFinding, ...]:
    breakage = truth.manifest.get("breakage")
    if not isinstance(breakage, dict):
        return ()
    findings = [
        DiagnosisFinding(kind="missing_body", ref=f"body:{body['id']}")
        for body in cast(list[Json], breakage["removedBodies"])
    ]
    findings.extend(
        DiagnosisFinding(kind="missing_joint", ref=f"joint:{joint['id']}")
        for joint in cast(list[Json], breakage["removedJoints"])
    )
    findings.extend(
        DiagnosisFinding(kind="empty_hole", ref=f"hole:{hole['bodyId']}/{hole['pointId']}")
        for hole in cast(list[Json], breakage["holes"])
    )
    return tuple(findings)


def _perfect(truth: LoadedTruth) -> AnalysisArtifacts:
    grouped: dict[tuple[str, str], list[TrackSample]] = {}
    for point in truth.points:
        grouped.setdefault(point.key, []).append(
            TrackSample(
                frame_index=point.frame_index,
                xPx=point.x_px,
                yPx=point.y_px,
                visible=point.visible,
                uncertainty_px=0.25,
            )
        )
    tracks = tuple(
        TrackArtifact(track_id=f"track-{index}", body_id=f"cluster-{body}", samples=tuple(samples))
        for index, ((body, _point), samples) in enumerate(sorted(grouped.items()))
    )
    bodies: list[BodyArtifact] = []
    lengths = _lengths(truth)
    for body_id in sorted({pose.body_id for frame in truth.frames for pose in frame.poses}):
        poses: list[BodyPoseArtifact] = []
        for frame in truth.frames:
            pose = next(item for item in frame.poses if item.body_id == body_id)
            x, y, z, w = pose.quaternion_xyzw
            angle = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            poses.append(
                BodyPoseArtifact(
                    frame_index=frame.frame_index,
                    xWorld=pose.translation[0],
                    yWorld=pose.translation[1],
                    angleRadians=angle,
                )
            )
        bodies.append(
            BodyArtifact(
                body_id=f"cluster-{body_id}",
                link_length_world=lengths.get(body_id),
                poses=tuple(poses),
            )
        )
    joints: list[JointArtifact] = []
    for joint in cast(list[Json], truth.graph["joints"]):
        x_px, y_px = _joint_location(truth, joint)
        joints.append(
            JointArtifact(
                joint_id=f"pred-{joint['id']}",
                body_a=f"cluster-{joint['bodyA']}",
                body_b=f"cluster-{joint['bodyB']}",
                kind=str(joint["kind"]),
                xPx=x_px,
                yPx=y_px,
            )
        )
    params = tuple(
        ParameterEstimate(parameter_id=key, estimate=float(value), standard_deviation=0.01)
        for key, value in sorted(cast(dict[str, float], truth.manifest["params"]).items())
    )
    key = truth_repair_key(truth)
    resurrection = (
        (ResurrectionCandidate(repair_key=key, rank=1, tie_group="leader"),) if key else ()
    )
    return AnalysisArtifacts(
        engine_version="test-engine-1",
        tracks=tracks,
        cameraMotion=tuple(
            CameraMotionArtifact(
                frame_index=frame.frame_index,
                reference_to_frame=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            )
            for frame in truth.frames
        ),
        bodies=tuple(bodies),
        joints=tuple(joints),
        mobility=_expected_mobility(truth),
        parameters=params,
        diagnosis=_expected_diagnosis(truth),
        resurrection=resurrection,
        stageRuntimes=(
            StageRuntime(stage="tracking", runtime_ms=12.5),
            StageRuntime(stage="fit", runtime_ms=8.25),
        ),
    )


@pytest.fixture(scope="module")
def clean_truth() -> LoadedTruth:
    return load_truth(FIXTURES / "clean-four-bar")


@pytest.fixture(scope="module")
def broken_truth() -> LoadedTruth:
    return load_truth(FIXTURES / "broken-flapping-wing")


def test_perfect_predictions_score_every_applicable_metric(clean_truth: LoadedTruth) -> None:
    report = evaluate(clean_truth, _perfect(clean_truth))

    assert report.format == "orrery.synthetic.evaluation"
    assert report.schema_version == 1
    assert report.tracking.endpoint_median_px == pytest.approx(0)
    assert report.tracking.endpoint_p90_px == pytest.approx(0)
    assert report.tracking.occlusion_accuracy == 1
    assert report.camera.motion_rmse_px == pytest.approx(0, abs=1e-8)
    assert report.grouping.adjusted_rand_index == 1
    assert report.joints.precision == report.joints.recall == report.joints.type_accuracy == 1
    assert report.model.mobility_accuracy == 1
    assert report.model.link_length_mean_relative_error == pytest.approx(0)
    assert report.model.pose_translation_rmse_world_units == pytest.approx(0)
    assert report.model.pose_rotation_rmse_radians == pytest.approx(0)
    assert report.calibration.one_sigma_coverage == 1
    assert report.diagnosis.accuracy == 1
    assert not report.resurrection.applicable
    assert report.stage_runtimes_ms == {"tracking": 12.5, "fit": 8.25}
    assert report.units["runtime"] == "milliseconds wall clock"


def test_controlled_tracking_occlusion_camera_and_grouping_errors(clean_truth: LoadedTruth) -> None:
    perfect = _perfect(clean_truth)
    shifted: list[TrackArtifact] = []
    for index, track in enumerate(perfect.tracks):
        body_id = track.body_id if index else perfect.tracks[1].body_id
        shifted.append(
            track.model_copy(
                update={
                    "body_id": body_id,
                    "samples": tuple(
                        sample.model_copy(
                            update={
                                "x_px": sample.x_px + 3,
                                "y_px": sample.y_px + 4,
                                "visible": (not sample.visible if index == 0 else sample.visible),
                            }
                        )
                        for sample in track.samples
                    ),
                }
            )
        )
    camera = tuple(
        item.model_copy(
            update={"reference_to_frame": (1.0, 0.0, 2.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)}
        )
        for item in perfect.camera_motion
    )
    report = evaluate(
        clean_truth,
        perfect.model_copy(update={"tracks": tuple(shifted), "camera_motion": camera}),
    )

    assert report.tracking.endpoint_median_px == pytest.approx(5)
    assert report.tracking.endpoint_p90_px == pytest.approx(5)
    assert cast(float, report.tracking.occlusion_accuracy) < 1
    assert report.camera.motion_rmse_px == pytest.approx(2, abs=1e-8)
    assert cast(float, report.grouping.adjusted_rand_index) < 1


def test_joint_mobility_geometry_pose_and_calibration_errors(clean_truth: LoadedTruth) -> None:
    perfect = _perfect(clean_truth)
    joints = list(perfect.joints[:-1])
    joints[0] = joints[0].model_copy(update={"kind": "prismatic"})
    bodies: list[BodyArtifact] = []
    for index, body in enumerate(perfect.bodies):
        updates: dict[str, object] = {}
        if body.link_length_world is not None:
            updates["link_length_world"] = body.link_length_world * (1.1 + 0.1 * index)
        updates["poses"] = tuple(
            pose.model_copy(update={"x_world": pose.x_world + (1 if index == 0 else 0)})
            for pose in body.poses
        )
        bodies.append(body.model_copy(update=updates))
    parameters = tuple(
        parameter.model_copy(update={"estimate": parameter.estimate + (0 if index % 2 else 10)})
        for index, parameter in enumerate(perfect.parameters)
    )
    report = evaluate(
        clean_truth,
        perfect.model_copy(
            update={
                "joints": tuple(joints),
                "mobility": cast(int, perfect.mobility) + 1,
                "bodies": tuple(bodies),
                "parameters": parameters,
            }
        ),
    )

    assert report.joints.precision == 1
    assert report.joints.recall < 1
    assert cast(float, report.joints.type_accuracy) < 1
    assert report.model.mobility_accuracy == 0
    assert cast(float, report.model.link_length_mean_relative_error) > 0
    assert cast(float, report.model.pose_translation_rmse_world_units) > 0
    assert cast(float, report.calibration.one_sigma_coverage) < 1
    assert cast(float, report.calibration.two_sigma_calibration_error) > 0


def test_empty_and_fully_occluded_predictions_are_explicit(clean_truth: LoadedTruth) -> None:
    empty = AnalysisArtifacts(engine_version="empty-engine")
    report = evaluate(clean_truth, empty)
    assert report.tracking.endpoint_median_px is None
    assert report.tracking.occlusion_accuracy is None
    assert report.grouping.adjusted_rand_index is None
    assert report.joints.precision == 0
    assert report.joints.recall == 0
    assert report.model.mobility_accuracy is None
    assert report.calibration.parameter_count == 0

    perfect = _perfect(clean_truth)
    visible_predictions = tuple(
        track.model_copy(
            update={
                "samples": tuple(
                    sample.model_copy(update={"visible": True}) for sample in track.samples
                )
            }
        )
        for track in perfect.tracks
    )
    occluded_report = evaluate(
        clean_truth, perfect.model_copy(update={"tracks": visible_predictions})
    )
    assert occluded_report.tracking.endpoint_median_px == pytest.approx(0)
    assert cast(float, occluded_report.tracking.occlusion_accuracy) < 1


def test_global_matching_handles_permuted_ids_and_rejects_distant_tracks(
    clean_truth: LoadedTruth,
) -> None:
    perfect = _perfect(clean_truth)
    permuted = tuple(reversed(perfect.tracks))
    distant = TrackArtifact(
        track_id="distant",
        body_id="noise",
        samples=(TrackSample(frame_index=0, xPx=10_000, yPx=10_000, visible=True),),
    )
    report = evaluate(clean_truth, perfect.model_copy(update={"tracks": (*permuted, distant)}))
    assert report.tracking.matched_tracks == len(perfect.tracks)
    assert report.tracking.predicted_tracks == len(perfect.tracks) + 1
    assert report.tracking.endpoint_median_px == pytest.approx(0)
    assert report.grouping.adjusted_rand_index == 1


def test_diagnosis_and_resurrection_top_k_and_tie_sets(broken_truth: LoadedTruth) -> None:
    perfect = _perfect(broken_truth)
    report = evaluate(broken_truth, perfect)
    assert report.diagnosis.accuracy == 1
    assert report.resurrection.top_1_correct
    assert report.resurrection.top_3_correct
    assert report.resurrection.tie_set_correct

    key = truth_repair_key(broken_truth)
    assert key is not None
    candidates = (
        ResurrectionCandidate(repair_key="binary_link:wrong-a", rank=1, tie_group="first"),
        ResurrectionCandidate(repair_key="binary_link:wrong-b", rank=2, tie_group="first"),
        ResurrectionCandidate(repair_key=key, rank=3, tie_group="first"),
    )
    tied = evaluate(
        broken_truth,
        perfect.model_copy(
            update={
                "diagnosis": perfect.diagnosis[:-1],
                "resurrection": candidates,
            }
        ),
    )
    assert tied.diagnosis.accuracy < 1
    assert not tied.resurrection.top_1_correct
    assert tied.resurrection.top_3_correct
    assert tied.resurrection.tie_set_correct

    outside = candidates[2].model_copy(update={"tie_group": "other"})
    untied = evaluate(
        broken_truth,
        perfect.model_copy(update={"resurrection": (*candidates[:2], outside)}),
    )
    assert not untied.resurrection.tie_set_correct


def test_artifact_and_report_round_trip_are_strict_and_versioned(
    clean_truth: LoadedTruth, tmp_path: Path
) -> None:
    artifacts = _perfect(clean_truth)
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(artifacts.model_dump_json(by_alias=True), encoding="utf-8")
    report = evaluate_paths(clean_truth.directory, artifact_path)
    encoded = report.model_dump_json(by_alias=True)
    assert json.loads(encoded)["schemaVersion"] == 1
    assert AnalysisArtifacts.model_validate_json(artifact_path.read_bytes()) == artifacts
    invalid = json.loads(artifact_path.read_text())
    invalid["truthLeak"] = clean_truth.manifest
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        AnalysisArtifacts.model_validate(invalid)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _real_engine_and_clip_server() -> Generator[tuple[str, str]]:
    from orrery_engine.app import create_app  # noqa: PLC0415
    from orrery_engine.settings import Settings  # noqa: PLC0415

    directory = FIXTURES / "clean-four-bar"
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    files = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    files_thread = threading.Thread(target=files.serve_forever, daemon=True)
    files_thread.start()
    source_origin = f"http://127.0.0.1:{files.server_address[1]}"
    port = _free_port()
    settings = Settings(
        service_token=TOKEN,  # pyright: ignore[reportArgumentType]
        allowed_source_origins=(source_origin,),
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    engine_thread = threading.Thread(target=server.run, daemon=True)
    engine_thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("engine failed to start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}", f"{source_origin}/clip.mp4"
    finally:
        server.should_exit = True
        engine_thread.join()
        files.shutdown()
        files_thread.join()


def test_real_engine_probe_executes_and_job_api_blocker_is_not_faked() -> None:
    with _real_engine_and_clip_server() as (engine_url, clip_url):
        client = EngineJobClient(engine_url, TOKEN)
        probe = client.probe_clip(clip_url)
        assert probe.width == 96
        assert probe.height == 64
        assert len(probe.sha256) == 64
        with pytest.raises(JobApiUnavailableError, match=r"vision-pipeline task 1\.1"):
            client.run_clip(clip_url)

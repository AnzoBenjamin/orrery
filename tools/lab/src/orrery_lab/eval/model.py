"""Joint, mobility, geometry, pose, calibration, diagnosis, and repair metrics."""

from __future__ import annotations

import json
import math
from typing import cast

import numpy as np
import numpy.typing as npt
from orrery_kinematics import Solver

from orrery_lab.eval.matching import assignment
from orrery_lab.eval.truth import LoadedTruth
from orrery_lab.eval.types import (
    AnalysisArtifacts,
    CalibrationMetrics,
    DiagnosisMetrics,
    JointMetrics,
    ModelMetrics,
    ResurrectionMetrics,
)
from orrery_lab.graph import Json

MIN_ALIGNMENT_VARIANCE = 1e-15


def joint_metrics(
    artifacts: AnalysisArtifacts,
    truth: LoadedTruth,
    body_map: dict[str, str],
    *,
    tolerance_px: float,
) -> JointMetrics:
    actual = _true_joints(truth)
    predicted = artifacts.joints
    if not predicted and not actual:
        return JointMetrics(
            precision=1.0, recall=1.0, f1=1.0, typeAccuracy=None, matched=0, predicted=0, truth=0
        )
    costs = np.full((len(predicted), len(actual)), tolerance_px + 1.0)
    for row, joint in enumerate(predicted):
        pair = frozenset((body_map.get(joint.body_a, ""), body_map.get(joint.body_b, "")))
        for column, (_, body_pair, _kind, x_px, y_px) in enumerate(actual):
            if pair == body_pair:
                costs[row, column] = math.hypot(joint.x_px - x_px, joint.y_px - y_px)
    matches = tuple(
        (row, column) for row, column in assignment(costs) if costs[row, column] <= tolerance_px
    )
    true_positive = len(matches)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(actual) if actual else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    type_correct = sum(predicted[row].kind == actual[column][2] for row, column in matches)
    return JointMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        typeAccuracy=type_correct / true_positive if true_positive else None,
        matched=true_positive,
        predicted=len(predicted),
        truth=len(actual),
    )


def model_metrics(
    artifacts: AnalysisArtifacts, truth: LoadedTruth, body_map: dict[str, str]
) -> ModelMetrics:
    expected_mobility = _truth_mobility(truth)
    length_error = _length_error(artifacts, truth, body_map)
    translation_rmse, rotation_rmse = _pose_errors(artifacts, truth, body_map)
    return ModelMetrics(
        mobilityAccuracy=(
            float(artifacts.mobility == expected_mobility)
            if artifacts.mobility is not None
            else None
        ),
        linkLengthMeanRelativeError=length_error,
        poseTranslationRmseWorldUnits=translation_rmse,
        poseRotationRmseRadians=rotation_rmse,
    )


def calibration_metrics(artifacts: AnalysisArtifacts, truth: LoadedTruth) -> CalibrationMetrics:
    params = cast(dict[str, object], truth.manifest.get("params", {}))
    inside_one = 0
    inside_two = 0
    count = 0
    for estimate in artifacts.parameters:
        actual = params.get(estimate.parameter_id)
        if not isinstance(actual, (float, int)) or isinstance(actual, bool):
            continue
        error = abs(estimate.estimate - float(actual))
        inside_one += error <= estimate.standard_deviation
        inside_two += error <= 2 * estimate.standard_deviation
        count += 1
    one = inside_one / count if count else None
    two = inside_two / count if count else None
    return CalibrationMetrics(
        oneSigmaCoverage=one,
        twoSigmaCoverage=two,
        oneSigmaCalibrationError=abs(one - 0.6827) if one is not None else None,
        twoSigmaCalibrationError=abs(two - 0.9545) if two is not None else None,
        parameterCount=count,
    )


def diagnosis_metrics(artifacts: AnalysisArtifacts, truth: LoadedTruth) -> DiagnosisMetrics:
    expected = _expected_findings(truth)
    predicted = {(finding.kind, finding.ref) for finding in artifacts.diagnosis}
    correct = len(expected & predicted)
    union = len(expected | predicted)
    precision = correct / len(predicted) if predicted else float(not expected)
    recall = correct / len(expected) if expected else float(not predicted)
    return DiagnosisMetrics(
        accuracy=correct / union if union else 1.0,
        precision=precision,
        recall=recall,
        expectedFindings=len(expected),
        predictedFindings=len(predicted),
    )


def resurrection_metrics(artifacts: AnalysisArtifacts, truth: LoadedTruth) -> ResurrectionMetrics:
    key = truth_repair_key(truth)
    if key is None:
        return ResurrectionMetrics(
            applicable=False, top1Correct=None, top3Correct=None, tieSetCorrect=None
        )
    ranked = sorted(artifacts.resurrection, key=lambda candidate: candidate.rank)
    top_one = bool(ranked and ranked[0].repair_key == key)
    top_three = any(candidate.repair_key == key for candidate in ranked[:3])
    if not ranked:
        tie_correct = False
    elif ranked[0].tie_group is None:
        tie_correct = top_one
    else:
        tie_correct = any(
            candidate.tie_group == ranked[0].tie_group and candidate.repair_key == key
            for candidate in ranked
        )
    return ResurrectionMetrics(
        applicable=True, top1Correct=top_one, top3Correct=top_three, tieSetCorrect=tie_correct
    )


def truth_repair_key(truth: LoadedTruth) -> str | None:
    raw_breakage = truth.manifest.get("breakage")
    if not isinstance(raw_breakage, dict):
        return None
    breakage = cast(Json, raw_breakage)
    bodies = cast(list[Json], breakage.get("removedBodies", []))
    ids = sorted(str(body["id"]) for body in bodies)
    return f"{breakage['kind']}:{','.join(ids)}"


def _true_joints(truth: LoadedTruth) -> list[tuple[str, frozenset[str], str, float, float]]:
    first = min(frame.frame_index for frame in truth.frames)
    points = {
        (point.body_id, point.point_id): point
        for point in truth.points
        if point.frame_index == first
    }
    result: list[tuple[str, frozenset[str], str, float, float]] = []
    for joint in cast(list[Json], truth.graph["joints"]):
        refs: list[Json] = []
        for key in ("anchorA", "anchorB", "pin", "followerPoint"):
            value = joint.get(key)
            if isinstance(value, dict):
                refs.append(cast(Json, value))
        locations = [points.get((str(ref["bodyId"]), str(ref["pointId"]))) for ref in refs]
        available = [point for point in locations if point is not None]
        if not available:
            continue
        result.append(
            (
                str(joint["id"]),
                frozenset((str(joint["bodyA"]), str(joint["bodyB"]))),
                str(joint["kind"]),
                sum(point.x_px for point in available) / len(available),
                sum(point.y_px for point in available) / len(available),
            )
        )
    return result


def _truth_mobility(truth: LoadedTruth) -> int:
    solver = Solver(json.dumps(truth.graph))
    first = truth.frames[0]
    driver_order = [str(driver["id"]) for driver in cast(list[Json], truth.graph["drivers"])]
    drive = np.asarray([first.drivers[driver_id] for driver_id in driver_order])
    state = solver.assemble(drive)
    return int(solver.mobility(state, drive).numerical)


def _true_lengths(truth: LoadedTruth) -> dict[str, float]:
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


def _length_error(
    artifacts: AnalysisArtifacts, truth: LoadedTruth, body_map: dict[str, str]
) -> float | None:
    actual = _true_lengths(truth)
    pairs = [
        (body.link_length_world, actual.get(body_map.get(body.body_id, "")))
        for body in artifacts.bodies
        if body.link_length_world is not None
    ]
    available = [(predicted, target) for predicted, target in pairs if target is not None]
    if not available:
        return None
    scale = float(np.median([target / predicted for predicted, target in available]))
    return float(
        np.mean([abs(scale * predicted - target) / target for predicted, target in available])
    )


def _pose_errors(
    artifacts: AnalysisArtifacts, truth: LoadedTruth, body_map: dict[str, str]
) -> tuple[float | None, float | None]:
    actual = {
        (frame.frame_index, pose.body_id): pose for frame in truth.frames for pose in frame.poses
    }
    paired = [
        (pose, actual[(pose.frame_index, body_map[body.body_id])])
        for body in artifacts.bodies
        if body.body_id in body_map
        for pose in body.poses
        if (pose.frame_index, body_map[body.body_id]) in actual
    ]
    if not paired:
        return None, None
    source = np.asarray([[pose.x_world, pose.y_world] for pose, _ in paired])
    target = np.asarray(
        [[truth_pose.translation[0], truth_pose.translation[1]] for _, truth_pose in paired]
    )
    scale, rotation, translation = _similarity(source, target)
    aligned = scale * (source @ rotation.T) + translation
    translation_rmse = math.sqrt(float(np.mean(np.sum((aligned - target) ** 2, axis=1))))
    offset = math.atan2(rotation[1, 0], rotation[0, 0])
    angle_errors: list[float] = []
    for pose, truth_pose in paired:
        x, y, z, w = truth_pose.quaternion_xyzw
        truth_angle = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        angle_errors.append(_angle_delta(pose.angle_radians + offset, truth_angle))
    return translation_rmse, math.sqrt(float(np.mean(np.square(angle_errors))))


def _similarity(
    source: npt.NDArray[np.float64], target: npt.NDArray[np.float64]
) -> tuple[float, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    source_mean, target_mean = np.mean(source, axis=0), np.mean(target, axis=0)
    centered_source, centered_target = source - source_mean, target - target_mean
    variance = float(np.mean(np.sum(centered_source**2, axis=1)))
    if variance <= MIN_ALIGNMENT_VARIANCE:
        rotation = np.eye(2)
        scale = 1.0
    else:
        covariance = centered_target.T @ centered_source / len(source)
        left, singular, right = np.linalg.svd(covariance)
        correction = np.diag([1.0, np.sign(np.linalg.det(left @ right))])
        rotation = left @ correction @ right
        scale = float(np.sum(singular * np.diag(correction)) / variance)
    return scale, rotation, target_mean - scale * (rotation @ source_mean)


def _angle_delta(left: float, right: float) -> float:
    return math.atan2(math.sin(left - right), math.cos(left - right))


def _expected_findings(truth: LoadedTruth) -> set[tuple[str, str]]:
    raw_breakage = truth.manifest.get("breakage")
    if not isinstance(raw_breakage, dict):
        return set()
    breakage = cast(Json, raw_breakage)
    expected = {
        ("missing_body", f"body:{body['id']}")
        for body in cast(list[Json], breakage.get("removedBodies", []))
    }
    expected.update(
        ("missing_joint", f"joint:{joint['id']}")
        for joint in cast(list[Json], breakage.get("removedJoints", []))
    )
    expected.update(
        ("empty_hole", f"hole:{hole['bodyId']}/{hole['pointId']}")
        for hole in cast(list[Json], breakage.get("holes", []))
    )
    return expected


__all__ = [
    "calibration_metrics",
    "diagnosis_metrics",
    "joint_metrics",
    "model_metrics",
    "resurrection_metrics",
    "truth_repair_key",
]

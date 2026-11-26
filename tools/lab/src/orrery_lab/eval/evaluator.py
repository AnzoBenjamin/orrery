"""Score one real engine artifact bundle against one synthetic truth export."""

from __future__ import annotations

from pathlib import Path

from orrery_lab.eval.matching import body_alignment, match_tracks
from orrery_lab.eval.model import (
    calibration_metrics,
    diagnosis_metrics,
    joint_metrics,
    model_metrics,
    resurrection_metrics,
)
from orrery_lab.eval.tracking import camera_metrics, grouping_metrics, tracking_metrics
from orrery_lab.eval.truth import LoadedTruth, load_truth
from orrery_lab.eval.types import AnalysisArtifacts, EvaluationReport

DEFAULT_TRACK_GATE_PX = 24.0
DEFAULT_JOINT_TOLERANCE_PX = 8.0


def evaluate(
    truth: LoadedTruth,
    artifacts: AnalysisArtifacts,
    *,
    track_gate_px: float = DEFAULT_TRACK_GATE_PX,
    joint_tolerance_px: float = DEFAULT_JOINT_TOLERANCE_PX,
) -> EvaluationReport:
    """Evaluate artifacts without passing any truth fields into the engine side."""
    if track_gate_px <= 0 or joint_tolerance_px <= 0:
        raise ValueError("matching tolerances must be positive")
    matches = match_tracks(artifacts.tracks, truth, gate_px=track_gate_px)
    body_map = body_alignment(artifacts.tracks, matches)
    manifest = truth.manifest
    return EvaluationReport(
        clipId=truth.clip_id,
        labVersion=str(manifest["labVersion"]),
        engineVersion=artifacts.engine_version,
        truthSchemaVersion=int(manifest["schemaVersion"]),
        artifactSchemaVersion=artifacts.schema_version,
        matchingPolicy={
            "time": "encoded frame_index exact",
            "tracks": "global Hungarian; median all-frame endpoint distance",
            "trackGatePx": track_gate_px,
            "camera": "reference-to-frame homography; RMS at four image corners and center",
            "bodies": "one-to-one Hungarian over matched-track contingency",
            "grouping": "adjusted Rand index over globally matched tracks",
            "joints": "mapped unordered body pair then global Hungarian location",
            "jointTolerancePx": joint_tolerance_px,
            "mobility": "exact integer equality",
            "geometry": "median-ratio positive similarity scale",
            "pose": "proper 2D Umeyama similarity over matched body/frame origins",
            "uncertainty": "manifest params by exact ID; inclusive Gaussian 1σ and 2σ",
            "diagnosis": "exact (kind, canonical ref); accuracy is intersection over union",
            "resurrection": (
                "breakage kind plus sorted removed body IDs; first rank/top 3/leader tie group"
            ),
        },
        units={
            "tracking": "pixels",
            "cameraMotion": "pixels",
            "jointLocation": "pixels",
            "mobilityAccuracy": "exact-match fraction",
            "linkLength": "dimensionless relative error after scale alignment",
            "poseTranslation": "mechanism graph world units after similarity alignment",
            "poseRotation": "radians",
            "uncertaintyCalibration": "coverage and absolute target deviation fractions",
            "diagnosisAccuracy": "set fraction",
            "resurrectionCorrectness": "boolean",
            "runtime": "milliseconds wall clock",
        },
        tracking=tracking_metrics(artifacts, truth, matches),
        camera=camera_metrics(artifacts, truth),
        grouping=grouping_metrics(artifacts, matches),
        joints=joint_metrics(artifacts, truth, body_map, tolerance_px=joint_tolerance_px),
        model=model_metrics(artifacts, truth, body_map),
        calibration=calibration_metrics(artifacts, truth),
        diagnosis=diagnosis_metrics(artifacts, truth),
        resurrection=resurrection_metrics(artifacts, truth),
        stageRuntimesMs={item.stage: item.runtime_ms for item in artifacts.stage_runtimes},
    )


def evaluate_paths(truth_directory: Path, artifact_json: Path) -> EvaluationReport:
    truth = load_truth(truth_directory)
    artifacts = AnalysisArtifacts.model_validate_json(artifact_json.read_bytes())
    return evaluate(truth, artifacts)


__all__ = [
    "DEFAULT_JOINT_TOLERANCE_PX",
    "DEFAULT_TRACK_GATE_PX",
    "evaluate",
    "evaluate_paths",
]

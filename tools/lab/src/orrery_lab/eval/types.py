"""Strict versioned engine artifacts and per-clip evaluation reports."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ARTIFACT_FORMAT = "orrery.engine.analysis-artifacts"
ARTIFACT_VERSION = 1
REPORT_FORMAT = "orrery.synthetic.evaluation"
REPORT_VERSION = 1
HOMOGRAPHY_VALUE_COUNT = 9


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class TrackSample(_Model):
    frame_index: Annotated[int, Field(alias="frameIndex", ge=0)]
    x_px: float = Field(alias="xPx")
    y_px: float = Field(alias="yPx")
    visible: bool
    uncertainty_px: Annotated[float | None, Field(alias="uncertaintyPx", gt=0)] = None


class TrackArtifact(_Model):
    track_id: Annotated[str, Field(alias="trackId", min_length=1)]
    body_id: Annotated[str, Field(alias="bodyId", min_length=1)]
    samples: tuple[TrackSample, ...]

    @model_validator(mode="after")
    def unique_frames(self) -> Self:
        frames = [sample.frame_index for sample in self.samples]
        if len(frames) != len(set(frames)):
            raise ValueError("track samples must have unique frame indices")
        return self


class CameraMotionArtifact(_Model):
    frame_index: Annotated[int, Field(alias="frameIndex", ge=0)]
    reference_to_frame: Annotated[tuple[float, ...], Field(alias="referenceToFrame")]

    @model_validator(mode="after")
    def homography_shape(self) -> Self:
        if len(self.reference_to_frame) != HOMOGRAPHY_VALUE_COUNT:
            raise ValueError("camera homography must have 9 row-major values")
        if not all(math.isfinite(value) for value in self.reference_to_frame):
            raise ValueError("camera homography values must be finite")
        return self


class BodyPoseArtifact(_Model):
    frame_index: Annotated[int, Field(alias="frameIndex", ge=0)]
    x_world: float = Field(alias="xWorld")
    y_world: float = Field(alias="yWorld")
    angle_radians: float = Field(alias="angleRadians")


class BodyArtifact(_Model):
    body_id: Annotated[str, Field(alias="bodyId", min_length=1)]
    link_length_world: Annotated[float | None, Field(alias="linkLengthWorld", gt=0)] = None
    poses: tuple[BodyPoseArtifact, ...] = ()


class JointArtifact(_Model):
    joint_id: Annotated[str, Field(alias="jointId", min_length=1)]
    body_a: Annotated[str, Field(alias="bodyA", min_length=1)]
    body_b: Annotated[str, Field(alias="bodyB", min_length=1)]
    kind: Annotated[str, Field(min_length=1)]
    x_px: float = Field(alias="xPx")
    y_px: float = Field(alias="yPx")


class ParameterEstimate(_Model):
    parameter_id: Annotated[str, Field(alias="parameterId", min_length=1)]
    estimate: float
    standard_deviation: Annotated[float, Field(alias="standardDeviation", ge=0)]


class DiagnosisFinding(_Model):
    kind: Literal["loose_body", "frozen_body", "empty_hole", "missing_joint", "missing_body"]
    ref: Annotated[str, Field(min_length=1)]


class ResurrectionCandidate(_Model):
    repair_key: Annotated[str, Field(alias="repairKey", min_length=1)]
    rank: Annotated[int, Field(ge=1)]
    tie_group: Annotated[str | None, Field(alias="tieGroup", min_length=1)] = None


class StageRuntime(_Model):
    stage: Annotated[str, Field(min_length=1)]
    runtime_ms: Annotated[float, Field(alias="runtimeMs", ge=0)]


class AnalysisArtifacts(_Model):
    """Ground-truth-free outputs downloaded from one completed engine job."""

    format: Literal["orrery.engine.analysis-artifacts"] = ARTIFACT_FORMAT
    schema_version: Literal[1] = Field(default=ARTIFACT_VERSION, alias="schemaVersion")
    engine_version: Annotated[str, Field(alias="engineVersion", min_length=1)]
    tracks: tuple[TrackArtifact, ...] = ()
    camera_motion: tuple[CameraMotionArtifact, ...] = Field(default=(), alias="cameraMotion")
    bodies: tuple[BodyArtifact, ...] = ()
    joints: tuple[JointArtifact, ...] = ()
    mobility: int | None = None
    parameters: tuple[ParameterEstimate, ...] = ()
    diagnosis: tuple[DiagnosisFinding, ...] = ()
    resurrection: tuple[ResurrectionCandidate, ...] = ()
    stage_runtimes: tuple[StageRuntime, ...] = Field(default=(), alias="stageRuntimes")

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        for label, values in (
            ("track", [item.track_id for item in self.tracks]),
            ("body", [item.body_id for item in self.bodies]),
            ("joint", [item.joint_id for item in self.joints]),
            ("parameter", [item.parameter_id for item in self.parameters]),
            ("stage", [item.stage for item in self.stage_runtimes]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} identifiers must be unique")
        ranks = [item.rank for item in self.resurrection]
        if len(ranks) != len(set(ranks)):
            raise ValueError("resurrection ranks must be unique")
        return self


class TrackingMetrics(_Model):
    endpoint_median_px: float | None = Field(alias="endpointMedianPx")
    endpoint_p90_px: float | None = Field(alias="endpointP90Px")
    occlusion_accuracy: float | None = Field(alias="occlusionAccuracy")
    matched_tracks: int = Field(alias="matchedTracks", ge=0)
    predicted_tracks: int = Field(alias="predictedTracks", ge=0)
    truth_points: int = Field(alias="truthPoints", ge=0)


class CameraMetrics(_Model):
    motion_rmse_px: float | None = Field(alias="motionRmsePx")
    compared_frames: int = Field(alias="comparedFrames", ge=0)


class GroupingMetrics(_Model):
    adjusted_rand_index: float | None = Field(alias="adjustedRandIndex")
    compared_tracks: int = Field(alias="comparedTracks", ge=0)


class JointMetrics(_Model):
    precision: float
    recall: float
    f1: float
    type_accuracy: float | None = Field(alias="typeAccuracy")
    matched: int = Field(ge=0)
    predicted: int = Field(ge=0)
    truth: int = Field(ge=0)


class ModelMetrics(_Model):
    mobility_accuracy: float | None = Field(alias="mobilityAccuracy")
    link_length_mean_relative_error: float | None = Field(alias="linkLengthMeanRelativeError")
    pose_translation_rmse_world_units: float | None = Field(alias="poseTranslationRmseWorldUnits")
    pose_rotation_rmse_radians: float | None = Field(alias="poseRotationRmseRadians")


class CalibrationMetrics(_Model):
    one_sigma_coverage: float | None = Field(alias="oneSigmaCoverage")
    two_sigma_coverage: float | None = Field(alias="twoSigmaCoverage")
    one_sigma_calibration_error: float | None = Field(alias="oneSigmaCalibrationError")
    two_sigma_calibration_error: float | None = Field(alias="twoSigmaCalibrationError")
    parameter_count: int = Field(alias="parameterCount", ge=0)


class DiagnosisMetrics(_Model):
    accuracy: float
    precision: float
    recall: float
    expected_findings: int = Field(alias="expectedFindings", ge=0)
    predicted_findings: int = Field(alias="predictedFindings", ge=0)


class ResurrectionMetrics(_Model):
    applicable: bool
    top_1_correct: bool | None = Field(alias="top1Correct")
    top_3_correct: bool | None = Field(alias="top3Correct")
    tie_set_correct: bool | None = Field(alias="tieSetCorrect")


class EvaluationReport(_Model):
    """Task 7.1's per-clip report; suite breakdown/report schema belongs to task 7.2."""

    format: Literal["orrery.synthetic.evaluation"] = REPORT_FORMAT
    schema_version: Literal[1] = Field(default=REPORT_VERSION, alias="schemaVersion")
    clip_id: str = Field(alias="clipId", min_length=1)
    lab_version: str = Field(alias="labVersion", min_length=1)
    engine_version: str = Field(alias="engineVersion", min_length=1)
    truth_schema_version: int = Field(alias="truthSchemaVersion", ge=1)
    artifact_schema_version: int = Field(alias="artifactSchemaVersion", ge=1)
    matching_policy: dict[str, object] = Field(alias="matchingPolicy")
    units: dict[str, str]
    tracking: TrackingMetrics
    camera: CameraMetrics
    grouping: GroupingMetrics
    joints: JointMetrics
    model: ModelMetrics
    calibration: CalibrationMetrics
    diagnosis: DiagnosisMetrics
    resurrection: ResurrectionMetrics
    stage_runtimes_ms: dict[str, float] = Field(alias="stageRuntimesMs")


__all__ = [
    "ARTIFACT_FORMAT",
    "ARTIFACT_VERSION",
    "REPORT_FORMAT",
    "REPORT_VERSION",
    "AnalysisArtifacts",
    "BodyArtifact",
    "BodyPoseArtifact",
    "CalibrationMetrics",
    "CameraMetrics",
    "CameraMotionArtifact",
    "DiagnosisFinding",
    "DiagnosisMetrics",
    "EvaluationReport",
    "GroupingMetrics",
    "JointArtifact",
    "JointMetrics",
    "ModelMetrics",
    "ParameterEstimate",
    "ResurrectionCandidate",
    "ResurrectionMetrics",
    "StageRuntime",
    "TrackArtifact",
    "TrackSample",
    "TrackingMetrics",
]

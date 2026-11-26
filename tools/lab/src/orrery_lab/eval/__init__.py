"""Production synthetic-lab evaluation against versioned engine artifacts."""

from orrery_lab.eval.api import EngineJobClient, JobApiUnavailableError, ProbeResult
from orrery_lab.eval.evaluator import evaluate, evaluate_paths
from orrery_lab.eval.truth import LoadedTruth, load_truth
from orrery_lab.eval.types import (
    AnalysisArtifacts,
    BodyArtifact,
    BodyPoseArtifact,
    CameraMotionArtifact,
    DiagnosisFinding,
    EvaluationReport,
    JointArtifact,
    ParameterEstimate,
    ResurrectionCandidate,
    StageRuntime,
    TrackArtifact,
    TrackSample,
)

__all__ = [
    "AnalysisArtifacts",
    "BodyArtifact",
    "BodyPoseArtifact",
    "CameraMotionArtifact",
    "DiagnosisFinding",
    "EngineJobClient",
    "EvaluationReport",
    "JobApiUnavailableError",
    "JointArtifact",
    "LoadedTruth",
    "ParameterEstimate",
    "ProbeResult",
    "ResurrectionCandidate",
    "StageRuntime",
    "TrackArtifact",
    "TrackSample",
    "evaluate",
    "evaluate_paths",
    "load_truth",
]

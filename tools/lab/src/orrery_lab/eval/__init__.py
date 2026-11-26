"""Production synthetic-lab evaluation against versioned engine artifacts."""

from orrery_lab.eval.api import (
    ArtifactGrant,
    ArtifactIntegrityError,
    EngineJobClient,
    EngineJobError,
    ProbeResult,
    ReconstructionUnavailableError,
)
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
    "ArtifactGrant",
    "ArtifactIntegrityError",
    "BodyArtifact",
    "BodyPoseArtifact",
    "CameraMotionArtifact",
    "DiagnosisFinding",
    "EngineJobClient",
    "EngineJobError",
    "EvaluationReport",
    "JointArtifact",
    "LoadedTruth",
    "ParameterEstimate",
    "ProbeResult",
    "ReconstructionUnavailableError",
    "ResurrectionCandidate",
    "StageRuntime",
    "TrackArtifact",
    "TrackSample",
    "evaluate",
    "evaluate_paths",
    "load_truth",
]

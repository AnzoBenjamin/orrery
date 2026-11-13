"""Orrery's mechanism solver: the Rust solver the browser runs, with NumPy arrays.

`Solver` wraps one mechanism graph (JSON text); `fit` fits geometry, drivers, and camera to
observations. Coordinates are SI (meters, radians) in the world frame unless a name says otherwise.
Failures raise subclasses of `SolverError`.
"""

from orrery_kinematics._native import (
    AssemblyFailedError,
    BodyMotion,
    Collision,
    DriverCountError,
    FitDivergedError,
    FitResult,
    FourBarLoop,
    GrashofClass,
    InvalidGraphError,
    JointResidual,
    Mobility,
    Plausibility,
    ReactionReversal,
    Redundant,
    SeedLengthError,
    Simulation,
    Singularity,
    SingularityKind,
    Solver,
    SolverError,
    Transmission,
    ValidationIssue,
    fit,
)

__all__ = [
    "AssemblyFailedError",
    "BodyMotion",
    "Collision",
    "DriverCountError",
    "FitDivergedError",
    "FitResult",
    "FourBarLoop",
    "GrashofClass",
    "InvalidGraphError",
    "JointResidual",
    "Mobility",
    "Plausibility",
    "ReactionReversal",
    "Redundant",
    "SeedLengthError",
    "Simulation",
    "Singularity",
    "SingularityKind",
    "Solver",
    "SolverError",
    "Transmission",
    "ValidationIssue",
    "fit",
]

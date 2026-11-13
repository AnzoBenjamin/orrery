//! Typed solver failures (mechanism-core design, "Error handling"). The bindings map each variant
//! to a typed error in TypeScript and Python.

use crate::validate::ValidationIssue;

/// One joint's remaining constraint error after a failed assembly.
#[derive(Debug, Clone, PartialEq)]
pub struct JointResidual {
    pub joint_id: String,
    /// Euclidean norm of the joint's residual rows, in meters or radians.
    pub residual: f64,
}

#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum SolverError {
    /// The graph breaks a schema rule, or describes something the solver cannot build.
    #[error("the mechanism graph is invalid: {}", describe(.0))]
    InvalidGraph(Vec<ValidationIssue>),
    /// No pose satisfies the constraints from the given seed. The joints are ordered from the
    /// largest remaining residual.
    #[error("the mechanism cannot be assembled; worst joints: {}", worst(.worst_joints))]
    AssemblyFailed { worst_joints: Vec<JointResidual> },
    /// The number of driver values does not match the mechanism's drivers.
    #[error("expected {expected} driver values, got {got}")]
    DriverCount { expected: usize, got: usize },
    /// The fit's cost became unbounded.
    #[error("the fit diverged at iteration {iteration} (cost {cost})")]
    FitDiverged { iteration: usize, cost: f64 },
    /// The seed does not have one pose per moving body.
    #[error("the seed has {got} coordinates; the mechanism has {expected}")]
    SeedLength { expected: usize, got: usize },
}

fn describe(issues: &[ValidationIssue]) -> String {
    issues
        .iter()
        .map(|i| format!("{} ({})", i.message, i.path))
        .collect::<Vec<_>>()
        .join("; ")
}

fn worst(joints: &[JointResidual]) -> String {
    joints
        .iter()
        .map(|j| format!("{} ({:.3e})", j.joint_id, j.residual))
        .collect::<Vec<_>>()
        .join(", ")
}

impl SolverError {
    pub(crate) fn invalid(path: impl Into<String>, message: impl Into<String>) -> Self {
        Self::InvalidGraph(vec![ValidationIssue {
            path: path.into(),
            message: message.into(),
        }])
    }
}

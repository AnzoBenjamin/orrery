//! `kinematics::SolverError` as a Python exception hierarchy: a `SolverError` base carrying the
//! same `kind` as the TypeScript client sees, and one subclass per variant with its fields.

use kinematics::SolverError as Failure;
use kinematics::validate::ValidationIssue as Issue;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::pyclass_init::PyClassInitializer;
use pyo3_stub_gen::derive::{gen_stub_pyclass, gen_stub_pymethods};

/// A solver failure. `kind` is the variant name the TypeScript client also sees
/// (`invalidGraph`, `assemblyFailed`, `driverCount`, `seedLength`, `fitDiverged`); each variant
/// is also a subclass with its fields.
#[gen_stub_pyclass]
#[pyclass(extends = PyException, subclass, frozen, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct SolverError {
    #[pyo3(get)]
    kind: String,
    message: String,
}

#[gen_stub_pymethods]
#[pymethods]
impl SolverError {
    fn __str__(&self) -> String {
        self.message.clone()
    }
}

/// One broken schema rule.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct ValidationIssue {
    /// Where in the document, such as `joints[1].anchorB` (empty when the document did not parse).
    path: String,
    message: String,
}

/// The graph breaks a schema rule, or describes something the solver cannot build.
#[gen_stub_pyclass]
#[pyclass(extends = SolverError, frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct InvalidGraphError {
    issues: Vec<ValidationIssue>,
}

/// One joint's remaining constraint error after a failed assembly.
#[gen_stub_pyclass]
#[pyclass(frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug, Clone)]
pub struct JointResidual {
    joint_id: String,
    /// Norm of the joint's residual rows, in meters or radians.
    residual: f64,
}

/// No pose satisfies the constraints from the given seed.
#[gen_stub_pyclass]
#[pyclass(extends = SolverError, frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct AssemblyFailedError {
    /// Ordered from the largest remaining residual.
    worst_joints: Vec<JointResidual>,
}

/// The number of driver values does not match the mechanism's drivers.
#[gen_stub_pyclass]
#[pyclass(extends = SolverError, frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct DriverCountError {
    expected: usize,
    got: usize,
}

/// A state or seed does not have the mechanism's state size.
#[gen_stub_pyclass]
#[pyclass(extends = SolverError, frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct SeedLengthError {
    expected: usize,
    got: usize,
}

/// The fit's cost became unbounded.
#[gen_stub_pyclass]
#[pyclass(extends = SolverError, frozen, get_all, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct FitDivergedError {
    iteration: usize,
    cost: f64,
}

/// The `kind` tag of the variant, as serialized for the TypeScript client.
fn kind(failure: &Failure) -> String {
    serde_json::to_value(failure)
        .ok()
        .and_then(|v| v.get("kind").and_then(|k| k.as_str()).map(str::to_owned))
        .unwrap_or_default()
}

fn issue(i: &Issue) -> ValidationIssue {
    ValidationIssue {
        path: i.path.clone(),
        message: i.message.clone(),
    }
}

/// The Python exception for a solver failure.
pub fn to_py(py: Python<'_>, failure: &Failure) -> PyErr {
    let base = PyClassInitializer::from(SolverError {
        kind: kind(failure),
        message: failure.to_string(),
    });
    let raised = match failure {
        Failure::InvalidGraph(issues) => Bound::new(
            py,
            base.add_subclass(InvalidGraphError {
                issues: issues.iter().map(issue).collect(),
            }),
        )
        .map(Bound::into_any),
        Failure::AssemblyFailed { worst_joints } => Bound::new(
            py,
            base.add_subclass(AssemblyFailedError {
                worst_joints: worst_joints
                    .iter()
                    .map(|j| JointResidual {
                        joint_id: j.joint_id.clone(),
                        residual: j.residual,
                    })
                    .collect(),
            }),
        )
        .map(Bound::into_any),
        Failure::DriverCount { expected, got } => Bound::new(
            py,
            base.add_subclass(DriverCountError {
                expected: *expected,
                got: *got,
            }),
        )
        .map(Bound::into_any),
        Failure::SeedLength { expected, got } => Bound::new(
            py,
            base.add_subclass(SeedLengthError {
                expected: *expected,
                got: *got,
            }),
        )
        .map(Bound::into_any),
        Failure::FitDiverged { iteration, cost } => Bound::new(
            py,
            base.add_subclass(FitDivergedError {
                iteration: *iteration,
                cost: *cost,
            }),
        )
        .map(Bound::into_any),
    };
    match raised {
        Ok(exception) => PyErr::from_value(exception),
        Err(e) => e,
    }
}

/// A document that does not parse, reported like any other invalid graph.
pub fn unparsable(py: Python<'_>, message: String) -> PyErr {
    to_py(
        py,
        &Failure::InvalidGraph(vec![Issue {
            path: String::new(),
            message,
        }]),
    )
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SolverError>()?;
    m.add_class::<ValidationIssue>()?;
    m.add_class::<InvalidGraphError>()?;
    m.add_class::<JointResidual>()?;
    m.add_class::<AssemblyFailedError>()?;
    m.add_class::<DriverCountError>()?;
    m.add_class::<SeedLengthError>()?;
    m.add_class::<FitDivergedError>()?;
    Ok(())
}

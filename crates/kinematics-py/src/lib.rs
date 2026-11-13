//! Python bindings of the mechanism solver (mechanism-core requirement 10, design "Python"),
//! imported as `orrery_kinematics`. The API mirrors the WebAssembly bindings: one `Solver` per
//! mechanism graph, and `fit` for a fit problem.
//!
//! NumPy arrays: results take ownership of the solver's buffers, so nothing is copied on the way
//! out. Inputs (driver values, seeds, states) are a few numbers each; they are copied into Rust
//! before the GIL is released, because Python code on another thread could write to an array the
//! solver is still reading.
//!
//! Solving, simulating, and fitting run with the GIL released (`Python::detach`).

mod errors;
mod results;

use kinematics::fit::{FitProblem, fit as run_fit};
use kinematics::schema::parse_mechanism;
use kinematics::simulate::SimulationOptions;
use kinematics::{AssemblyOptions, Model, SolverError as Failure};
use numpy::{AllowTypeChange, PyArray1, PyArray2, PyArrayLike1};
use pyo3::prelude::*;
use pyo3_stub_gen::derive::{gen_stub_pyclass, gen_stub_pyfunction, gen_stub_pymethods};
use pyo3_stub_gen::{PyStubType, TypeInfo, define_stub_info_gatherer};
use results::{FitResult, Mobility, Plausibility, Simulation, matrix};

/// Driver values, a seed, or a state: any one-dimensional array or sequence of numbers, copied
/// into Rust when the call starts.
#[derive(Debug)]
struct Numbers(Vec<f64>);

impl<'a, 'py> FromPyObject<'a, 'py> for Numbers {
    type Error = PyErr;

    fn extract(obj: Borrowed<'a, 'py, PyAny>) -> PyResult<Self> {
        let array: PyArrayLike1<'py, f64, AllowTypeChange> = obj.extract()?;
        Ok(Self(array.as_array().to_vec()))
    }
}

impl PyStubType for Numbers {
    fn type_output() -> TypeInfo {
        // `with_module` alone marks the type as defined in that module, and the generator then
        // qualifies it a second time; only its import is wanted.
        TypeInfo {
            source_module: None,
            ..TypeInfo::with_module("numpy.typing.ArrayLike", "numpy.typing".into())
        }
    }
}

/// The solver for one mechanism graph.
#[gen_stub_pyclass]
#[pyclass(frozen, module = "orrery_kinematics._native")]
#[derive(Debug)]
pub struct Solver {
    model: Model,
    /// Every named point, in the order point arrays use: `(body index, body id, point id)`.
    points: Vec<(usize, String, String)>,
}

impl Solver {
    fn check_state(&self, state: &[f64]) -> Result<(), Failure> {
        if state.len() == self.model.n_vars {
            Ok(())
        } else {
            Err(Failure::SeedLength {
                expected: self.model.n_vars,
                got: state.len(),
            })
        }
    }

    fn check_drive(&self, drive: &[f64]) -> Result<(), Failure> {
        if drive.len() == self.model.drivers.len() {
            Ok(())
        } else {
            Err(Failure::DriverCount {
                expected: self.model.drivers.len(),
                got: drive.len(),
            })
        }
    }

    /// World positions of every named point at `state`, as `x, y, z` triples.
    fn positions(&self, state: &[f64], out: &mut Vec<f64>) {
        for (b, _, p) in &self.points {
            out.extend(
                self.model
                    .point_world(*b, p, state)
                    .unwrap_or([f64::NAN; 3]),
            );
        }
    }

    fn sweep(
        &self,
        py: Python<'_>,
        driver: usize,
        drive: &[f64],
        (start, end, step): (f64, f64, f64),
        seed: Option<&[f64]>,
    ) -> PyResult<kinematics::simulate::Simulation> {
        py.detach(|| {
            self.model.simulate(
                driver,
                drive,
                (start, end, step),
                seed,
                &SimulationOptions::default(),
            )
        })
        .map_err(|e| errors::to_py(py, &e))
    }
}

#[gen_stub_pymethods]
#[pymethods]
impl Solver {
    /// Builds the solver from a mechanism graph document (JSON text).
    ///
    /// Raises `InvalidGraphError` when the document does not parse or breaks a schema rule.
    #[new]
    fn new(py: Python<'_>, graph_json: &str) -> PyResult<Self> {
        let mechanism =
            parse_mechanism(graph_json).map_err(|e| errors::unparsable(py, e.to_string()))?;
        let model = Model::new(&mechanism).map_err(|e| errors::to_py(py, &e))?;
        let mut points: Vec<(usize, String, String)> = model
            .bodies
            .iter()
            .enumerate()
            .flat_map(|(i, b)| b.points.keys().map(move |p| (i, b.id.clone(), p.clone())))
            .collect();
        points.sort_by(|a, b| (a.0, &a.2).cmp(&(b.0, &b.2)));
        Ok(Self { model, points })
    }

    /// Length of a state vector.
    #[getter]
    fn state_size(&self) -> usize {
        self.model.n_vars
    }

    /// Number of drivers, in graph order.
    #[getter]
    fn driver_count(&self) -> usize {
        self.model.drivers.len()
    }

    /// `(body_id, point_id)` pairs, in the order of every point array.
    #[getter]
    fn point_names(&self) -> Vec<(String, String)> {
        self.points
            .iter()
            .map(|(_, b, p)| (b.clone(), p.clone()))
            .collect()
    }

    /// Assembles for the driver values, from `seed` when given (keeping its branch). Returns the
    /// state vector.
    #[pyo3(signature = (drive, seed = None))]
    fn assemble<'py>(
        &self,
        py: Python<'py>,
        drive: Numbers,
        seed: Option<Numbers>,
    ) -> PyResult<Bound<'py, PyArray1<f64>>> {
        let (drive, seed) = (drive.0, seed.map(|s| s.0));
        let assembly = py
            .detach(|| {
                self.model
                    .assemble(&drive, seed.as_deref(), &AssemblyOptions::default())
            })
            .map_err(|e| errors::to_py(py, &e))?;
        Ok(PyArray1::from_vec(py, assembly.q))
    }

    /// World positions of every named point at `state`, shape `(points, 3)`, in meters.
    fn point_positions(&self, py: Python<'_>, state: Numbers) -> PyResult<Py<PyArray2<f64>>> {
        let state = state.0;
        self.check_state(&state)
            .map_err(|e| errors::to_py(py, &e))?;
        let mut flat = Vec::with_capacity(self.points.len() * 3);
        self.positions(&state, &mut flat);
        matrix(py, flat, 3)
    }

    /// Sweeps driver `driver` from `start` to `end` by `step` (radians or meters), the other
    /// drivers held at `drive`, from `seed` when given.
    #[pyo3(signature = (driver, drive, start, end, step, seed = None))]
    #[allow(
        clippy::too_many_arguments,
        reason = "mirrors the keyword arguments of the Python method"
    )]
    fn simulate(
        &self,
        py: Python<'_>,
        driver: usize,
        drive: Numbers,
        start: f64,
        end: f64,
        step: f64,
        seed: Option<Numbers>,
    ) -> PyResult<Simulation> {
        let sim = self.sweep(
            py,
            driver,
            &drive.0,
            (start, end, step),
            seed.as_ref().map(|s| s.0.as_slice()),
        )?;
        let values: Vec<f64> = sim.samples.iter().map(|s| s.drive).collect();
        let states: Vec<f64> = sim
            .samples
            .iter()
            .flat_map(|s| s.q.iter().copied())
            .collect();
        let mut points = Vec::with_capacity(sim.samples.len() * self.points.len() * 3);
        for s in &sim.samples {
            self.positions(&s.q, &mut points);
        }
        Simulation::new(
            py,
            values,
            states,
            self.model.n_vars,
            (points, self.points.len()),
            sim.reachable,
            &sim.singularities,
        )
    }

    /// Grübler and numerical mobility, redundant joints, and free motions at `state`.
    fn mobility(&self, py: Python<'_>, state: Numbers, drive: Numbers) -> PyResult<Mobility> {
        let state = state.0;
        let drive = drive.0;
        self.check_state(&state)
            .and_then(|()| self.check_drive(&drive))
            .map_err(|e| errors::to_py(py, &e))?;
        Ok(py.detach(|| self.model.mobility(&state, &drive)).into())
    }

    /// Transmission angles, Grashof classes, collisions, slenderness, and reaction reversals
    /// over a sweep (arguments as for `simulate`).
    #[pyo3(signature = (driver, drive, start, end, step, seed = None))]
    #[allow(
        clippy::too_many_arguments,
        reason = "mirrors the keyword arguments of the Python method"
    )]
    fn plausibility(
        &self,
        py: Python<'_>,
        driver: usize,
        drive: Numbers,
        start: f64,
        end: f64,
        step: f64,
        seed: Option<Numbers>,
    ) -> PyResult<Plausibility> {
        let sim = self.sweep(
            py,
            driver,
            &drive.0,
            (start, end, step),
            seed.as_ref().map(|s| s.0.as_slice()),
        )?;
        Ok(py
            .detach(|| self.model.plausibility(&sim, driver, &drive.0))
            .into())
    }
}

/// Fits geometry, driver values, and camera parameters to observations (a fit problem as JSON
/// text, in the shape the TypeScript client sends).
///
/// Raises `InvalidGraphError` when the problem does not parse, and `FitDivergedError` when the
/// cost becomes unbounded.
#[gen_stub_pyfunction(module = "orrery_kinematics._native")]
#[pyfunction]
fn fit(py: Python<'_>, problem_json: &str) -> PyResult<FitResult> {
    let problem: FitProblem =
        serde_json::from_str(problem_json).map_err(|e| errors::unparsable(py, e.to_string()))?;
    let fitted = py
        .detach(|| run_fit(&problem))
        .map_err(|e| errors::to_py(py, &e))?;
    FitResult::new(py, fitted)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Solver>()?;
    m.add_function(wrap_pyfunction!(fit, m)?)?;
    errors::register(m)?;
    results::register(m)?;
    Ok(())
}

define_stub_info_gatherer!(stub_info);

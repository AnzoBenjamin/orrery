//! WebAssembly bindings of the mechanism solver (mechanism-core requirement 9, design
//! "WebAssembly"). One `Solver` per open mechanism lives in the browser's solver worker; state
//! vectors and trajectories cross as `Float64Array`s so the worker can transfer them.
//!
//! Errors are thrown as plain objects with a `kind` (`invalidGraph`, `assemblyFailed`, ...) and
//! the fields of `kinematics::SolverError`, so the TypeScript client can type them.

use js_sys::{Float64Array, Object, Reflect};
use kinematics::fit::{FitProblem, fit as run_fit};
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use kinematics::simulate::SimulationOptions;
use kinematics::validate::ValidationIssue;
use kinematics::{AssemblyOptions, SolverError};
use serde::Serialize;
use wasm_bindgen::prelude::*;

fn to_js<T: Serialize + ?Sized>(value: &T) -> Result<JsValue, JsValue> {
    value
        .serialize(&serde_wasm_bindgen::Serializer::json_compatible())
        .map_err(|e| JsValue::from_str(&e.to_string()))
}

fn error(e: &SolverError) -> JsValue {
    to_js(e).unwrap_or_else(|v| v)
}

fn invalid(message: String) -> JsValue {
    error(&SolverError::InvalidGraph(vec![ValidationIssue {
        path: String::new(),
        message,
    }]))
}

fn set(target: &Object, key: &str, value: &JsValue) -> Result<(), JsValue> {
    Reflect::set(target, &JsValue::from_str(key), value).map(|_| ())
}

/// The solver for one mechanism graph.
#[wasm_bindgen]
#[derive(Debug)]
pub struct Solver {
    model: Model,
    /// Every named point, in the order point arrays use: `(body index, body id, point id)`.
    points: Vec<(usize, String, String)>,
}

#[wasm_bindgen]
impl Solver {
    /// Builds the solver from a mechanism graph document (JSON text).
    #[wasm_bindgen(constructor)]
    pub fn new(graph_json: &str) -> Result<Solver, JsValue> {
        let mechanism = parse_mechanism(graph_json).map_err(|e| invalid(e.to_string()))?;
        let model = Model::new(&mechanism).map_err(|e| error(&e))?;
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
    #[wasm_bindgen(js_name = stateSize)]
    pub fn state_size(&self) -> usize {
        self.model.n_vars
    }

    /// Number of drivers, in graph order.
    #[wasm_bindgen(js_name = driverCount)]
    pub fn driver_count(&self) -> usize {
        self.model.drivers.len()
    }

    /// `[bodyId, pointId]` pairs, in the order of every point array.
    #[wasm_bindgen(js_name = pointNames)]
    pub fn point_names(&self) -> Result<JsValue, JsValue> {
        let names: Vec<[&str; 2]> = self
            .points
            .iter()
            .map(|(_, b, p)| [b.as_str(), p.as_str()])
            .collect();
        to_js(&names)
    }

    /// Assembles for the driver values, from `seed` when given (keeping its branch).
    pub fn assemble(&self, drive: &[f64], seed: Option<Vec<f64>>) -> Result<Float64Array, JsValue> {
        let a = self
            .model
            .assemble(drive, seed.as_deref(), &AssemblyOptions::default())
            .map_err(|e| error(&e))?;
        Ok(Float64Array::from(a.q.as_slice()))
    }

    /// World positions of every named point at `state`, as `x, y, z` triples.
    #[wasm_bindgen(js_name = pointPositions)]
    pub fn point_positions(&self, state: &[f64]) -> Result<Float64Array, JsValue> {
        if state.len() != self.model.n_vars {
            return Err(error(&SolverError::SeedLength {
                expected: self.model.n_vars,
                got: state.len(),
            }));
        }
        let flat: Vec<f64> = self
            .points
            .iter()
            .flat_map(|(b, _, p)| {
                self.model
                    .point_world(*b, p, state)
                    .unwrap_or([f64::NAN; 3])
            })
            .collect();
        Ok(Float64Array::from(flat.as_slice()))
    }

    /// Sweeps driver `driver` from `start` to `end` by `step`. Returns `{ drive, states, points,
    /// reachable, singularities }`: `drive` per sample, `states` and `points` (point triples)
    /// flattened sample by sample.
    pub fn simulate(
        &self,
        driver: usize,
        drive: &[f64],
        start: f64,
        end: f64,
        step: f64,
        seed: Option<Vec<f64>>,
    ) -> Result<Object, JsValue> {
        let sim = self
            .model
            .simulate(
                driver,
                drive,
                (start, end, step),
                seed.as_deref(),
                &SimulationOptions::default(),
            )
            .map_err(|e| error(&e))?;
        let values: Vec<f64> = sim.samples.iter().map(|s| s.drive).collect();
        let states: Vec<f64> = sim
            .samples
            .iter()
            .flat_map(|s| s.q.iter().copied())
            .collect();
        let points: Vec<f64> = sim
            .samples
            .iter()
            .flat_map(|s| {
                self.points.iter().flat_map(|(b, _, p)| {
                    self.model.point_world(*b, p, &s.q).unwrap_or([f64::NAN; 3])
                })
            })
            .collect();
        let out = Object::new();
        set(&out, "drive", &Float64Array::from(values.as_slice()))?;
        set(&out, "states", &Float64Array::from(states.as_slice()))?;
        set(&out, "points", &Float64Array::from(points.as_slice()))?;
        set(&out, "reachable", &to_js(&sim.reachable)?)?;
        set(&out, "singularities", &to_js(&sim.singularities)?)?;
        Ok(out)
    }

    /// Grübler and numerical mobility, redundant joints, and free motions at `state`.
    pub fn mobility(&self, state: &[f64], drive: &[f64]) -> Result<JsValue, JsValue> {
        to_js(&self.model.mobility(state, drive))
    }

    /// Transmission angles, Grashof classes, collisions, and fabrication risk over a sweep.
    pub fn plausibility(
        &self,
        driver: usize,
        drive: &[f64],
        start: f64,
        end: f64,
        step: f64,
        seed: Option<Vec<f64>>,
    ) -> Result<JsValue, JsValue> {
        let sim = self
            .model
            .simulate(
                driver,
                drive,
                (start, end, step),
                seed.as_deref(),
                &SimulationOptions::default(),
            )
            .map_err(|e| error(&e))?;
        to_js(&self.model.plausibility(&sim, driver, drive))
    }
}

/// Fits geometry, driver values, and camera parameters (a `FitProblem` as JSON text).
#[wasm_bindgen]
pub fn fit(problem_json: &str) -> Result<JsValue, JsValue> {
    let problem: FitProblem =
        serde_json::from_str(problem_json).map_err(|e| invalid(e.to_string()))?;
    let result = run_fit(&problem).map_err(|e| error(&e))?;
    to_js(&result)
}

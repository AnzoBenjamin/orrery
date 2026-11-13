//! The fitter (mechanism-core requirement 7, design "Fitter"): geometry, per-frame driver
//! values, and optionally camera parameters from observed point tracks, with every frame's pose
//! assembled exactly.
//!
//! Unknowns split in two:
//! - global: the free geometry parameters `θ` (numbers in the graph, named by the same paths as
//!   the schema's `uncertainty` map, such as `bodies.coupler.points.c.local.x`) and any static
//!   camera parameters;
//! - per frame: the driver values `d_t` and any per-frame camera parameters `c_t`.
//!
//! Each frame's pose `q_t` is not an unknown: it is assembled from `(θ, d_t)`, so the joints hold
//! exactly (requirement 7.3), and its derivatives come from the implicit function theorem,
//! `dq/d(θ, d) = −Φ_q⁻¹ Φ_(θ, d)`. `Φ_θ` is a central difference on the graph with the parameter
//! nudged; derivatives in `q` and in the camera are exact (Jets).
//!
//! The Gauss–Newton system has the arrow structure of bundle adjustment: a small block per frame
//! and a dense global block. The frame blocks are eliminated by the Schur complement, the reduced
//! system is solved, and the frame steps follow (requirement 7.4). Robust losses enter through
//! iteratively reweighted least squares, and priors are extra residual rows.

use faer::linalg::solvers::{DenseSolveCore, Solve, SolveLstsqCore};
use faer::{Conj, Mat};
use serde_json::Value;

use crate::assembly::AssemblyOptions;
use crate::dual::{Jet, Scalar};
use crate::error::SolverError;
use crate::model::{Model, PlaneFrame};
use crate::schema::Mechanism;

/// The loss applied to each observation's residual length `r` (in the observation's units).
#[derive(serde::Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Loss {
    /// `r²/2`.
    Squared,
    /// Quadratic within `delta`, linear beyond.
    Huber { delta: f64 },
    /// `c²/2 · ln(1 + r²/c²)`: outliers lose influence altogether.
    Cauchy { c: f64 },
}

impl Loss {
    /// The IRLS weight for a residual of length `r`.
    fn weight(self, r: f64) -> f64 {
        match self {
            Self::Squared => 1.0,
            Self::Huber { delta } => {
                if r <= delta {
                    1.0
                } else {
                    delta / r
                }
            }
            Self::Cauchy { c } => 1.0 / (1.0 + (r / c).powi(2)),
        }
    }

    /// The loss of a residual of length `r`.
    fn rho(self, r: f64) -> f64 {
        match self {
            Self::Squared => 0.5 * r * r,
            Self::Huber { delta } => {
                if r <= delta {
                    0.5 * r * r
                } else {
                    delta * (r - 0.5 * delta)
                }
            }
            Self::Cauchy { c } => 0.5 * c * c * (r / c).powi(2).ln_1p(),
        }
    }
}

/// One geometry parameter to estimate or hold.
#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Parameter {
    /// A path into the graph, such as `bodies.crank.points.b.local.x` or `joints.mesh.phase`.
    pub path: String,
    /// Held at its value in the graph (requirement 7.6).
    #[serde(default)]
    pub fixed: bool,
    /// A Gaussian prior `(mean, standard deviation)` (requirement 7.6).
    #[serde(default)]
    pub prior: Option<(f64, f64)>,
}

/// One observed point in one frame.
#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Observation {
    pub frame: usize,
    pub body: String,
    pub point: String,
    /// Observed position in the observation frame.
    pub position: [f64; 2],
    /// Relative weight (inverse variance). Zero means not visible.
    pub weight: f64,
}

/// How observations relate to the mechanism (requirement 7.2).
#[derive(serde::Deserialize)]
#[serde(
    tag = "type",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
#[derive(Debug, Clone, PartialEq)]
pub enum Camera {
    /// Meters in the 2D coordinates of `plane:<id>`: a stabilized, scaled view.
    Plane { plane: String },
    /// Pixels, through a planar homography from `plane:<id>` coordinates (meters): `[u v 1]ᵀ ∝
    /// H [x y 1]ᵀ` with `H[2][2] = 1`. Static (one `H`) or one per frame for a moving camera.
    /// `initial` holds the eight free entries, row by row, of each `H`.
    Homography {
        plane: String,
        initial: Vec<[f64; 8]>,
    },
    /// Pixels, through a pinhole camera: `p = R(r) X + t` for a world point `X`, then
    /// `u = f p.x / p.z + cx`, `v = f p.y / p.z + cy`. The intrinsics `[f, cx, cy]` are shared,
    /// and held when `fixed_intrinsics` (a calibrated camera: a single view of a planar
    /// mechanism cannot tell focal length from distance). The poses `[r (rotation vector), t]`
    /// are one static pose or one per frame.
    Projection {
        intrinsics: [f64; 3],
        fixed_intrinsics: bool,
        poses: Vec<[f64; 6]>,
    },
}

impl Camera {
    /// Global camera parameters and per-frame camera parameters, by count.
    fn split(&self, frames: usize) -> (usize, usize) {
        match self {
            Self::Plane { .. } => (0, 0),
            Self::Homography { initial, .. } => {
                if initial.len() == 1 && frames != 1 {
                    (8, 0)
                } else {
                    (0, 8)
                }
            }
            Self::Projection {
                poses,
                fixed_intrinsics,
                ..
            } => {
                let k = if *fixed_intrinsics { 0 } else { 3 };
                if poses.len() == 1 && frames != 1 {
                    (k + 6, 0)
                } else {
                    (k, 6)
                }
            }
        }
    }

    /// Initial global and per-frame camera parameters.
    fn initial(&self, frames: usize) -> (Vec<f64>, Vec<Vec<f64>>) {
        let (global, _) = self.split(frames);
        match self {
            Self::Plane { .. } => (Vec::new(), vec![Vec::new(); frames]),
            Self::Homography { initial, .. } => {
                if global > 0 {
                    (initial[0].to_vec(), vec![Vec::new(); frames])
                } else {
                    (Vec::new(), initial.iter().map(|h| h.to_vec()).collect())
                }
            }
            Self::Projection {
                intrinsics,
                fixed_intrinsics,
                poses,
            } => {
                let mut g = if *fixed_intrinsics {
                    Vec::new()
                } else {
                    intrinsics.to_vec()
                };
                if poses.len() == 1 && frames != 1 {
                    g.extend(poses[0]);
                    (g, vec![Vec::new(); frames])
                } else {
                    (g, poses.iter().map(|p| p.to_vec()).collect())
                }
            }
        }
    }
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone)]
pub struct FitProblem {
    /// The topology with initial geometry.
    pub mechanism: Mechanism,
    pub parameters: Vec<Parameter>,
    /// Initial driver values, one vector per frame.
    pub drive: Vec<Vec<f64>>,
    /// Starting poses, one per frame, that pick the assembly branch (from tracked points). Without
    /// them each frame is seeded from the previous one, and the first from the drawn pose.
    #[serde(default)]
    pub seeds: Option<Vec<Vec<f64>>>,
    pub observations: Vec<Observation>,
    pub camera: Camera,
    pub loss: Loss,
    pub max_iterations: usize,
}

/// One observation's fitted residual.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct ObservationResidual {
    /// Index into the problem's observations.
    pub observation: usize,
    /// Fitted minus observed, in the observation frame.
    pub residual: [f64; 2],
    /// The robust weight it ended with (1 for an inlier).
    pub weight: f64,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone)]
pub struct FitResult {
    /// The graph with the fitted geometry written in, and standard deviations in `uncertainty`.
    pub mechanism: Mechanism,
    /// Fitted values of the parameters, in problem order (fixed ones unchanged).
    pub values: Vec<f64>,
    /// Standard deviations of the parameters (zero for fixed ones) (requirement 7.5).
    pub sigma: Vec<f64>,
    /// Fitted driver values, one vector per frame.
    pub drive: Vec<Vec<f64>>,
    /// Fitted global camera parameters (empty for a plane frame).
    pub camera_global: Vec<f64>,
    /// Fitted per-frame camera parameters.
    pub camera_frames: Vec<Vec<f64>>,
    /// Each frame's pose.
    pub poses: Vec<Vec<f64>>,
    pub residuals: Vec<ObservationResidual>,
    /// Root mean square of the observation residual lengths.
    pub rms: f64,
    /// Final robust cost.
    pub cost: f64,
    pub iterations: usize,
}

/// Walks `path` in a graph document: object keys, array indices, or array elements by `id`.
fn lookup<'a>(value: &'a mut Value, path: &str) -> Option<&'a mut Value> {
    let mut cur = value;
    for token in path.split('.') {
        cur = match cur {
            Value::Object(map) => map.get_mut(token)?,
            Value::Array(items) => {
                if let Ok(i) = token.parse::<usize>() {
                    items.get_mut(i)?
                } else {
                    items
                        .iter_mut()
                        .find(|v| v.get("id").and_then(Value::as_str) == Some(token))?
                }
            }
            _ => return None,
        };
    }
    Some(cur)
}

/// `R(r) v` for a rotation vector `r`, by Rodrigues' formula (with its small-angle limit).
fn rotate<T: Scalar>(r: [T; 3], v: [T; 3]) -> [T; 3] {
    let angle2 = r[0] * r[0] + r[1] * r[1] + r[2] * r[2];
    let cross = [
        r[1] * v[2] - r[2] * v[1],
        r[2] * v[0] - r[0] * v[2],
        r[0] * v[1] - r[1] * v[0],
    ];
    let dot = r[0] * v[0] + r[1] * v[1] + r[2] * v[2];
    let (a, b) = if angle2.value() < 1e-12 {
        (
            T::cst(1.0) - angle2 * (1.0 / 6.0),
            T::cst(0.5) - angle2 * (1.0 / 24.0),
        )
    } else {
        let angle = angle2.sqrt();
        (angle.sin() / angle, (T::cst(1.0) - angle.cos()) / angle2)
    };
    // v cos θ + (r × v) sin θ/θ + r (r·v)(1 − cos θ)/θ², with cos θ = 1 − θ² b.
    std::array::from_fn(|k| v[k] * (T::cst(1.0) - angle2 * b) + cross[k] * a + r[k] * dot * b)
}

/// Where a world point appears, given the camera parameters (global then per frame).
fn observe<T: Scalar>(
    camera: &Camera,
    plane: Option<&PlaneFrame>,
    global: &[T],
    local: &[T],
    w: [T; 3],
) -> [T; 2] {
    let in_plane = |f: &PlaneFrame| {
        let d: [T; 3] = std::array::from_fn(|k| w[k] - f.origin[k]);
        let along = |a: [f64; 3]| d[0] * a[0] + d[1] * a[1] + d[2] * a[2];
        (along(f.u), along(f.v))
    };
    match camera {
        Camera::Plane { .. } => {
            let (x, y) = plane.map_or((w[0], w[1]), in_plane);
            [x, y]
        }
        Camera::Homography { .. } => {
            let h = if global.is_empty() { local } else { global };
            let (x, y) = plane.map_or((w[0], w[1]), in_plane);
            let z = h[6] * x + h[7] * y + 1.0;
            [
                (h[0] * x + h[1] * y + h[2]) / z,
                (h[3] * x + h[4] * y + h[5]) / z,
            ]
        }
        Camera::Projection {
            intrinsics,
            fixed_intrinsics,
            ..
        } => {
            let (k, rest): ([T; 3], &[T]) = if *fixed_intrinsics {
                (intrinsics.map(T::cst), global)
            } else {
                ([global[0], global[1], global[2]], &global[3..])
            };
            let pose = if local.is_empty() { rest } else { local };
            let p = rotate([pose[0], pose[1], pose[2]], w);
            let p = [p[0] + pose[3], p[1] + pose[4], p[2] + pose[5]];
            [k[0] * p[0] / p[2] + k[1], k[0] * p[1] / p[2] + k[2]]
        }
    }
}

/// The fitter's view of the problem.
struct Setup<'a> {
    problem: &'a FitProblem,
    document: Value,
    /// Problem indices of the free parameters.
    free: Vec<usize>,
    plane: Option<PlaneFrame>,
    /// `(body index, point id)` of each observation.
    targets: Vec<(usize, String)>,
    frames: usize,
    n_drive: usize,
    /// Global camera parameter count, per-frame camera parameter count.
    n_cam: (usize, usize),
}

/// The state of the estimate.
#[derive(Clone)]
struct Estimate {
    theta: Vec<f64>,
    cam_global: Vec<f64>,
    drive: Vec<Vec<f64>>,
    cam_frames: Vec<Vec<f64>>,
    poses: Vec<Vec<f64>>,
}

impl Setup<'_> {
    fn model_at(&self, theta: &[f64]) -> Result<Model, SolverError> {
        let mut doc = self.document.clone();
        for (value, &p) in theta.iter().zip(&self.free) {
            let path = &self.problem.parameters[p].path;
            let slot = lookup(&mut doc, path).ok_or_else(|| {
                SolverError::invalid(
                    path.clone(),
                    format!("Parameter {path} names nothing in the graph"),
                )
            })?;
            *slot = Value::from(*value);
        }
        let mechanism: Mechanism = serde_json::from_value(doc).map_err(|e| {
            SolverError::invalid("parameters", format!("The fitted graph is not valid: {e}"))
        })?;
        Model::new(&mechanism)
    }

    /// Assembles every frame. Seeds from `seed` where given, else from the previous frame.
    fn assemble_all(
        &self,
        model: &Model,
        drive: &[Vec<f64>],
        seed: Option<&[Vec<f64>]>,
    ) -> Result<Vec<Vec<f64>>, SolverError> {
        let mut poses: Vec<Vec<f64>> = Vec::with_capacity(self.frames);
        for t in 0..self.frames {
            let start = seed
                .map(|s| s[t].as_slice())
                .or_else(|| poses.last().map(Vec::as_slice));
            let a = model
                .assemble(&drive[t], start, &AssemblyOptions::default())
                .or_else(|_| model.assemble(&drive[t], None, &AssemblyOptions::default()))?;
            poses.push(a.q);
        }
        Ok(poses)
    }

    /// Residuals (fitted − observed) of every observation, unweighted.
    fn residuals(&self, model: &Model, est: &Estimate) -> Vec<[f64; 2]> {
        self.problem
            .observations
            .iter()
            .zip(&self.targets)
            .map(|(o, (body, point))| {
                let local = model.bodies[*body].points[point];
                let w = model.bodies[*body]
                    .placement
                    .point(&est.poses[o.frame], local);
                let p = observe(
                    &self.problem.camera,
                    self.plane.as_ref(),
                    &est.cam_global,
                    &est.cam_frames[o.frame],
                    w,
                );
                [p[0] - o.position[0], p[1] - o.position[1]]
            })
            .collect()
    }

    fn cost(&self, model: &Model, est: &Estimate) -> f64 {
        let data: f64 = self
            .residuals(model, est)
            .iter()
            .zip(&self.problem.observations)
            .map(|(r, o)| o.weight * self.problem.loss.rho(r[0].hypot(r[1])))
            .sum();
        let prior: f64 = self
            .free
            .iter()
            .zip(&est.theta)
            .filter_map(|(&p, v)| {
                self.problem.parameters[p]
                    .prior
                    .map(|(m, s)| 0.5 * ((v - m) / s).powi(2))
            })
            .sum();
        data + prior
    }
}

impl Model {
    /// Solves `J X = R` for several right-hand sides at once, least squares.
    fn solve_many(&self, q: &[f64], drive: &[f64], rhs: &Mat<f64>) -> Mat<f64> {
        let (m, n) = (self.n_rows(), self.n_vars);
        let mut a = Mat::<f64>::zeros(m, n);
        for (i, j, v) in self.jacobian(q, drive) {
            a[(i, j)] += v;
        }
        let mut x = rhs.clone();
        a.col_piv_qr()
            .solve_lstsq_in_place_with_conj(Conj::No, x.as_mut());
        x.subrows(0, n).to_owned()
    }
}

/// Fits geometry, driver values, and camera parameters to the observations.
pub fn fit(problem: &FitProblem) -> Result<FitResult, SolverError> {
    let frames = problem.drive.len();
    let document = serde_json::to_value(&problem.mechanism)
        .map_err(|e| SolverError::invalid("mechanism", e.to_string()))?;
    let base = Model::new(&problem.mechanism)?;
    let plane = match &problem.camera {
        Camera::Plane { plane: id } | Camera::Homography { plane: id, .. } => {
            Some(*base.planes.get(id).ok_or_else(|| {
                SolverError::invalid(
                    "camera",
                    format!("The observation plane {id} is not in the graph"),
                )
            })?)
        }
        Camera::Projection { .. } => None,
    };
    match &problem.camera {
        Camera::Homography { initial, .. } if initial.len() != 1 && initial.len() != frames => {
            return Err(SolverError::invalid(
                "camera",
                "Give one homography, or one per frame",
            ));
        }
        Camera::Projection { poses, .. } if poses.len() != 1 && poses.len() != frames => {
            return Err(SolverError::invalid(
                "camera",
                "Give one camera pose, or one per frame",
            ));
        }
        _ => {}
    }
    let mut targets = Vec::with_capacity(problem.observations.len());
    for (i, o) in problem.observations.iter().enumerate() {
        let body = base
            .body(&o.body)
            .filter(|b| base.bodies[*b].points.contains_key(&o.point))
            .ok_or_else(|| {
                SolverError::invalid(
                    format!("observations[{i}]"),
                    format!("Point {}.{} is not in the graph", o.body, o.point),
                )
            })?;
        if o.frame >= frames {
            return Err(SolverError::invalid(
                format!("observations[{i}]"),
                format!("Frame {} has no driver values", o.frame),
            ));
        }
        targets.push((body, o.point.clone()));
    }
    let free: Vec<usize> = (0..problem.parameters.len())
        .filter(|&i| !problem.parameters[i].fixed)
        .collect();
    let mut doc_for_values = document.clone();
    let mut initial = Vec::with_capacity(problem.parameters.len());
    for p in &problem.parameters {
        let v = lookup(&mut doc_for_values, &p.path)
            .and_then(|v| v.as_f64())
            .ok_or_else(|| {
                SolverError::invalid(
                    p.path.clone(),
                    format!("Parameter {} names no number in the graph", p.path),
                )
            })?;
        initial.push(v);
    }
    let n_cam = problem.camera.split(frames);
    let setup = Setup {
        problem,
        document,
        free: free.clone(),
        plane,
        targets,
        frames,
        n_drive: base.drivers.len(),
        n_cam,
    };
    let theta0: Vec<f64> = free.iter().map(|&p| initial[p]).collect();
    let mut model = setup.model_at(&theta0)?;
    if let Some(seeds) = &problem.seeds
        && (seeds.len() != frames || seeds.iter().any(|s| s.len() != base.n_vars))
    {
        return Err(SolverError::invalid(
            "seeds",
            "Give one starting pose per frame, sized to the state",
        ));
    }
    let poses = setup.assemble_all(&model, &problem.drive, problem.seeds.as_deref())?;
    let (cam_global, cam_frames) = problem.camera.initial(frames);
    let mut est = Estimate {
        theta: theta0,
        cam_global,
        drive: problem.drive.clone(),
        cam_frames,
        poses,
    };
    let mut cost = setup.cost(&model, &est);
    let mut lambda = 1e-3;
    let mut iterations = 0;

    for iteration in 0..problem.max_iterations {
        iterations = iteration + 1;
        let system = normal_equations(&setup, &model, &est)?;
        let Some(step) = solve_damped(&system, lambda) else {
            break;
        };
        let mut trial = est.clone();
        let n_theta = trial.theta.len();
        for (k, d) in step.global.iter().enumerate() {
            if k < n_theta {
                trial.theta[k] += d
            } else {
                trial.cam_global[k - n_theta] += d
            }
        }
        for t in 0..frames {
            for (k, d) in step.local[t].iter().enumerate() {
                if k < setup.n_drive {
                    trial.drive[t][k] += d
                } else {
                    trial.cam_frames[t][k - setup.n_drive] += d
                }
            }
        }
        let accepted = setup.model_at(&trial.theta).ok().and_then(|m| {
            let poses = setup
                .assemble_all(&m, &trial.drive, Some(&est.poses))
                .ok()?;
            Some((m, poses))
        });
        let Some((trial_model, poses)) = accepted else {
            lambda *= 10.0;
            continue;
        };
        trial.poses = poses;
        let trial_cost = setup.cost(&trial_model, &trial);
        if trial_cost.is_finite() && trial_cost < cost {
            let improvement = (cost - trial_cost) / cost.max(1e-300);
            est = trial;
            model = trial_model;
            cost = trial_cost;
            lambda = (lambda * 0.3).max(1e-12);
            if improvement < 1e-12 {
                break;
            }
        } else {
            lambda *= 10.0;
            if lambda > 1e12 {
                break;
            }
        }
    }
    if !cost.is_finite() {
        return Err(SolverError::FitDiverged {
            iteration: iterations,
            cost,
        });
    }

    // Covariance from the undamped reduced system at the solution, scaled by the residual
    // variance (requirement 7.5).
    let system = normal_equations(&setup, &model, &est)?;
    let observed = problem
        .observations
        .iter()
        .filter(|o| o.weight > 0.0)
        .count();
    let unknowns = system.h_gg.nrows() + frames * (setup.n_drive + n_cam.1);
    let dof = (2 * observed).saturating_sub(unknowns).max(1);
    #[allow(clippy::cast_precision_loss, reason = "observation counts are small")]
    let variance = 2.0 * system.data_cost / dof as f64;
    let (reduced, _, _) = reduce(&system, 0.0);
    let covariance = if reduced.nrows() > 0 {
        reduced.partial_piv_lu().inverse()
    } else {
        Mat::zeros(0, 0)
    };
    let mut sigma = vec![0.0; problem.parameters.len()];
    let mut values = initial;
    for (k, &p) in free.iter().enumerate() {
        values[p] = est.theta[k];
        sigma[p] = (covariance[(k, k)] * variance).max(0.0).sqrt();
    }

    let residuals: Vec<ObservationResidual> = setup
        .residuals(&model, &est)
        .into_iter()
        .enumerate()
        .map(|(i, r)| ObservationResidual {
            observation: i,
            residual: r,
            weight: problem.loss.weight(r[0].hypot(r[1])),
        })
        .collect();
    #[allow(clippy::cast_precision_loss, reason = "observation counts are small")]
    let rms = (residuals
        .iter()
        .map(|r| r.residual[0].powi(2) + r.residual[1].powi(2))
        .sum::<f64>()
        / residuals.len().max(1) as f64)
        .sqrt();

    let mut document = setup.document.clone();
    for (k, &p) in free.iter().enumerate() {
        if let Some(slot) = lookup(&mut document, &problem.parameters[p].path) {
            *slot = Value::from(est.theta[k]);
        }
    }
    let mut mechanism: Mechanism = serde_json::from_value(document)
        .map_err(|e| SolverError::invalid("mechanism", e.to_string()))?;
    for (p, s) in problem.parameters.iter().zip(&sigma) {
        if !p.fixed {
            mechanism.uncertainty.insert(p.path.clone(), *s);
        }
    }
    Ok(FitResult {
        mechanism,
        values,
        sigma,
        drive: est.drive,
        camera_global: est.cam_global,
        camera_frames: est.cam_frames,
        poses: est.poses,
        residuals,
        rms,
        cost,
        iterations,
    })
}

/// The Gauss–Newton normal equations in arrow form: a global block (geometry, then static
/// camera) and one local block per frame (drivers, then per-frame camera).
struct System {
    h_gg: Mat<f64>,
    g_g: Vec<f64>,
    h_ll: Vec<Mat<f64>>,
    /// Local × global coupling per frame.
    h_lg: Vec<Mat<f64>>,
    g_l: Vec<Vec<f64>>,
    data_cost: f64,
}

#[allow(
    clippy::too_many_lines,
    reason = "one pass that builds the arrow system"
)]
fn normal_equations(
    setup: &Setup<'_>,
    model: &Model,
    est: &Estimate,
) -> Result<System, SolverError> {
    let problem = setup.problem;
    let n_theta = setup.free.len();
    let n_global = n_theta + setup.n_cam.0;
    let n_local = setup.n_drive + setup.n_cam.1;
    let n_drive = setup.n_drive;
    let n = model.n_vars;
    let mut sys = System {
        h_gg: Mat::zeros(n_global, n_global),
        g_g: vec![0.0; n_global],
        h_ll: (0..setup.frames)
            .map(|_| Mat::zeros(n_local, n_local))
            .collect(),
        h_lg: (0..setup.frames)
            .map(|_| Mat::zeros(n_local, n_global))
            .collect(),
        g_l: vec![vec![0.0; n_local]; setup.frames],
        data_cost: 0.0,
    };
    // Nudged models for Φ_θ and the explicit dependence of points on θ.
    let mut nudged = Vec::with_capacity(n_theta);
    for k in 0..n_theta {
        let h = 1e-6 * (1.0 + est.theta[k].abs());
        let (mut up, mut down) = (est.theta.clone(), est.theta.clone());
        up[k] += h;
        down[k] -= h;
        nudged.push((setup.model_at(&up)?, setup.model_at(&down)?, h));
    }
    let rows = model.n_rows();
    let joint_rows = rows - n_drive;
    let mut by_frame: Vec<Vec<usize>> = vec![Vec::new(); setup.frames];
    for (i, o) in problem.observations.iter().enumerate() {
        if o.weight > 0.0 {
            by_frame[o.frame].push(i);
        }
    }
    let lift = |v: &[f64]| -> Vec<Jet> { v.iter().map(|x| Jet::new(*x, 0.0, 0.0)).collect() };
    for t in 0..setup.frames {
        if by_frame[t].is_empty() {
            continue;
        }
        let q = &est.poses[t];
        let drive = &est.drive[t];
        // dq/dd and dq/dθ from one multi-column solve.
        let mut rhs = Mat::<f64>::zeros(rows, n_drive + n_theta);
        for k in 0..n_drive {
            rhs[(joint_rows + k, k)] = 1.0;
        }
        for (k, (up, down, h)) in nudged.iter().enumerate() {
            let (ru, rd) = (up.residuals(q, drive), down.residuals(q, drive));
            for r in 0..rows {
                rhs[(r, n_drive + k)] = -(ru[r] - rd[r]) / (2.0 * h);
            }
        }
        let dq = model.solve_many(q, drive, &rhs);
        let (cg, cl) = (lift(&est.cam_global), lift(&est.cam_frames[t]));
        for &i in &by_frame[t] {
            let o = &problem.observations[i];
            let (body, point) = &setup.targets[i];
            let local = model.bodies[*body].points[point];
            let placement = model.bodies[*body].placement;
            let at = |qv: &[Jet], g: &[Jet], l: &[Jet]| {
                observe(
                    &problem.camera,
                    setup.plane.as_ref(),
                    g,
                    l,
                    placement.point(qv, local),
                )
            };
            let p = at(&lift(q), &cg, &cl);
            let r = [p[0].v - o.position[0], p[1].v - o.position[1]];
            let len = r[0].hypot(r[1]);
            let w = o.weight * problem.loss.weight(len);
            sys.data_cost += o.weight * problem.loss.rho(len);
            // Jacobian columns: local (drivers, frame camera), then global (θ, static camera).
            let mut jl = vec![[0.0; 2]; n_local];
            let mut jg = vec![[0.0; 2]; n_global];
            let through_q = |c: usize| {
                let dir: Vec<Jet> = (0..n).map(|j| Jet::new(q[j], dq[(j, c)], 0.0)).collect();
                let d = at(&dir, &cg, &cl);
                [d[0].d1, d[1].d1]
            };
            for (k, col) in jl.iter_mut().enumerate().take(n_drive) {
                *col = through_q(k);
            }
            for k in 0..setup.n_cam.1 {
                let mut l = cl.clone();
                l[k].d1 = 1.0;
                let d = at(&lift(q), &cg, &l);
                jl[n_drive + k] = [d[0].d1, d[1].d1];
            }
            for (k, (up, down, h)) in nudged.iter().enumerate() {
                let mut col = through_q(n_drive + k);
                // The tracked point's own coordinates may be parameters.
                let (a, b) = (
                    up.point_world(*body, point, q),
                    down.point_world(*body, point, q),
                );
                if let (Some(a), Some(b)) = (a, b) {
                    let explicit: [Jet; 3] =
                        std::array::from_fn(|c| Jet::new(a[c], (a[c] - b[c]) / (2.0 * h), 0.0));
                    let d = observe(&problem.camera, setup.plane.as_ref(), &cg, &cl, explicit);
                    col[0] += d[0].d1;
                    col[1] += d[1].d1;
                }
                jg[k] = col;
            }
            for k in 0..setup.n_cam.0 {
                let mut g = cg.clone();
                g[k].d1 = 1.0;
                let d = at(&lift(q), &g, &cl);
                jg[n_theta + k] = [d[0].d1, d[1].d1];
            }
            let dot = |a: [f64; 2], b: [f64; 2]| w * (a[0] * b[0] + a[1] * b[1]);
            for a in 0..n_local {
                sys.g_l[t][a] += dot(jl[a], r);
                for b in 0..n_local {
                    sys.h_ll[t][(a, b)] += dot(jl[a], jl[b]);
                }
                for b in 0..n_global {
                    sys.h_lg[t][(a, b)] += dot(jl[a], jg[b]);
                }
            }
            for a in 0..n_global {
                sys.g_g[a] += dot(jg[a], r);
                for b in 0..n_global {
                    sys.h_gg[(a, b)] += dot(jg[a], jg[b]);
                }
            }
        }
    }
    for (k, &p) in setup.free.iter().enumerate() {
        if let Some((m, s)) = problem.parameters[p].prior {
            sys.h_gg[(k, k)] += 1.0 / (s * s);
            sys.g_g[k] += (est.theta[k] - m) / (s * s);
        }
    }
    Ok(sys)
}

/// The reduced global system `S`, its gradient, and the per-frame inverse blocks, damped.
fn reduce(sys: &System, lambda: f64) -> (Mat<f64>, Vec<f64>, Vec<Mat<f64>>) {
    let n_global = sys.h_gg.nrows();
    let mut s = sys.h_gg.clone();
    for k in 0..n_global {
        s[(k, k)] += lambda * sys.h_gg[(k, k)].max(1e-12);
    }
    let mut g = sys.g_g.clone();
    let mut inverses = Vec::with_capacity(sys.h_ll.len());
    for t in 0..sys.h_ll.len() {
        let mut d = sys.h_ll[t].clone();
        for k in 0..d.nrows() {
            // A frame no observation reaches still needs an invertible block.
            d[(k, k)] += lambda * d[(k, k)].max(1e-12) + 1e-15;
        }
        let inv = d.partial_piv_lu().inverse();
        let w = sys.h_lg[t].transpose() * &inv;
        s -= &w * &sys.h_lg[t];
        for k in 0..n_global {
            g[k] -= (0..d.nrows())
                .map(|a| w[(k, a)] * sys.g_l[t][a])
                .sum::<f64>();
        }
        inverses.push(inv);
    }
    (s, g, inverses)
}

struct Step {
    global: Vec<f64>,
    local: Vec<Vec<f64>>,
}

fn solve_damped(sys: &System, lambda: f64) -> Option<Step> {
    let (s, g, inverses) = reduce(sys, lambda);
    let n_global = s.nrows();
    let global: Vec<f64> = if n_global > 0 {
        let rhs = Mat::from_fn(n_global, 1, |k, _| -g[k]);
        let x = s.partial_piv_lu().solve(&rhs);
        (0..n_global).map(|k| x[(k, 0)]).collect()
    } else {
        Vec::new()
    };
    // Back-substitution per frame: δl_t = −H_ll⁻¹ (g_l + H_lg δg).
    let local: Vec<Vec<f64>> = (0..sys.h_ll.len())
        .map(|t| {
            let n_local = sys.h_ll[t].nrows();
            let r: Vec<f64> = (0..n_local)
                .map(|a| {
                    sys.g_l[t][a]
                        + (0..n_global)
                            .map(|k| sys.h_lg[t][(a, k)] * global[k])
                            .sum::<f64>()
                })
                .collect();
            (0..n_local)
                .map(|a| {
                    -(0..n_local)
                        .map(|b| inverses[t][(a, b)] * r[b])
                        .sum::<f64>()
                })
                .collect()
        })
        .collect();
    let finite = global
        .iter()
        .chain(local.iter().flatten())
        .all(|v| v.is_finite());
    finite.then_some(Step { global, local })
}

//! The fitter (mechanism-core requirement 7, design "Fitter"): geometry and per-frame driver
//! values from observed point tracks, with every frame's pose assembled exactly.
//!
//! Unknowns are the free geometry parameters `θ` (numbers in the graph, named by the same paths
//! as the schema's `uncertainty` map, such as `bodies.coupler.points.c.local.x`) and each
//! frame's driver values `d_t`. Each frame's pose `q_t` is not an unknown: it is assembled from
//! `(θ, d_t)`, so the joints hold exactly (requirement 7.3), and its derivatives come from the
//! implicit function theorem, `dq/d(θ, d) = −Φ_q⁻¹ Φ_(θ, d)`.
//!
//! Each Gauss–Newton step has the arrow structure of bundle adjustment: a small block per frame
//! for `d_t` and a dense block for `θ`. The frame blocks are eliminated by the Schur complement,
//! the reduced system is solved for `θ`, and the frame steps follow (requirement 7.4). Robust
//! losses enter through iteratively reweighted least squares, and priors are extra residual rows.
//! `Φ_θ` is a central difference on the graph with the parameter nudged; everything in `q` is
//! exact.

use faer::Conj;
use faer::Mat;
use faer::linalg::solvers::{DenseSolveCore, Solve, SolveLstsqCore};
use serde_json::Value;

use crate::assembly::AssemblyOptions;
use crate::dual::Jet;
use crate::error::SolverError;
use crate::model::Model;
use crate::schema::Mechanism;

/// The loss applied to each observation's residual length `r` (in the observation's units).
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
#[derive(Debug, Clone, PartialEq)]
pub struct Parameter {
    /// A path into the graph, such as `bodies.crank.points.b.local.x` or `joints.mesh.phase`.
    pub path: String,
    /// Held at its value in the graph (requirement 7.6).
    pub fixed: bool,
    /// A Gaussian prior `(mean, standard deviation)` (requirement 7.6).
    pub prior: Option<(f64, f64)>,
}

/// One observed point in one frame.
#[derive(Debug, Clone, PartialEq)]
pub struct Observation {
    pub frame: usize,
    pub body: String,
    pub point: String,
    /// Observed position in the observation frame.
    pub position: [f64; 2],
    /// Relative weight (inverse variance). Zero, or absence, means not visible.
    pub weight: f64,
}

/// Where observations are measured.
#[derive(Debug, Clone, PartialEq)]
pub enum ObservationFrame {
    /// Meters in the 2D coordinates of `plane:<id>` (a stabilized, scaled view).
    Plane(String),
}

#[derive(Debug, Clone)]
pub struct FitProblem {
    /// The topology with initial geometry.
    pub mechanism: Mechanism,
    pub parameters: Vec<Parameter>,
    /// Initial driver values, one vector per frame.
    pub drive: Vec<Vec<f64>>,
    pub observations: Vec<Observation>,
    pub frame: ObservationFrame,
    pub loss: Loss,
    pub max_iterations: usize,
}

/// One observation's fitted residual.
#[derive(Debug, Clone, PartialEq)]
pub struct ObservationResidual {
    /// Index into the problem's observations.
    pub observation: usize,
    /// Fitted minus observed, in the observation frame.
    pub residual: [f64; 2],
    /// The robust weight it ended with (1 for an inlier).
    pub weight: f64,
}

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

/// The fitter's view of the problem: the graph document and the free parameters.
struct Setup<'a> {
    problem: &'a FitProblem,
    document: Value,
    /// Problem indices of the free parameters.
    free: Vec<usize>,
    plane: crate::model::PlaneFrame,
    /// `(body index, point id)` of each observation, resolved once.
    targets: Vec<(usize, String)>,
    frames: usize,
}

/// The state of the estimate.
#[derive(Clone)]
struct Estimate {
    theta: Vec<f64>,
    drive: Vec<Vec<f64>>,
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

    /// An observed point's position in the observation frame, along a Jet of the state.
    fn project(&self, model: &Model, body: usize, point: &str, q: &[Jet]) -> Option<[Jet; 2]> {
        let local = *model.bodies[body].points.get(point)?;
        let w = model.bodies[body].placement.point(q, local);
        let d = std::array::from_fn::<Jet, 3, _>(|k| w[k] - self.plane.origin[k]);
        let along = |axis: [f64; 3]| d[0] * axis[0] + d[1] * axis[1] + d[2] * axis[2];
        Some([along(self.plane.u), along(self.plane.v)])
    }

    /// Residuals (fitted − observed) of every observation, unweighted.
    fn residuals(&self, model: &Model, poses: &[Vec<f64>]) -> Vec<Option<[f64; 2]>> {
        self.problem
            .observations
            .iter()
            .zip(&self.targets)
            .map(|(o, (body, point))| {
                let q: Vec<Jet> = poses[o.frame]
                    .iter()
                    .map(|v| Jet::new(*v, 0.0, 0.0))
                    .collect();
                let p = self.project(model, *body, point, &q)?;
                Some([p[0].v - o.position[0], p[1].v - o.position[1]])
            })
            .collect()
    }

    fn cost(&self, model: &Model, est: &Estimate) -> f64 {
        let data: f64 = self
            .residuals(model, &est.poses)
            .iter()
            .zip(&self.problem.observations)
            .filter_map(|(r, o)| r.map(|r| o.weight * self.problem.loss.rho(r[0].hypot(r[1]))))
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

/// Fits geometry and driver values to the observations.
pub fn fit(problem: &FitProblem) -> Result<FitResult, SolverError> {
    let frames = problem.drive.len();
    let document = serde_json::to_value(&problem.mechanism)
        .map_err(|e| SolverError::invalid("mechanism", e.to_string()))?;
    let base = Model::new(&problem.mechanism)?;
    let ObservationFrame::Plane(plane_id) = &problem.frame;
    let plane = *base.planes.get(plane_id).ok_or_else(|| {
        SolverError::invalid(
            "frame",
            format!("The observation plane {plane_id} is not in the graph"),
        )
    })?;
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
    let setup = Setup {
        problem,
        document,
        free: free.clone(),
        plane,
        targets,
        frames,
    };
    let theta0: Vec<f64> = free.iter().map(|&p| initial[p]).collect();
    let model = setup.model_at(&theta0)?;
    let poses = setup.assemble_all(&model, &problem.drive, None)?;
    let mut est = Estimate {
        theta: theta0,
        drive: problem.drive.clone(),
        poses,
    };
    let mut model = model;
    let mut cost = setup.cost(&model, &est);
    let mut lambda = 1e-3;
    let mut iterations = 0;
    let n_theta = free.len();
    let n_drive = base.drivers.len();

    for iteration in 0..problem.max_iterations {
        iterations = iteration + 1;
        let system = normal_equations(&setup, &model, &est)?;
        let step = solve_damped(&system, lambda, n_theta, n_drive, frames);
        let Some(step) = step else { break };
        let mut trial = est.clone();
        for (v, d) in trial.theta.iter_mut().zip(&step.theta) {
            *v += d;
        }
        for (t, row) in trial.drive.iter_mut().enumerate() {
            for (v, d) in row.iter_mut().zip(&step.drive[t]) {
                *v += d;
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
        if trial_cost < cost {
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

    // Covariance from the undamped reduced system at the solution, scaled by the residual
    // variance (requirement 7.5).
    let system = normal_equations(&setup, &model, &est)?;
    let observed: usize = setup
        .residuals(&model, &est.poses)
        .iter()
        .zip(&problem.observations)
        .filter(|(r, o)| r.is_some() && o.weight > 0.0)
        .count();
    let dof = (2 * observed)
        .saturating_sub(n_theta + n_drive * frames)
        .max(1);
    #[allow(clippy::cast_precision_loss, reason = "observation counts are small")]
    let variance = 2.0 * system.data_cost / dof as f64;
    let reduced = reduce(&system, 0.0, n_theta, n_drive, frames);
    let covariance = if n_theta > 0 {
        reduced.0.partial_piv_lu().inverse()
    } else {
        Mat::zeros(0, 0)
    };
    let mut sigma = vec![0.0; problem.parameters.len()];
    let mut values = initial;
    for (k, &p) in free.iter().enumerate() {
        values[p] = est.theta[k];
        sigma[p] = (covariance[(k, k)] * variance).max(0.0).sqrt();
    }

    let raw = setup.residuals(&model, &est.poses);
    let residuals: Vec<ObservationResidual> = raw
        .iter()
        .enumerate()
        .filter_map(|(i, r)| {
            let r = (*r)?;
            Some(ObservationResidual {
                observation: i,
                residual: r,
                weight: problem.loss.weight(r[0].hypot(r[1])),
            })
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
        poses: est.poses,
        residuals,
        rms,
        cost,
        iterations,
    })
}

/// The Gauss–Newton normal equations in arrow form.
struct System {
    /// θθ block.
    h_tt: Mat<f64>,
    g_t: Vec<f64>,
    /// Per frame: dd block, dθ block (n_drive × n_theta), gradient.
    h_dd: Vec<Mat<f64>>,
    h_dt: Vec<Mat<f64>>,
    g_d: Vec<Vec<f64>>,
    data_cost: f64,
}

fn normal_equations(
    setup: &Setup<'_>,
    model: &Model,
    est: &Estimate,
) -> Result<System, SolverError> {
    let problem = setup.problem;
    let n_theta = setup.free.len();
    let n_drive = model.drivers.len();
    let n = model.n_vars;
    let mut sys = System {
        h_tt: Mat::zeros(n_theta, n_theta),
        g_t: vec![0.0; n_theta],
        h_dd: (0..setup.frames)
            .map(|_| Mat::zeros(n_drive, n_drive))
            .collect(),
        h_dt: (0..setup.frames)
            .map(|_| Mat::zeros(n_drive, n_theta))
            .collect(),
        g_d: vec![vec![0.0; n_drive]; setup.frames],
        data_cost: 0.0,
    };
    // Nudged models for Φ_θ and the explicit dependence of points on θ.
    let step = |v: f64| 1e-6 * (1.0 + v.abs());
    let mut nudged = Vec::with_capacity(n_theta);
    for k in 0..n_theta {
        let h = step(est.theta[k]);
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
    for t in 0..setup.frames {
        if by_frame[t].is_empty() {
            continue;
        }
        let q = &est.poses[t];
        let drive = &est.drive[t];
        // Right-hand sides: driver columns (+e) and parameter columns (−Φ_θ).
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
        for &i in &by_frame[t] {
            let o = &problem.observations[i];
            let (body, point) = &setup.targets[i];
            let base: Vec<Jet> = q.iter().map(|v| Jet::new(*v, 0.0, 0.0)).collect();
            let Some(p) = setup.project(model, *body, point, &base) else {
                continue;
            };
            let r = [p[0].v - o.position[0], p[1].v - o.position[1]];
            let len = r[0].hypot(r[1]);
            let w = o.weight * problem.loss.weight(len);
            sys.data_cost += o.weight * problem.loss.rho(len);
            // Column c of the observation's 2×(n_drive + n_theta) Jacobian.
            let mut jac = vec![[0.0; 2]; n_drive + n_theta];
            for (c, col) in jac.iter_mut().enumerate() {
                let dir: Vec<Jet> = (0..n).map(|j| Jet::new(q[j], dq[(j, c)], 0.0)).collect();
                if let Some(pp) = setup.project(model, *body, point, &dir) {
                    *col = [pp[0].d1, pp[1].d1];
                }
            }
            // Explicit dependence: the tracked point's own coordinates may be parameters.
            for (k, (up, down, h)) in nudged.iter().enumerate() {
                let (a, b) = (
                    up.point_world(*body, point, q),
                    down.point_world(*body, point, q),
                );
                if let (Some(a), Some(b)) = (a, b) {
                    let d: Vec<f64> = (0..3).map(|c| (a[c] - b[c]) / (2.0 * h)).collect();
                    let du =
                        d[0] * setup.plane.u[0] + d[1] * setup.plane.u[1] + d[2] * setup.plane.u[2];
                    let dv =
                        d[0] * setup.plane.v[0] + d[1] * setup.plane.v[1] + d[2] * setup.plane.v[2];
                    jac[n_drive + k][0] += du;
                    jac[n_drive + k][1] += dv;
                }
            }
            for a in 0..n_drive + n_theta {
                let ga = w * (jac[a][0] * r[0] + jac[a][1] * r[1]);
                if a < n_drive {
                    sys.g_d[t][a] += ga
                } else {
                    sys.g_t[a - n_drive] += ga
                }
                for b in 0..n_drive + n_theta {
                    let hab = w * (jac[a][0] * jac[b][0] + jac[a][1] * jac[b][1]);
                    match (a < n_drive, b < n_drive) {
                        (true, true) => sys.h_dd[t][(a, b)] += hab,
                        (true, false) => sys.h_dt[t][(a, b - n_drive)] += hab,
                        (false, false) => sys.h_tt[(a - n_drive, b - n_drive)] += hab,
                        (false, true) => {}
                    }
                }
            }
        }
    }
    for (k, &p) in setup.free.iter().enumerate() {
        if let Some((m, s)) = problem.parameters[p].prior {
            sys.h_tt[(k, k)] += 1.0 / (s * s);
            sys.g_t[k] += (est.theta[k] - m) / (s * s);
        }
    }
    Ok(sys)
}

/// The reduced θ system `S`, gradient `g`, and the per-frame inverse blocks, with damping.
fn reduce(
    sys: &System,
    lambda: f64,
    n_theta: usize,
    n_drive: usize,
    frames: usize,
) -> (Mat<f64>, Vec<f64>, Vec<Mat<f64>>) {
    let mut s = sys.h_tt.clone();
    for k in 0..n_theta {
        s[(k, k)] += lambda * sys.h_tt[(k, k)].max(1e-12);
    }
    let mut g = sys.g_t.clone();
    let mut inverses = Vec::with_capacity(frames);
    for t in 0..frames {
        let mut d = sys.h_dd[t].clone();
        for k in 0..n_drive {
            // A frame no observation reaches still needs an invertible block.
            d[(k, k)] += lambda * d[(k, k)].max(1e-12) + 1e-15;
        }
        let inv = d.partial_piv_lu().inverse();
        let w = sys.h_dt[t].transpose() * &inv;
        s -= &w * &sys.h_dt[t];
        for k in 0..n_theta {
            g[k] -= (0..n_drive).map(|a| w[(k, a)] * sys.g_d[t][a]).sum::<f64>();
        }
        inverses.push(inv);
    }
    (s, g, inverses)
}

struct Step {
    theta: Vec<f64>,
    drive: Vec<Vec<f64>>,
}

fn solve_damped(
    sys: &System,
    lambda: f64,
    n_theta: usize,
    n_drive: usize,
    frames: usize,
) -> Option<Step> {
    let (s, g, inverses) = reduce(sys, lambda, n_theta, n_drive, frames);
    let theta: Vec<f64> = if n_theta > 0 {
        let rhs = Mat::from_fn(n_theta, 1, |k, _| -g[k]);
        let x = s.partial_piv_lu().solve(&rhs);
        (0..n_theta).map(|k| x[(k, 0)]).collect()
    } else {
        Vec::new()
    };
    // Back-substitution per frame: δd_t = −H_dd⁻¹ (g_d + H_dθ δθ).
    let drive: Vec<Vec<f64>> = (0..frames)
        .map(|t| {
            let r: Vec<f64> = (0..n_drive)
                .map(|a| {
                    sys.g_d[t][a]
                        + (0..n_theta)
                            .map(|k| sys.h_dt[t][(a, k)] * theta[k])
                            .sum::<f64>()
                })
                .collect();
            (0..n_drive)
                .map(|a| {
                    -(0..n_drive)
                        .map(|b| inverses[t][(a, b)] * r[b])
                        .sum::<f64>()
                })
                .collect()
        })
        .collect();
    let finite = theta
        .iter()
        .chain(drive.iter().flatten())
        .all(|v| v.is_finite());
    finite.then_some(Step { theta, drive })
}

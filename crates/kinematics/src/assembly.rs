//! Assembly: the body poses that satisfy every constraint for given driver values
//! (mechanism-core requirement 4, design "Assembly").
//!
//! Levenberg–Marquardt on the residual vector. Each step solves the damped least-squares problem
//! `[J; √μ·D] δ = [−r; 0]` by QR, dense for small mechanisms and sparse for large ones, so a
//! rank-deficient Jacobian (free motion, singular poses) still gives a bounded step.

use std::collections::{BTreeMap, VecDeque};

use faer::linalg::solvers::SolveLstsqCore;
use faer::sparse::{SparseColMat, Triplet};
use faer::{Conj, Mat};

use crate::error::{JointResidual, SolverError};
use crate::model::{Link, Model};
use crate::planar::{Pose2, V2};

/// Mechanisms with fewer unknowns than this use dense QR (design: "a small dense path").
pub const DENSE_LIMIT: usize = 30;

/// Which linear solver an assembly uses.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum LinearPath {
    /// Dense below [`DENSE_LIMIT`] unknowns, sparse otherwise.
    #[default]
    Auto,
    Dense,
    Sparse,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AssemblyOptions {
    /// Converged when every residual is below this (meters or radians).
    pub tolerance: f64,
    pub max_iterations: usize,
    pub path: LinearPath,
}

impl Default for AssemblyOptions {
    fn default() -> Self {
        Self {
            tolerance: 1e-12,
            max_iterations: 200,
            path: LinearPath::Auto,
        }
    }
}

/// A solved pose of the mechanism.
#[derive(Debug, Clone, PartialEq)]
pub struct Assembly {
    /// The state: `(x, y, θ)` of each moving body, in body order.
    pub q: Vec<f64>,
    /// Largest absolute residual at `q`.
    pub max_residual: f64,
    pub iterations: usize,
}

/// Requirement 4.1: residuals must end below this, whatever the tolerance asked for.
const REQUIRED: f64 = 1e-9;

fn max_abs(r: &[f64]) -> f64 {
    r.iter().fold(0.0_f64, |m, v| m.max(v.abs()))
}

fn half_sq(r: &[f64]) -> f64 {
    0.5 * r.iter().map(|v| v * v).sum::<f64>()
}

/// Sums entries that share a row and column, in a deterministic order.
fn combine(entries: Vec<(usize, usize, f64)>) -> Vec<(usize, usize, f64)> {
    let mut map: BTreeMap<(usize, usize), f64> = BTreeMap::new();
    for (r, c, v) in entries {
        *map.entry((c, r)).or_insert(0.0) += v;
    }
    map.into_iter().map(|((c, r), v)| (r, c, v)).collect()
}

/// Solves `[J; diag(damp)] δ = [−r; 0]` in the least-squares sense.
fn damped_step(
    entries: &[(usize, usize, f64)],
    r: &[f64],
    damp: &[f64],
    n: usize,
    sparse: bool,
) -> Option<Vec<f64>> {
    let m = r.len();
    let rows = m + n;
    let mut rhs = Mat::<f64>::zeros(rows, 1);
    for (i, v) in r.iter().enumerate() {
        rhs[(i, 0)] = -v;
    }
    if sparse {
        let mut triplets: Vec<Triplet<usize, usize, f64>> = entries
            .iter()
            .map(|&(i, j, v)| Triplet::new(i, j, v))
            .collect();
        triplets.extend(
            damp.iter()
                .enumerate()
                .map(|(j, &d)| Triplet::new(m + j, j, d)),
        );
        let a = SparseColMat::<usize, f64>::try_new_from_triplets(rows, n, &triplets).ok()?;
        let qr = a.sp_qr().ok()?;
        qr.solve_lstsq_in_place_with_conj(Conj::No, rhs.as_mut());
    } else {
        let mut a = Mat::<f64>::zeros(rows, n);
        for &(i, j, v) in entries {
            a[(i, j)] += v;
        }
        for (j, &d) in damp.iter().enumerate() {
            a[(m + j, j)] = d;
        }
        a.qr()
            .solve_lstsq_in_place_with_conj(Conj::No, rhs.as_mut());
    }
    let step: Vec<f64> = (0..n).map(|j| rhs[(j, 0)]).collect();
    step.iter().all(|v| v.is_finite()).then_some(step)
}

/// `‖r + J δ‖² / 2`: the cost the linear model predicts after the step.
fn predicted(entries: &[(usize, usize, f64)], r: &[f64], step: &[f64]) -> f64 {
    let mut lin = r.to_vec();
    for &(i, j, v) in entries {
        lin[i] += v * step[j];
    }
    half_sq(&lin)
}

impl Model {
    /// The joints with the largest residuals at `q`, largest first.
    #[must_use]
    pub fn worst_joints(&self, q: &[f64], drive: &[f64], count: usize) -> Vec<JointResidual> {
        let r = self.residuals(q, drive);
        let mut row = 0;
        let mut out: Vec<JointResidual> = self
            .constraints
            .iter()
            .map(|c| {
                let d = c.dim();
                let norm = r[row..row + d].iter().map(|v| v * v).sum::<f64>().sqrt();
                row += d;
                JointResidual {
                    joint_id: c.source_id().to_owned(),
                    residual: norm,
                }
            })
            .collect();
        out.sort_by(|a, b| {
            b.residual
                .total_cmp(&a.residual)
                .then(a.joint_id.cmp(&b.joint_id))
        });
        out.truncate(count);
        out
    }

    fn check_drive(&self, drive: &[f64]) -> Result<(), SolverError> {
        if drive.len() == self.drivers.len() {
            Ok(())
        } else {
            Err(SolverError::DriverCount {
                expected: self.drivers.len(),
                got: drive.len(),
            })
        }
    }

    /// Levenberg–Marquardt from `start`. Returns the final state and whether it converged.
    pub(crate) fn levenberg_marquardt(
        &self,
        start: Vec<f64>,
        drive: &[f64],
        options: &AssemblyOptions,
    ) -> (Assembly, bool) {
        let n = self.n_vars;
        let sparse = match options.path {
            LinearPath::Auto => n >= DENSE_LIMIT,
            LinearPath::Dense => false,
            LinearPath::Sparse => true,
        };
        let mut q = start;
        let mut r = self.residuals(&q, drive);
        let mut cost = half_sq(&r);
        let mut mu: f64 = 1e-3;
        let mut nu = 2.0;
        for iteration in 0..options.max_iterations {
            if max_abs(&r) <= options.tolerance || n == 0 {
                return (
                    Assembly {
                        max_residual: max_abs(&r),
                        q,
                        iterations: iteration,
                    },
                    true,
                );
            }
            let entries = combine(self.jacobian(&q, drive));
            // Marquardt scaling: each unknown is damped by its column norm, so meters and
            // radians are treated alike. Unconstrained unknowns get a floor and stay put.
            let mut col = vec![0.0; n];
            for &(_, j, v) in &entries {
                col[j] += v * v;
            }
            let scale: Vec<f64> = col.iter().map(|c| c.sqrt().max(1e-6)).collect();
            let damp: Vec<f64> = scale.iter().map(|s| mu.sqrt() * s).collect();
            let Some(step) = damped_step(&entries, &r, &damp, n, sparse) else {
                break;
            };
            let candidate: Vec<f64> = q.iter().zip(&step).map(|(a, b)| a + b).collect();
            let r_new = self.residuals(&candidate, drive);
            let cost_new = half_sq(&r_new);
            let expected = cost - predicted(&entries, &r, &step);
            let rho = if expected > 0.0 {
                (cost - cost_new) / expected
            } else {
                -1.0
            };
            if rho > 1e-4 && cost_new.is_finite() {
                q = candidate;
                r = r_new;
                cost = cost_new;
                mu *= (1.0 / 3.0_f64).max(1.0 - (2.0f64.mul_add(rho, -1.0)).powi(3));
                mu = mu.max(1e-20);
                nu = 2.0;
            } else {
                mu *= nu;
                nu *= 2.0;
                let step_norm = step.iter().map(|v| v * v).sum::<f64>().sqrt();
                let q_norm = q.iter().map(|v| v * v).sum::<f64>().sqrt();
                if step_norm <= 1e-15 * (q_norm + 1e-15) || mu > 1e20 {
                    break;
                }
            }
        }
        let max_residual = max_abs(&r);
        // Stalled short of the tolerance: still an assembly if it meets requirement 4.1.
        let done = max_residual <= REQUIRED;
        (
            Assembly {
                q,
                max_residual,
                iterations: options.max_iterations,
            },
            done,
        )
    }

    /// Assembles the mechanism for `drive` (one value per driver, in driver order).
    ///
    /// With a `seed` (a previous assembly's state), the result is the pose on the seed's branch
    /// (requirement 4.2). Without one, deterministic starting guesses are tried in turn.
    pub fn assemble(
        &self,
        drive: &[f64],
        seed: Option<&[f64]>,
        options: &AssemblyOptions,
    ) -> Result<Assembly, SolverError> {
        self.check_drive(drive)?;
        let starts: Vec<Vec<f64>> = match seed {
            Some(s) if s.len() != self.n_vars => {
                return Err(SolverError::SeedLength {
                    expected: self.n_vars,
                    got: s.len(),
                });
            }
            Some(s) => vec![s.to_vec()],
            None => [(0.9, 1.0), (0.9, -1.0), (2.2, 1.0), (2.2, -1.0), (0.3, 1.0)]
                .into_iter()
                .map(|(turn, sign)| self.initial_guess(drive, turn, sign))
                .collect(),
        };
        let mut best: Option<Assembly> = None;
        // A pose that satisfies the equations but leaves a slot or slider range.
        let mut outside_range: Option<Vec<JointResidual>> = None;
        for start in starts {
            let (assembly, converged) = self.levenberg_marquardt(start, drive, options);
            if converged {
                let assembly = if self.springs.is_empty() {
                    assembly
                } else {
                    self.relax(assembly, drive, options)
                };
                // A pin past the end of its slot, or a slider past its limits, is not a pose the
                // machine can take (requirement 4.3). Another start may find one that is.
                let outside: Vec<JointResidual> = self
                    .constraints
                    .iter()
                    .filter_map(|c| {
                        c.violation(&assembly.q).map(|v| JointResidual {
                            joint_id: c.source_id().to_owned(),
                            residual: v,
                        })
                    })
                    .collect();
                if outside.is_empty() {
                    return Ok(assembly);
                }
                outside_range.get_or_insert(outside);
                continue;
            }
            if best
                .as_ref()
                .is_none_or(|b| assembly.max_residual < b.max_residual)
            {
                best = Some(assembly);
            }
        }
        if let Some(mut worst_joints) = outside_range {
            worst_joints.sort_by(|a, b| b.residual.total_cmp(&a.residual));
            return Err(SolverError::AssemblyFailed { worst_joints });
        }
        let q = best.map(|b| b.q).unwrap_or_else(|| vec![0.0; self.n_vars]);
        Err(SolverError::AssemblyFailed {
            worst_joints: self.worst_joints(&q, drive, 3),
        })
    }

    /// A starting pose built outward from the ground: each body is placed so its joint to an
    /// already-placed body is satisfied, turned by the driver's value where one drives that
    /// joint and by `±turn` otherwise, alternating with depth so links are not collinear.
    #[must_use]
    pub fn initial_guess(&self, drive: &[f64], turn: f64, sign: f64) -> Vec<f64> {
        let mut poses: Vec<Option<Pose2>> = self
            .bodies
            .iter()
            .map(|b| b.is_ground.then(Pose2::default))
            .collect();
        let mut depth = vec![0usize; self.bodies.len()];
        let mut queue: VecDeque<usize> = self
            .bodies
            .iter()
            .enumerate()
            .filter(|(_, b)| b.is_ground)
            .map(|(i, _)| i)
            .collect();
        while let Some(known) = queue.pop_front() {
            for (a, b, link) in &self.links {
                let (from, to, forward) = if *a == known {
                    (*a, *b, true)
                } else if *b == known {
                    (*b, *a, false)
                } else {
                    continue;
                };
                if poses[to].is_some() {
                    continue;
                }
                let Some(base) = poses[from] else { continue };
                let parity = if depth[from].is_multiple_of(2) {
                    1.0
                } else {
                    -1.0
                };
                let placed = self.place(link, base, forward, drive, sign * parity * turn);
                poses[to] = Some(placed);
                depth[to] = depth[from] + 1;
                queue.push_back(to);
            }
        }
        let mut q = vec![0.0; self.n_vars];
        for (body, pose) in self.bodies.iter().zip(poses) {
            if let (crate::constraint::BodySlot::Var(i), Some(p)) = (body.slot, pose) {
                q[i] = p.x;
                q[i + 1] = p.y;
                q[i + 2] = p.theta;
            }
        }
        // Curve parameters start where the curve passes closest to its partner.
        for c in &self.constraints {
            c.init_aux(&mut q);
        }
        q
    }

    /// The pose of the body at the far end of `link`, given the near body's pose.
    fn place(&self, link: &Link, base: Pose2, forward: bool, drive: &[f64], turn: f64) -> Pose2 {
        let link_id = match link {
            Link::Revolute(r) => r.id.as_str(),
            Link::Prismatic(p) => p.id.as_str(),
        };
        let driven = self
            .drivers
            .iter()
            .find(|d| d.joint_id == link_id)
            .map(|d| drive[d.index]);
        match link {
            Link::Revolute(r) => {
                let (near, far) = if forward {
                    (r.anchor_a, r.anchor_b)
                } else {
                    (r.anchor_b, r.anchor_a)
                };
                // The driven angle is θB − θA.
                let delta = driven.map_or(turn, |v| if forward { v } else { -v });
                let theta = base.theta + delta;
                let pin = base.apply(near);
                let far_offset = Pose2 {
                    x: 0.0,
                    y: 0.0,
                    theta,
                }
                .rotate(far);
                Pose2 {
                    x: pin.x - far_offset.x,
                    y: pin.y - far_offset.y,
                    theta,
                }
            }
            Link::Prismatic(p) => {
                let (near, far) = if forward {
                    (p.anchor_a, p.anchor_b)
                } else {
                    (p.anchor_b, p.anchor_a)
                };
                let s = driven.unwrap_or(0.0);
                let theta = base.theta;
                let rot = Pose2 {
                    x: 0.0,
                    y: 0.0,
                    theta,
                };
                // Seen from B the slide direction points the other way.
                let dir = base.rotate(p.axis) * if forward { 1.0 } else { -1.0 };
                let target: V2 = base.apply(near) + dir * s;
                let far_offset = rot.rotate(far);
                Pose2 {
                    x: target.x - far_offset.x,
                    y: target.y - far_offset.y,
                    theta,
                }
            }
        }
    }
}

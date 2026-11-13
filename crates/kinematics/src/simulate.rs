//! Cycle simulation (mechanism-core requirement 5, design "Simulation and singularities").
//!
//! Continuation over one driver's range: each step is seeded from the previous pose (with a
//! secant predictor), and a step that fails to converge or turns any body too far is halved.
//! When halving cannot get past a value, that reachable sub-range ends and the rest of the range
//! is searched for where the mechanism can be assembled again.
//!
//! Singularities, in the terms of the design:
//! - `dead_center`: the driver loses influence. The full Jacobian (joints and drivers) becomes
//!   singular while the joints alone keep their rank, so the driver cannot move the mechanism on.
//!   The reachable range ends there.
//! - `lockup`: the output loses mobility. The velocity of the output points (role `output`) passes
//!   through zero while the driver keeps moving, as at a rocker's extreme.
//! - `bifurcation`: the joints alone lose rank, so the null space grows and branches meet.

use faer::Mat;

use crate::assembly::AssemblyOptions;
use crate::constraint::BodySlot;
use crate::error::SolverError;
use crate::model::Model;

/// The kind of a singularity event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SingularityKind {
    DeadCenter,
    Lockup,
    Bifurcation,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Singularity {
    /// The swept driver's value at the event.
    pub drive: f64,
    pub kind: SingularityKind,
    /// The joints of the bodies that move in the singular direction.
    pub joints: Vec<String>,
}

/// One output step.
#[derive(Debug, Clone, PartialEq)]
pub struct Sample {
    /// The swept driver's value.
    pub drive: f64,
    pub q: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Simulation {
    /// The assembled steps, in sweep order. Values outside every reachable sub-range are absent.
    pub samples: Vec<Sample>,
    /// Inclusive driver ranges that could be assembled, in sweep order.
    pub reachable: Vec<(f64, f64)>,
    pub singularities: Vec<Singularity>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SimulationOptions {
    /// Largest rotation any body may make in one continuation step, in radians.
    pub max_turn: f64,
    /// The smallest step, as a fraction of the requested step, before a range is declared ended.
    pub min_fraction: f64,
    pub assembly: AssemblyOptions,
}

impl Default for SimulationOptions {
    fn default() -> Self {
        Self {
            max_turn: 0.3,
            min_fraction: 1e-6,
            assembly: AssemblyOptions::default(),
        }
    }
}

/// Singular values of a dense copy of the given Jacobian entries, largest first.
fn singular_values(entries: &[(usize, usize, f64)], m: usize, n: usize) -> Vec<f64> {
    if m == 0 || n == 0 {
        return Vec::new();
    }
    let mut a = Mat::<f64>::zeros(m, n);
    for &(i, j, v) in entries {
        a[(i, j)] += v;
    }
    a.singular_values().unwrap_or_default()
}

impl Model {
    /// The rows that belong to joints (not drivers).
    fn joint_rows(&self) -> usize {
        self.n_rows() - self.drivers.len()
    }

    /// Bodies that move in direction `v` of the state, and the joints touching them.
    fn joints_moving(&self, v: &[f64]) -> Vec<String> {
        let largest = v.iter().fold(0.0_f64, |m, x| m.max(x.abs()));
        let moving: Vec<usize> = self
            .bodies
            .iter()
            .enumerate()
            .filter(|(_, b)| match b.slot {
                BodySlot::Var(i) => v[i..i + 3].iter().any(|x| x.abs() > 0.1 * largest),
                BodySlot::Spatial(i) => v[i..i + 7].iter().any(|x| x.abs() > 0.1 * largest),
                BodySlot::Fixed(_) => false,
            })
            .map(|(i, _)| i)
            .collect();
        let mut joints: Vec<String> = self
            .links
            .iter()
            .filter(|(a, b, _)| moving.contains(a) || moving.contains(b))
            .map(|(_, _, l)| l.id().to_owned())
            .collect();
        joints.sort();
        joints.dedup();
        joints
    }

    /// The direction of least singular value of the full Jacobian at `q`.
    fn singular_direction(&self, q: &[f64], drive: &[f64]) -> Vec<f64> {
        let (m, n) = (self.n_rows(), self.n_vars);
        let mut a = Mat::<f64>::zeros(m.max(1), n);
        for (i, j, v) in self.jacobian(q, drive) {
            a[(i, j)] += v;
        }
        a.svd().map_or_else(
            |_| vec![0.0; n],
            |svd| (0..n).map(|r| svd.V()[(r, n - 1)]).collect(),
        )
    }

    /// Smallest singular value of the full Jacobian relative to the largest, the rank of the
    /// joint rows alone, and those rows' singular values relative to their largest.
    fn conditioning(&self, q: &[f64], drive: &[f64]) -> (f64, usize, Vec<f64>) {
        let entries = self.jacobian(q, drive);
        let n = self.n_vars;
        let full = singular_values(&entries, self.n_rows(), n);
        let joints: Vec<(usize, usize, f64)> = entries
            .iter()
            .copied()
            .filter(|(i, _, _)| *i < self.joint_rows())
            .collect();
        let only = singular_values(&joints, self.joint_rows(), n);
        let top = only.first().copied().unwrap_or(0.0).max(1e-300);
        let rank = only.iter().filter(|s| **s > 1e-8 * top).count();
        let ratio = if full.len() < n {
            0.0
        } else {
            full.last().copied().unwrap_or(0.0) / full.first().copied().unwrap_or(1.0).max(1e-300)
        };
        (ratio, rank, only.iter().map(|s| s / top).collect())
    }

    fn largest_turn(&self, from: &[f64], to: &[f64]) -> f64 {
        self.bodies
            .iter()
            .filter_map(|b| match b.slot {
                BodySlot::Var(i) => Some((to[i + 2] - from[i + 2]).abs()),
                // The angle between two orientations: 2·acos(|q₁·q₂|).
                BodySlot::Spatial(i) => {
                    let d: f64 = (3..7).map(|k| from[i + k] * to[i + k]).sum();
                    Some(2.0 * d.abs().min(1.0).acos())
                }
                BodySlot::Fixed(_) => None,
            })
            .fold(0.0, f64::max)
    }

    /// Sweeps driver `k` from `start` to `end` in steps of `step` (the other drivers held at
    /// `drive`), returning every reachable step's pose (requirements 5.1 to 5.4).
    pub fn simulate(
        &self,
        k: usize,
        drive: &[f64],
        (start, end, step): (f64, f64, f64),
        seed: Option<&[f64]>,
        options: &SimulationOptions,
    ) -> Result<Simulation, SolverError> {
        if drive.len() != self.drivers.len() {
            return Err(SolverError::DriverCount {
                expected: self.drivers.len(),
                got: drive.len(),
            });
        }
        if k >= self.drivers.len() {
            return Err(SolverError::invalid(
                "drivers",
                format!("There is no driver {k} to sweep"),
            ));
        }
        let span = end - start;
        let count = if step > 0.0 && span.is_finite() {
            ((span.abs() / step).round() as usize).max(1)
        } else {
            return Err(SolverError::invalid(
                "simulation",
                "The step must be a positive number",
            ));
        };
        let grid: Vec<f64> = (0..=count)
            .map(|i| start + span * (i as f64) / (count as f64))
            .collect();
        let values = |d: f64| {
            let mut v = drive.to_vec();
            v[k] = d;
            v
        };
        let mut sim = Simulation {
            samples: Vec::new(),
            reachable: Vec::new(),
            singularities: Vec::new(),
        };
        let mut current: Option<(f64, Vec<f64>)> = None;
        let mut previous: Option<(f64, Vec<f64>)> = None;
        let mut range_start = 0.0;
        let mut tracker = Tracker::default();
        let mut g = 0;
        while g < grid.len() {
            let target = grid[g];
            let Some((d0, q0)) = current.clone() else {
                // Outside a reachable range: try to assemble afresh here.
                let first_seed = if g == 0 { seed } else { None };
                if let Ok(a) = self.assemble(&values(target), first_seed, &options.assembly) {
                    range_start = target;
                    current = Some((target, a.q.clone()));
                    previous = None;
                    tracker.restart();
                    self.record(&mut sim, target, a.q, &values(target), k, &mut tracker);
                }
                g += 1;
                continue;
            };
            // Continue from d0 towards the target, halving on trouble.
            let full = target - d0;
            let mut h = full;
            let mut reached = d0;
            let mut q = q0;
            let mut ended = false;
            while (target - reached).abs() > 1e-15 * (1.0 + target.abs()) {
                let next = if (target - reached).abs() < h.abs() {
                    target
                } else {
                    reached + h
                };
                // Secant predictor from the last two accepted poses.
                let guess: Vec<f64> = match &previous {
                    Some((dp, qp)) if (reached - dp).abs() > 0.0 => {
                        let t = (next - reached) / (reached - dp);
                        q.iter().zip(qp).map(|(a, b)| a + t * (a - b)).collect()
                    }
                    _ => q.clone(),
                };
                let attempt = self
                    .assemble(&values(next), Some(&guess), &options.assembly)
                    .ok()
                    .filter(|a| self.largest_turn(&q, &a.q) <= options.max_turn);
                if let Some(a) = attempt {
                    previous = Some((reached, q));
                    reached = next;
                    q = a.q;
                    if h.abs() < full.abs() {
                        h *= 1.5;
                    }
                } else {
                    h *= 0.5;
                    if h.abs() < options.min_fraction * step {
                        ended = true;
                        break;
                    }
                }
            }
            if ended {
                // The range ends between `reached` and the next value: a limit of motion.
                sim.reachable.push((range_start, reached));
                let (ratio, rank, _) = self.conditioning(&q, &values(reached));
                if rank < tracker.rank.unwrap_or(rank) {
                    sim.singularities.push(Singularity {
                        drive: reached,
                        kind: SingularityKind::Bifurcation,
                        joints: self.joints_moving(&self.singular_direction(&q, &values(reached))),
                    });
                } else if ratio < 1e-3 {
                    sim.singularities.push(Singularity {
                        drive: reached,
                        kind: SingularityKind::DeadCenter,
                        joints: self.joints_moving(&self.singular_direction(&q, &values(reached))),
                    });
                }
                current = None;
                g += 1;
                continue;
            }
            current = Some((target, q.clone()));
            self.record(&mut sim, target, q, &values(target), k, &mut tracker);
            g += 1;
        }
        if current.is_some() {
            sim.reachable.push((range_start, grid[grid.len() - 1]));
        }
        Ok(sim)
    }

    /// Stores a sample and checks for a lockup or a bifurcation since the previous samples.
    fn record(
        &self,
        sim: &mut Simulation,
        d: f64,
        q: Vec<f64>,
        drive: &[f64],
        k: usize,
        tracker: &mut Tracker,
    ) {
        let (_, rank, joint_sv) = self.conditioning(&q, drive);
        let baseline = *tracker.rank.get_or_insert(rank);
        // How close the joints are to losing rank: their last kept singular value.
        let indicator = baseline
            .checked_sub(1)
            .and_then(|r| joint_sv.get(r))
            .copied()
            .unwrap_or(1.0);
        // The middle of the last three samples is a dip below 1e-3: refine where it is deepest.
        if let [(d_a, s_a), (_, s_b)] = tracker.recent[..]
            && s_b < s_a
            && s_b <= indicator
            && s_b < 1e-3
        {
            let (at, depth, q_at) = self.deepest_dip(sim, d_a, d, drive, k, baseline);
            if depth < 1e-6 {
                let joints = self.joints_moving(&self.singular_direction(&q_at, drive));
                sim.singularities.push(Singularity {
                    drive: at,
                    kind: SingularityKind::Bifurcation,
                    joints,
                });
            }
        }
        tracker.recent.push((d, indicator));
        if tracker.recent.len() > 2 {
            tracker.recent.remove(0);
        }
        let v = self.output_velocity(&q, drive, k);
        if let (Some(prev), Some(pd)) =
            (tracker.output.as_ref(), sim.samples.last().map(|s| s.drive))
        {
            let turn: f64 = prev.iter().zip(&v).map(|(a, b)| a * b).sum();
            if turn < 0.0 && !v.is_empty() {
                // The output reversed between the two samples: locate where its speed is least.
                let at = self.locate_reversal(sim, pd, d, drive, k);
                let joints = self.joints_moving(&self.velocity(&q, drive, k));
                sim.singularities.push(Singularity {
                    drive: at,
                    kind: SingularityKind::Lockup,
                    joints,
                });
            }
        }
        tracker.output = Some(v);
        sim.samples.push(Sample { drive: d, q });
    }

    /// Golden-section search between `lo` and `hi` for the least kept singular value of the joint
    /// rows, assembling from the sample before `lo`'s neighbor. Returns where, how small, and the
    /// pose there.
    fn deepest_dip(
        &self,
        sim: &Simulation,
        lo: f64,
        hi: f64,
        drive: &[f64],
        k: usize,
        baseline: usize,
    ) -> (f64, f64, Vec<f64>) {
        let seed = sim.samples.last().map(|s| s.q.clone()).unwrap_or_default();
        let mut values = drive.to_vec();
        let mut measure = |d: f64, seed: &[f64]| -> Option<(f64, Vec<f64>)> {
            values[k] = d;
            let a = self
                .assemble(&values, Some(seed), &AssemblyOptions::default())
                .ok()?;
            let (_, _, sv) = self.conditioning(&a.q, &values);
            Some((sv.get(baseline - 1).copied().unwrap_or(0.0), a.q))
        };
        let ratio = 0.5 * (5.0_f64.sqrt() - 1.0);
        let (mut a, mut b) = (lo, hi);
        let mut best = (0.5 * (lo + hi), f64::INFINITY, seed.clone());
        for _ in 0..60 {
            let (x1, x2) = (b - ratio * (b - a), a + ratio * (b - a));
            let (Some((f1, q1)), Some((f2, q2))) = (measure(x1, &best.2), measure(x2, &best.2))
            else {
                break;
            };
            if f1 < f2 {
                b = x2;
                if f1 < best.1 {
                    best = (x1, f1, q1);
                }
            } else {
                a = x1;
                if f2 < best.1 {
                    best = (x2, f2, q2);
                }
            }
            if (b - a).abs() < 1e-12 * (1.0 + a.abs()) {
                break;
            }
        }
        best
    }

    /// Bisection for the driver value where the output velocity reverses, between two samples.
    fn locate_reversal(&self, sim: &Simulation, lo: f64, hi: f64, drive: &[f64], k: usize) -> f64 {
        let Some(mut q) = sim.samples.last().map(|s| s.q.clone()) else {
            return 0.5 * (lo + hi);
        };
        let mut values = drive.to_vec();
        let reference = {
            values[k] = lo;
            self.output_velocity(&q, &values, k)
        };
        let (mut a, mut b) = (lo, hi);
        for _ in 0..40 {
            let mid = 0.5 * (a + b);
            values[k] = mid;
            let Ok(asm) = self.assemble(&values, Some(&q), &AssemblyOptions::default()) else {
                break;
            };
            q = asm.q;
            let v = self.output_velocity(&q, &values, k);
            if reference.iter().zip(&v).map(|(x, y)| x * y).sum::<f64>() > 0.0 {
                a = mid
            } else {
                b = mid
            }
        }
        0.5 * (a + b)
    }

    /// World positions of every named point at every sample, keyed by `(body id, point id)`.
    #[must_use]
    pub fn trajectories(
        &self,
        sim: &Simulation,
    ) -> std::collections::BTreeMap<(String, String), Vec<[f64; 3]>> {
        let mut out = std::collections::BTreeMap::new();
        for (i, body) in self.bodies.iter().enumerate() {
            for name in body.points.keys() {
                let path = sim
                    .samples
                    .iter()
                    .filter_map(|s| self.point_world(i, name, &s.q))
                    .collect();
                out.insert((body.id.clone(), name.clone()), path);
            }
        }
        out
    }
}

/// What continuation remembers between samples.
#[derive(Debug, Default)]
struct Tracker {
    /// The joint rows' rank at the first sample of the sweep.
    rank: Option<usize>,
    /// The output velocity at the previous sample.
    output: Option<Vec<f64>>,
    /// The last two samples' driver values and rank indicators.
    recent: Vec<(f64, f64)>,
}

impl Tracker {
    /// A new reachable range: no continuity with the previous one.
    fn restart(&mut self) {
        self.output = None;
        self.recent.clear();
    }
}

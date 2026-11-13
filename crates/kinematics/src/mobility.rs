//! Mobility analysis (mechanism-core requirement 6).
//!
//! In maximal coordinates the Grübler–Kutzbach count is the number of unknowns minus the number
//! of joint equations: each moving planar body brings 3, each joint removes as many as it has
//! rows, less the curve parameters it brings (a pin-in-slot has 2 rows and 1 parameter, so it
//! removes 1, as the formula counts a higher pair). The numerical mobility uses the rank of the
//! joint rows instead, so it sees through special geometry: where they differ, the joints whose
//! rows add no rank are the redundant constraints.

use faer::Mat;

use crate::model::Model;
use crate::spatial::Placement;

/// A joint whose equations repeat what earlier joints already impose.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Redundant {
    pub joint_id: String,
    /// How many of its rows are dependent.
    pub rows: usize,
}

/// One body's share of a free motion, per unit of the motion, in world coordinates: the
/// velocity of the body's local origin and its angular velocity.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct BodyMotion {
    pub body_id: String,
    pub translation: [f64; 3],
    pub rotation: [f64; 3],
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Mobility {
    /// Grübler–Kutzbach mobility from body and joint counts (may be negative).
    pub grubler: i64,
    /// Unknowns minus the numerical rank of the joint equations at the pose.
    pub numerical: usize,
    /// Joints with dependent equations, in graph order (requirement 6.2).
    pub redundant: Vec<Redundant>,
    /// Motions the joints and drivers together leave free at the pose (requirement 6.3), each
    /// as the bodies it moves.
    pub free_motions: Vec<Vec<BodyMotion>>,
}

/// Relative tolerance for numerical rank.
const RANK_TOLERANCE: f64 = 1e-9;

fn dense(
    entries: &[(usize, usize, f64)],
    rows: usize,
    n: usize,
    keep: impl Fn(usize) -> bool,
) -> Mat<f64> {
    let mut a = Mat::<f64>::zeros(rows.max(1), n);
    for &(i, j, v) in entries {
        if keep(i) {
            a[(i, j)] += v;
        }
    }
    a
}

fn rank(a: &Mat<f64>, scale: f64) -> usize {
    a.singular_values()
        .map(|s| s.iter().filter(|v| **v > RANK_TOLERANCE * scale).count())
        .unwrap_or(0)
}

impl Model {
    /// Mobility at the assembled pose `q`.
    #[must_use]
    pub fn mobility(&self, q: &[f64], drive: &[f64]) -> Mobility {
        let n = self.n_vars;
        let joint_rows = self.n_rows() - self.drivers.len();
        let entries = self.jacobian(q, drive);
        let scale = entries.iter().fold(1.0_f64, |m, e| m.max(e.2.abs()));

        // Add the joints one at a time; rows that add no rank are redundant.
        let mut redundant = Vec::new();
        let mut row = 0;
        let mut known = 0;
        // Joint constraints come before the drivers.
        for c in &self.constraints[..self.constraints.len() - self.drivers.len()] {
            let end = row + c.dim();
            if end > joint_rows {
                break;
            }
            let r = rank(&dense(&entries, joint_rows, n, |i| i < end), scale);
            if r < known + c.dim() {
                redundant.push(Redundant {
                    joint_id: c.source_id().to_owned(),
                    rows: known + c.dim() - r,
                });
            }
            known = r;
            row = end;
        }

        // Free motions: the null space of the joint and driver rows together.
        let full = dense(&entries, self.n_rows(), n, |_| true);
        let mut free_motions = Vec::new();
        if let Ok(svd) = full.svd() {
            let s = svd.S().column_vector();
            let r = (0..s.nrows())
                .filter(|&i| s[i] > RANK_TOLERANCE * scale)
                .count();
            let v = svd.V();
            for col in r..n {
                let largest = (0..n).fold(0.0_f64, |m, i| m.max(v[(i, col)].abs()));
                let motion: Vec<BodyMotion> = self
                    .bodies
                    .iter()
                    .filter_map(|b| {
                        let dv = |k: usize| v[(k, col)] / largest;
                        let (translation, rotation) = match b.placement {
                            Placement::Planar { index, frame } => {
                                let (dx, dy, dt) = (dv(index), dv(index + 1), dv(index + 2));
                                (
                                    std::array::from_fn(|k| dx * frame.u[k] + dy * frame.v[k]),
                                    std::array::from_fn(|k| dt * frame.normal[k]),
                                )
                            }
                            Placement::Spatial { index } => {
                                // ω = 2 · vec(q̇ q*) for a unit quaternion q.
                                let (w, x, y, z) =
                                    (q[index + 3], q[index + 4], q[index + 5], q[index + 6]);
                                let (dw, dx, dy, dz) =
                                    (dv(index + 3), dv(index + 4), dv(index + 5), dv(index + 6));
                                (
                                    [dv(index), dv(index + 1), dv(index + 2)],
                                    [
                                        2.0 * (-dw * x + dx * w - dy * z + dz * y),
                                        2.0 * (-dw * y + dx * z + dy * w - dz * x),
                                        2.0 * (-dw * z - dx * y + dy * x + dz * w),
                                    ],
                                )
                            }
                            Placement::Fixed { .. } => return None,
                        };
                        let size = translation
                            .iter()
                            .chain(&rotation)
                            .fold(0.0_f64, |m, c| m.max(c.abs()));
                        (size > 1e-9).then(|| BodyMotion {
                            body_id: b.id.clone(),
                            translation,
                            rotation,
                        })
                    })
                    .collect();
                if !motion.is_empty() {
                    free_motions.push(motion);
                }
            }
        }

        #[allow(clippy::cast_possible_wrap, reason = "counts of a mechanism are small")]
        let grubler = n as i64 - joint_rows as i64;
        Mobility {
            grubler,
            numerical: n - known,
            redundant,
            free_motions,
        }
    }
}

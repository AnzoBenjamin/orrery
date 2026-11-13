//! Velocities and accelerations (mechanism-core requirement 5.5).
//!
//! Along a sweep of driver `k`, the constraints `Φ(q(d), d) = 0` hold for every `d`, so
//! `J q′ = e_k` and `J q″ = −γ`, where `γ` is the second derivative of `Φ` along `q′` (from a
//! [`Jet`] evaluation). Points then follow from a Jet evaluation at `q + q′ε + ½q″ε²`.
//! Derivatives are with respect to the driver's value; multiply by the driver's rate (and its
//! square) for time derivatives at a constant rate.

use std::collections::BTreeMap;

use faer::linalg::solvers::SolveLstsqCore;
use faer::{Conj, Mat};

use crate::dual::Jet;
use crate::model::Model;
use crate::planar::V2;

/// A named point's position and its first and second derivatives with respect to the driver,
/// in world coordinates.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PointMotion {
    pub position: [f64; 3],
    pub velocity: [f64; 3],
    pub acceleration: [f64; 3],
}

impl Model {
    /// Solves `J x = rhs` at `q` in the least-squares sense, with the minimum-norm solution when
    /// there are fewer rows than unknowns, so free motions get no velocity.
    fn solve_rows(&self, q: &[f64], drive: &[f64], rhs: &[f64]) -> Vec<f64> {
        let (m, n) = (self.n_rows(), self.n_vars);
        let mut a = Mat::<f64>::zeros(m, n);
        for (i, j, v) in self.jacobian(q, drive) {
            a[(i, j)] += v;
        }
        let mut y = Mat::from_fn(m, 1, |i, _| rhs[i]);
        if m < n {
            let at = a.transpose().to_owned();
            let gram = &a * &at;
            gram.col_piv_qr()
                .solve_lstsq_in_place_with_conj(Conj::No, y.as_mut());
            let x = &at * &y;
            return (0..n).map(|j| x[(j, 0)]).collect();
        }
        a.col_piv_qr()
            .solve_lstsq_in_place_with_conj(Conj::No, y.as_mut());
        (0..n).map(|j| y[(j, 0)]).collect()
    }

    /// The residuals along a Taylor series of the state.
    #[must_use]
    pub fn residuals_jet(&self, q: &[Jet], drive: &[f64]) -> Vec<Jet> {
        let mut out = vec![Jet::default(); self.n_rows()];
        let mut row = 0;
        for c in &self.constraints {
            let d = c.dim();
            c.residual_jet(q, drive, &mut out[row..row + d]);
            row += d;
        }
        out
    }

    /// `dq/dd` for driver `k`.
    #[must_use]
    pub fn velocity(&self, q: &[f64], drive: &[f64], k: usize) -> Vec<f64> {
        let mut rhs = vec![0.0; self.n_rows()];
        rhs[self.n_rows() - self.drivers.len() + k] = 1.0;
        self.solve_rows(q, drive, &rhs)
    }

    /// `d²q/dd²` for driver `k`, given the velocity `dq`.
    #[must_use]
    pub fn acceleration(&self, q: &[f64], drive: &[f64], dq: &[f64]) -> Vec<f64> {
        let jets: Vec<Jet> = q
            .iter()
            .zip(dq)
            .map(|(v, d)| Jet::new(*v, *d, 0.0))
            .collect();
        let gamma: Vec<f64> = self
            .residuals_jet(&jets, drive)
            .iter()
            .map(|r| -2.0 * r.d2)
            .collect();
        self.solve_rows(q, drive, &gamma)
    }

    /// Position, velocity, and acceleration of every named point with respect to driver `k`,
    /// keyed by `(body id, point id)`.
    #[must_use]
    pub fn point_motion(
        &self,
        q: &[f64],
        drive: &[f64],
        k: usize,
    ) -> BTreeMap<(String, String), PointMotion> {
        let dq = self.velocity(q, drive, k);
        let ddq = self.acceleration(q, drive, &dq);
        let jets: Vec<Jet> = (0..self.n_vars)
            .map(|i| Jet::new(q[i], dq[i], 0.5 * ddq[i]))
            .collect();
        let mut out = BTreeMap::new();
        for (i, body) in self.bodies.iter().enumerate() {
            for (name, local) in &body.points {
                if let Some(motion) = self.point_jet(i, *local, &jets) {
                    out.insert((body.id.clone(), name.clone()), motion);
                }
            }
        }
        out
    }

    fn point_jet(&self, body: usize, local: [f64; 3], q: &[Jet]) -> Option<PointMotion> {
        let info = &self.bodies[body];
        let Some(plane) = &info.plane else {
            // A spatial ground does not move.
            return Some(PointMotion {
                position: local,
                velocity: [0.0; 3],
                acceleration: [0.0; 3],
            });
        };
        let frame = self.planes.get(plane)?;
        let p = info.slot.pose(q).apply(V2::new(local[0], local[1]).lift());
        let (x, y) = (p.x, p.y);
        let position = frame.to_world(V2::new(x.v, y.v), local[2]);
        let along = |a: f64, b: f64| std::array::from_fn(|c| a * frame.u[c] + b * frame.v[c]);
        Some(PointMotion {
            position,
            velocity: along(x.d1, y.d1),
            acceleration: along(2.0 * x.d2, 2.0 * y.d2),
        })
    }

    /// Velocity of every output point with respect to driver `k`, stacked.
    pub(crate) fn output_velocity(&self, q: &[f64], drive: &[f64], k: usize) -> Vec<f64> {
        let motion = self.point_motion(q, drive, k);
        self.outputs
            .iter()
            .filter_map(|(b, p)| motion.get(&(self.bodies[*b].id.clone(), p.clone())))
            .flat_map(|m| m.velocity)
            .collect()
    }
}

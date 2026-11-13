//! Springs (mechanism-core requirement 4.4, design "Assembly"): among the poses that satisfy the
//! constraints, the one of least spring energy.
//!
//! Projected Gauss–Newton in the constraint null space: the energy gradient and its Gauss–Newton
//! Hessian are restricted to the motions the constraints allow (an SVD basis of the Jacobian's
//! null space), the step is taken there, and the pose is re-assembled. A backtracking line search
//! keeps each accepted step downhill.

use faer::Mat;
use faer::linalg::solvers::Solve;

use crate::assembly::{Assembly, AssemblyOptions};
use crate::model::Model;

/// Total spring energy at `q`, in joules.
#[must_use]
pub fn spring_energy(model: &Model, q: &[f64]) -> f64 {
    model.springs.iter().map(|s| s.energy(q)).sum()
}

impl Model {
    /// A basis of the motions that keep every constraint satisfied to first order, as columns.
    fn null_space(&self, q: &[f64], drive: &[f64]) -> Option<Mat<f64>> {
        let (m, n) = (self.n_rows(), self.n_vars);
        let mut j = Mat::<f64>::zeros(m.max(1), n);
        for (r, c, v) in self.jacobian(q, drive) {
            j[(r, c)] += v;
        }
        let svd = j.svd().ok()?;
        let s = svd.S().column_vector();
        let largest = (0..s.nrows()).map(|i| s[i]).fold(0.0_f64, f64::max);
        let rank = (0..s.nrows())
            .filter(|&i| s[i] > 1e-10 * largest.max(1.0))
            .count();
        let v = svd.V();
        let free = n - rank;
        (free > 0).then(|| Mat::from_fn(n, free, |r, c| v[(r, rank + c)]))
    }

    /// Moves an assembled pose to the least spring energy without breaking any constraint.
    pub(crate) fn relax(
        &self,
        mut assembly: Assembly,
        drive: &[f64],
        options: &AssemblyOptions,
    ) -> Assembly {
        let n = self.n_vars;
        for _ in 0..100 {
            let q = &assembly.q;
            let energy = spring_energy(self, q);
            let Some(z) = self.null_space(q, drive) else {
                return assembly;
            };
            let free = z.ncols();
            // Gradient and Gauss–Newton Hessian of the energy.
            let mut g = vec![0.0; n];
            let mut h = Mat::<f64>::zeros(n, n);
            let mut force_scale = 0.0_f64;
            for spring in &self.springs {
                let grad = spring.length_gradient(q);
                let tension = spring.stiffness * (spring.length(q) - spring.free_length);
                force_scale = force_scale.max(tension.abs());
                for &(c, v) in &grad {
                    g[c] += tension * v;
                    for &(d, w) in &grad {
                        h[(c, d)] += spring.stiffness * v * w;
                    }
                }
            }
            // Restricted to the null space.
            let gz: Vec<f64> = (0..free)
                .map(|k| (0..n).map(|i| z[(i, k)] * g[i]).sum())
                .collect();
            let gz_norm = gz.iter().map(|v| v * v).sum::<f64>().sqrt();
            if gz_norm <= 1e-11 * (1.0 + force_scale) {
                return assembly;
            }
            let hz = z.transpose() * &h * &z;
            let ridge = 1e-9 * (0..free).map(|k| hz[(k, k)]).fold(0.0_f64, f64::max) + 1e-15;
            let mut a = hz.clone();
            for k in 0..free {
                a[(k, k)] += ridge;
            }
            let rhs = Mat::from_fn(free, 1, |k, _| -gz[k]);
            let y = a.partial_piv_lu().solve(&rhs);
            let step: Vec<f64> = (0..n)
                .map(|i| (0..free).map(|k| z[(i, k)] * y[(k, 0)]).sum())
                .collect();
            let slope: f64 = (0..free).map(|k| gz[k] * y[(k, 0)]).sum();

            let mut t = 1.0;
            let mut accepted = None;
            for _ in 0..30 {
                let trial: Vec<f64> = q.iter().zip(&step).map(|(a, b)| a + t * b).collect();
                let (projected, ok) = self.levenberg_marquardt(trial, drive, options);
                if ok {
                    let e = spring_energy(self, &projected.q);
                    if e <= 1e-4f64.mul_add(t * slope, energy) {
                        accepted = Some(projected);
                        break;
                    }
                }
                t *= 0.5;
            }
            match accepted {
                Some(next) => assembly = next,
                None => return assembly,
            }
        }
        assembly
    }
}

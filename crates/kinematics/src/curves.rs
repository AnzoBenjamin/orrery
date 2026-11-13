//! Slot curves and cam profiles in a body's local 2D frame (mechanism-core requirements 3.5 and
//! 3.6), with the derivatives the constraints need.

use std::f64::consts::TAU;

use crate::planar::V2;

/// A slot curve, parameterized on `[lo, hi]`.
#[derive(Debug, Clone, PartialEq)]
pub enum Curve {
    /// `start + s (end − start)`, `s ∈ [0, 1]`.
    Line { start: V2, end: V2 },
    /// `center + radius (cos a, sin a)`, `a` between the two angles.
    Arc {
        center: V2,
        radius: f64,
        a0: f64,
        a1: f64,
    },
    /// Cubic B-spline with the given knot vector, on `[knots[3], knots[n]]`.
    BSpline { control: Vec<V2>, knots: Vec<f64> },
}

impl Curve {
    /// Builds a B-spline after checking its knot vector.
    pub fn bspline(control: Vec<V2>, knots: Vec<f64>) -> Result<Self, String> {
        if knots.len() != control.len() + 4 {
            return Err(format!(
                "a cubic B-spline with {} control points needs {} knots, found {}",
                control.len(),
                control.len() + 4,
                knots.len()
            ));
        }
        if knots.windows(2).any(|w| w[1] < w[0]) {
            return Err("the knot vector must not decrease".into());
        }
        if knots[3] >= knots[control.len()] {
            return Err("the knot vector leaves the curve no parameter range".into());
        }
        Ok(Self::BSpline { control, knots })
    }

    /// The parameter range.
    #[must_use]
    pub fn bounds(&self) -> (f64, f64) {
        match self {
            Self::Line { .. } => (0.0, 1.0),
            Self::Arc { a0, a1, .. } => (a0.min(*a1), a0.max(*a1)),
            Self::BSpline { control, knots } => (knots[3], knots[control.len()]),
        }
    }

    /// The point and its derivative with respect to the parameter.
    #[must_use]
    pub fn eval(&self, s: f64) -> (V2, V2) {
        match self {
            Self::Line { start, end } => (*start + (*end - *start) * s, *end - *start),
            Self::Arc { center, radius, .. } => {
                let (sin, cos) = s.sin_cos();
                (
                    *center + V2::new(cos, sin) * *radius,
                    V2::new(-sin, cos) * *radius,
                )
            }
            Self::BSpline { control, knots } => de_boor(control, knots, s),
        }
    }
}

/// Cubic B-spline point and derivative by de Boor's algorithm. Outside the range the end
/// polynomial pieces are extended, so the solver sees a smooth function everywhere.
fn de_boor(control: &[V2], knots: &[f64], s: f64) -> (V2, V2) {
    let n = control.len();
    // The span k with knots[k] <= s < knots[k + 1], clamped to the valid spans [3, n − 1].
    let mut k = 3;
    while k < n - 1 && s >= knots[k + 1] {
        k += 1;
    }
    let d: [V2; 4] = std::array::from_fn(|j| control[k - 3 + j]);
    // Derivative control points of the degree-2 spline.
    let dd: [V2; 3] = std::array::from_fn(|j| {
        let i = k - 3 + j + 1;
        let span = knots[i + 3] - knots[i];
        if span > 0.0 {
            (control[i] - control[i - 1]) * (3.0 / span)
        } else {
            V2::default()
        }
    });
    let point = de_boor_level(&d, knots, k, s, 3);
    let derivative = de_boor_level(&dd, &knots[1..], k - 1, s, 2);
    (point, derivative)
}

fn de_boor_level<const N: usize>(pts: &[V2; N], knots: &[f64], k: usize, s: f64, p: usize) -> V2 {
    let mut d = *pts;
    for r in 1..=p {
        for j in (r..=p).rev() {
            let i = k + j - p;
            let span = knots[i + 1 + p - r] - knots[i];
            let alpha = if span > 0.0 {
                (s - knots[i]) / span
            } else {
                0.0
            };
            d[j] = d[j - 1] * (1.0 - alpha) + d[j] * alpha;
        }
    }
    d[p]
}

/// A cam's radial profile `ρ(ψ) = base + Σ (aₙ cos nψ + bₙ sin nψ)`, `n` from 0 (`a₀` is a constant
/// offset), in the cam body's frame.
#[derive(Debug, Clone, PartialEq)]
pub struct CamProfile {
    pub base: f64,
    pub a: Vec<f64>,
    pub b: Vec<f64>,
}

impl CamProfile {
    /// `ρ`, `ρ'`, and `ρ''` at angle `psi`.
    #[must_use]
    pub fn radius(&self, psi: f64) -> (f64, f64, f64) {
        let mut r = (self.base, 0.0, 0.0);
        for n in 0..self.a.len().max(self.b.len()) {
            let a = self.a.get(n).copied().unwrap_or(0.0);
            let b = if n == 0 {
                0.0
            } else {
                self.b.get(n).copied().unwrap_or(0.0)
            };
            #[allow(clippy::cast_precision_loss, reason = "harmonic numbers are small")]
            let k = n as f64;
            let (sin, cos) = (k * psi).sin_cos();
            r.0 += a.mul_add(cos, b * sin);
            r.1 += k * b.mul_add(cos, -a * sin);
            r.2 -= k * k * a.mul_add(cos, b * sin);
        }
        r
    }

    /// The profile point `c(ψ) = ρ(ψ) (cos ψ, sin ψ)` and its first two derivatives.
    #[must_use]
    pub fn point(&self, psi: f64) -> (V2, V2, V2) {
        let (r, r1, r2) = self.radius(psi);
        let (sin, cos) = psi.sin_cos();
        let u = V2::new(cos, sin);
        let up = u.perp();
        let c = u * r;
        let c1 = u * r1 + up * r;
        let c2 = u * (r2 - r) + up * (2.0 * r1);
        (c, c1, c2)
    }

    /// The point a roller of radius `roller` centers on when touching the profile at `psi`:
    /// `c + roller · n`, with `n` the outward unit normal, and its derivative in `psi`.
    #[must_use]
    pub fn roller_center(&self, psi: f64, roller: f64) -> (V2, V2) {
        let (c, t, t1) = self.point(psi);
        let len = t.norm();
        // Outward normal of a counter-clockwise curve: the tangent turned clockwise.
        let n = V2::new(t.y, -t.x) * (1.0 / len);
        let dt_unit = (t1 * (1.0 / len)) - t * (t.dot(t1) / (len * len * len));
        let dn = V2::new(dt_unit.y, -dt_unit.x);
        (c + n * roller, t + dn * roller)
    }

    /// The profile as a closed polyline whose chords stay within `tolerance` of the curve.
    #[must_use]
    pub fn polyline(&self, tolerance: f64) -> Vec<V2> {
        let tolerance = tolerance.max(1e-9);
        let mut out = Vec::new();
        let samples = 32_u32;
        for i in 0..samples {
            let a = TAU * f64::from(i) / f64::from(samples);
            let b = TAU * f64::from(i + 1) / f64::from(samples);
            out.push(self.point(a).0);
            self.refine(a, b, tolerance, 12, &mut out);
        }
        out
    }

    /// Adds points strictly between `a` and `b` until the chord deviation is within tolerance.
    fn refine(&self, a: f64, b: f64, tolerance: f64, depth: u32, out: &mut Vec<V2>) {
        let (pa, pb) = (self.point(a).0, self.point(b).0);
        let mid = 0.5 * (a + b);
        let pm = self.point(mid).0;
        let chord = pb - pa;
        let len = chord.norm();
        let deviation = if len > 0.0 {
            (pm - pa).dot(chord.perp()).abs() / len
        } else {
            0.0
        };
        if deviation > tolerance && depth > 0 {
            self.refine(a, mid, tolerance, depth - 1, out);
            out.push(pm);
            self.refine(mid, b, tolerance, depth - 1, out);
        }
    }
}

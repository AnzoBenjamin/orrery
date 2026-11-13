//! Forward-mode automatic differentiation to second order (mechanism-core design, "Simulation
//! and singularities": accelerations from the second-order term).
//!
//! A [`Jet`] is a truncated Taylor series `v + d₁ε + d₂ε²`. Evaluating the residuals at
//! `q + q′ε` gives `Φ + (J q′) ε + ½ γ ε²` in one pass, where `γ` is the second directional
//! derivative the acceleration equation `J q″ = −γ` needs.

use std::fmt::Debug;
use std::ops::{Add, Div, Mul, Neg, Sub};

/// The number type residuals are written in: `f64` for solving, [`Jet`] for derivatives.
pub trait Scalar:
    Copy
    + Debug
    + PartialEq
    + Add<Output = Self>
    + Sub<Output = Self>
    + Mul<Output = Self>
    + Div<Output = Self>
    + Neg<Output = Self>
    + Add<f64, Output = Self>
    + Sub<f64, Output = Self>
    + Mul<f64, Output = Self>
{
    fn cst(value: f64) -> Self;
    /// The plain value, for comparisons and branch choices.
    fn value(self) -> f64;
    fn sin(self) -> Self;
    fn cos(self) -> Self;
    fn sqrt(self) -> Self;
    fn sin_cos(self) -> (Self, Self) {
        (self.sin(), self.cos())
    }
}

impl Scalar for f64 {
    fn cst(value: f64) -> Self {
        value
    }
    fn value(self) -> f64 {
        self
    }
    fn sin(self) -> Self {
        f64::sin(self)
    }
    fn cos(self) -> Self {
        f64::cos(self)
    }
    fn sqrt(self) -> Self {
        f64::sqrt(self)
    }
    fn sin_cos(self) -> (Self, Self) {
        f64::sin_cos(self)
    }
}

/// `v + d1·ε + d2·ε²`, with `ε³ = 0`. The second derivative is `2·d2`.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Jet {
    pub v: f64,
    pub d1: f64,
    pub d2: f64,
}

impl Jet {
    #[must_use]
    pub const fn new(v: f64, d1: f64, d2: f64) -> Self {
        Self { v, d1, d2 }
    }

    /// `f(v) + f′(v)·d1 ε + (f′(v)·d2 + ½f″(v)·d1²) ε²` for a scalar function with value `f0` and
    /// derivatives `f1`, `f2` at `v`.
    fn chain(self, f0: f64, f1: f64, f2: f64) -> Self {
        Self::new(
            f0,
            f1 * self.d1,
            f1.mul_add(self.d2, 0.5 * f2 * self.d1 * self.d1),
        )
    }
}

impl Add for Jet {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::new(self.v + o.v, self.d1 + o.d1, self.d2 + o.d2)
    }
}
impl Sub for Jet {
    type Output = Self;
    fn sub(self, o: Self) -> Self {
        Self::new(self.v - o.v, self.d1 - o.d1, self.d2 - o.d2)
    }
}
impl Mul for Jet {
    type Output = Self;
    fn mul(self, o: Self) -> Self {
        Self::new(
            self.v * o.v,
            self.v.mul_add(o.d1, self.d1 * o.v),
            self.v.mul_add(o.d2, self.d1.mul_add(o.d1, self.d2 * o.v)),
        )
    }
}
impl Div for Jet {
    type Output = Self;
    fn div(self, o: Self) -> Self {
        let r = 1.0 / o.v;
        self * o.chain(r, -r * r, 2.0 * r * r * r)
    }
}
impl Neg for Jet {
    type Output = Self;
    fn neg(self) -> Self {
        Self::new(-self.v, -self.d1, -self.d2)
    }
}
impl Add<f64> for Jet {
    type Output = Self;
    fn add(self, o: f64) -> Self {
        Self::new(self.v + o, self.d1, self.d2)
    }
}
impl Sub<f64> for Jet {
    type Output = Self;
    fn sub(self, o: f64) -> Self {
        Self::new(self.v - o, self.d1, self.d2)
    }
}
impl Mul<f64> for Jet {
    type Output = Self;
    fn mul(self, o: f64) -> Self {
        Self::new(self.v * o, self.d1 * o, self.d2 * o)
    }
}

impl Scalar for Jet {
    fn cst(value: f64) -> Self {
        Self::new(value, 0.0, 0.0)
    }
    fn value(self) -> f64 {
        self.v
    }
    fn sin(self) -> Self {
        let (s, c) = self.v.sin_cos();
        self.chain(s, c, -s)
    }
    fn cos(self) -> Self {
        let (s, c) = self.v.sin_cos();
        self.chain(c, -s, -c)
    }
    fn sqrt(self) -> Self {
        let r = self.v.sqrt();
        self.chain(r, 0.5 / r, -0.25 / (r * self.v))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// f(x) = sin(x)·√x / (1 + cos x)² along x = x0 + ε: compare with finite differences.
    #[test]
    fn jets_carry_first_and_second_derivatives() {
        fn f<T: Scalar>(x: T) -> T {
            let d = x.cos() + 1.0;
            x.sin() * x.sqrt() / (d * d)
        }
        let x0 = 0.7;
        let jet = f(Jet::new(x0, 1.0, 0.0));
        let h = 1e-4;
        let d1 = (f(x0 + h) - f(x0 - h)) / (2.0 * h);
        let d2 = (f(x0 + h) - 2.0 * f(x0) + f(x0 - h)) / (h * h);
        assert!((jet.v - f(x0)).abs() < 1e-15);
        assert!((jet.d1 - d1).abs() < 1e-7);
        assert!((2.0 * jet.d2 - d2).abs() < 1e-5);
    }
}

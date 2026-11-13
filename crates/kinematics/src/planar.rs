//! Planar geometry in a plane's 2D frame. A planar body's pose is `(x, y, θ)`: the position of
//! its local origin and the counter-clockwise rotation of its local frame, both in `plane:<id>`.
//!
//! The types are generic over the number type so the same formulas give values (`f64`) and
//! derivatives ([`crate::dual::Jet`]).

use crate::dual::Scalar;

/// A 2D vector in meters.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct V2<T = f64> {
    pub x: T,
    pub y: T,
}

impl<T: Scalar> V2<T> {
    #[must_use]
    pub const fn new(x: T, y: T) -> Self {
        Self { x, y }
    }

    #[must_use]
    pub fn dot(self, o: Self) -> T {
        self.x * o.x + self.y * o.y
    }

    /// Rotated a quarter turn counter-clockwise.
    #[must_use]
    pub fn perp(self) -> Self {
        Self {
            x: -self.y,
            y: self.x,
        }
    }

    #[must_use]
    pub fn norm(self) -> T {
        self.dot(self).sqrt()
    }

    /// Scaled by a number of the same type.
    #[must_use]
    pub fn scale(self, k: T) -> Self {
        Self::new(self.x * k, self.y * k)
    }
}

impl V2<f64> {
    /// The same vector in another number type, as a constant.
    #[must_use]
    pub fn lift<T: Scalar>(self) -> V2<T> {
        V2 {
            x: T::cst(self.x),
            y: T::cst(self.y),
        }
    }
}

impl<T: Scalar> std::ops::Add for V2<T> {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::new(self.x + o.x, self.y + o.y)
    }
}

impl<T: Scalar> std::ops::Sub for V2<T> {
    type Output = Self;
    fn sub(self, o: Self) -> Self {
        Self::new(self.x - o.x, self.y - o.y)
    }
}

impl<T: Scalar> std::ops::Mul<f64> for V2<T> {
    type Output = Self;
    fn mul(self, k: f64) -> Self {
        Self::new(self.x * k, self.y * k)
    }
}

/// A planar pose: position and rotation in the plane frame.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Pose2<T = f64> {
    pub x: T,
    pub y: T,
    pub theta: T,
}

impl<T: Scalar> Pose2<T> {
    /// `R(θ) v`.
    #[must_use]
    pub fn rotate(self, v: V2<T>) -> V2<T> {
        let (s, c) = self.theta.sin_cos();
        V2::new(c * v.x - s * v.y, s * v.x + c * v.y)
    }

    /// `dR(θ)/dθ · v`, which equals `R(θ) v` turned a quarter turn.
    #[must_use]
    pub fn rotate_derivative(self, v: V2<T>) -> V2<T> {
        self.rotate(v).perp()
    }

    /// A point given in the body's local frame, in the plane frame.
    #[must_use]
    pub fn apply(self, local: V2<T>) -> V2<T> {
        V2::new(self.x, self.y) + self.rotate(local)
    }
}

impl Pose2<f64> {
    /// The same pose in another number type, as a constant.
    #[must_use]
    pub fn lift<T: Scalar>(self) -> Pose2<T> {
        Pose2 {
            x: T::cst(self.x),
            y: T::cst(self.y),
            theta: T::cst(self.theta),
        }
    }
}

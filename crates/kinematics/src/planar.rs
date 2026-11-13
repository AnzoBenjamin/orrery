//! Planar geometry in a plane's 2D frame. A planar body's pose is `(x, y, θ)`: the position of
//! its local origin and the counter-clockwise rotation of its local frame, both in `plane:<id>`.

/// A 2D vector in meters.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct V2 {
    pub x: f64,
    pub y: f64,
}

impl V2 {
    #[must_use]
    pub const fn new(x: f64, y: f64) -> Self {
        Self { x, y }
    }

    #[must_use]
    pub fn dot(self, o: Self) -> f64 {
        self.x.mul_add(o.x, self.y * o.y)
    }

    /// Rotated a quarter turn counter-clockwise.
    #[must_use]
    pub const fn perp(self) -> Self {
        Self {
            x: -self.y,
            y: self.x,
        }
    }

    #[must_use]
    pub fn norm(self) -> f64 {
        self.x.hypot(self.y)
    }
}

impl std::ops::Add for V2 {
    type Output = Self;
    fn add(self, o: Self) -> Self {
        Self::new(self.x + o.x, self.y + o.y)
    }
}

impl std::ops::Sub for V2 {
    type Output = Self;
    fn sub(self, o: Self) -> Self {
        Self::new(self.x - o.x, self.y - o.y)
    }
}

impl std::ops::Mul<f64> for V2 {
    type Output = Self;
    fn mul(self, k: f64) -> Self {
        Self::new(self.x * k, self.y * k)
    }
}

/// A planar pose: position and rotation in the plane frame.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Pose2 {
    pub x: f64,
    pub y: f64,
    pub theta: f64,
}

impl Pose2 {
    /// `R(θ) v`.
    #[must_use]
    pub fn rotate(self, v: V2) -> V2 {
        let (s, c) = self.theta.sin_cos();
        V2::new(c.mul_add(v.x, -s * v.y), s.mul_add(v.x, c * v.y))
    }

    /// `dR(θ)/dθ · v`, which equals `R(θ) v` turned a quarter turn.
    #[must_use]
    pub fn rotate_derivative(self, v: V2) -> V2 {
        self.rotate(v).perp()
    }

    /// A point given in the body's local frame, in the plane frame.
    #[must_use]
    pub fn apply(self, local: V2) -> V2 {
        V2::new(self.x, self.y) + self.rotate(local)
    }
}

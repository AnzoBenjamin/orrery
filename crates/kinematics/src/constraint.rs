//! Joint constraints as residual equations with analytic Jacobians (mechanism-core design,
//! "Constraints"). Each constraint reads body poses from the state vector `q` and writes its
//! residual rows; driver values arrive separately so the same model serves every crank angle.

use crate::planar::{Pose2, V2};

/// Where a body's pose comes from: fixed (the ground) or three unknowns in `q`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BodySlot {
    Fixed(Pose2),
    /// Index of the body's `x` in `q`; `y` and `θ` follow.
    Var(usize),
}

impl BodySlot {
    #[must_use]
    pub fn pose(self, q: &[f64]) -> Pose2 {
        match self {
            Self::Fixed(p) => p,
            Self::Var(i) => Pose2 {
                x: q[i],
                y: q[i + 1],
                theta: q[i + 2],
            },
        }
    }
}

/// One nonzero Jacobian entry: row, column, value.
pub type Entry = (usize, usize, f64);

/// Adds the derivative of a world point `r + R(θ) p` of `slot`, weighted by `w`, to row `row`.
/// `dθ` is the derivative of the point with respect to θ.
fn push_point(out: &mut Vec<Entry>, row: usize, slot: BodySlot, w: V2, d_theta: V2, sign: f64) {
    if let BodySlot::Var(i) = slot {
        if w.x != 0.0 {
            out.push((row, i, sign * w.x));
        }
        if w.y != 0.0 {
            out.push((row, i + 1, sign * w.y));
        }
        out.push((row, i + 2, sign * w.dot(d_theta)));
    }
}

fn push_theta(out: &mut Vec<Entry>, row: usize, slot: BodySlot, value: f64) {
    if let BodySlot::Var(i) = slot {
        out.push((row, i + 2, value));
    }
}

/// A joint's residual equations.
pub trait Constraint: std::fmt::Debug + Send + Sync {
    /// The joint (or driver) these rows belong to, for diagnostics.
    fn source_id(&self) -> &str;
    /// Number of residual rows.
    fn dim(&self) -> usize;
    /// Writes `dim()` residuals into `out`.
    fn residual(&self, q: &[f64], drive: &[f64], out: &mut [f64]);
    /// Appends the Jacobian rows, starting at `row`, with respect to `q`.
    fn jacobian(&self, q: &[f64], drive: &[f64], row: usize, out: &mut Vec<Entry>);
}

/// Planar revolute joint: the two anchors coincide (2 rows, meters).
#[derive(Debug, Clone)]
pub struct Revolute {
    pub id: String,
    pub a: BodySlot,
    pub anchor_a: V2,
    pub b: BodySlot,
    pub anchor_b: V2,
}

impl Constraint for Revolute {
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
    }
    fn residual(&self, q: &[f64], _: &[f64], out: &mut [f64]) {
        let d = self.a.pose(q).apply(self.anchor_a) - self.b.pose(q).apply(self.anchor_b);
        out[0] = d.x;
        out[1] = d.y;
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        let (pa, pb) = (self.a.pose(q), self.b.pose(q));
        let (da, db) = (
            pa.rotate_derivative(self.anchor_a),
            pb.rotate_derivative(self.anchor_b),
        );
        for (k, w) in [V2::new(1.0, 0.0), V2::new(0.0, 1.0)]
            .into_iter()
            .enumerate()
        {
            push_point(out, row + k, self.a, w, da, 1.0);
            push_point(out, row + k, self.b, w, db, -1.0);
        }
    }
}

/// Planar prismatic joint: B's anchor stays on the line through A's anchor along `axis` (in A's
/// frame), and B keeps the rotation of A (2 rows: meters, radians).
///
/// The relative rotation is held at zero: B's local frame is parallel to A's. Mechanism graphs
/// state slider frames that way, so no reference angle needs storing.
#[derive(Debug, Clone)]
pub struct Prismatic {
    pub id: String,
    pub a: BodySlot,
    pub anchor_a: V2,
    /// Unit slide direction in A's frame.
    pub axis: V2,
    pub b: BodySlot,
    pub anchor_b: V2,
}

impl Prismatic {
    /// Offset of B's anchor from A's along the world direction `R(θA) dir`, with its derivative.
    fn along(&self, q: &[f64], dir: V2, row: usize, out: Option<&mut Vec<Entry>>) -> f64 {
        let (pa, pb) = (self.a.pose(q), self.b.pose(q));
        let dir_world = pa.rotate(dir);
        let d = pb.apply(self.anchor_b) - pa.apply(self.anchor_a);
        if let Some(out) = out {
            push_point(
                out,
                row,
                self.b,
                dir_world,
                pb.rotate_derivative(self.anchor_b),
                1.0,
            );
            push_point(
                out,
                row,
                self.a,
                dir_world,
                pa.rotate_derivative(self.anchor_a),
                -1.0,
            );
            // The direction turns with A as well.
            push_theta(out, row, self.a, pa.rotate_derivative(dir).dot(d));
        }
        dir_world.dot(d)
    }

    /// The slide coordinate: B's anchor's offset from A's along the axis (meters).
    #[must_use]
    pub fn displacement(&self, q: &[f64]) -> f64 {
        self.along(q, self.axis, 0, None)
    }

    fn displacement_jacobian(&self, q: &[f64], row: usize, out: &mut Vec<Entry>) {
        self.along(q, self.axis, row, Some(out));
    }
}

impl Constraint for Prismatic {
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
    }
    fn residual(&self, q: &[f64], _: &[f64], out: &mut [f64]) {
        out[0] = self.along(q, self.axis.perp(), 0, None);
        out[1] = self.b.pose(q).theta - self.a.pose(q).theta;
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        self.along(q, self.axis.perp(), row, Some(out));
        push_theta(out, row + 1, self.b, 1.0);
        push_theta(out, row + 1, self.a, -1.0);
    }
}

/// What a driver sets.
#[derive(Debug, Clone)]
pub enum DrivenCoordinate {
    /// θB − θA of a revolute joint (radians).
    Angle { a: BodySlot, b: BodySlot },
    /// The slide coordinate of a prismatic joint (meters).
    Displacement(Prismatic),
}

/// A driver: the joint coordinate equals the driver's value (1 row).
#[derive(Debug, Clone)]
pub struct Driver {
    pub id: String,
    /// The joint whose coordinate is set.
    pub joint_id: String,
    /// Index into the driver values.
    pub index: usize,
    pub coordinate: DrivenCoordinate,
}

impl Driver {
    /// The joint coordinate the driver sets, at `q`.
    #[must_use]
    pub fn coordinate_value(&self, q: &[f64]) -> f64 {
        match &self.coordinate {
            DrivenCoordinate::Angle { a, b } => b.pose(q).theta - a.pose(q).theta,
            DrivenCoordinate::Displacement(p) => p.displacement(q),
        }
    }
}

impl Constraint for Driver {
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        1
    }
    fn residual(&self, q: &[f64], drive: &[f64], out: &mut [f64]) {
        out[0] = self.coordinate_value(q) - drive[self.index];
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        match &self.coordinate {
            DrivenCoordinate::Angle { a, b } => {
                push_theta(out, row, *b, 1.0);
                push_theta(out, row, *a, -1.0);
            }
            DrivenCoordinate::Displacement(p) => p.displacement_jacobian(q, row, out),
        }
    }
}

//! Spatial bodies and joints (mechanism-core requirements 3.3 and 3.4, design "State").
//!
//! A spatial body's pose is a position and a unit quaternion `(w, x, y, z)` in the state, with
//! one residual row holding the quaternion at unit length. Joints are written in world
//! coordinates against a [`Placement`], so they connect spatial bodies, the ground, and planar
//! bodies in any plane: planar subsystems in different planes meet through these joints.
//!
//! The Jacobians come from forward-mode [`Jet`] passes over just the unknowns each joint
//! touches, so they are exact.

use crate::constraint::{Constraint, Entry};
use crate::dual::{Jet, Scalar};
use crate::model::PlaneFrame;

pub type V3<T = f64> = [T; 3];

fn add<T: Scalar>(a: V3<T>, b: V3<T>) -> V3<T> {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
fn sub<T: Scalar>(a: V3<T>, b: V3<T>) -> V3<T> {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn scale<T: Scalar>(a: V3<T>, k: T) -> V3<T> {
    [a[0] * k, a[1] * k, a[2] * k]
}
pub fn dot<T: Scalar>(a: V3<T>, b: V3<T>) -> T {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}
pub fn cross<T: Scalar>(a: V3<T>, b: V3<T>) -> V3<T> {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn lift<T: Scalar>(a: V3) -> V3<T> {
    [T::cst(a[0]), T::cst(a[1]), T::cst(a[2])]
}

/// `q v q*` for a unit quaternion `(w, u)`: `v + 2w (u × v) + 2u × (u × v)`.
pub fn quat_rotate<T: Scalar>(w: T, u: V3<T>, v: V3<T>) -> V3<T> {
    let t = cross(u, v);
    add(add(v, scale(t, w * 2.0)), scale(cross(u, t), T::cst(2.0)))
}

/// Two unit vectors perpendicular to `axis` and to each other, right-handed with it.
#[must_use]
pub fn perpendiculars(axis: V3) -> (V3, V3) {
    let helper = if axis[0].abs() < 0.9 {
        [1.0, 0.0, 0.0]
    } else {
        [0.0, 1.0, 0.0]
    };
    let p = cross(axis, helper);
    let n = dot(p, p).sqrt();
    let p = [p[0] / n, p[1] / n, p[2] / n];
    (p, cross(axis, p))
}

/// Normalized copy of `v`, or `None` when it has no length.
#[must_use]
pub fn unit(v: V3) -> Option<V3> {
    let n = dot(v, v).sqrt();
    (n > 1e-12 && n.is_finite()).then(|| [v[0] / n, v[1] / n, v[2] / n])
}

/// Where a body is in the world.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Placement {
    /// The ground: `world = origin + basis · local` (basis columns are the local axes).
    Fixed { origin: V3, basis: [V3; 3] },
    /// A planar body: `(x, y, θ)` at `index` in the plane `frame`.
    Planar { index: usize, frame: PlaneFrame },
    /// A spatial body: position at `index`, quaternion `(w, x, y, z)` at `index + 3`.
    Spatial { index: usize },
}

impl Placement {
    /// A local direction in world coordinates.
    pub fn rotate<T: Scalar>(&self, q: &[T], v: V3) -> V3<T> {
        match self {
            Self::Fixed { basis, .. } => std::array::from_fn(|k| {
                T::cst(basis[0][k] * v[0] + basis[1][k] * v[1] + basis[2][k] * v[2])
            }),
            Self::Planar { index, frame } => {
                let (s, c) = q[index + 2].sin_cos();
                let x = c * v[0] - s * v[1];
                let y = s * v[0] + c * v[1];
                std::array::from_fn(|k| x * frame.u[k] + y * frame.v[k] + frame.normal[k] * v[2])
            }
            Self::Spatial { index } => {
                let i = *index;
                quat_rotate(q[i + 3], [q[i + 4], q[i + 5], q[i + 6]], lift(v))
            }
        }
    }

    /// A local point in world coordinates.
    pub fn point<T: Scalar>(&self, q: &[T], local: V3) -> V3<T> {
        let origin: V3<T> = match self {
            Self::Fixed { origin, .. } => lift(*origin),
            Self::Planar { index, frame } => std::array::from_fn(|k| {
                q[*index] * frame.u[k] + q[index + 1] * frame.v[k] + frame.origin[k]
            }),
            Self::Spatial { index } => [q[*index], q[index + 1], q[index + 2]],
        };
        add(origin, self.rotate(q, local))
    }

    /// The unknowns this placement reads.
    #[must_use]
    pub fn vars(&self) -> Vec<usize> {
        match self {
            Self::Fixed { .. } => Vec::new(),
            Self::Planar { index, .. } => (*index..index + 3).collect(),
            Self::Spatial { index } => (*index..index + 7).collect(),
        }
    }
}

/// The equations of a spatial joint.
#[derive(Debug, Clone)]
pub enum SpatialKind {
    /// Anchors coincide (3 rows).
    Spherical,
    /// Anchors coincide and the two cross arms stay perpendicular (4 rows).
    Universal { arm_a: V3, arm_b: V3 },
    /// Anchors coincide and B turns about `axis` only; B uses the same local axis (5 rows).
    Revolute { axis: V3, perp: (V3, V3) },
    /// B's anchor stays on A's axis line and B keeps A's orientation (5 rows).
    Prismatic { axis: V3, perp: (V3, V3) },
    /// B's anchor stays on A's axis line and the two axes stay parallel (4 rows).
    Cylindrical {
        axis_a: V3,
        perp_a: (V3, V3),
        axis_b: V3,
        perp_b: (V3, V3),
    },
}

#[derive(Debug, Clone)]
pub struct SpatialJoint {
    pub id: String,
    pub a: Placement,
    pub anchor_a: V3,
    pub b: Placement,
    pub anchor_b: V3,
    pub kind: SpatialKind,
    /// Allowed slide range of a prismatic joint, in meters.
    pub limits: Option<(f64, f64)>,
}

impl SpatialJoint {
    fn eval<T: Scalar>(&self, q: &[T], out: &mut [T]) {
        let (pa, pb) = (
            self.a.point(q, self.anchor_a),
            self.b.point(q, self.anchor_b),
        );
        let d = sub(pb, pa);
        let coincide = |out: &mut [T]| {
            out[0] = d[0];
            out[1] = d[1];
            out[2] = d[2];
        };
        match &self.kind {
            SpatialKind::Spherical => coincide(out),
            SpatialKind::Universal { arm_a, arm_b } => {
                coincide(out);
                out[3] = dot(self.a.rotate(q, *arm_a), self.b.rotate(q, *arm_b));
            }
            SpatialKind::Revolute { axis, perp } => {
                coincide(out);
                let a = self.a.rotate(q, *axis);
                out[3] = dot(a, self.b.rotate(q, perp.0));
                out[4] = dot(a, self.b.rotate(q, perp.1));
            }
            SpatialKind::Prismatic { perp, .. } => {
                out[0] = dot(d, self.a.rotate(q, perp.0));
                out[1] = dot(d, self.a.rotate(q, perp.1));
                let (ex, ey, ez) = ([1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]);
                out[2] = dot(self.b.rotate(q, ex), self.a.rotate(q, ey));
                out[3] = dot(self.b.rotate(q, ey), self.a.rotate(q, ez));
                out[4] = dot(self.b.rotate(q, ez), self.a.rotate(q, ex));
            }
            SpatialKind::Cylindrical {
                axis_a,
                perp_a,
                perp_b,
                ..
            } => {
                out[0] = dot(d, self.a.rotate(q, perp_a.0));
                out[1] = dot(d, self.a.rotate(q, perp_a.1));
                let a = self.a.rotate(q, *axis_a);
                out[2] = dot(a, self.b.rotate(q, perp_b.0));
                out[3] = dot(a, self.b.rotate(q, perp_b.1));
            }
        }
    }

    fn vars(&self) -> Vec<usize> {
        let mut v = self.a.vars();
        v.extend(self.b.vars());
        v
    }

    /// The slide coordinate of a prismatic joint: B's anchor's offset along A's axis.
    pub fn displacement<T: Scalar>(&self, q: &[T]) -> T {
        let axis = match &self.kind {
            SpatialKind::Prismatic { axis, .. } => *axis,
            SpatialKind::Cylindrical { axis_a, .. } => *axis_a,
            _ => [0.0, 0.0, 0.0],
        };
        let d = sub(
            self.b.point(q, self.anchor_b),
            self.a.point(q, self.anchor_a),
        );
        dot(d, self.a.rotate(q, axis))
    }
}

/// Appends the Jacobian of `eval` over `vars` from one Jet pass per unknown.
pub(crate) fn jet_jacobian(
    q: &[f64],
    vars: &[usize],
    dim: usize,
    row: usize,
    out: &mut Vec<Entry>,
    eval: impl Fn(&[Jet], &mut [Jet]),
) {
    let mut jets: Vec<Jet> = q.iter().map(|v| Jet::new(*v, 0.0, 0.0)).collect();
    let mut r = vec![Jet::default(); dim];
    let mut seen = Vec::with_capacity(vars.len());
    for &j in vars {
        if seen.contains(&j) {
            continue;
        }
        seen.push(j);
        jets[j].d1 = 1.0;
        eval(&jets, &mut r);
        jets[j].d1 = 0.0;
        for (k, value) in r.iter().enumerate() {
            if value.d1 != 0.0 {
                out.push((row + k, j, value.d1));
            }
        }
    }
}

impl Constraint for SpatialJoint {
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        match self.kind {
            SpatialKind::Spherical => 3,
            SpatialKind::Universal { .. } | SpatialKind::Cylindrical { .. } => 4,
            SpatialKind::Revolute { .. } | SpatialKind::Prismatic { .. } => 5,
        }
    }
    fn residual(&self, q: &[f64], _: &[f64], out: &mut [f64]) {
        self.eval(q, out);
    }
    fn residual_jet(&self, q: &[Jet], _: &[f64], out: &mut [Jet]) {
        self.eval(q, out);
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        jet_jacobian(q, &self.vars(), self.dim(), row, out, |jq, r| {
            self.eval(jq, r)
        });
    }
    fn violation(&self, q: &[f64]) -> Option<f64> {
        let (lo, hi) = self.limits?;
        let s = self.displacement(q);
        let outside = (lo - s).max(s - hi);
        (outside > 1e-9).then_some(outside)
    }
}

/// Keeps a spatial body's quaternion at unit length (1 row).
#[derive(Debug, Clone)]
pub struct UnitQuaternion {
    pub id: String,
    /// Index of `w`.
    pub index: usize,
}

impl UnitQuaternion {
    fn eval<T: Scalar>(&self, q: &[T], out: &mut [T]) {
        let i = self.index;
        out[0] =
            q[i] * q[i] + q[i + 1] * q[i + 1] + q[i + 2] * q[i + 2] + q[i + 3] * q[i + 3] - 1.0;
    }
}

impl Constraint for UnitQuaternion {
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        1
    }
    fn residual(&self, q: &[f64], _: &[f64], out: &mut [f64]) {
        self.eval(q, out);
    }
    fn residual_jet(&self, q: &[Jet], _: &[f64], out: &mut [Jet]) {
        self.eval(q, out);
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        for k in 0..4 {
            out.push((row, self.index + k, 2.0 * q[self.index + k]));
        }
    }
}

/// The angle a driver sets on a spatial revolute: B's reference arm `perp.0` turns from A's by
/// the driver's value about the axis. The residual is `sin(φ − d)`, zero where the angle `φ`
/// equals the value `d`, with slope 1 there.
pub(crate) fn spatial_angle<T: Scalar>(joint: &SpatialJoint, q: &[T], value: f64) -> T {
    let SpatialKind::Revolute { perp, .. } = &joint.kind else {
        return T::cst(0.0);
    };
    let (p, r) = (joint.a.rotate(q, perp.0), joint.a.rotate(q, perp.1));
    let target = add(
        scale(p, T::cst(-value.sin())),
        scale(r, T::cst(value.cos())),
    );
    dot(joint.b.rotate(q, perp.0), target)
}

/// `vars` of a spatial joint, for the driver's Jacobian.
pub(crate) fn joint_vars(joint: &SpatialJoint) -> Vec<usize> {
    joint.vars()
}

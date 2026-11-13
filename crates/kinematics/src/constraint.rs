//! Joint constraints as residual equations with analytic Jacobians (mechanism-core design,
//! "Constraints"). Each constraint reads body poses from the state vector `q` and writes its
//! residual rows; driver values arrive separately so the same model serves every crank angle.
//!
//! Each residual is written once over [`Scalar`], so it gives values (`f64`) for solving and
//! Taylor coefficients ([`Jet`]) for velocities and accelerations.

use crate::curves::{CamProfile, Curve};
use crate::dual::{Jet, Scalar};
use crate::planar::{Pose2, V2};
use crate::spatial::{SpatialJoint, jet_jacobian, joint_vars, spatial_angle};

/// Where a body's pose comes from: fixed (the ground), three planar unknowns in `q`, or a
/// spatial pose (position and quaternion, seven unknowns).
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BodySlot {
    Fixed(Pose2),
    /// Index of the body's `x` in `q`; `y` and `θ` follow.
    Var(usize),
    /// Index of the body's position in `q`; the quaternion `(w, x, y, z)` follows.
    Spatial(usize),
}

impl BodySlot {
    #[must_use]
    pub fn pose<T: Scalar>(self, q: &[T]) -> Pose2<T> {
        match self {
            Self::Fixed(p) => p.lift(),
            Self::Var(i) => Pose2 {
                x: q[i],
                y: q[i + 1],
                theta: q[i + 2],
            },
            // Planar constraints are only built between planar bodies and the ground
            // (`Model::compile_joint` routes every joint touching a spatial body to
            // `SpatialJoint`), so no planar pose of a spatial body is ever asked for.
            Self::Spatial(_) => unreachable!("planar pose of a spatial body"),
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

/// Golden-section search for the least value of `f` on `[lo, hi]`, where it has one minimum (a
/// grid point's neighborhood). Grid starts are within a step of the answer; a pose drawn exactly
/// on a curve needs the parameter to rounding so it is recognized as already assembled.
fn refine_minimum(mut lo: f64, mut hi: f64, mut f: impl FnMut(f64) -> f64) -> f64 {
    let ratio = 0.5 * (5.0_f64.sqrt() - 1.0);
    let (mut a, mut b) = (hi - ratio * (hi - lo), lo + ratio * (hi - lo));
    let (mut fa, mut fb) = (f(a), f(b));
    for _ in 0..80 {
        if fa < fb {
            hi = b;
            (b, fb) = (a, fa);
            a = hi - ratio * (hi - lo);
            fa = f(a);
        } else {
            lo = a;
            (a, fa) = (b, fb);
            b = lo + ratio * (hi - lo);
            fb = f(b);
        }
    }
    0.5 * (lo + hi)
}

/// A joint's residual equations.
pub trait Constraint: std::fmt::Debug + Send + Sync {
    /// The joint (or driver) these rows belong to, for diagnostics.
    fn source_id(&self) -> &str;
    /// Number of residual rows.
    fn dim(&self) -> usize;
    /// Writes `dim()` residuals into `out`.
    fn residual(&self, q: &[f64], drive: &[f64], out: &mut [f64]);
    /// The residuals along a Taylor series of the state.
    fn residual_jet(&self, q: &[Jet], drive: &[f64], out: &mut [Jet]);
    /// Appends the Jacobian rows, starting at `row`, with respect to `q`.
    fn jacobian(&self, q: &[f64], drive: &[f64], row: usize, out: &mut Vec<Entry>);
    /// Sets this constraint's own unknowns (curve parameters) to a good start for the body
    /// poses already in `q`.
    fn init_aux(&self, _q: &mut [f64]) {}
    /// How far the pose at `q` is outside a range the joint allows (a slot's ends, a slider's
    /// limits), in meters, or `None` when it is inside.
    fn violation(&self, _q: &[f64]) -> Option<f64> {
        None
    }
}

/// Implements the two residual methods through the constraint's generic `eval`.
macro_rules! residuals {
    () => {
        fn residual(&self, q: &[f64], drive: &[f64], out: &mut [f64]) {
            self.eval(q, drive, out);
        }
        fn residual_jet(&self, q: &[Jet], drive: &[f64], out: &mut [Jet]) {
            self.eval(q, drive, out);
        }
    };
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

impl Revolute {
    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        let d =
            self.a.pose(q).apply(self.anchor_a.lift()) - self.b.pose(q).apply(self.anchor_b.lift());
        out[0] = d.x;
        out[1] = d.y;
    }
}

impl Constraint for Revolute {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
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
    /// Allowed displacement range, in meters.
    pub limits: Option<(f64, f64)>,
}

impl Prismatic {
    /// Offset of B's anchor from A's along the world direction `R(θA) dir`.
    fn along<T: Scalar>(&self, q: &[T], dir: V2) -> T {
        let (pa, pb) = (self.a.pose(q), self.b.pose(q));
        let d = pb.apply(self.anchor_b.lift()) - pa.apply(self.anchor_a.lift());
        pa.rotate(dir.lift()).dot(d)
    }

    /// The derivative of [`Self::along`], appended to row `row`.
    fn along_jacobian(&self, q: &[f64], dir: V2, row: usize, out: &mut Vec<Entry>) {
        let (pa, pb) = (self.a.pose(q), self.b.pose(q));
        let dir_world = pa.rotate(dir);
        let d = pb.apply(self.anchor_b) - pa.apply(self.anchor_a);
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

    /// The slide coordinate: B's anchor's offset from A's along the axis (meters).
    #[must_use]
    pub fn displacement<T: Scalar>(&self, q: &[T]) -> T {
        self.along(q, self.axis)
    }

    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        out[0] = self.along(q, self.axis.perp());
        out[1] = self.b.pose(q).theta - self.a.pose(q).theta;
    }
}

impl Constraint for Prismatic {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        self.along_jacobian(q, self.axis.perp(), row, out);
        push_theta(out, row + 1, self.b, 1.0);
        push_theta(out, row + 1, self.a, -1.0);
    }
    fn violation(&self, q: &[f64]) -> Option<f64> {
        let (lo, hi) = self.limits?;
        let s = self.displacement(q);
        let outside = (lo - s).max(s - hi);
        (outside > 1e-9).then_some(outside)
    }
}

/// What a driver sets.
#[derive(Debug, Clone)]
pub enum DrivenCoordinate {
    /// θB − θA of a revolute joint (radians).
    Angle { a: BodySlot, b: BodySlot },
    /// The slide coordinate of a prismatic joint (meters).
    Displacement(Prismatic),
    /// The turn of a spatial revolute about its axis (radians).
    SpatialAngle(SpatialJoint),
    /// The slide of a spatial prismatic or cylindrical joint along its axis (meters).
    SpatialDisplacement(SpatialJoint),
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
    /// The driver's residual: zero where the joint coordinate equals `value`, with slope one
    /// in the coordinate there.
    fn row<T: Scalar>(&self, q: &[T], value: f64) -> T {
        match &self.coordinate {
            DrivenCoordinate::Angle { a, b } => b.pose(q).theta - a.pose(q).theta - value,
            DrivenCoordinate::Displacement(p) => p.displacement(q) - value,
            DrivenCoordinate::SpatialAngle(j) => spatial_angle(j, q, value),
            DrivenCoordinate::SpatialDisplacement(j) => j.displacement(q) - value,
        }
    }

    fn eval<T: Scalar>(&self, q: &[T], drive: &[f64], out: &mut [T]) {
        out[0] = self.row(q, drive[self.index]);
    }
}

impl Constraint for Driver {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        1
    }
    fn jacobian(&self, q: &[f64], drive: &[f64], row: usize, out: &mut Vec<Entry>) {
        match &self.coordinate {
            DrivenCoordinate::Angle { a, b } => {
                push_theta(out, row, *b, 1.0);
                push_theta(out, row, *a, -1.0);
            }
            DrivenCoordinate::Displacement(p) => p.along_jacobian(q, p.axis, row, out),
            DrivenCoordinate::SpatialAngle(j) | DrivenCoordinate::SpatialDisplacement(j) => {
                let value = drive[self.index];
                jet_jacobian(q, &joint_vars(j), 1, row, out, |jq, r| {
                    r[0] = self.row(jq, value)
                });
            }
        }
    }
}

/// Pin-in-slot: the pin coincides with the slot curve at parameter `s`, an extra unknown
/// (2 rows, 1 unknown).
#[derive(Debug, Clone)]
pub struct PinInSlot {
    pub id: String,
    pub pin_body: BodySlot,
    pub pin: V2,
    pub slot_body: BodySlot,
    /// The slot in the slot body's frame.
    pub curve: Curve,
    /// Index of `s` in `q`.
    pub s_index: usize,
}

impl PinInSlot {
    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        let (c, _) = self.curve.eval(q[self.s_index]);
        let d = self.pin_body.pose(q).apply(self.pin.lift()) - self.slot_body.pose(q).apply(c);
        out[0] = d.x;
        out[1] = d.y;
    }
}

impl Constraint for PinInSlot {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        let (pp, ps) = (self.pin_body.pose(q), self.slot_body.pose(q));
        let (c, dc) = self.curve.eval(q[self.s_index]);
        let along = ps.rotate(dc);
        let (dp, dsl) = (pp.rotate_derivative(self.pin), ps.rotate_derivative(c));
        for (k, w) in [V2::new(1.0, 0.0), V2::new(0.0, 1.0)]
            .into_iter()
            .enumerate()
        {
            push_point(out, row + k, self.pin_body, w, dp, 1.0);
            push_point(out, row + k, self.slot_body, w, dsl, -1.0);
            out.push((row + k, self.s_index, -w.dot(along)));
        }
    }
    fn init_aux(&self, q: &mut [f64]) {
        let target = self.pin_body.pose(q).apply(self.pin);
        let pose = self.slot_body.pose(q);
        let (lo, hi) = self.curve.bounds();
        let samples = 64_u32;
        let step = (hi - lo) / f64::from(samples);
        let distance = |s: f64| (pose.apply(self.curve.eval(s).0) - target).norm();
        let best = (0..=samples)
            .map(|i| lo + step * f64::from(i))
            .min_by(|a, b| distance(*a).total_cmp(&distance(*b)))
            .unwrap_or(lo);
        q[self.s_index] = refine_minimum((best - step).max(lo), (best + step).min(hi), distance);
    }
    fn violation(&self, q: &[f64]) -> Option<f64> {
        let s = q[self.s_index];
        let (lo, hi) = self.curve.bounds();
        let outside = (lo - s).max(s - hi);
        // In meters: the parameter overshoot times the curve's speed at the nearer end.
        let end = if s < lo { lo } else { hi };
        let meters = outside * self.curve.eval(end).1.norm();
        (outside > 0.0 && meters > 1e-9).then_some(meters)
    }
}

/// Gear mesh or belt: `(θA − θC) = ratio · (θB − θC) + phase`, angles relative to the carrier `C`
/// both wheels turn on (1 row, radians). For a gear, `ratio` is teeth B over teeth A, negative for
/// an external mesh; for a belt, radius B over radius A, negative when crossed.
#[derive(Debug, Clone)]
pub struct AngleRatio {
    pub id: String,
    pub a: BodySlot,
    pub b: BodySlot,
    pub carrier: BodySlot,
    pub ratio: f64,
    pub phase: f64,
}

impl AngleRatio {
    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        let c = self.carrier.pose(q).theta;
        let (ta, tb) = (self.a.pose(q).theta - c, self.b.pose(q).theta - c);
        out[0] = ta - tb * self.ratio - self.phase;
    }
}

impl Constraint for AngleRatio {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        1
    }
    fn jacobian(&self, _: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        push_theta(out, row, self.a, 1.0);
        push_theta(out, row, self.b, -self.ratio);
        push_theta(out, row, self.carrier, self.ratio - 1.0);
    }
}

/// Rack and pinion: the rack's displacement along its axis, relative to the carrier both ride on,
/// is `ratio` (the pinion's pitch radius, meters per radian) times the pinion's angle relative to
/// the carrier, plus `phase` (1 row, meters).
#[derive(Debug, Clone)]
pub struct RackMesh {
    pub id: String,
    pub pinion: BodySlot,
    pub rack: BodySlot,
    pub carrier: BodySlot,
    /// Unit slide direction in the rack's frame.
    pub axis: V2,
    pub ratio: f64,
    pub phase: f64,
}

impl RackMesh {
    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        let (rack, carrier) = (self.rack.pose(q), self.carrier.pose(q));
        let offset = V2::new(rack.x - carrier.x, rack.y - carrier.y);
        let along = rack.rotate(self.axis.lift()).dot(offset);
        let turned = self.pinion.pose(q).theta - carrier.theta;
        out[0] = along - turned * self.ratio - self.phase;
    }
}

impl Constraint for RackMesh {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        1
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        let (rack, carrier) = (self.rack.pose(q), self.carrier.pose(q));
        let dir = rack.rotate(self.axis);
        let offset = V2::new(rack.x - carrier.x, rack.y - carrier.y);
        let zero = V2::new(0.0, 0.0);
        push_point(out, row, self.rack, dir, zero, 1.0);
        push_point(out, row, self.carrier, dir, zero, -1.0);
        // The direction turns with the rack.
        push_theta(
            out,
            row,
            self.rack,
            rack.rotate_derivative(self.axis).dot(offset),
        );
        push_theta(out, row, self.pinion, -self.ratio);
        push_theta(out, row, self.carrier, self.ratio);
    }
}

/// The follower's contact with a cam.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FollowerShape {
    /// The follower point touches the profile.
    Knife,
    /// The follower point is the center of a roller of this radius.
    Roller(f64),
    /// A flat face through the follower point along the follower's local x axis.
    Flat,
}

/// Cam and follower in contact at profile angle `ψ`, an extra unknown (2 rows, 1 unknown).
#[derive(Debug, Clone)]
pub struct CamContact {
    pub id: String,
    pub cam: BodySlot,
    pub profile: CamProfile,
    pub follower: BodySlot,
    pub point: V2,
    pub shape: FollowerShape,
    /// Index of `ψ` in `q`.
    pub psi_index: usize,
}

impl CamContact {
    /// The cam-frame point the follower point must reach, and its derivative in ψ.
    fn target<T: Scalar>(&self, psi: T) -> (V2<T>, V2<T>) {
        match self.shape {
            FollowerShape::Roller(r) => self.profile.roller_center(psi, r),
            FollowerShape::Knife | FollowerShape::Flat => {
                let (c, c1, _) = self.profile.point(psi);
                (c, c1)
            }
        }
    }

    fn eval<T: Scalar>(&self, q: &[T], _: &[f64], out: &mut [T]) {
        let (pc, pf) = (self.cam.pose(q), self.follower.pose(q));
        let psi = q[self.psi_index];
        let follower = pf.apply(self.point.lift());
        if self.shape == FollowerShape::Flat {
            let (c, c1, _) = self.profile.point(psi);
            let normal = pf.rotate(V2::new(T::cst(0.0), T::cst(1.0)));
            out[0] = normal.dot(pc.apply(c) - follower);
            out[1] = normal.dot(pc.rotate(c1));
        } else {
            let d = follower - pc.apply(self.target(psi).0);
            out[0] = d.x;
            out[1] = d.y;
        }
    }
}

impl Constraint for CamContact {
    residuals!();
    fn source_id(&self) -> &str {
        &self.id
    }
    fn dim(&self) -> usize {
        2
    }
    fn jacobian(&self, q: &[f64], _: &[f64], row: usize, out: &mut Vec<Entry>) {
        let (pc, pf) = (self.cam.pose(q), self.follower.pose(q));
        let psi = q[self.psi_index];
        if self.shape == FollowerShape::Flat {
            let (c, c1, c2) = self.profile.point(psi);
            let normal = pf.rotate(V2::new(0.0, 1.0));
            let d_normal = pf.rotate_derivative(V2::new(0.0, 1.0));
            let gap = pc.apply(c) - pf.apply(self.point);
            // Row 1: the profile point lies on the face.
            push_point(out, row, self.cam, normal, pc.rotate_derivative(c), 1.0);
            push_point(
                out,
                row,
                self.follower,
                normal,
                pf.rotate_derivative(self.point),
                -1.0,
            );
            push_theta(out, row, self.follower, d_normal.dot(gap));
            out.push((row, self.psi_index, normal.dot(pc.rotate(c1))));
            // Row 2: the profile tangent there is parallel to the face.
            push_theta(out, row + 1, self.cam, normal.dot(pc.rotate_derivative(c1)));
            push_theta(out, row + 1, self.follower, d_normal.dot(pc.rotate(c1)));
            out.push((row + 1, self.psi_index, normal.dot(pc.rotate(c2))));
        } else {
            let (t, dt) = self.target(psi);
            let (df, dc) = (pf.rotate_derivative(self.point), pc.rotate_derivative(t));
            let along = pc.rotate(dt);
            for (k, w) in [V2::new(1.0, 0.0), V2::new(0.0, 1.0)]
                .into_iter()
                .enumerate()
            {
                push_point(out, row + k, self.follower, w, df, 1.0);
                push_point(out, row + k, self.cam, w, dc, -1.0);
                out.push((row + k, self.psi_index, -w.dot(along)));
            }
        }
    }
    fn init_aux(&self, q: &mut [f64]) {
        let samples = 180_u32;
        let step = std::f64::consts::TAU / f64::from(samples);
        let mut residual = [0.0; 2];
        let mut trial = q.to_vec();
        let mut cost = |psi: f64| {
            trial[self.psi_index] = psi;
            self.eval(&trial, &[], &mut residual);
            residual[0].hypot(residual[1])
        };
        let best = (0..samples)
            .map(|i| step * f64::from(i))
            .min_by(|a, b| cost(*a).total_cmp(&cost(*b)))
            .unwrap_or(0.0);
        q[self.psi_index] = refine_minimum(best - step, best + step, cost);
    }
}

/// A linear spring: energy `k (L − L₀)² / 2`, no residual rows (design: "Springs do not add
/// residuals").
#[derive(Debug, Clone)]
pub struct Spring {
    pub id: String,
    pub a: BodySlot,
    pub anchor_a: V2,
    pub b: BodySlot,
    pub anchor_b: V2,
    pub stiffness: f64,
    pub free_length: f64,
}

impl Spring {
    /// The spring's length at `q`, in meters.
    #[must_use]
    pub fn length(&self, q: &[f64]) -> f64 {
        (self.b.pose(q).apply(self.anchor_b) - self.a.pose(q).apply(self.anchor_a)).norm()
    }

    /// The spring's energy in joules.
    #[must_use]
    pub fn energy(&self, q: &[f64]) -> f64 {
        let stretch = self.length(q) - self.free_length;
        0.5 * self.stiffness * stretch * stretch
    }

    /// The gradient of the length with respect to `q`, as (column, value) entries.
    #[must_use]
    pub fn length_gradient(&self, q: &[f64]) -> Vec<(usize, f64)> {
        let (pa, pb) = (self.a.pose(q), self.b.pose(q));
        let d = pb.apply(self.anchor_b) - pa.apply(self.anchor_a);
        let len = d.norm();
        if len < 1e-15 {
            return Vec::new();
        }
        let u = d * (1.0 / len);
        let mut rows = Vec::new();
        push_point(
            &mut rows,
            0,
            self.b,
            u,
            pb.rotate_derivative(self.anchor_b),
            1.0,
        );
        push_point(
            &mut rows,
            0,
            self.a,
            u,
            pa.rotate_derivative(self.anchor_a),
            -1.0,
        );
        rows.into_iter().map(|(_, c, v)| (c, v)).collect()
    }
}

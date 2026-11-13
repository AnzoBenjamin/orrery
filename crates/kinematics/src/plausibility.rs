//! Physical plausibility over a simulated cycle (mechanism-core requirement 8): transmission
//! angles and Grashof classes of four-bar loops, collisions between body outlines, and
//! fabrication risk indicators.

use std::collections::{BTreeMap, BTreeSet};

use faer::linalg::solvers::SolveLstsqCore;
use faer::{Conj, Mat};
use parry2d_f64::math::{Pose, Vector};
use parry2d_f64::query::intersection_test;
use parry2d_f64::shape::SharedShape;

use crate::assembly::AssemblyOptions;
use crate::constraint::BodySlot;
use crate::model::{Link, Model};
use crate::planar::V2;
use crate::simulate::Simulation;

/// Grashof class of a four-bar loop (requirement 8.2).
#[derive(serde::Serialize)]
#[serde(rename_all = "snake_case")]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GrashofClass {
    /// Shortest link beside the frame: it turns fully, the opposite link rocks.
    CrankRocker,
    /// Shortest link is the frame: both side links turn fully.
    DoubleCrank,
    /// Grashof with the shortest link as coupler: the coupler turns fully, both sides rock.
    DoubleRocker,
    /// s + l = p + q: the loop can fold flat and change branch.
    ChangePoint,
    /// s + l > p + q: no link turns fully.
    TripleRocker,
}

/// The least transmission angle at one floating joint of a loop over the cycle.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Transmission {
    pub joint_id: String,
    /// The angle between the two links at the joint, folded to `[0, π/2]`: π/2 transmits best,
    /// 0 is a toggle.
    pub min_angle: f64,
    /// The driver value where it occurs.
    pub at: f64,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct FourBarLoop {
    /// Frame, input, coupler, output.
    pub bodies: [String; 4],
    /// Frame–input, input–coupler, coupler–output, output–frame.
    pub joints: [String; 4],
    /// Frame, input, coupler, output lengths, in meters.
    pub lengths: [f64; 4],
    pub grashof: GrashofClass,
    /// At the input–coupler and coupler–output joints.
    pub transmission: Vec<Transmission>,
}

/// Two outlines overlapping, over driver ranges (requirement 8.3).
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Collision {
    pub bodies: (String, String),
    /// Inclusive driver ranges where they overlap.
    pub ranges: Vec<(f64, f64)>,
}

/// Where a joint's reaction force flips direction (requirement 8.4).
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct ReactionReversal {
    pub joint_id: String,
    /// Driver values where the reaction passes through a reversal.
    pub at: Vec<f64>,
    /// Largest reaction over the cycle, in newtons per newton of load.
    pub peak: f64,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
#[derive(Debug, Clone, PartialEq)]
pub struct Plausibility {
    pub loops: Vec<FourBarLoop>,
    pub collisions: Vec<Collision>,
    /// Length over width of each body with an outline (requirement 8.4).
    pub slenderness: Vec<(String, f64)>,
    pub reaction_reversals: Vec<ReactionReversal>,
}

/// Triangles of a simple polygon by ear clipping, in counter-clockwise order.
fn triangulate(polygon: &[V2]) -> Vec<[V2; 3]> {
    let mut pts: Vec<V2> = polygon.to_vec();
    let area: f64 = (0..pts.len())
        .map(|i| {
            let (a, b) = (pts[i], pts[(i + 1) % pts.len()]);
            a.x * b.y - b.x * a.y
        })
        .sum();
    if area < 0.0 {
        pts.reverse();
    }
    let cross = |o: V2, a: V2, b: V2| (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    let mut out = Vec::new();
    let mut guard = 0;
    while pts.len() > 3 && guard < 10_000 {
        guard += 1;
        let n = pts.len();
        let ear = (0..n).find(|&i| {
            let (a, b, c) = (pts[(i + n - 1) % n], pts[i], pts[(i + 1) % n]);
            cross(a, b, c) > 0.0
                && pts.iter().enumerate().all(|(j, &p)| {
                    j == i
                        || j == (i + n - 1) % n
                        || j == (i + 1) % n
                        || !(cross(a, b, p) >= 0.0
                            && cross(b, c, p) >= 0.0
                            && cross(c, a, p) >= 0.0)
                })
        });
        let Some(i) = ear else { break };
        out.push([pts[(i + n - 1) % n], pts[i], pts[(i + 1) % n]]);
        pts.remove(i);
    }
    if pts.len() == 3 {
        out.push([pts[0], pts[1], pts[2]]);
    }
    out
}

/// An outline as a parry compound of triangles, in the body's local 2D frame.
fn outline_shape(polygon: &[V2]) -> Option<SharedShape> {
    let parts: Vec<(Pose, SharedShape)> = triangulate(polygon)
        .into_iter()
        .map(|[a, b, c]| {
            (
                Pose::IDENTITY,
                SharedShape::triangle(
                    Vector::new(a.x, a.y),
                    Vector::new(b.x, b.y),
                    Vector::new(c.x, c.y),
                ),
            )
        })
        .collect();
    (!parts.is_empty()).then(|| SharedShape::compound(parts))
}

impl Model {
    /// Four-bar loops: cycles of four bodies joined by revolute joints.
    fn four_bar_loops(&self) -> Vec<([usize; 4], [usize; 4])> {
        let revolutes: Vec<(usize, usize, usize)> = self
            .links
            .iter()
            .enumerate()
            .filter(|(_, (_, _, l))| matches!(l, Link::Revolute(_)))
            .map(|(i, (a, b, _))| (*a, *b, i))
            .collect();
        let edge = |x: usize, y: usize| {
            revolutes
                .iter()
                .find(|(a, b, _)| (*a == x && *b == y) || (*a == y && *b == x))
                .map(|e| e.2)
        };
        let n = self.bodies.len();
        let mut seen = BTreeSet::new();
        let mut loops = Vec::new();
        for a in 0..n {
            for b in 0..n {
                for c in 0..n {
                    for d in 0..n {
                        let set = [a, b, c, d];
                        if set.iter().collect::<BTreeSet<_>>().len() < 4 {
                            continue;
                        }
                        let (Some(e1), Some(e2), Some(e3), Some(e4)) =
                            (edge(a, b), edge(b, c), edge(c, d), edge(d, a))
                        else {
                            continue;
                        };
                        let mut key = vec![e1, e2, e3, e4];
                        key.sort_unstable();
                        if seen.insert(key) {
                            loops.push((set, [e1, e2, e3, e4]));
                        }
                    }
                }
            }
        }
        // Orient each: the frame first (the ground, else the lowest index), then the driven side.
        loops
            .into_iter()
            .map(|(set, edges)| {
                let start = set
                    .iter()
                    .position(|&b| self.bodies[b].is_ground)
                    .unwrap_or_else(|| (0..4).min_by_key(|&i| set[i]).unwrap_or(0));
                let rot = |i: usize| (start + i) % 4;
                let bodies = [set[rot(0)], set[rot(1)], set[rot(2)], set[rot(3)]];
                // Edges: e_i joins set[i] and set[i+1].
                let joints = [
                    edges[rot(0)],
                    edges[rot(1)],
                    edges[rot(2)],
                    edges[(start + 3) % 4],
                ];
                let driven = |e: usize| {
                    let id = link_id(&self.links[e].2);
                    self.drivers.iter().any(|d| d.joint_id == id)
                };
                if driven(joints[3]) && !driven(joints[0]) {
                    // Reverse so the input is the driven side.
                    (
                        [bodies[0], bodies[3], bodies[2], bodies[1]],
                        [joints[3], joints[2], joints[1], joints[0]],
                    )
                } else {
                    (bodies, joints)
                }
            })
            .collect()
    }

    /// The anchor of a revolute on `body`, in that body's local plane coordinates.
    fn anchor_on(&self, edge: usize, body: usize) -> V2 {
        let (a, _, link) = &self.links[edge];
        match link {
            Link::Revolute(r) => {
                if *a == body {
                    r.anchor_a
                } else {
                    r.anchor_b
                }
            }
            Link::Prismatic(p) => {
                if *a == body {
                    p.anchor_a
                } else {
                    p.anchor_b
                }
            }
            // Four-bar loops are found among planar revolutes only.
            Link::Spatial(_) => V2::default(),
        }
    }

    fn anchor_world(&self, edge: usize, body: usize, q: &[f64]) -> V2 {
        self.bodies[body]
            .slot
            .pose(q)
            .apply(self.anchor_on(edge, body))
    }

    /// Plausibility over a simulation of driver `k` (other drivers at `drive`).
    #[must_use]
    pub fn plausibility(&self, sim: &Simulation, k: usize, drive: &[f64]) -> Plausibility {
        Plausibility {
            loops: self.loop_report(sim),
            collisions: self.collisions(sim, k, drive),
            slenderness: self.slenderness(),
            reaction_reversals: self.reaction_reversals(sim, k, drive),
        }
    }

    fn loop_report(&self, sim: &Simulation) -> Vec<FourBarLoop> {
        self.four_bar_loops()
            .into_iter()
            .map(|(b, e)| {
                let len = |body: usize, e1: usize, e2: usize| {
                    (self.anchor_on(e1, body) - self.anchor_on(e2, body)).norm()
                };
                let lengths = [
                    len(b[0], e[3], e[0]),
                    len(b[1], e[0], e[1]),
                    len(b[2], e[1], e[2]),
                    len(b[3], e[2], e[3]),
                ];
                let grashof = classify(lengths);
                // Transmission at input–coupler (between input and coupler) and coupler–output.
                let mut transmission = Vec::new();
                for (joint, (first, second), (far1, far2)) in [
                    (e[1], (b[1], b[2]), (e[0], e[2])),
                    (e[2], (b[2], b[3]), (e[1], e[3])),
                ] {
                    let mut best = (f64::INFINITY, 0.0);
                    for s in &sim.samples {
                        let at = self.anchor_world(joint, first, &s.q);
                        let u = self.anchor_world(far1, first, &s.q) - at;
                        let v = self.anchor_world(far2, second, &s.q) - at;
                        let cos = (u.dot(v) / (u.norm() * v.norm())).clamp(-1.0, 1.0);
                        let mu = cos.acos();
                        let folded = mu.min(std::f64::consts::PI - mu);
                        if folded < best.0 {
                            best = (folded, s.drive);
                        }
                    }
                    transmission.push(Transmission {
                        joint_id: link_id(&self.links[joint].2),
                        min_angle: best.0,
                        at: best.1,
                    });
                }
                FourBarLoop {
                    bodies: b.map(|i| self.bodies[i].id.clone()),
                    joints: e.map(|i| link_id(&self.links[i].2)),
                    lengths,
                    grashof,
                    transmission,
                }
            })
            .collect()
    }

    /// Bodies with outlines, with their parry shapes, thicknesses, and planes.
    fn shapes(&self) -> Vec<(usize, SharedShape, f64, Vec<V2>)> {
        self.bodies
            .iter()
            .enumerate()
            .filter_map(|(i, b)| {
                let (polygon, thickness) = b.outline.as_ref()?;
                let shape = outline_shape(polygon)?;
                Some((i, shape, *thickness, polygon.clone()))
            })
            .collect()
    }

    /// Pairs of bodies whose outlines can meet: not joined by any joint, in the same plane or in
    /// parallel planes closer than their half thicknesses.
    fn collision_pairs(&self) -> Vec<(usize, usize)> {
        let shapes = self.shapes();
        let mut pairs = Vec::new();
        for (x, (i, _, ti, _)) in shapes.iter().enumerate() {
            for (j, _, tj, _) in &shapes[x + 1..] {
                if self.joined.contains(&(*i.min(j), *i.max(j))) {
                    continue;
                }
                let (Some(pi), Some(pj)) = (&self.bodies[*i].plane, &self.bodies[*j].plane) else {
                    continue;
                };
                let (Some(fi), Some(fj)) = (self.planes.get(pi), self.planes.get(pj)) else {
                    continue;
                };
                let parallel = (fi.normal[0] * fj.normal[0]
                    + fi.normal[1] * fj.normal[1]
                    + fi.normal[2] * fj.normal[2])
                    .abs()
                    > 1.0 - 1e-9;
                let gap = (0..3)
                    .map(|c| (fj.origin[c] - fi.origin[c]) * fi.normal[c])
                    .sum::<f64>()
                    .abs();
                // Same plane, parallel planes closer than the half thicknesses, or planes that
                // cross (checked as extruded prisms in 3D).
                if pi == pj || (parallel && gap < 0.5 * (ti + tj)) || !parallel {
                    pairs.push((*i, *j));
                }
            }
        }
        pairs
    }

    /// Whether two bodies move in planes that are not parallel.
    fn crossing_planes(&self, i: usize, j: usize) -> bool {
        let normal = |b: usize| {
            self.bodies[b]
                .plane
                .as_ref()
                .and_then(|p| self.planes.get(p))
                .map(|f| f.normal)
        };
        match (normal(i), normal(j)) {
            (Some(a), Some(b)) => (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]).abs() <= 1.0 - 1e-9,
            _ => false,
        }
    }

    /// Each outline extruded through its thickness, centered on its plane, as a parry3d compound
    /// of triangular prisms in the body's local frame.
    fn prisms(&self) -> BTreeMap<usize, parry3d_f64::shape::SharedShape> {
        use parry3d_f64::math::{Pose as Pose3, Vector as Vector3};
        use parry3d_f64::shape::SharedShape as Shape3;
        self.bodies
            .iter()
            .enumerate()
            .filter_map(|(i, b)| {
                let (polygon, thickness) = b.outline.as_ref()?;
                let h = 0.5 * thickness;
                let parts: Vec<(Pose3, Shape3)> = triangulate(polygon)
                    .into_iter()
                    .filter_map(|tri| {
                        let points: Vec<Vector3> = tri
                            .iter()
                            .flat_map(|p| [Vector3::new(p.x, p.y, -h), Vector3::new(p.x, p.y, h)])
                            .collect();
                        Shape3::convex_hull(&points).map(|s| (Pose3::IDENTITY, s))
                    })
                    .collect();
                (!parts.is_empty()).then(|| (i, Shape3::compound(parts)))
            })
            .collect()
    }

    /// A body's pose in the world, for parry3d.
    fn world_pose(&self, body: usize, q: &[f64]) -> parry3d_f64::math::Pose {
        use parry3d_f64::math::{Mat3, Pose as Pose3, Rot3, Vector as Vector3};
        let placement = &self.bodies[body].placement;
        let t = placement.point(q, [0.0; 3]);
        let col = |v: [f64; 3]| {
            let w = placement.rotate(q, v);
            Vector3::new(w[0], w[1], w[2])
        };
        let rotation = Rot3::from_mat3(&Mat3::from_cols(
            col([1.0, 0.0, 0.0]),
            col([0.0, 1.0, 0.0]),
            col([0.0, 0.0, 1.0]),
        ));
        Pose3::from_parts(Vector3::new(t[0], t[1], t[2]), rotation)
    }

    /// The pairs of `pairs` whose outlines overlap at `q`.
    fn overlapping(
        &self,
        q: &[f64],
        pairs: &[(usize, usize)],
        shapes: &BTreeMap<usize, SharedShape>,
        prisms: &BTreeMap<usize, parry3d_f64::shape::SharedShape>,
    ) -> BTreeSet<(usize, usize)> {
        let pose_in = |body: usize, reference: usize| -> Option<Pose> {
            let frame = self.planes.get(self.bodies[body].plane.as_ref()?)?;
            let target = self.planes.get(self.bodies[reference].plane.as_ref()?)?;
            let p = self.bodies[body].slot.pose(q);
            // Body origin and x axis in world, then in the reference plane's coordinates.
            let origin = target.project_point(frame.to_world(V2::new(p.x, p.y), 0.0));
            let tip = target.project_point(
                frame.to_world(V2::new(p.x + p.theta.cos(), p.y + p.theta.sin()), 0.0),
            );
            let angle = (tip.y - origin.y).atan2(tip.x - origin.x);
            Some(Pose::new(Vector::new(origin.x, origin.y), angle))
        };
        pairs
            .iter()
            .filter(|(i, j)| {
                if let (Some(a), Some(b)) = (prisms.get(i), prisms.get(j))
                    && self.crossing_planes(*i, *j)
                {
                    let (pa, pb) = (self.world_pose(*i, q), self.world_pose(*j, q));
                    return parry3d_f64::query::intersection_test(&pa, a.as_ref(), &pb, b.as_ref())
                        .is_ok_and(|r| r.intersecting);
                }
                let (Some(a), Some(b), Some(sa), Some(sb)) = (
                    pose_in(*i, *i),
                    pose_in(*j, *i),
                    shapes.get(i),
                    shapes.get(j),
                ) else {
                    return false;
                };
                intersection_test(&a, sa.as_ref(), &b, sb.as_ref()).is_ok_and(|r| r.intersecting)
            })
            .copied()
            .collect()
    }

    fn collisions(&self, sim: &Simulation, k: usize, drive: &[f64]) -> Vec<Collision> {
        let pairs = self.collision_pairs();
        if pairs.is_empty() || sim.samples.is_empty() {
            return Vec::new();
        }
        let shapes: BTreeMap<usize, SharedShape> = self
            .shapes()
            .into_iter()
            .map(|(i, s, _, _)| (i, s))
            .collect();
        let prisms = self.prisms();
        let mut values = drive.to_vec();
        let mut at = |d: f64, seed: &[f64]| -> Option<Vec<f64>> {
            values[k] = d;
            self.assemble(&values, Some(seed), &AssemblyOptions::default())
                .ok()
                .map(|a| a.q)
        };
        let mut ranges: BTreeMap<(usize, usize), Vec<(f64, f64)>> = BTreeMap::new();
        let mut open: BTreeMap<(usize, usize), f64> = BTreeMap::new();
        let mut before = self.overlapping(&sim.samples[0].q, &pairs, &shapes, &prisms);
        for pair in &before {
            open.insert(*pair, sim.samples[0].drive);
        }
        for w in sim.samples.windows(2) {
            let (s0, s1) = (&w[0], &w[1]);
            // Subdivide so outlines move less than a fraction of their size between checks.
            let pieces = 8;
            let mut prev = (s0.drive, s0.q.clone(), before.clone());
            for step in 1..=pieces {
                let d = s0.drive + (s1.drive - s0.drive) * f64::from(step) / f64::from(pieces);
                let q = if step == pieces {
                    s1.q.clone()
                } else {
                    at(d, &prev.1).unwrap_or_else(|| s1.q.clone())
                };
                let now = self.overlapping(&q, &pairs, &shapes, &prisms);
                for pair in now.symmetric_difference(&prev.2) {
                    // Bisect the change between the two checks.
                    let (mut lo, mut hi, mut q_lo) = (prev.0, d, prev.1.clone());
                    let start_state = prev.2.contains(pair);
                    for _ in 0..40 {
                        let mid = 0.5 * (lo + hi);
                        let Some(qm) = at(mid, &q_lo) else { break };
                        if self
                            .overlapping(&qm, &[*pair], &shapes, &prisms)
                            .contains(pair)
                            == start_state
                        {
                            lo = mid;
                            q_lo = qm;
                        } else {
                            hi = mid;
                        }
                    }
                    let boundary = 0.5 * (lo + hi);
                    if start_state {
                        let from = open.remove(pair).unwrap_or(boundary);
                        ranges.entry(*pair).or_default().push((from, boundary));
                    } else {
                        open.insert(*pair, boundary);
                    }
                }
                prev = (d, q, now);
            }
            before = prev.2;
        }
        let last = sim.samples[sim.samples.len() - 1].drive;
        for (pair, from) in open {
            ranges.entry(pair).or_default().push((from, last));
        }
        ranges
            .into_iter()
            .map(|((i, j), r)| Collision {
                bodies: (self.bodies[i].id.clone(), self.bodies[j].id.clone()),
                ranges: r,
            })
            .collect()
    }

    /// Length over width per outlined body: length along the body's longest joint-anchor span
    /// (or its outline's longest extent), width across it.
    fn slenderness(&self) -> Vec<(String, f64)> {
        self.bodies
            .iter()
            .filter_map(|b| {
                let (polygon, _) = b.outline.as_ref()?;
                let pts: Vec<V2> = b.points.values().map(|p| V2::new(p[0], p[1])).collect();
                let mut axis = V2::new(1.0, 0.0);
                let mut longest = 0.0;
                for (i, a) in pts.iter().enumerate() {
                    for c in &pts[i + 1..] {
                        let d = *c - *a;
                        if d.norm() > longest {
                            longest = d.norm();
                            axis = d * (1.0 / d.norm());
                        }
                    }
                }
                let extent = |dir: V2| {
                    let proj: Vec<f64> = polygon.iter().map(|p| p.dot(dir)).collect();
                    proj.iter().copied().fold(f64::NEG_INFINITY, f64::max)
                        - proj.iter().copied().fold(f64::INFINITY, f64::min)
                };
                let (length, width) = (extent(axis), extent(axis.perp()));
                (width > 0.0).then(|| (b.id.clone(), length / width))
            })
            .collect()
    }

    /// Joint reactions holding the mechanism against its springs and a unit load opposing each
    /// output point's motion, from `Jᵀ λ = −f` (quasi-static, massless). Reports where each
    /// revolute's reaction reverses.
    fn reaction_reversals(
        &self,
        sim: &Simulation,
        k: usize,
        drive: &[f64],
    ) -> Vec<ReactionReversal> {
        let n = self.n_vars;
        let rows = self.n_rows();
        let mut offsets = Vec::new();
        let mut row = 0;
        for c in &self.constraints {
            offsets.push((c.source_id().to_owned(), row, c.dim()));
            row += c.dim();
        }
        let mut history: BTreeMap<String, Vec<(f64, V2)>> = BTreeMap::new();
        let mut values = drive.to_vec();
        for s in &sim.samples {
            values[k] = s.drive;
            let mut f = vec![0.0; n];
            for spring in &self.springs {
                let tension = spring.stiffness * (spring.length(&s.q) - spring.free_length);
                for (c, v) in spring.length_gradient(&s.q) {
                    f[c] -= tension * v;
                }
            }
            let motion = self.point_motion(&s.q, &values, k);
            for (b, p) in &self.outputs {
                let Some(m) = motion.get(&(self.bodies[*b].id.clone(), p.clone())) else {
                    continue;
                };
                let speed = m.velocity[0].hypot(m.velocity[1]);
                if speed < 1e-12 {
                    continue;
                }
                // Generalized force of a unit force opposing the point's velocity: −(dp/dq)ᵀ u.
                let BodySlot::Var(i) = self.bodies[*b].slot else {
                    continue;
                };
                let local = self.bodies[*b].points[p];
                let pose = self.bodies[*b].slot.pose(&s.q);
                let d_theta = pose.rotate_derivative(V2::new(local[0], local[1]));
                let u = V2::new(m.velocity[0] / speed, m.velocity[1] / speed);
                f[i] -= u.x;
                f[i + 1] -= u.y;
                f[i + 2] -= u.dot(d_theta);
            }
            if f.iter().all(|v| v.abs() < 1e-15) {
                continue;
            }
            let mut jt = Mat::<f64>::zeros(n, rows);
            for (r, c, v) in self.jacobian(&s.q, &values) {
                jt[(c, r)] += v;
            }
            // Over-constrained mechanisms have no unique reactions; they are skipped.
            if n < rows {
                continue;
            }
            let mut rhs = Mat::from_fn(n, 1, |i, _| -f[i]);
            jt.col_piv_qr()
                .solve_lstsq_in_place_with_conj(Conj::No, rhs.as_mut());
            for (id, start, dim) in &offsets {
                if *dim == 2
                    && self
                        .links
                        .iter()
                        .any(|(_, _, l)| matches!(l, Link::Revolute(r) if &r.id == id))
                {
                    history
                        .entry(id.clone())
                        .or_default()
                        .push((s.drive, V2::new(rhs[(*start, 0)], rhs[(start + 1, 0)])));
                }
            }
        }
        history
            .into_iter()
            .filter_map(|(joint_id, h)| {
                let peak = h.iter().map(|(_, v)| v.norm()).fold(0.0, f64::max);
                if peak < 1e-12 {
                    return None;
                }
                let at: Vec<f64> = h
                    .windows(2)
                    .filter(|w| w[0].1.dot(w[1].1) < 0.0)
                    .map(|w| 0.5 * (w[0].0 + w[1].0))
                    .collect();
                Some(ReactionReversal { joint_id, at, peak })
            })
            .collect()
    }
}

fn link_id(link: &Link) -> String {
    link.id().to_owned()
}

/// Grashof class from frame, input, coupler, and output lengths.
#[must_use]
pub fn classify(lengths: [f64; 4]) -> GrashofClass {
    let mut sorted = lengths;
    sorted.sort_by(f64::total_cmp);
    let (s, p, q, l) = (sorted[0], sorted[1], sorted[2], sorted[3]);
    let tolerance = 1e-9 * l.max(1e-12);
    let excess = s + l - (p + q);
    if excess.abs() <= tolerance {
        return GrashofClass::ChangePoint;
    }
    if excess > 0.0 {
        return GrashofClass::TripleRocker;
    }
    let shortest = (0..4)
        .min_by(|a, b| lengths[*a].total_cmp(&lengths[*b]))
        .unwrap_or(0);
    match shortest {
        0 => GrashofClass::DoubleCrank,
        2 => GrashofClass::DoubleRocker,
        _ => GrashofClass::CrankRocker,
    }
}

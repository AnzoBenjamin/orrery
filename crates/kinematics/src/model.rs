//! A mechanism graph compiled into the solver's form: one pose per moving body in the state
//! vector, and the joints and drivers as residual equations (mechanism-core design, "State").

use std::collections::HashMap;

use crate::constraint::{
    AngleRatio, BodySlot, CamContact, Constraint, DrivenCoordinate, Driver, FollowerShape,
    PinInSlot, Prismatic, RackMesh, Revolute, Spring,
};
use crate::curves::{CamProfile, Curve};
use crate::error::SolverError;
use crate::planar::{Pose2, V2};
use crate::schema::{
    self, BodyKind, DriverCoordinate, FollowerType, Joint, Mechanism, PointRef, SlotCurve, Vec3,
};
use crate::spatial::{Placement, SpatialJoint, SpatialKind, UnitQuaternion, perpendiculars, unit};
use crate::validate::{joint_common, joint_kind, validate};

/// A plane's frame in world coordinates: `world = origin + x·u + y·v + z·normal`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PlaneFrame {
    pub origin: [f64; 3],
    pub u: [f64; 3],
    pub v: [f64; 3],
    pub normal: [f64; 3],
}

fn arr(v: &Vec3) -> [f64; 3] {
    [v.x, v.y, v.z]
}
fn dot3(a: [f64; 3], b: [f64; 3]) -> f64 {
    a[0].mul_add(b[0], a[1].mul_add(b[1], a[2] * b[2]))
}
fn cross3(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn unit3(a: [f64; 3]) -> Option<[f64; 3]> {
    let n = dot3(a, a).sqrt();
    (n > 1e-12 && n.is_finite()).then(|| [a[0] / n, a[1] / n, a[2] / n])
}

impl PlaneFrame {
    fn new(plane: &schema::Plane) -> Result<Self, SolverError> {
        let path = || format!("planes.{}", plane.id.as_str());
        let normal = unit3(arr(&plane.normal_world))
            .ok_or_else(|| SolverError::invalid(path(), "The plane normal has zero length"))?;
        let x = arr(&plane.x_axis_world);
        // Remove any component along the normal, so a slightly tilted x-axis still works.
        let along = dot3(x, normal);
        let u = unit3([
            x[0] - along * normal[0],
            x[1] - along * normal[1],
            x[2] - along * normal[2],
        ])
        .ok_or_else(|| {
            SolverError::invalid(path(), "The plane x-axis is parallel to its normal")
        })?;
        Ok(Self {
            origin: arr(&plane.origin_world),
            u,
            v: cross3(normal, u),
            normal,
        })
    }

    /// The world frame as a plane, for planar mechanisms whose ground is spatial.
    const WORLD_XY: Self = Self {
        origin: [0.0, 0.0, 0.0],
        u: [1.0, 0.0, 0.0],
        v: [0.0, 1.0, 0.0],
        normal: [0.0, 0.0, 1.0],
    };

    /// A world point in this plane's 2D coordinates (its offset along the normal is dropped).
    #[must_use]
    pub fn project_point(&self, p: [f64; 3]) -> V2 {
        let d = [
            p[0] - self.origin[0],
            p[1] - self.origin[1],
            p[2] - self.origin[2],
        ];
        V2::new(dot3(d, self.u), dot3(d, self.v))
    }

    /// A world direction in this plane's 2D coordinates.
    #[must_use]
    pub fn project_direction(&self, d: [f64; 3]) -> V2 {
        V2::new(dot3(d, self.u), dot3(d, self.v))
    }

    /// A point in plane coordinates, at `height` along the normal, in world coordinates.
    #[must_use]
    pub fn to_world(&self, p: V2, height: f64) -> [f64; 3] {
        std::array::from_fn(|k| {
            self.origin[k] + p.x * self.u[k] + p.y * self.v[k] + height * self.normal[k]
        })
    }
}

/// A body's outline extruded into a plate, in meters.
#[derive(Debug, Clone, PartialEq)]
pub struct Outline {
    /// The polygon in the body's local frame.
    pub polygon: Vec<V2>,
    pub thickness: f64,
    /// The plate's mid-plane distance from the body's plane, along the plane normal (its layer).
    pub offset: f64,
}

/// One body as the solver sees it.
#[derive(Debug, Clone)]
pub struct BodyInfo {
    pub id: String,
    pub is_ground: bool,
    pub slot: BodySlot,
    /// The plane the body moves in. The ground of a planar mechanism may be spatial (`None`).
    pub plane: Option<String>,
    /// Named points in the body's local frame.
    pub points: HashMap<String, [f64; 3]>,
    pub outline: Option<Outline>,
    /// Where the body is in the world, for spatial joints and world points.
    pub placement: Placement,
}

/// A revolute or prismatic joint, kept for building initial guesses.
#[derive(Debug, Clone)]
pub enum Link {
    Revolute(Revolute),
    Prismatic(Prismatic),
    /// Any joint in world coordinates: spherical, universal, cylindrical, or a revolute or
    /// prismatic joint touching a spatial body.
    Spatial(Box<SpatialJoint>),
}

impl Link {
    /// The joint's id.
    #[must_use]
    pub fn id(&self) -> &str {
        match self {
            Self::Revolute(r) => &r.id,
            Self::Prismatic(p) => &p.id,
            Self::Spatial(j) => &j.id,
        }
    }
}

/// What one joint of the graph becomes.
enum Compiled {
    Link(Link),
    Constraint(Box<dyn Constraint>),
    Spring(Spring),
}

/// The compiled mechanism.
#[derive(Debug)]
pub struct Model {
    pub bodies: Vec<BodyInfo>,
    pub n_vars: usize,
    pub constraints: Vec<Box<dyn Constraint>>,
    pub drivers: Vec<Driver>,
    pub links: Vec<(usize, usize, Link)>,
    pub springs: Vec<Spring>,
    /// Body pairs (lower index first) that some joint connects.
    pub joined: std::collections::BTreeSet<(usize, usize)>,
    /// Points with the `output` role: (body index, point id).
    pub outputs: Vec<(usize, String)>,
    pub planes: HashMap<String, PlaneFrame>,
    body_index: HashMap<String, usize>,
}

/// What a body's local point means in a given plane's coordinates.
fn local_in_plane(
    body: &BodyInfo,
    plane_id: &str,
    point: [f64; 3],
    planes: &HashMap<String, PlaneFrame>,
) -> V2 {
    match (&body.plane, body.is_ground) {
        // A spatial ground's local frame is the world frame.
        (None, true) => planes.get(plane_id).map_or_else(
            || PlaneFrame::WORLD_XY.project_point(point),
            |f| f.project_point(point),
        ),
        _ => V2::new(point[0], point[1]),
    }
}

impl Model {
    /// Builds the solver model. Fails with `InvalidGraph` when the graph breaks a schema rule or
    /// uses a joint the planar solver does not implement.
    pub fn new(mechanism: &Mechanism) -> Result<Self, SolverError> {
        validate(mechanism).map_err(SolverError::InvalidGraph)?;

        let mut planes = HashMap::new();
        for plane in &mechanism.planes {
            planes.insert(plane.id.as_str().to_owned(), PlaneFrame::new(plane)?);
        }

        let mut bodies = Vec::with_capacity(mechanism.bodies.len());
        let mut n_vars = 0;
        for body in &mechanism.bodies {
            let is_ground = body.kind == BodyKind::Ground;
            let plane = body.plane_id.as_ref().map(|p| p.as_str().to_owned());
            let frame = plane.as_ref().and_then(|p| planes.get(p)).copied();
            let (slot, placement) = if is_ground {
                let (origin, basis) = frame.map_or(
                    (
                        [0.0; 3],
                        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                    ),
                    |f| (f.origin, [f.u, f.v, f.normal]),
                );
                (
                    BodySlot::Fixed(Pose2::default()),
                    Placement::Fixed { origin, basis },
                )
            } else if let Some(frame) = frame {
                n_vars += 3;
                (
                    BodySlot::Var(n_vars - 3),
                    Placement::Planar {
                        index: n_vars - 3,
                        frame,
                    },
                )
            } else {
                n_vars += 7;
                (
                    BodySlot::Spatial(n_vars - 7),
                    Placement::Spatial { index: n_vars - 7 },
                )
            };
            let points = body
                .points
                .iter()
                .map(|p| (p.id.as_str().to_owned(), arr(&p.local)))
                .collect();
            let outline = body.outline.as_ref().map(|o| Outline {
                polygon: o.polygon_local.iter().map(|p| V2::new(p.x, p.y)).collect(),
                thickness: o.thickness,
                offset: o.offset.unwrap_or(0.0),
            });
            bodies.push(BodyInfo {
                id: body.id.as_str().to_owned(),
                is_ground,
                slot,
                plane,
                points,
                outline,
                placement,
            });
        }
        let body_index: HashMap<String, usize> = bodies
            .iter()
            .enumerate()
            .map(|(i, b)| (b.id.clone(), i))
            .collect();

        let mut model = Self {
            bodies,
            n_vars,
            constraints: Vec::new(),
            drivers: Vec::new(),
            links: Vec::new(),
            springs: Vec::new(),
            joined: std::collections::BTreeSet::new(),
            outputs: mechanism
                .bodies
                .iter()
                .enumerate()
                .flat_map(|(i, b)| {
                    b.points
                        .iter()
                        .filter(|p| p.role == schema::PointRole::Output)
                        .map(move |p| (i, p.id.as_str().to_owned()))
                })
                .collect(),
            planes,
            body_index,
        };
        // Each spatial body's quaternion stays at unit length.
        for body in &model.bodies {
            if let BodySlot::Spatial(i) = body.slot {
                model.constraints.push(Box::new(UnitQuaternion {
                    id: format!("{} (orientation)", body.id),
                    index: i + 3,
                }));
            }
        }
        let mut by_joint: HashMap<String, Link> = HashMap::new();
        for (i, joint) in mechanism.joints.iter().enumerate() {
            let common = joint_common(joint);
            let (a, b) = (
                model.body_index[common.body_a],
                model.body_index[common.body_b],
            );
            model.joined.insert((a.min(b), a.max(b)));
            match model.compile_joint(i, joint, mechanism)? {
                Compiled::Link(link) => {
                    match &link {
                        Link::Revolute(r) => model.constraints.push(Box::new(r.clone())),
                        Link::Prismatic(p) => model.constraints.push(Box::new(p.clone())),
                        Link::Spatial(j) => model.constraints.push(Box::new(j.as_ref().clone())),
                    }
                    by_joint.insert(common.id.to_owned(), link.clone());
                    model.links.push((a, b, link));
                }
                Compiled::Constraint(c) => model.constraints.push(c),
                Compiled::Spring(spring) => model.springs.push(spring),
            }
        }
        for (index, driver) in mechanism.drivers.iter().enumerate() {
            let path = format!("drivers[{index}]");
            let joint = driver.joint_id.as_str();
            let coordinate = match (by_joint.get(joint), driver.coordinate) {
                (Some(Link::Revolute(r)), DriverCoordinate::Angle) => {
                    DrivenCoordinate::Angle { a: r.a, b: r.b }
                }
                (Some(Link::Prismatic(p)), DriverCoordinate::Displacement) => {
                    DrivenCoordinate::Displacement(p.clone())
                }
                (Some(Link::Spatial(j)), DriverCoordinate::Angle)
                    if matches!(j.kind, SpatialKind::Revolute { .. }) =>
                {
                    DrivenCoordinate::SpatialAngle(j.as_ref().clone())
                }
                (Some(Link::Spatial(j)), DriverCoordinate::Displacement)
                    if matches!(
                        j.kind,
                        SpatialKind::Prismatic { .. } | SpatialKind::Cylindrical { .. }
                    ) =>
                {
                    DrivenCoordinate::SpatialDisplacement(j.as_ref().clone())
                }
                _ => {
                    return Err(SolverError::invalid(
                        path,
                        format!(
                            "Driver {} sets the {} of joint {joint}, which has no such coordinate",
                            driver.id.as_str(),
                            match driver.coordinate {
                                DriverCoordinate::Angle => "angle",
                                DriverCoordinate::Displacement => "displacement",
                            }
                        ),
                    ));
                }
            };
            let compiled = Driver {
                id: driver.id.as_str().to_owned(),
                joint_id: joint.to_owned(),
                index,
                coordinate,
            };
            model.constraints.push(Box::new(compiled.clone()));
            model.drivers.push(compiled);
        }
        Ok(model)
    }

    /// The plane a planar joint between `a` and `b` acts in.
    fn joint_plane(&self, a: usize, b: usize) -> String {
        let (ba, bb) = (&self.bodies[a], &self.bodies[b]);
        let moving = if ba.is_ground { bb } else { ba };
        moving
            .plane
            .clone()
            .or_else(|| ba.plane.clone())
            .unwrap_or_default()
    }

    fn anchor(&self, plane: &str, point: &PointRef, path: &str) -> Result<V2, SolverError> {
        let body = &self.bodies[self.body_index[point.body_id.as_str()]];
        let local = body
            .points
            .get(point.point_id.as_str())
            .copied()
            .ok_or_else(|| {
                SolverError::invalid(path, format!("Point {} not found", point.point_id.as_str()))
            })?;
        Ok(local_in_plane(body, plane, local, &self.planes))
    }

    /// A new extra unknown (a curve parameter) at the end of the state.
    fn aux(&mut self) -> usize {
        self.n_vars += 1;
        self.n_vars - 1
    }

    /// The body both `a` and `b` turn on: one with a revolute joint to each.
    fn carrier(mechanism: &Mechanism, a: &str, b: &str) -> Option<String> {
        let partners = |body: &str| -> Vec<String> {
            mechanism
                .joints
                .iter()
                .filter(|j| matches!(j, Joint::Revolute { .. }))
                .filter_map(|j| {
                    let c = joint_common(j);
                    if c.body_a == body {
                        Some(c.body_b.to_owned())
                    } else if c.body_b == body {
                        Some(c.body_a.to_owned())
                    } else {
                        None
                    }
                })
                .collect()
        };
        let of_b = partners(b);
        partners(a).into_iter().find(|c| of_b.contains(c))
    }

    /// The body a pinion turns on (by a revolute joint) that its rack slides on (by a prismatic
    /// joint).
    fn rack_carrier(mechanism: &Mechanism, pinion: &str, rack: &str) -> Option<String> {
        let partners = |body: &str, revolute: bool| -> Vec<String> {
            mechanism
                .joints
                .iter()
                .filter(|j| {
                    if revolute {
                        matches!(j, Joint::Revolute { .. })
                    } else {
                        matches!(j, Joint::Prismatic { .. })
                    }
                })
                .filter_map(|j| {
                    let c = joint_common(j);
                    if c.body_a == body {
                        Some(c.body_b.to_owned())
                    } else if c.body_b == body {
                        Some(c.body_a.to_owned())
                    } else {
                        None
                    }
                })
                .collect()
        };
        let of_rack = partners(rack, false);
        partners(pinion, true)
            .into_iter()
            .find(|c| of_rack.contains(c))
    }

    /// A curve or profile cut in `body` must be in the joint's plane frame. A spatial ground has
    /// no 2D frame of its own, so such a body is refused.
    fn require_planar_frame(&self, body: usize, id: &str, path: &str) -> Result<(), SolverError> {
        let info = &self.bodies[body];
        if info.plane.is_none() {
            return Err(SolverError::invalid(
                path,
                format!(
                    "Joint {id} cuts its curve in body {}, which has no plane; give that body the joint's plane",
                    info.id
                ),
            ));
        }
        Ok(())
    }

    #[allow(
        clippy::too_many_arguments,
        reason = "the parts of one ratio constraint"
    )]
    fn angle_ratio(
        &self,
        id: String,
        a: usize,
        b: usize,
        ratio: f64,
        phase: f64,
        mechanism: &Mechanism,
        path: &str,
    ) -> Result<Compiled, SolverError> {
        let carrier = Self::carrier(mechanism, &self.bodies[a].id, &self.bodies[b].id)
            .and_then(|c| self.body_index.get(&c).copied())
            .ok_or_else(|| {
                SolverError::invalid(
                    path,
                    format!(
                        "Joint {id} needs both wheels pinned by revolute joints to one carrier body"
                    ),
                )
            })?;
        Ok(Compiled::Constraint(Box::new(AngleRatio {
            id,
            a: self.bodies[a].slot,
            b: self.bodies[b].slot,
            carrier: self.bodies[carrier].slot,
            ratio,
            phase,
        })))
    }

    fn compile_joint(
        &mut self,
        i: usize,
        joint: &Joint,
        mechanism: &Mechanism,
    ) -> Result<Compiled, SolverError> {
        let path = format!("joints[{i}]");
        let common = joint_common(joint);
        let (a, b) = (
            self.body_index[common.body_a],
            self.body_index[common.body_b],
        );
        let id = common.id.to_owned();
        let spatial = |i: usize| matches!(self.bodies[i].slot, BodySlot::Spatial(_));
        match joint {
            Joint::Spherical { .. } | Joint::Universal { .. } | Joint::Cylindrical { .. } => {
                return self.compile_spatial(joint, a, b, id, &path);
            }
            Joint::Revolute { .. } | Joint::Prismatic { .. } if spatial(a) || spatial(b) => {
                return self.compile_spatial(joint, a, b, id, &path);
            }
            other if spatial(a) || spatial(b) => {
                let body = if spatial(a) {
                    &self.bodies[a].id
                } else {
                    &self.bodies[b].id
                };
                return Err(SolverError::invalid(
                    path,
                    format!(
                        "Joint {id} is a {} joint, which acts in a plane, but body {body} is spatial; give it a plane",
                        joint_kind(other)
                    ),
                ));
            }
            _ => {}
        }
        let plane = self.joint_plane(a, b);
        let (slot_a, slot_b) = (self.bodies[a].slot, self.bodies[b].slot);
        match joint {
            Joint::Revolute {
                anchor_a,
                anchor_b,
                axis_local_a,
                ..
            } => {
                if let Some(axis) = axis_local_a {
                    // A planar revolute turns about the plane normal: local z.
                    if axis.x.abs() > 1e-9 || axis.y.abs() > 1e-9 || axis.z.abs() < 1e-12 {
                        return Err(SolverError::invalid(
                            path,
                            format!(
                                "Revolute joint {id} has a tilted axis; planar bodies turn about the plane normal"
                            ),
                        ));
                    }
                }
                Ok(Compiled::Link(Link::Revolute(Revolute {
                    id,
                    a: slot_a,
                    anchor_a: self.anchor(&plane, anchor_a, &path)?,
                    b: slot_b,
                    anchor_b: self.anchor(&plane, anchor_b, &path)?,
                })))
            }
            Joint::Prismatic {
                anchor_a,
                anchor_b,
                axis_local_a,
                limits,
                ..
            } => {
                let body_a = &self.bodies[a];
                let raw = arr(axis_local_a);
                let spatial_ground = body_a.is_ground && body_a.plane.is_none();
                let axis = if spatial_ground {
                    self.planes
                        .get(&plane)
                        .unwrap_or(&PlaneFrame::WORLD_XY)
                        .project_direction(raw)
                } else {
                    V2::new(raw[0], raw[1])
                };
                let len = axis.norm();
                // In a planar body's frame the axis must lie in the plane (no local z).
                let tilted = !spatial_ground && raw[2].abs() > 1e-9 * dot3(raw, raw).sqrt();
                if len < 1e-12 || tilted {
                    return Err(SolverError::invalid(
                        path,
                        format!("Prismatic joint {id} needs a slide axis in the plane"),
                    ));
                }
                Ok(Compiled::Link(Link::Prismatic(Prismatic {
                    id,
                    a: slot_a,
                    anchor_a: self.anchor(&plane, anchor_a, &path)?,
                    axis: axis * (1.0 / len),
                    b: slot_b,
                    anchor_b: self.anchor(&plane, anchor_b, &path)?,
                    limits: limits.map(|(lo, hi)| (lo.min(hi), lo.max(hi))),
                })))
            }
            Joint::PinInSlot { pin, slot, .. } => {
                let pin_index = self.body_index[pin.body_id.as_str()];
                let slot_index = if pin_index == a { b } else { a };
                self.require_planar_frame(slot_index, &id, &path)?;
                let curve = match slot {
                    SlotCurve::LineSegment { start, end } => Curve::Line {
                        start: V2::new(start.x, start.y),
                        end: V2::new(end.x, end.y),
                    },
                    SlotCurve::CircularArc {
                        center,
                        radius,
                        angle_start,
                        angle_end,
                    } => Curve::Arc {
                        center: V2::new(center.x, center.y),
                        radius: *radius,
                        a0: *angle_start,
                        a1: *angle_end,
                    },
                    SlotCurve::CubicBspline {
                        control_points,
                        knots,
                    } => Curve::bspline(
                        control_points.iter().map(|p| V2::new(p.x, p.y)).collect(),
                        knots.clone(),
                    )
                    .map_err(|e| SolverError::invalid(&path, format!("Slot of joint {id}: {e}")))?,
                };
                let pin_local = self.anchor(&plane, pin, &path)?;
                Ok(Compiled::Constraint(Box::new(PinInSlot {
                    id,
                    pin_body: self.bodies[pin_index].slot,
                    pin: pin_local,
                    slot_body: self.bodies[slot_index].slot,
                    curve,
                    s_index: self.aux(),
                })))
            }
            Joint::GearMesh {
                ratio,
                phase,
                rack: Some(rack),
                ..
            } => {
                let raw = arr(&rack.axis_local_b);
                let axis = V2::new(raw[0], raw[1]);
                let len = axis.norm();
                if len < 1e-12 || raw[2].abs() > 1e-9 * dot3(raw, raw).sqrt() {
                    return Err(SolverError::invalid(
                        path,
                        format!("Rack joint {id} needs a slide axis in the plane"),
                    ));
                }
                let carrier = Self::rack_carrier(mechanism, &self.bodies[a].id, &self.bodies[b].id)
                    .and_then(|c| self.body_index.get(&c).copied())
                    .ok_or_else(|| {
                        SolverError::invalid(
                            &path,
                            format!(
                                "Rack joint {id} needs the pinion pinned by a revolute joint and the rack on a prismatic joint to one carrier body"
                            ),
                        )
                    })?;
                Ok(Compiled::Constraint(Box::new(RackMesh {
                    id,
                    pinion: slot_a,
                    rack: slot_b,
                    carrier: self.bodies[carrier].slot,
                    axis: axis * (1.0 / len),
                    ratio: *ratio,
                    phase: *phase,
                })))
            }
            Joint::GearMesh { ratio, phase, .. } => {
                self.angle_ratio(id, a, b, *ratio, *phase, mechanism, &path)
            }
            Joint::Belt { ratio, crossed, .. } => {
                let signed = if *crossed { -*ratio } else { *ratio };
                self.angle_ratio(id, a, b, signed, 0.0, mechanism, &path)
            }
            Joint::CamFollower {
                follower,
                follower_point,
                roller_radius,
                ..
            } => {
                let (cam_index, follower_index) = if mechanism.bodies[a].kind == BodyKind::Cam {
                    (a, b)
                } else {
                    (b, a)
                };
                self.require_planar_frame(cam_index, &id, &path)?;
                let Some(cam) = &mechanism.bodies[cam_index].cam else {
                    return Err(SolverError::invalid(
                        path,
                        format!("Joint {id} has no cam profile"),
                    ));
                };
                let shape = match follower {
                    FollowerType::Knife => FollowerShape::Knife,
                    FollowerType::Flat => FollowerShape::Flat,
                    FollowerType::Roller => FollowerShape::Roller(roller_radius.unwrap_or(0.0)),
                };
                let point = self.anchor(&plane, follower_point, &path)?;
                Ok(Compiled::Constraint(Box::new(CamContact {
                    id,
                    cam: self.bodies[cam_index].slot,
                    profile: CamProfile {
                        base: cam.base_radius,
                        a: cam.fourier.a.clone(),
                        b: cam.fourier.b.clone(),
                    },
                    follower: self.bodies[follower_index].slot,
                    point,
                    shape,
                    psi_index: self.aux(),
                })))
            }
            Joint::Spring {
                anchor_a,
                anchor_b,
                stiffness,
                free_length,
                ..
            } => Ok(Compiled::Spring(Spring {
                id,
                a: slot_a,
                anchor_a: self.anchor(&plane, anchor_a, &path)?,
                b: slot_b,
                anchor_b: self.anchor(&plane, anchor_b, &path)?,
                stiffness: *stiffness,
                free_length: *free_length,
            })),
            other => Err(SolverError::invalid(
                path,
                format!(
                    "Joint {id} is a {} joint; this solver build handles planar joints only",
                    joint_kind(other)
                ),
            )),
        }
    }

    /// Number of residual rows.
    #[must_use]
    pub fn n_rows(&self) -> usize {
        self.constraints.iter().map(|c| c.dim()).sum()
    }

    /// All residuals at `q` for the driver values `drive`.
    #[must_use]
    pub fn residuals(&self, q: &[f64], drive: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0; self.n_rows()];
        let mut row = 0;
        for c in &self.constraints {
            let d = c.dim();
            c.residual(q, drive, &mut out[row..row + d]);
            row += d;
        }
        out
    }

    /// The constraint Jacobian at `q` as (row, column, value) entries.
    #[must_use]
    pub fn jacobian(&self, q: &[f64], drive: &[f64]) -> Vec<(usize, usize, f64)> {
        let mut out = Vec::new();
        let mut row = 0;
        for c in &self.constraints {
            c.jacobian(q, drive, row, &mut out);
            row += c.dim();
        }
        out
    }

    /// Index of a body by id.
    #[must_use]
    pub fn body(&self, id: &str) -> Option<usize> {
        self.body_index.get(id).copied()
    }

    /// A body's pose in its plane frame.
    #[must_use]
    pub fn pose(&self, body: usize, q: &[f64]) -> Pose2 {
        self.bodies[body].slot.pose(q)
    }

    /// A named point of a body in world coordinates.
    #[must_use]
    pub fn point_world(&self, body: usize, point: &str, q: &[f64]) -> Option<[f64; 3]> {
        let info = &self.bodies[body];
        Some(info.placement.point(q, *info.points.get(point)?))
    }

    /// A joint in world coordinates, for joints that touch a spatial body or are spatial kinds.
    fn compile_spatial(
        &self,
        joint: &Joint,
        a: usize,
        b: usize,
        id: String,
        path: &str,
    ) -> Result<Compiled, SolverError> {
        let point = |r: &PointRef| -> Result<[f64; 3], SolverError> {
            let body = &self.bodies[self.body_index[r.body_id.as_str()]];
            body.points
                .get(r.point_id.as_str())
                .copied()
                .ok_or_else(|| {
                    SolverError::invalid(path, format!("Point {} not found", r.point_id.as_str()))
                })
        };
        let axis = |v: Option<&Vec3>, what: &str| -> Result<[f64; 3], SolverError> {
            v.and_then(|v| unit(arr(v))).ok_or_else(|| {
                SolverError::invalid(path, format!("Joint {id} needs {what} with nonzero length"))
            })
        };
        let (anchor_a, anchor_b, kind, limits) = match joint {
            Joint::Spherical {
                anchor_a, anchor_b, ..
            } => (anchor_a, anchor_b, SpatialKind::Spherical, None),
            Joint::Universal {
                anchor_a,
                anchor_b,
                axes_local,
                ..
            } => {
                let (arm_a, arm_b) = match axes_local {
                    Some((x, y)) => (axis(Some(x), "axesLocal")?, axis(Some(y), "axesLocal")?),
                    None => (axis(None, "axesLocal")?, [0.0; 3]),
                };
                (
                    anchor_a,
                    anchor_b,
                    SpatialKind::Universal { arm_a, arm_b },
                    None,
                )
            }
            Joint::Cylindrical {
                anchor_a,
                anchor_b,
                axes_local,
                ..
            } => {
                let (axis_a, axis_b) = match axes_local {
                    Some((x, y)) => (axis(Some(x), "axesLocal")?, axis(Some(y), "axesLocal")?),
                    None => (axis(None, "axesLocal")?, [0.0; 3]),
                };
                let kind = SpatialKind::Cylindrical {
                    axis_a,
                    perp_a: perpendiculars(axis_a),
                    axis_b,
                    perp_b: perpendiculars(axis_b),
                };
                (anchor_a, anchor_b, kind, None)
            }
            Joint::Revolute {
                anchor_a,
                anchor_b,
                axis_local_a,
                ..
            } => {
                let axis = axis(axis_local_a.as_ref(), "axisLocalA (the turning axis)")?;
                (
                    anchor_a,
                    anchor_b,
                    SpatialKind::Revolute {
                        axis,
                        perp: perpendiculars(axis),
                    },
                    None,
                )
            }
            Joint::Prismatic {
                anchor_a,
                anchor_b,
                axis_local_a,
                limits,
                ..
            } => {
                let axis = axis(Some(axis_local_a), "axisLocalA (the slide axis)")?;
                let kind = SpatialKind::Prismatic {
                    axis,
                    perp: perpendiculars(axis),
                };
                (
                    anchor_a,
                    anchor_b,
                    kind,
                    limits.map(|(lo, hi)| (lo.min(hi), lo.max(hi))),
                )
            }
            other => {
                return Err(SolverError::invalid(
                    path,
                    format!(
                        "Joint {id} is a {} joint, which acts in a plane",
                        joint_kind(other)
                    ),
                ));
            }
        };
        Ok(Compiled::Link(Link::Spatial(Box::new(SpatialJoint {
            id,
            a: self.bodies[a].placement,
            anchor_a: point(anchor_a)?,
            b: self.bodies[b].placement,
            anchor_b: point(anchor_b)?,
            kind,
            limits,
        }))))
    }
}

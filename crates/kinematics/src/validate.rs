//! The cross-reference rules of the mechanism graph (mechanism-core requirement 2.4), the same
//! rules as the Zod schema's refinement in `packages/schema/src/mechanism.ts`. JSON Schema cannot
//! express them, so each language checks them itself.

use std::collections::{HashMap, HashSet};

use crate::schema::{Body, BodyKind, FollowerType, Joint, Mechanism, PointRef};

/// One broken rule, with a message in the same words as the Zod refinement.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationIssue {
    /// Where in the document, such as `joints[1].anchorB`.
    pub path: String,
    pub message: String,
}

/// The fields every joint kind shares.
#[derive(Debug, Clone, Copy)]
pub struct JointCommon<'a> {
    pub id: &'a str,
    pub body_a: &'a str,
    pub body_b: &'a str,
}

/// The id and the two bodies of any joint.
#[must_use]
pub fn joint_common(joint: &Joint) -> JointCommon<'_> {
    macro_rules! common {
        ($id:expr, $a:expr, $b:expr) => {
            JointCommon {
                id: $id.as_str(),
                body_a: $a.as_str(),
                body_b: $b.as_str(),
            }
        };
    }
    match joint {
        Joint::Revolute {
            id, body_a, body_b, ..
        }
        | Joint::Prismatic {
            id, body_a, body_b, ..
        }
        | Joint::PinInSlot {
            id, body_a, body_b, ..
        }
        | Joint::GearMesh {
            id, body_a, body_b, ..
        }
        | Joint::Belt {
            id, body_a, body_b, ..
        }
        | Joint::CamFollower {
            id, body_a, body_b, ..
        }
        | Joint::Spring {
            id, body_a, body_b, ..
        }
        | Joint::Spherical {
            id, body_a, body_b, ..
        }
        | Joint::Universal {
            id, body_a, body_b, ..
        }
        | Joint::Cylindrical {
            id, body_a, body_b, ..
        } => common!(id, body_a, body_b),
    }
}

/// The joint's kind as written in the document.
#[must_use]
pub fn joint_kind(joint: &Joint) -> &'static str {
    match joint {
        Joint::Revolute { .. } => "revolute",
        Joint::Prismatic { .. } => "prismatic",
        Joint::PinInSlot { .. } => "pin_in_slot",
        Joint::GearMesh { .. } => "gear_mesh",
        Joint::Belt { .. } => "belt",
        Joint::CamFollower { .. } => "cam_follower",
        Joint::Spring { .. } => "spring",
        Joint::Spherical { .. } => "spherical",
        Joint::Universal { .. } => "universal",
        Joint::Cylindrical { .. } => "cylindrical",
    }
}

/// The point references a joint makes, with the field name each sits in.
fn point_refs(joint: &Joint) -> Vec<(&'static str, &PointRef)> {
    match joint {
        Joint::Revolute {
            anchor_a, anchor_b, ..
        }
        | Joint::Prismatic {
            anchor_a, anchor_b, ..
        }
        | Joint::Spring {
            anchor_a, anchor_b, ..
        }
        | Joint::Spherical {
            anchor_a, anchor_b, ..
        }
        | Joint::Universal {
            anchor_a, anchor_b, ..
        }
        | Joint::Cylindrical {
            anchor_a, anchor_b, ..
        } => {
            vec![("anchorA", anchor_a), ("anchorB", anchor_b)]
        }
        Joint::PinInSlot { pin, .. } => vec![("pin", pin)],
        Joint::CamFollower { follower_point, .. } => vec![("followerPoint", follower_point)],
        Joint::GearMesh { .. } | Joint::Belt { .. } => vec![],
    }
}

const fn is_planar(joint: &Joint) -> bool {
    matches!(
        joint,
        Joint::Revolute { .. }
            | Joint::Prismatic { .. }
            | Joint::PinInSlot { .. }
            | Joint::GearMesh { .. }
            | Joint::Belt { .. }
            | Joint::CamFollower { .. }
            | Joint::Spring { .. }
    )
}

fn has_duplicates<'a>(ids: impl Iterator<Item = &'a str>) -> bool {
    let mut seen = HashSet::new();
    ids.into_iter().any(|id| !seen.insert(id))
}

/// Checks every cross-reference rule. Returns all broken rules, in document order.
pub fn validate(mechanism: &Mechanism) -> Result<(), Vec<ValidationIssue>> {
    let mut issues = Vec::new();
    let mut issue = |path: String, message: String| issues.push(ValidationIssue { path, message });

    if has_duplicates(mechanism.bodies.iter().map(|b| b.id.as_str())) {
        issue("bodies".into(), "Duplicate body IDs found".into());
    }
    if has_duplicates(mechanism.joints.iter().map(|j| joint_common(j).id)) {
        issue("joints".into(), "Duplicate joint IDs found".into());
    }
    if has_duplicates(mechanism.planes.iter().map(|p| p.id.as_str())) {
        issue("planes".into(), "Duplicate plane IDs found".into());
    }
    let grounds = mechanism
        .bodies
        .iter()
        .filter(|b| b.kind == BodyKind::Ground)
        .count();
    match grounds {
        1 => {}
        0 => issue(
            "bodies".into(),
            "Mechanism must have exactly one ground body".into(),
        ),
        n => issue(
            "bodies".into(),
            format!("Mechanism must have exactly one ground body, found {n}"),
        ),
    }

    let planes: HashSet<&str> = mechanism.planes.iter().map(|p| p.id.as_str()).collect();
    let bodies: HashMap<&str, &Body> = mechanism
        .bodies
        .iter()
        .map(|b| (b.id.as_str(), b))
        .collect();
    for body in &mechanism.bodies {
        let id = body.id.as_str();
        if has_duplicates(body.points.iter().map(|p| p.id.as_str())) {
            issue(
                "bodies".into(),
                format!("Body {id} has duplicate point IDs"),
            );
        }
        if let Some(plane) = &body.plane_id
            && !planes.contains(plane.as_str())
        {
            issue(
                "bodies".into(),
                format!("Body {id} references non-existent plane {}", **plane),
            );
        }
        let missing = match body.kind {
            BodyKind::Gear if body.gear.is_none() => Some("a gear but missing gear data"),
            BodyKind::Cam if body.cam.is_none() => Some("a cam but missing cam data"),
            BodyKind::Pulley if body.pulley.is_none() => Some("a pulley but missing pulley data"),
            _ => None,
        };
        if let Some(what) = missing {
            issue("bodies".into(), format!("Body {id} is {what}"));
        }
    }

    for (i, joint) in mechanism.joints.iter().enumerate() {
        let JointCommon { id, body_a, body_b } = joint_common(joint);
        let path = format!("joints[{i}]");
        for (field, body) in [("bodyA", body_a), ("bodyB", body_b)] {
            if !bodies.contains_key(body) {
                issue(
                    format!("{path}.{field}"),
                    format!("Joint {id} references non-existent body {body}"),
                );
            }
        }
        if body_a == body_b {
            issue(
                path.clone(),
                format!("Joint {id} connects body {body_a} to itself"),
            );
        }
        if let (Some(a), Some(b)) = (bodies.get(body_a), bodies.get(body_b)) {
            if is_planar(joint)
                && let (Some(pa), Some(pb)) = (&a.plane_id, &b.plane_id)
                && pa.as_str() != pb.as_str()
            {
                issue(
                    path.clone(),
                    format!(
                        "Planar joint {id} connects bodies in different planes ({} and {})",
                        **pa, **pb
                    ),
                );
            }
            match joint {
                Joint::GearMesh { .. } if a.kind != BodyKind::Gear || b.kind != BodyKind::Gear => {
                    issue(
                        path.clone(),
                        format!("Gear mesh joint {id} connects non-gear bodies"),
                    );
                }
                Joint::Belt { .. } if a.kind != BodyKind::Pulley || b.kind != BodyKind::Pulley => {
                    issue(
                        path.clone(),
                        format!("Belt joint {id} connects non-pulley bodies"),
                    );
                }
                Joint::CamFollower { .. } if a.kind != BodyKind::Cam && b.kind != BodyKind::Cam => {
                    issue(
                        path.clone(),
                        format!("Cam follower joint {id} does not connect a cam body"),
                    );
                }
                _ => {}
            }
        }
        if let Joint::CamFollower {
            follower: FollowerType::Roller,
            roller_radius: None,
            ..
        } = joint
        {
            issue(
                path.clone(),
                format!("Cam follower joint {id} with roller follower missing rollerRadius"),
            );
        }
        for (field, point) in point_refs(joint) {
            let body = point.body_id.as_str();
            let pid = point.point_id.as_str();
            match bodies.get(body) {
                None => issue(
                    format!("{path}.{field}"),
                    format!("Joint {id} {field} references non-existent body {body}"),
                ),
                Some(b) if !b.points.iter().any(|p| p.id.as_str() == pid) => issue(
                    format!("{path}.{field}"),
                    format!(
                        "Joint {id} {field} references non-existent point {pid} on body {body}"
                    ),
                ),
                Some(_) => {}
            }
        }
    }

    let joints: HashSet<&str> = mechanism
        .joints
        .iter()
        .map(|j| joint_common(j).id)
        .collect();
    for (i, driver) in mechanism.drivers.iter().enumerate() {
        let id = driver.id.as_str();
        if !joints.contains(driver.joint_id.as_str()) {
            issue(
                format!("drivers[{i}].jointId"),
                format!(
                    "Driver {id} references non-existent joint {}",
                    driver.joint_id.as_str()
                ),
            );
        }
        if let crate::schema::DriverProfile::Samples { t, q } = &driver.profile
            && t.len() != q.len()
        {
            issue(
                format!("drivers[{i}].profile"),
                format!("Driver {id} samples profile has mismatched array lengths"),
            );
        }
    }

    if issues.is_empty() {
        Ok(())
    } else {
        Err(issues)
    }
}

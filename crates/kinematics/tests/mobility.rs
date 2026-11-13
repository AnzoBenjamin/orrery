//! Mobility analysis (mechanism-core requirement 6, property 4's special-geometry case).

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::path::Path;

use kinematics::AssemblyOptions;
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use serde_json::{Value, json};

fn golden(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn model(v: &Value) -> Model {
    Model::new(&parse_mechanism(&v.to_string()).unwrap()).unwrap()
}

fn point(id: &str, x: f64) -> Value {
    json!({ "id": id, "local": {"x": x, "y": 0, "z": 0}, "role": "joint_anchor" })
}

fn revolute(id: &str, a: &str, pa: &str, b: &str, pb: &str) -> Value {
    json!({ "id": id, "kind": "revolute", "bodyA": a, "bodyB": b,
        "anchorA": {"bodyId": a, "pointId": pa}, "anchorB": {"bodyId": b, "pointId": pb},
        "status": "observed", "confidence": 1 })
}

/// A coupler carried by three equal, parallel cranks: Grübler counts 0, yet it moves.
fn triple_crank() -> Value {
    let body = |id: &str, kind: &str, points: Vec<Value>| {
        json!({ "id": id, "label": id, "kind": kind,
        "planeId": "p", "points": points, "status": "observed", "confidence": 1 })
    };
    let crank = |i: usize| {
        body(
            &format!("crank-{i}"),
            "link",
            vec![point("base", 0.0), point("top", 0.1)],
        )
    };
    json!({
        "schemaVersion": 1, "id": "triple", "name": "Triple crank parallelogram",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [{ "id": "p", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": [
            body("ground", "ground", vec![point("o1", 0.0), point("o2", 0.2), point("o3", 0.4)]),
            body("coupler", "link", vec![point("c1", 0.0), point("c2", 0.2), point("c3", 0.4)]),
            crank(1), crank(2), crank(3)],
        "joints": [
            revolute("base-1", "ground", "o1", "crank-1", "base"),
            revolute("base-2", "ground", "o2", "crank-2", "base"),
            revolute("base-3", "ground", "o3", "crank-3", "base"),
            revolute("top-1", "crank-1", "top", "coupler", "c1"),
            revolute("top-2", "crank-2", "top", "coupler", "c2"),
            revolute("top-3", "crank-3", "top", "coupler", "c3")],
        "drivers": [{ "id": "drive", "jointId": "base-1", "coordinate": "angle",
            "profile": { "type": "constant_rate", "rate": 1, "phase0": 0 } }],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    })
}

#[test]
fn a_parallelogram_with_a_third_crank_moves_and_reports_the_redundant_joint() {
    let m = model(&triple_crank());
    let a = m
        .assemble(&[0.9], None, &AssemblyOptions::default())
        .unwrap();
    let mobility = m.mobility(&a.q, &[0.9]);
    assert_eq!(mobility.grubler, 0);
    assert_eq!(mobility.numerical, 1);
    assert_eq!(mobility.redundant.len(), 1, "{:?}", mobility.redundant);
    assert_eq!(mobility.redundant[0].rows, 1);
    assert_eq!(mobility.redundant[0].joint_id, "top-3");
    assert!(mobility.free_motions.is_empty());
}

#[test]
fn an_undriven_four_bar_has_one_free_motion_through_its_moving_links() {
    let mut v = golden("four-bar-crank-rocker.json");
    v["drivers"] = json!([]);
    let m = model(&v);
    let a = m.assemble(&[], None, &AssemblyOptions::default()).unwrap();
    let mobility = m.mobility(&a.q, &[]);
    assert_eq!((mobility.grubler, mobility.numerical), (1, 1));
    assert_eq!(mobility.free_motions.len(), 1);
    let mut bodies: Vec<&str> = mobility.free_motions[0]
        .iter()
        .map(|b| b.body_id.as_str())
        .collect();
    bodies.sort_unstable();
    assert_eq!(bodies, ["coupler", "crank", "rocker"]);
}

#[test]
fn the_cam_mechanisms_free_leaf_is_reported() {
    let m = model(&golden("cam-followers-and-spring.json"));
    let a = m
        .assemble(&[0.3], None, &AssemblyOptions::default())
        .unwrap();
    let mobility = m.mobility(&a.q, &[0.3]);
    // The cam (1 driven) plus the leaf, which nothing holds.
    assert_eq!(mobility.numerical, 2);
    assert_eq!(mobility.free_motions.len(), 1);
    assert_eq!(mobility.free_motions[0].len(), 1);
    let leaf = &mobility.free_motions[0][0];
    assert_eq!(leaf.body_id, "leaf");
    assert!(leaf.dtheta.abs() > 0.5);
}

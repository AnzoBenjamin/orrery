//! Pin-in-slot, gear, belt, and cam joints, and springs (mechanism-core requirements 3.1, 3.2,
//! 3.5, 3.6, and 4.4), on the golden mechanisms and on small purpose-built ones.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::{FRAC_PI_2, TAU};
use std::path::Path;

use kinematics::curves::{CamProfile, Curve};
use kinematics::energy::spring_energy;
use kinematics::model::Model;
use kinematics::planar::V2;
use kinematics::schema::{Mechanism, parse_mechanism};
use kinematics::{AssemblyOptions, SolverError};
use proptest::prelude::*;
use serde_json::{Value, json};

fn golden(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn mechanism(value: &Value) -> Mechanism {
    parse_mechanism(&value.to_string()).unwrap()
}

fn model_of(value: &Value) -> Model {
    Model::new(&mechanism(value)).unwrap()
}

fn theta(m: &Model, q: &[f64], body: &str) -> f64 {
    m.pose(m.body(body).unwrap(), q).theta
}

fn world(m: &Model, q: &[f64], body: &str, point: &str) -> V2 {
    let w = m.point_world(m.body(body).unwrap(), point, q).unwrap();
    V2::new(w[0], w[1])
}

/// A world point in a body's local frame.
fn local(m: &Model, q: &[f64], body: &str, p: V2) -> V2 {
    let pose = m.pose(m.body(body).unwrap(), q);
    let d = p - V2::new(pose.x, pose.y);
    let (s, c) = pose.theta.sin_cos();
    V2::new(c * d.x + s * d.y, -s * d.x + c * d.y)
}

fn sweep(m: &Model, steps: u32, mut check: impl FnMut(f64, &[f64])) {
    let mut seed: Option<Vec<f64>> = None;
    for step in 0..=steps {
        let angle = TAU * f64::from(step) / f64::from(steps);
        let drive: Vec<f64> = vec![angle; m.drivers.len()];
        let a = m
            .assemble(&drive, seed.as_deref(), &AssemblyOptions::default())
            .unwrap_or_else(|e| panic!("at {angle}: {e}"));
        assert!(a.max_residual < 1e-9);
        check(angle, &a.q);
        seed = Some(a.q);
    }
}

#[test]
fn gears_and_belts_turn_at_their_ratios() {
    let m = model_of(&golden("gear-train-and-belts.json"));
    let mut seed: Option<Vec<f64>> = None;
    for step in 0..24 {
        let (pinion, belt) = (0.3 * f64::from(step), -0.2 * f64::from(step));
        let a = m
            .assemble(
                &[pinion, belt],
                seed.as_deref(),
                &AssemblyOptions::default(),
            )
            .unwrap();
        let q = &a.q;
        // External mesh, ratio −3 (36 teeth over 12): the wheel turns a third as far, backwards.
        assert!((theta(&m, q, "wheel") + pinion / 3.0).abs() < 1e-9);
        // Internal mesh, ratio 3 with phase 0.05: planet = 3·ring + 0.05, same direction.
        assert!((theta(&m, q, "planet") - 3.0f64.mul_add(theta(&m, q, "ring"), 0.05)).abs() < 1e-9);
        // Open belt, ratio 2: same direction, half as far. Crossed belt, ratio 1.5: reversed.
        assert!((theta(&m, q, "p2") - belt / 2.0).abs() < 1e-9);
        assert!((theta(&m, q, "p3") + belt / 1.5).abs() < 1e-9);
        seed = Some(a.q);
    }
}

#[test]
fn slots_hold_their_pins_through_a_full_turn() {
    let m = model_of(&golden("slots.json"));
    let spline = Curve::bspline(
        [
            (-0.13, 0.06),
            (-0.095, 0.075),
            (-0.06, 0.05),
            (-0.025, 0.07),
            (0.01, 0.06),
        ]
        .map(|(x, y)| V2::new(x, y))
        .to_vec(),
        vec![0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0],
    )
    .unwrap();
    sweep(&m, 72, |angle, q| {
        let pin = world(&m, q, "crank", "pin");
        assert!((pin - V2::new(0.04 * angle.cos(), 0.04 * angle.sin())).norm() < 1e-9);
        // Scotch yoke: the yoke follows the pin's x exactly.
        assert!(
            (world(&m, q, "yoke", "guide").x - (0.04f64.mul_add(angle.cos(), -0.04))).abs() < 1e-9
        );
        // The pin is 0.1 from the lever's arc center.
        let center = local(&m, q, "lever", pin) - V2::new(-0.2, 0.0);
        assert!((center.norm() - 0.1).abs() < 1e-9);
        // The pin block's pin sits on the spline groove in the frame.
        let p = world(&m, q, "pin-block", "pin");
        let nearest = (0..=4000)
            .map(|i| (spline.eval(f64::from(i) / 4000.0).0 - p).norm())
            .fold(f64::INFINITY, f64::min);
        assert!(nearest < 2e-5, "pin is {nearest} from the groove");
    });
}

#[test]
fn cam_followers_touch_the_profile() {
    let m = model_of(&golden("cam-followers-and-spring.json"));
    let profile = CamProfile {
        base: 0.03,
        a: vec![0.0, 0.008, 0.002],
        b: vec![0.0, 0.004, 0.0],
    };
    let samples: Vec<V2> = (0..20_000)
        .map(|i| profile.point(TAU * f64::from(i) / 20_000.0).0)
        .collect();
    sweep(&m, 36, |_, q| {
        // Knife: the edge is on the profile.
        let edge = local(&m, q, "cam", world(&m, q, "knife-follower", "edge"));
        assert!((edge.norm() - profile.radius(edge.y.atan2(edge.x)).0).abs() < 1e-9);
        // Roller: its center is one roller radius from the profile.
        let roller = local(&m, q, "cam", world(&m, q, "roller-follower", "roller"));
        let gap = samples
            .iter()
            .map(|c| (*c - roller).norm())
            .fold(f64::INFINITY, f64::min);
        assert!((gap - 0.008).abs() < 1e-5, "roller gap {gap}");
        // Flat face: a supporting line of the cam, touching it with the cam on one side.
        let face = local(&m, q, "cam", world(&m, q, "flat-follower", "face"));
        // The face runs along the follower's local x axis, so its normal is the local y axis.
        let relative = theta(&m, q, "flat-follower") - theta(&m, q, "cam");
        let normal = V2::new(-relative.sin(), relative.cos());
        let sides: Vec<f64> = samples.iter().map(|c| normal.dot(*c - face)).collect();
        let (lo, hi) = sides
            .iter()
            .fold((f64::INFINITY, f64::NEG_INFINITY), |(l, h), v| {
                (l.min(*v), h.max(*v))
            });
        assert!(
            lo.abs() < 1e-6 || hi.abs() < 1e-6,
            "face cuts the cam: {lo} to {hi}"
        );
    });
}

fn pendulum(springs: &Value) -> Value {
    let hinge = json!({ "id": "hinge", "kind": "revolute", "bodyA": "ground", "bodyB": "lever",
        "anchorA": {"bodyId":"ground","pointId":"pivot"}, "anchorB": {"bodyId":"lever","pointId":"pivot"},
        "status": "observed", "confidence": 1 });
    let joints: Vec<Value> = std::iter::once(hinge)
        .chain(springs.as_array().unwrap().iter().cloned())
        .collect();
    json!({
        "schemaVersion": 1, "id": "pendulum", "name": "Sprung lever",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [{ "id": "p", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": [
            { "id": "ground", "label": "G", "kind": "ground", "planeId": "p", "status": "observed", "confidence": 1,
              "points": [
                { "id": "pivot", "local": {"x":0,"y":0,"z":0}, "role": "joint_anchor" },
                { "id": "below", "local": {"x":0,"y":-0.3,"z":0}, "role": "joint_anchor" },
                { "id": "right", "local": {"x":0.3,"y":0,"z":0}, "role": "joint_anchor" }] },
            { "id": "lever", "label": "A", "kind": "link", "planeId": "p", "status": "observed", "confidence": 1,
              "points": [
                { "id": "pivot", "local": {"x":0,"y":0,"z":0}, "role": "joint_anchor" },
                { "id": "tip", "local": {"x":0.1,"y":0,"z":0}, "role": "joint_anchor" }] }],
        "joints": joints,
        "drivers": [],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    })
}

fn spring(id: &str, to: &str, k: f64, free: f64) -> Value {
    json!({ "id": id, "kind": "spring", "bodyA": "ground", "bodyB": "lever",
        "anchorA": {"bodyId":"ground","pointId":to}, "anchorB": {"bodyId":"lever","pointId":"tip"},
        "stiffness": k, "freeLength": free, "status": "observed", "confidence": 1 })
}

#[test]
fn springs_settle_a_free_lever_at_least_energy() {
    // Zero free length: the tip points along k₁·(0, −0.3) + k₂·(0.3, 0).
    let m = model_of(&pendulum(&json!([
        spring("s1", "below", 100.0, 0.0),
        spring("s2", "right", 300.0, 0.0)
    ])));
    let a = m.assemble(&[], None, &AssemblyOptions::default()).unwrap();
    let angle = theta(&m, &a.q, "lever");
    assert!(
        (angle - (-30.0f64).atan2(90.0)).abs() < 1e-7,
        "lever at {angle}"
    );

    // Stretched springs with free lengths: compare with the minimum over a fine search.
    let m = model_of(&pendulum(&json!([
        spring("s1", "below", 120.0, 0.15),
        spring("s2", "right", 40.0, 0.05)
    ])));
    let a = m.assemble(&[], None, &AssemblyOptions::default()).unwrap();
    let energy_at = |phi: f64| {
        let tip = V2::new(0.1 * phi.cos(), 0.1 * phi.sin());
        let e1 = 0.5 * 120.0 * ((tip - V2::new(0.0, -0.3)).norm() - 0.15).powi(2);
        let e2 = 0.5 * 40.0 * ((tip - V2::new(0.3, 0.0)).norm() - 0.05).powi(2);
        e1 + e2
    };
    let best = (0..200_000)
        .map(|i| TAU * f64::from(i) / 200_000.0 - std::f64::consts::PI)
        .min_by(|x, y| energy_at(*x).total_cmp(&energy_at(*y)))
        .unwrap();
    let got = theta(&m, &a.q, "lever");
    let wrapped = (got - best + std::f64::consts::PI).rem_euclid(TAU) - std::f64::consts::PI;
    assert!(
        wrapped.abs() < 1e-4,
        "lever at {got}, least energy at {best}"
    );
    assert!(spring_energy(&m, &a.q) <= energy_at(best) + 1e-12);
    assert!(a.max_residual < 1e-9);
}

#[test]
fn a_pin_past_its_slot_end_is_an_assembly_failure() {
    let mut value = golden("slots.json");
    value["joints"][2]["slot"]["start"]["y"] = (-0.02).into();
    value["joints"][2]["slot"]["end"]["y"] = 0.02.into();
    let m = model_of(&value);
    assert!(
        m.assemble(&[0.1], None, &AssemblyOptions::default())
            .is_ok()
    );
    match m.assemble(&[FRAC_PI_2], None, &AssemblyOptions::default()) {
        Err(SolverError::AssemblyFailed { worst_joints }) => {
            assert!(
                worst_joints.iter().any(|j| j.joint_id == "slot-straight"),
                "{worst_joints:?}"
            );
        }
        other => panic!("expected AssemblyFailed, got {other:?}"),
    }
}

#[test]
fn a_slider_past_its_limits_is_an_assembly_failure() {
    let mut value = golden("slider-crank.json");
    value["joints"][3]["limits"] = json!([0.15, 0.24]);
    let m = model_of(&value);
    assert!(
        m.assemble(&[0.0], None, &AssemblyOptions::default())
            .is_ok()
    );
    match m.assemble(&[std::f64::consts::PI], None, &AssemblyOptions::default()) {
        Err(SolverError::AssemblyFailed { worst_joints }) => {
            assert_eq!(worst_joints[0].joint_id, "j-rail");
            // The near branch overshoots by 0.15 − 0.13; the mirrored branch by more.
            assert!(worst_joints[0].residual >= 0.02 - 1e-9);
        }
        other => panic!("expected AssemblyFailed, got {other:?}"),
    }
}

#[test]
fn gears_need_a_shared_carrier() {
    let mut value = golden("gear-train-and-belts.json");
    // Unpin the wheel: the external mesh has no carrier left.
    let joints = value["joints"].as_array_mut().unwrap();
    joints.retain(|j| j["id"] != "j-wheel");
    match Model::new(&mechanism(&value)) {
        Err(SolverError::InvalidGraph(issues)) => {
            assert!(
                issues
                    .iter()
                    .any(|i| i.message.contains("one carrier body"))
            );
        }
        other => panic!("expected InvalidGraph, got {other:?}"),
    }
}

#[test]
fn cam_polyline_stays_within_tolerance() {
    let profile = CamProfile {
        base: 0.03,
        a: vec![0.0, 0.008, 0.002],
        b: vec![0.0, 0.004, 0.0],
    };
    for tolerance in [1e-4, 1e-5, 1e-6] {
        let poly = profile.polyline(tolerance);
        for (i, a) in poly.iter().enumerate() {
            let b = poly[(i + 1) % poly.len()];
            // The curve between two neighbors: sample it and measure its distance to the chord.
            let (ta, tb) = (a.y.atan2(a.x), b.y.atan2(b.x));
            let span = (tb - ta).rem_euclid(TAU);
            for k in 1..8 {
                let c = profile.point(ta + span * f64::from(k) / 8.0).0;
                let chord = b - *a;
                let off = (c - *a).dot(chord.perp()).abs() / chord.norm();
                assert!(off <= tolerance * 1.01, "deviation {off} > {tolerance}");
            }
        }
    }
}

fn finite_difference_matches(m: &Model, q: &[f64], drive: &[f64]) -> Result<(), TestCaseError> {
    let rows = m.n_rows();
    let mut analytic = vec![vec![0.0; m.n_vars]; rows];
    for (i, j, v) in m.jacobian(q, drive) {
        analytic[i][j] += v;
    }
    let h = 1e-6;
    for j in 0..m.n_vars {
        let (mut up, mut down) = (q.to_vec(), q.to_vec());
        up[j] += h;
        down[j] -= h;
        let (ru, rd) = (m.residuals(&up, drive), m.residuals(&down, drive));
        for i in 0..rows {
            let numeric = (ru[i] - rd[i]) / (2.0 * h);
            prop_assert!(
                (numeric - analytic[i][j]).abs() < 1e-5 * (1.0 + numeric.abs()),
                "{}: d r{i} / d q{j}: analytic {} numeric {numeric}",
                m.constraints
                    .iter()
                    .scan(0, |row, c| {
                        let start = *row;
                        *row += c.dim();
                        Some((start, c))
                    })
                    .filter(|(start, c)| *start <= i && i < start + c.dim())
                    .map(|(_, c)| c.source_id().to_owned())
                    .next()
                    .unwrap_or_default(),
                analytic[i][j]
            );
        }
    }
    Ok(())
}

proptest! {
    #[test]
    fn slot_gear_belt_and_cam_jacobians_are_exact(
        seed in prop::collection::vec(-1.0..1.0_f64, 40),
        drive in -3.0..3.0_f64,
    ) {
        for name in ["slots.json", "gear-train-and-belts.json", "cam-followers-and-spring.json"] {
            let m = model_of(&golden(name));
            let q: Vec<f64> = (0..m.n_vars).map(|i| seed[i % seed.len()] * 0.2 + 0.05 * (i as f64)).collect();
            finite_difference_matches(&m, &q, &vec![drive; m.drivers.len()])?;
        }
    }

    /// Property 9: for any gear pair with ratio r, the input turns r times the output (the
    /// schema's ratio is teeth B over teeth A, negative for an external mesh).
    #[test]
    fn gear_pairs_hold_their_ratio(ratio in prop_oneof![-6.0..-0.2_f64, 0.2..6.0_f64], input in -20.0..20.0_f64) {
        let mut value = golden("gear-train-and-belts.json");
        value["joints"].as_array_mut().unwrap().iter_mut()
            .find(|j| j["id"] == "mesh-external").unwrap()["ratio"] = ratio.into();
        let m = model_of(&value);
        let a = m.assemble(&[input, 0.0], None, &AssemblyOptions::default()).unwrap();
        prop_assert!((theta(&m, &a.q, "pinion") - ratio * theta(&m, &a.q, "wheel")).abs() < 1e-9);
    }

    #[test]
    fn bspline_derivative_matches_finite_differences(s in 0.0..1.0_f64) {
        let curve = Curve::bspline(
            [(0.0, 0.0), (0.1, 0.3), (0.4, -0.2), (0.6, 0.5), (0.9, 0.1), (1.0, 0.0)].map(|(x, y)| V2::new(x, y)).to_vec(),
            vec![0.0, 0.0, 0.0, 0.0, 0.3, 0.7, 1.0, 1.0, 1.0, 1.0],
        ).unwrap();
        let h = 1e-6;
        let numeric = (curve.eval(s + h).0 - curve.eval(s - h).0) * (0.5 / h);
        prop_assert!((numeric - curve.eval(s).1).norm() < 1e-5);
    }
}

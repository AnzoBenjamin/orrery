//! Spatial bodies and joints (mechanism-core requirements 3.3 and 3.4).

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::TAU;
use std::path::Path;

use kinematics::AssemblyOptions;
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use kinematics::simulate::SimulationOptions;
use proptest::prelude::*;
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

fn world(m: &Model, q: &[f64], body: &str, point: &str) -> [f64; 3] {
    m.point_world(m.body(body).unwrap(), point, q).unwrap()
}

fn dist(a: [f64; 3], b: [f64; 3]) -> f64 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

#[test]
fn a_double_cardan_shaft_between_two_planar_yokes_turns_at_constant_velocity() {
    let m = model(&golden("two-plane-subsystems.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 72.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    assert_eq!(sim.reachable, vec![(0.0, TAU)]);
    for s in &sim.samples {
        let (input, output) = (
            m.pose(m.body("input-yoke").unwrap(), &s.q).theta,
            m.pose(m.body("output-yoke").unwrap(), &s.q).theta,
        );
        assert!(
            (output - input).abs() < 1e-9,
            "at {}: output {output}, input {input}",
            s.drive
        );
        // The universal joint centers stay on the bearing axes.
        assert!(dist(world(&m, &s.q, "shaft-front", "cross"), [0.0, 0.0, 0.0]) < 1e-9);
        assert!(dist(world(&m, &s.q, "shaft-rear", "cross"), [0.4, 0.1, 0.0]) < 1e-9);
    }
    // The universal joint centers are fixed, so the slip joint cannot slide: once driven,
    // nothing is free.
    let last = &sim.samples[sim.samples.len() - 1];
    let mobility = m.mobility(&last.q, &[last.drive]);
    assert_eq!(mobility.numerical, 1);
    assert!(
        mobility.free_motions.is_empty(),
        "{:?}",
        mobility.free_motions
    );
}

#[test]
fn a_spatial_rssr_keeps_its_links_rigid_through_a_turn() {
    let m = model(&golden("spatial-rssr.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 72.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    assert_eq!(sim.reachable, vec![(0.0, TAU)]);
    let axis = [
        0.0,
        std::f64::consts::FRAC_1_SQRT_2,
        std::f64::consts::FRAC_1_SQRT_2,
    ];
    for s in &sim.samples {
        let ball = world(&m, &s.q, "crank", "ball");
        // The crank turns about world z through the origin.
        assert!((ball[0].hypot(ball[1]) - 0.06).abs() < 1e-9 && ball[2].abs() < 1e-9);
        assert!((ball[1].atan2(ball[0]) - s.drive).sin().abs() < 1e-9);
        // The coupler keeps its length between the two balls.
        let rocker_ball = world(&m, &s.q, "rocker", "ball");
        assert!((dist(ball, rocker_ball) - 0.32).abs() < 1e-9);
        let d: Vec<f64> = (0..3)
            .map(|k| rocker_ball[k] - [0.3, 0.1, 0.05][k])
            .collect();
        let along: f64 = (0..3).map(|k| d[k] * axis[k]).sum();
        let radial = (d.iter().map(|x| x * x).sum::<f64>() - along * along).sqrt();
        // The rocker arm is square to its axis: the ball stays in the plane through the axle,
        // 0.18 from the axis.
        assert!(along.abs() < 1e-9);
        assert!((radial - 0.18).abs() < 1e-9);
    }
}

#[test]
fn a_spatial_slider_crank_moves_its_piston_by_the_closed_form() {
    let m = model(&golden("spatial-slider-crank.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 72.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    assert_eq!(sim.reachable, vec![(0.0, TAU)]);
    for s in &sim.samples {
        let pin = [0.04 * s.drive.cos(), 0.04 * s.drive.sin(), 0.0];
        // The wrist is on the bore line (y = 0.02, z = 0.04), 0.2 from the crank pin.
        let x = pin[0] + (0.2f64.powi(2) - (0.02 - pin[1]).powi(2) - 0.04f64.powi(2)).sqrt();
        let wrist = world(&m, &s.q, "piston", "wrist");
        assert!(
            dist(wrist, [x, 0.02, 0.04]) < 1e-9,
            "at {}: {wrist:?} vs x = {x}",
            s.drive
        );
    }
    // Driven, the rod's spin and the piston's spin are left: idle freedoms.
    let last = &sim.samples[sim.samples.len() - 1];
    let mobility = m.mobility(&last.q, &[last.drive]);
    assert_eq!(mobility.numerical, 3);
    assert_eq!(
        mobility.free_motions.len(),
        2,
        "{:?}",
        mobility.free_motions
    );
}

#[test]
fn a_spatial_slider_moves_along_its_tilted_axis_without_turning() {
    let k = 1.0 / 3.0_f64.sqrt();
    let v = json!({
        "schemaVersion": 1, "id": "tilted", "name": "Tilted slider",
        "scale": { "source": "unscaled", "metersPerUnit": 1 }, "planes": [],
        "bodies": [
            { "id": "ground", "label": "G", "kind": "ground", "planeId": null, "status": "observed", "confidence": 1,
              "points": [{ "id": "rail", "local": {"x": 0.1, "y": 0.2, "z": 0.3}, "role": "joint_anchor" }] },
            { "id": "slider", "label": "A", "kind": "slider_block", "planeId": null, "status": "observed", "confidence": 1,
              "points": [{ "id": "rail", "local": {"x": 0, "y": 0, "z": 0}, "role": "joint_anchor" },
                         { "id": "corner", "local": {"x": 0.02, "y": 0.01, "z": 0}, "role": "tracked" }] }],
        "joints": [{ "id": "rail", "kind": "prismatic", "bodyA": "ground", "bodyB": "slider",
            "anchorA": {"bodyId":"ground","pointId":"rail"}, "anchorB": {"bodyId":"slider","pointId":"rail"},
            "axisLocalA": {"x": 1, "y": 1, "z": 1}, "limits": [-0.1, 0.1], "status": "observed", "confidence": 1 }],
        "drivers": [{ "id": "push", "jointId": "rail", "coordinate": "displacement",
            "profile": { "type": "constant_rate", "rate": 0.01, "phase0": 0 } }],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    });
    let m = model(&v);
    for s in [-0.08, 0.0, 0.05] {
        let a = m.assemble(&[s], None, &AssemblyOptions::default()).unwrap();
        let p = world(&m, &a.q, "slider", "rail");
        for (c, base) in [0.1, 0.2, 0.3].iter().enumerate() {
            assert!((p[c] - (base + s * k)).abs() < 1e-9);
        }
        // Orientation unchanged: the corner keeps its offset.
        let corner = world(&m, &a.q, "slider", "corner");
        assert!((corner[0] - p[0] - 0.02).abs() < 1e-9 && (corner[1] - p[1] - 0.01).abs() < 1e-9);
    }
    assert!(
        m.assemble(&[0.15], None, &AssemblyOptions::default())
            .is_err()
    );
}

#[test]
fn spatial_point_derivatives_match_finite_differences() {
    for name in [
        "spatial-rssr.json",
        "two-plane-subsystems.json",
        "spatial-slider-crank.json",
    ] {
        let m = model(&golden(name));
        let base = m
            .assemble(&[0.7], None, &AssemblyOptions::default())
            .unwrap();
        let motion = m.point_motion(&base.q, &[0.7], 0);
        let h = 1e-4;
        let near = |d: f64| {
            m.assemble(&[d], Some(&base.q), &AssemblyOptions::default())
                .unwrap()
                .q
        };
        let (up, down) = (near(0.7 + h), near(0.7 - h));
        // Only points the driver moves: free spins and slides are not part of the motion.
        for (body, point) in [
            ("crank", "ball"),
            ("crank", "pin"),
            ("rocker", "tip"),
            ("input-yoke", "rim"),
            ("output-yoke", "rim"),
            ("piston", "wrist"),
        ] {
            let Some(b) = m.body(body) else { continue };
            let Some(p0) = m.point_world(b, point, &base.q) else {
                continue;
            };
            let (pu, pd) = (
                m.point_world(b, point, &up).unwrap(),
                m.point_world(b, point, &down).unwrap(),
            );
            let got = motion[&(body.to_owned(), point.to_owned())];
            for c in 0..3 {
                let v = (pu[c] - pd[c]) / (2.0 * h);
                let a = (pu[c] - 2.0 * p0[c] + pd[c]) / (h * h);
                assert!(
                    (got.velocity[c] - v).abs() < 1e-6,
                    "{name} {body}.{point} v[{c}]: {} vs {v}",
                    got.velocity[c]
                );
                assert!(
                    (got.acceleration[c] - a).abs() < 1e-3 * (1.0 + a.abs()),
                    "{name} {body}.{point} a[{c}]: {} vs {a}",
                    got.acceleration[c]
                );
            }
        }
    }
}

proptest! {
    #[test]
    fn spatial_jacobians_match_finite_differences(
        seed in prop::collection::vec(-1.0..1.0_f64, 40),
        drive in -3.0..3.0_f64,
    ) {
        for name in ["spatial-rssr.json", "two-plane-subsystems.json", "spatial-slider-crank.json"] {
            let m = model(&golden(name));
            let q: Vec<f64> = (0..m.n_vars).map(|i| seed[i % seed.len()] * 0.5 + 0.03 * (i as f64)).collect();
            let rows = m.n_rows();
            let mut analytic = vec![vec![0.0; m.n_vars]; rows];
            for (i, j, v) in m.jacobian(&q, &[drive]) {
                analytic[i][j] += v;
            }
            let h = 1e-6;
            for j in 0..m.n_vars {
                let (mut up, mut down) = (q.clone(), q.clone());
                up[j] += h;
                down[j] -= h;
                let (ru, rd) = (m.residuals(&up, &[drive]), m.residuals(&down, &[drive]));
                for i in 0..rows {
                    let numeric = (ru[i] - rd[i]) / (2.0 * h);
                    prop_assert!((numeric - analytic[i][j]).abs() < 1e-5 * (1.0 + numeric.abs()),
                        "{name} d r{i} / d q{j}: {} vs {numeric}", analytic[i][j]);
                }
            }
        }
    }
}

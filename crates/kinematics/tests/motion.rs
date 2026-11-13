//! Velocities and accelerations of named points (mechanism-core requirement 5.5).

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::path::Path;

use kinematics::AssemblyOptions;
use kinematics::dual::Jet;
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use proptest::prelude::*;

fn model(name: &str) -> Model {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    Model::new(&parse_mechanism(&std::fs::read_to_string(path).unwrap()).unwrap()).unwrap()
}

#[test]
fn slider_velocity_and_acceleration_match_the_closed_form() {
    let m = model("slider-crank.json");
    let (r, l) = (0.05_f64, 0.18_f64);
    let x = |t: f64| r * t.cos() + (l * l - (r * t.sin()).powi(2)).sqrt();
    let dx = |t: f64| {
        let root = (l * l - (r * t.sin()).powi(2)).sqrt();
        -r * t.sin() - r * r * t.sin() * t.cos() / root
    };
    let mut seed: Option<Vec<f64>> = None;
    for step in 0..24 {
        let t = 0.27 * f64::from(step);
        let a = m
            .assemble(&[t], seed.as_deref(), &AssemblyOptions::default())
            .unwrap();
        let motion = m.point_motion(&a.q, &[t], 0);
        let slider = motion[&("slider".to_owned(), "c".to_owned())];
        let h = 1e-5;
        let ddx = (dx(t + h) - dx(t - h)) / (2.0 * h);
        assert!((slider.position[0] - x(t)).abs() < 1e-9);
        assert!(
            (slider.velocity[0] - dx(t)).abs() < 1e-9,
            "{} vs {}",
            slider.velocity[0],
            dx(t)
        );
        assert!(
            (slider.acceleration[0] - ddx).abs() < 1e-7,
            "{} vs {ddx}",
            slider.acceleration[0]
        );
        assert!(slider.velocity[1].abs() < 1e-12 && slider.acceleration[1].abs() < 1e-12);
        seed = Some(a.q);
    }
}

/// Every named point's derivatives against central differences of re-assembled poses.
fn matches_finite_differences(name: &str, at: f64) {
    let m = model(name);
    let drive = |d: f64| {
        let mut v = vec![0.0; m.drivers.len()];
        v[0] = d;
        v
    };
    let base = m
        .assemble(&drive(at), None, &AssemblyOptions::default())
        .unwrap();
    let motion = m.point_motion(&base.q, &drive(at), 0);
    let h = 1e-4;
    let near = |d: f64| {
        m.assemble(&drive(d), Some(&base.q), &AssemblyOptions::default())
            .unwrap()
    };
    let (up, down) = (near(at + h), near(at - h));
    for (i, body) in m.bodies.iter().enumerate() {
        for point in body.points.keys() {
            let (p0, pu, pd) = (
                m.point_world(i, point, &base.q).unwrap(),
                m.point_world(i, point, &up.q).unwrap(),
                m.point_world(i, point, &down.q).unwrap(),
            );
            let got = motion[&(body.id.clone(), point.clone())];
            for c in 0..3 {
                let v = (pu[c] - pd[c]) / (2.0 * h);
                let a = (pu[c] - 2.0 * p0[c] + pd[c]) / (h * h);
                assert!(
                    (got.velocity[c] - v).abs() < 1e-6,
                    "{name} {}.{point} v[{c}]: {} vs {v}",
                    body.id,
                    got.velocity[c]
                );
                assert!(
                    (got.acceleration[c] - a).abs() < 1e-3 * (1.0 + a.abs()),
                    "{name} {}.{point} a[{c}]: {} vs {a}",
                    body.id,
                    got.acceleration[c]
                );
            }
        }
    }
}

#[test]
fn point_derivatives_match_finite_differences_on_the_goldens() {
    for (name, at) in [
        ("four-bar-crank-rocker.json", 0.8),
        ("slots.json", 1.1),
        ("cam-followers-and-spring.json", 0.4),
        ("gear-train-and-belts.json", 0.6),
    ] {
        matches_finite_differences(name, at);
    }
}

proptest! {
    /// The Jet's first-order term is the analytic Jacobian times the direction, for every
    /// constraint kind.
    #[test]
    fn jet_first_order_terms_equal_the_jacobian_product(
        q in prop::collection::vec(-1.0..1.0_f64, 40),
        v in prop::collection::vec(-1.0..1.0_f64, 40),
        d in -2.0..2.0_f64,
    ) {
        for name in ["four-bar-crank-rocker.json", "slider-crank.json", "slots.json", "gear-train-and-belts.json", "cam-followers-and-spring.json"] {
            let m = model(name);
            let n = m.n_vars;
            let q: Vec<f64> = (0..n).map(|i| q[i % 40] * 0.3 + 0.01 * (i as f64)).collect();
            let v: Vec<f64> = (0..n).map(|i| v[i % 40]).collect();
            let drive = vec![d; m.drivers.len()];
            let jets: Vec<Jet> = q.iter().zip(&v).map(|(a, b)| Jet::new(*a, *b, 0.0)).collect();
            let r = m.residuals_jet(&jets, &drive);
            let mut jv = vec![0.0; m.n_rows()];
            for (i, j, x) in m.jacobian(&q, &drive) {
                jv[i] += x * v[j];
            }
            let plain = m.residuals(&q, &drive);
            for i in 0..m.n_rows() {
                prop_assert!((r[i].v - plain[i]).abs() < 1e-12);
                prop_assert!((r[i].d1 - jv[i]).abs() < 1e-9 * (1.0 + jv[i].abs()), "{name} row {i}: {} vs {}", r[i].d1, jv[i]);
            }
        }
    }
}

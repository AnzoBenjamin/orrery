//! Assembly of planar mechanisms (mechanism-core requirements 4.1 to 4.3) checked against
//! closed-form positions, plus analytic Jacobians checked against finite differences.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::TAU;
use std::path::Path;

use kinematics::model::Model;
use kinematics::schema::{Mechanism, parse_mechanism};
use kinematics::{AssemblyOptions, LinearPath, SolverError};
use proptest::prelude::*;
use serde_json::Value;

fn golden(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn mechanism(value: &Value) -> Mechanism {
    parse_mechanism(&value.to_string()).unwrap()
}

fn model(name: &str) -> Model {
    Model::new(&mechanism(&golden(name))).unwrap()
}

fn point(m: &Model, q: &[f64], body: &str, p: &str) -> [f64; 2] {
    let w = m.point_world(m.body(body).unwrap(), p, q).unwrap();
    [w[0], w[1]]
}

fn dist(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}

/// The two intersections of circle(c1, r1) and circle(c2, r2).
fn circle_intersections(c1: [f64; 2], r1: f64, c2: [f64; 2], r2: f64) -> [[f64; 2]; 2] {
    let d = dist(c1, c2);
    let a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d);
    let h = (r1 * r1 - a * a).sqrt();
    let (ux, uy) = ((c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d);
    let (mx, my) = (c1[0] + a * ux, c1[1] + a * uy);
    [[mx - h * uy, my + h * ux], [mx + h * uy, my - h * ux]]
}

#[test]
fn four_bar_follows_the_closed_form_on_one_branch_through_a_full_turn() {
    let m = model("four-bar-crank-rocker.json");
    let options = AssemblyOptions::default();
    let mut seed: Option<Vec<f64>> = None;
    let mut branch: Option<usize> = None;
    for step in 0..=72 {
        let theta = TAU * f64::from(step) / 72.0;
        let a = m.assemble(&[theta], seed.as_deref(), &options).unwrap();
        assert!(
            a.max_residual < 1e-9,
            "residual {} at {theta}",
            a.max_residual
        );
        let b = point(&m, &a.q, "crank", "b");
        assert!(dist(b, [0.1 * theta.cos(), 0.1 * theta.sin()]) < 1e-9);
        let c = point(&m, &a.q, "rocker", "c");
        let candidates = circle_intersections(b, 0.25, [0.3, 0.0], 0.2);
        let (which, error) = candidates
            .iter()
            .map(|k| dist(*k, c))
            .enumerate()
            .min_by(|x, y| x.1.total_cmp(&y.1))
            .unwrap();
        assert!(
            error < 1e-9,
            "C is off the closed form by {error} at {theta}"
        );
        // Continuation keeps the mechanism on the branch it started on (requirement 4.2).
        assert_eq!(
            *branch.get_or_insert(which),
            which,
            "branch flipped at {theta}"
        );
        // Rigid bodies keep their shape.
        assert!(
            (dist(
                point(&m, &a.q, "coupler", "b"),
                point(&m, &a.q, "coupler", "trace")
            ) - 0.125_f64.hypot(0.06))
            .abs()
                < 1e-9
        );
        seed = Some(a.q);
    }
}

#[test]
fn slider_crank_slider_position_matches_the_closed_form() {
    let m = model("slider-crank.json");
    let (r, l) = (0.05_f64, 0.18_f64);
    let mut seed: Option<Vec<f64>> = None;
    for step in 0..36 {
        let theta = TAU * f64::from(step) / 36.0;
        let a = m
            .assemble(&[theta], seed.as_deref(), &AssemblyOptions::default())
            .unwrap();
        let slider = point(&m, &a.q, "slider", "c");
        let expected = r * theta.cos() + (l * l - (r * theta.sin()).powi(2)).sqrt();
        assert!(
            (slider[0] - expected).abs() < 1e-9,
            "x {} vs {expected} at {theta}",
            slider[0]
        );
        assert!(slider[1].abs() < 1e-9);
        // The slider keeps the ground's orientation.
        assert!(m.pose(m.body("slider").unwrap(), &a.q).theta.abs() < 1e-9);
        seed = Some(a.q);
    }
}

#[test]
fn dense_and_sparse_paths_agree() {
    let m = model("four-bar-crank-rocker.json");
    let seed = m
        .assemble(&[0.4], None, &AssemblyOptions::default())
        .unwrap()
        .q;
    let dense = m
        .assemble(
            &[0.7],
            Some(&seed),
            &AssemblyOptions {
                path: LinearPath::Dense,
                ..Default::default()
            },
        )
        .unwrap();
    let sparse = m
        .assemble(
            &[0.7],
            Some(&seed),
            &AssemblyOptions {
                path: LinearPath::Sparse,
                ..Default::default()
            },
        )
        .unwrap();
    for (x, y) in dense.q.iter().zip(&sparse.q) {
        assert!((x - y).abs() < 1e-9);
    }
}

#[test]
fn a_linkage_that_cannot_close_reports_the_worst_joints() {
    let mut value = golden("four-bar-crank-rocker.json");
    // Move the rocker pivot out of reach: 0.1 + 0.25 + 0.2 < 0.8.
    value["bodies"][0]["points"][1]["local"]["x"] = 0.8.into();
    let m = Model::new(&mechanism(&value)).unwrap();
    match m.assemble(&[0.3], None, &AssemblyOptions::default()) {
        Err(SolverError::AssemblyFailed { worst_joints }) => {
            assert!(!worst_joints.is_empty() && worst_joints.len() <= 3);
            assert!(worst_joints[0].residual > 1e-3);
            assert!(
                worst_joints
                    .windows(2)
                    .all(|w| w[0].residual >= w[1].residual)
            );
        }
        other => panic!("expected AssemblyFailed, got {other:?}"),
    }
}

#[test]
fn wrong_driver_or_seed_sizes_are_typed_errors() {
    let m = model("four-bar-crank-rocker.json");
    assert_eq!(
        m.assemble(&[], None, &AssemblyOptions::default()),
        Err(SolverError::DriverCount {
            expected: 1,
            got: 0
        })
    );
    assert_eq!(
        m.assemble(&[0.0], Some(&[0.0; 4]), &AssemblyOptions::default()),
        Err(SolverError::SeedLength {
            expected: 9,
            got: 4
        })
    );
}

#[test]
fn joints_and_bodies_beyond_this_build_are_refused_with_a_reason() {
    // A spatial joint between planar links.
    let mut spherical = golden("four-bar-crank-rocker.json");
    spherical["joints"][1]["kind"] = "spherical".into();
    for (name, value, message) in [
        (
            "spatial-rssr.json",
            golden("spatial-rssr.json"),
            "handles planar bodies only",
        ),
        (
            "two-plane-subsystems.json",
            golden("two-plane-subsystems.json"),
            "handles planar bodies only",
        ),
        (
            "a spherical joint in a four-bar",
            spherical,
            "handles planar joints only",
        ),
    ] {
        match Model::new(&mechanism(&value)) {
            Err(SolverError::InvalidGraph(issues)) => {
                assert!(
                    issues.iter().any(|i| i.message.contains(message)),
                    "{name}: {issues:?}"
                );
            }
            other => panic!("{name}: expected InvalidGraph, got {other:?}"),
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
                (numeric - analytic[i][j]).abs() < 1e-6 * (1.0 + numeric.abs()),
                "d r{i} / d q{j}: analytic {} numeric {numeric}",
                analytic[i][j]
            );
        }
    }
    Ok(())
}

proptest! {
    #[test]
    fn analytic_jacobians_match_finite_differences(
        q in prop::collection::vec(-1.0..1.0_f64, 9),
        drive in -10.0..10.0_f64,
    ) {
        finite_difference_matches(&model("four-bar-crank-rocker.json"), &q, &[drive])?;
        // The slider-crank has a prismatic joint between the ground and the slider.
        finite_difference_matches(&model("slider-crank.json"), &q, &[drive])?;
    }

    #[test]
    fn displacement_drivers_have_exact_jacobians(
        q in prop::collection::vec(-1.0..1.0_f64, 9),
        s in -0.3..0.3_f64,
    ) {
        let mut value = golden("slider-crank.json");
        value["drivers"][0]["jointId"] = "j-rail".into();
        value["drivers"][0]["coordinate"] = "displacement".into();
        let m = Model::new(&mechanism(&value)).unwrap();
        finite_difference_matches(&m, &q, &[s])?;
    }
}

#[test]
fn a_displacement_driver_places_the_slider() {
    let mut value = golden("slider-crank.json");
    value["drivers"][0]["jointId"] = "j-rail".into();
    value["drivers"][0]["coordinate"] = "displacement".into();
    let m = Model::new(&mechanism(&value)).unwrap();
    let a = m
        .assemble(&[0.2], None, &AssemblyOptions::default())
        .unwrap();
    assert!((point(&m, &a.q, "slider", "c")[0] - 0.2).abs() < 1e-9);
    // The crank pin is then on one of the two crank angles that reach x = 0.2.
    let b = point(&m, &a.q, "crank", "b");
    assert!((dist(b, [0.0, 0.0]) - 0.05).abs() < 1e-9);
    assert!((dist(b, [0.2, 0.0]) - 0.18).abs() < 1e-9);
}

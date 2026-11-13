//! Correctness properties 5 and 6 of the mechanism-core design, over generated crank-rocker
//! four-bars, noise levels, and starting errors.
//!
//! 5. For any mechanism, driver sweep, and Gaussian observation noise σ (with no outliers),
//!    fitting from perturbed initial guesses recovers link lengths within 3 times the reported
//!    standard deviation.
//! 6. For any observation set with up to 20% outliers, the robust fit's error stays within 2× the
//!    outlier-free error. The outlier-free error of one sample is itself random and can land far
//!    below the noise, so its scale is taken as the larger of that error and 1.5 reported standard
//!    deviations (the error a typical sample reaches). Outliers are gross: 5 to 20 mm off.
//!
//! The noise is drawn inside each case, so the runs use a fixed seed: the property's 3σ bound is
//! probabilistic, and a fixed seed keeps a pass from turning into a coin toss.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use kinematics::AssemblyOptions;
use kinematics::fit::{Camera, FitProblem, Loss, Observation, Parameter, fit};
use kinematics::model::Model;
use kinematics::schema::{Mechanism, parse_mechanism};
use proptest::prelude::*;
use proptest::test_runner::RngSeed;
use serde_json::{Value, json};

fn four_bar(g: f64, c: f64, k: f64, r: f64) -> Value {
    let p = |id: &str, x: f64, y: f64| json!({ "id": id, "local": {"x": x, "y": y, "z": 0}, "role": "joint_anchor" });
    let body = |id: &str, kind: &str, points: Vec<Value>| {
        json!({ "id": id, "label": id, "kind": kind,
        "planeId": "p", "points": points, "status": "observed", "confidence": 1 })
    };
    let rev = |id: &str, a: &str, pa: &str, b: &str, pb: &str| {
        json!({ "id": id, "kind": "revolute", "bodyA": a, "bodyB": b,
        "anchorA": {"bodyId": a, "pointId": pa}, "anchorB": {"bodyId": b, "pointId": pb}, "status": "observed", "confidence": 1 })
    };
    json!({
        "schemaVersion": 1, "id": "fb", "name": "Four-bar",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [{ "id": "p", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": [
            body("ground", "ground", vec![p("o2", 0.0, 0.0), p("o4", g, 0.0)]),
            body("crank", "link", vec![p("a", 0.0, 0.0), p("b", c, 0.0)]),
            body("coupler", "link", vec![p("b", 0.0, 0.0), p("c", k, 0.0), p("trace", k / 2.0, 0.05)]),
            body("rocker", "link", vec![p("d", 0.0, 0.0), p("c", r, 0.0), p("tip", r, 0.0)])],
        "joints": [rev("drive-pivot", "ground", "o2", "crank", "a"), rev("j-b", "crank", "b", "coupler", "b"),
                   rev("j-c", "coupler", "c", "rocker", "c"), rev("j-d", "ground", "o4", "rocker", "d")],
        "drivers": [{ "id": "drive", "jointId": "drive-pivot", "coordinate": "angle",
            "profile": { "type": "constant_rate", "rate": 1, "phase0": 0 } }],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    })
}

fn mechanism(v: &Value) -> Mechanism {
    parse_mechanism(&v.to_string()).unwrap()
}

const PATHS: [&str; 4] = [
    "bodies.ground.points.o4.local.x",
    "bodies.crank.points.b.local.x",
    "bodies.coupler.points.c.local.x",
    "bodies.rocker.points.c.local.x",
];

/// Lengths of a crank-rocker with margins (as in `properties.rs`).
fn lengths() -> impl Strategy<Value = [f64; 4]> {
    (0.02..0.08_f64, 0.15..0.4_f64, 0.15..0.4_f64, 0.15..0.4_f64)
        .prop_filter("Grashof crank-rocker with a margin", |(s, g, k, r)| {
            let longest = g.max(*k).max(*r);
            s + longest < g + k + r - longest - 0.02
                && (k - r).abs() < (g - s) - 0.02
                && k + r > g + s + 0.02
        })
        .prop_map(|(c, g, k, r)| [g, c, k, r])
}

/// Normal samples from a seeded source.
fn normals(seed: u64, n: usize) -> Vec<f64> {
    let mut x = seed | 1;
    let mut uniform = move || {
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        #[allow(clippy::cast_precision_loss, reason = "a test random source")]
        let u = (x >> 11) as f64 / (1u64 << 53) as f64;
        u.max(1e-300)
    };
    (0..n)
        .map(|_| (-2.0 * uniform().ln()).sqrt() * (std::f64::consts::TAU * uniform()).cos())
        .collect()
}

/// Tracks of the true mechanism over 60 frames, with noise, outliers, and a perturbed start.
fn problem(
    truth: [f64; 4],
    sigma: f64,
    outliers: f64,
    perturb: [f64; 4],
    seed: u64,
    loss: Loss,
) -> FitProblem {
    let m = Model::new(&mechanism(&four_bar(
        truth[0], truth[1], truth[2], truth[3],
    )))
    .unwrap();
    let frames = 60;
    // Up to 16 draws a frame: 3 points × (2 noise, 1 outlier test, 2 outlier offsets) + 1.
    let noise = normals(seed, frames * 16);
    let mut n = noise.iter();
    let mut next = || *n.next().unwrap();
    let mut seed_q: Option<Vec<f64>> = None;
    let mut observations = Vec::new();
    let mut drive = Vec::new();
    let mut poses = Vec::new();
    for t in 0..frames {
        #[allow(clippy::cast_precision_loss, reason = "frame counts are small")]
        let angle = 6.0 * t as f64 / frames as f64;
        let a = m
            .assemble(&[angle], seed_q.as_deref(), &AssemblyOptions::default())
            .unwrap();
        for (body, point) in [("crank", "b"), ("coupler", "trace"), ("rocker", "tip")] {
            let w = m.point_world(m.body(body).unwrap(), point, &a.q).unwrap();
            let mut position = [w[0] + sigma * next(), w[1] + sigma * next()];
            // Outliers: a share of observations land 5 to 20 mm off, in a random direction.
            if (next().abs() * 0.4).fract() < outliers {
                let (size, angle) = (0.005 + 0.015 * (0.5 + 0.5 * next().tanh()), 3.0 * next());
                position[0] += size * angle.cos();
                position[1] += size * angle.sin();
            }
            observations.push(Observation {
                frame: t,
                body: body.into(),
                point: point.into(),
                position,
                weight: 1.0,
            });
        }
        drive.push(vec![angle + 0.03 * next().tanh()]);
        poses.push(a.q.clone());
        seed_q = Some(a.q);
    }
    // Only the four fitted lengths start wrong; tracked points stay where they are on the
    // real machine.
    let mut start = four_bar(truth[0], truth[1], truth[2], truth[3]);
    for (path, k) in PATHS.iter().zip(perturb) {
        let mut slot = &mut start;
        for token in path.split('.') {
            slot = match slot {
                Value::Array(items) => items.iter_mut().find(|v| v["id"] == token).unwrap(),
                other => &mut other[token],
            };
        }
        *slot = (slot.as_f64().unwrap() * (1.0 + k)).into();
    }
    FitProblem {
        mechanism: mechanism(&start),
        parameters: PATHS
            .iter()
            .map(|p| Parameter {
                path: (*p).into(),
                fixed: false,
                prior: None,
            })
            .collect(),
        drive,
        // The true poses only pick the branch: the fit re-assembles from the wrong geometry.
        seeds: Some(poses),
        observations,
        camera: Camera::Plane("p".into()),
        loss,
        max_iterations: 60,
    }
}

fn perturbation() -> impl Strategy<Value = [f64; 4]> {
    prop::array::uniform4(-0.04..0.04_f64)
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 10, rng_seed: RngSeed::Fixed(20_261_113), ..ProptestConfig::default() })]

    #[test]
    fn noisy_fits_recover_lengths_within_three_sigma(
        truth in lengths(), sigma in 1e-5..5e-4_f64, perturb in perturbation(), seed in any::<u64>(),
    ) {
        let result = fit(&problem(truth, sigma, 0.0, perturb, seed, Loss::Squared))
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        for ((path, t), (v, s)) in PATHS.iter().zip(truth).zip(result.values.iter().zip(&result.sigma)) {
            prop_assert!(*s > 0.0);
            prop_assert!((v - t).abs() <= 3.0 * s, "{path}: {v} vs {t}, sigma {s}");
        }
    }

    #[test]
    fn robust_fits_hold_against_outliers(
        truth in lengths(), sigma in 1e-5..5e-4_f64, share in 0.0..0.2_f64, perturb in perturbation(), seed in any::<u64>(),
    ) {
        let error = |r: &kinematics::fit::FitResult| {
            PATHS.iter().zip(truth).zip(&r.values).map(|((_, t), v)| (v - t).abs()).fold(0.0, f64::max)
        };
        let clean = fit(&problem(truth, sigma, 0.0, perturb, seed, Loss::Squared))
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        let robust = fit(&problem(truth, sigma, share, perturb, seed, Loss::Cauchy { c: 3.0 * sigma }))
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        let floor = 1.5 * clean.sigma.iter().copied().fold(0.0, f64::max);
        prop_assert!(error(&robust) <= 2.0 * error(&clean).max(floor),
            "robust {} vs clean {} (sigma {floor})", error(&robust), error(&clean));
    }
}

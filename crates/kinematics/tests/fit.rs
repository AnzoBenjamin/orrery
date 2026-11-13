//! The fitter (mechanism-core requirement 7) on synthetic tracks of the golden four-bar.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::path::Path;

use kinematics::AssemblyOptions;
use kinematics::fit::{Camera, FitProblem, Loss, Observation, Parameter, fit};
use kinematics::model::Model;
use kinematics::schema::{Mechanism, parse_mechanism};
use serde_json::Value;

fn golden(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn mechanism(v: &Value) -> Mechanism {
    parse_mechanism(&v.to_string()).unwrap()
}

/// Deterministic standard normal samples (xorshift and Box–Muller).
struct Noise(u64);
impl Noise {
    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        #[allow(clippy::cast_precision_loss, reason = "a test random source")]
        let u = (self.0 >> 11) as f64 / (1u64 << 53) as f64;
        u.max(1e-300)
    }
    fn normal(&mut self) -> f64 {
        let (a, b) = (self.uniform(), self.uniform());
        (-2.0 * a.ln()).sqrt() * (std::f64::consts::TAU * b).cos()
    }
}

const TRACKED: [(&str, &str); 3] = [("crank", "b"), ("coupler", "trace"), ("rocker", "tip")];

/// Observations of the true four-bar over `frames` crank angles, with noise `sigma` and a share
/// of gross outliers.
fn observe(
    frames: usize,
    sigma: f64,
    outliers: f64,
    noise: &mut Noise,
) -> (Vec<Observation>, Vec<f64>) {
    let truth = Model::new(&mechanism(&golden("four-bar-crank-rocker.json"))).unwrap();
    let mut seed: Option<Vec<f64>> = None;
    let mut out = Vec::new();
    let mut angles = Vec::new();
    for t in 0..frames {
        #[allow(clippy::cast_precision_loss, reason = "frame counts are small")]
        let angle = 0.3 + 5.5 * t as f64 / frames as f64;
        angles.push(angle);
        let a = truth
            .assemble(&[angle], seed.as_deref(), &AssemblyOptions::default())
            .unwrap();
        for (body, point) in TRACKED {
            let w = truth
                .point_world(truth.body(body).unwrap(), point, &a.q)
                .unwrap();
            let mut position = [w[0] + sigma * noise.normal(), w[1] + sigma * noise.normal()];
            if noise.uniform() < outliers {
                position[0] += 0.02 * (noise.uniform() - 0.5);
                position[1] += 0.02 * (noise.uniform() - 0.5);
            }
            out.push(Observation {
                frame: t,
                body: body.into(),
                point: point.into(),
                position,
                weight: 1.0,
            });
        }
        seed = Some(a.q);
    }
    (out, angles)
}

const PATHS: [(&str, f64); 4] = [
    ("bodies.ground.points.o4.local.x", 0.3),
    ("bodies.crank.points.b.local.x", 0.1),
    ("bodies.coupler.points.c.local.x", 0.25),
    ("bodies.rocker.points.c.local.x", 0.2),
];

/// A problem starting from wrong lengths and rough crank angles.
fn problem(observations: Vec<Observation>, angles: &[f64], loss: Loss) -> FitProblem {
    let mut start = golden("four-bar-crank-rocker.json");
    start["bodies"][0]["points"][1]["local"]["x"] = 0.31.into();
    start["bodies"][1]["points"][1]["local"]["x"] = 0.104.into();
    start["bodies"][2]["points"][1]["local"]["x"] = 0.265.into();
    start["bodies"][3]["points"][1]["local"]["x"] = 0.19.into();
    let mut noise = Noise(99);
    FitProblem {
        mechanism: mechanism(&start),
        parameters: PATHS
            .iter()
            .map(|(p, _)| Parameter {
                path: (*p).into(),
                fixed: false,
                prior: None,
            })
            .collect(),
        drive: angles
            .iter()
            .map(|a| vec![a + 0.05 * noise.normal()])
            .collect(),
        seeds: None,
        observations,
        camera: Camera::Plane {
            plane: "plane-main".into(),
        },
        loss,
        max_iterations: 50,
    }
}

#[test]
fn exact_tracks_recover_the_geometry_and_crank_angles() {
    let (obs, angles) = observe(40, 0.0, 0.0, &mut Noise(7));
    let result = fit(&problem(obs, &angles, Loss::Squared)).unwrap();
    for ((path, truth), value) in PATHS.iter().zip(&result.values) {
        assert!((value - truth).abs() < 1e-7, "{path}: {value} vs {truth}");
    }
    for (d, a) in result.drive.iter().zip(&angles) {
        assert!((d[0] - a).abs() < 1e-6);
    }
    assert!(result.rms < 1e-8, "rms {}", result.rms);
    // Every frame's pose satisfies the joints exactly.
    let fitted = Model::new(&result.mechanism).unwrap();
    for (q, d) in result.poses.iter().zip(&result.drive) {
        assert!(fitted.residuals(q, d).iter().all(|r| r.abs() < 1e-9));
    }
}

#[test]
fn noisy_tracks_land_within_three_reported_sigmas() {
    let sigma = 2e-4;
    let (obs, angles) = observe(80, sigma, 0.0, &mut Noise(11));
    let result = fit(&problem(obs, &angles, Loss::Squared)).unwrap();
    for (((path, truth), value), s) in PATHS.iter().zip(&result.values).zip(&result.sigma) {
        assert!(*s > 0.0 && *s < 10.0 * sigma, "{path}: sigma {s}");
        assert!(
            (value - truth).abs() <= 3.0 * s,
            "{path}: {value} vs {truth}, sigma {s}"
        );
        // The graph carries the standard deviation in its uncertainty map.
        assert_eq!(result.mechanism.uncertainty.get(*path), Some(s));
    }
    // The residuals are the noise: their RMS is near √2·σ per 2D point.
    assert!(
        (result.rms / (sigma * 2f64.sqrt()) - 1.0).abs() < 0.3,
        "rms {}",
        result.rms
    );
    assert_eq!(result.residuals.len(), 240);
}

#[test]
fn a_robust_loss_keeps_outliers_from_pulling_the_fit() {
    let sigma = 2e-4;
    let (obs, angles) = observe(80, sigma, 0.2, &mut Noise(23));
    let error = |loss| {
        let result = fit(&problem(obs.clone(), &angles, loss)).unwrap();
        PATHS
            .iter()
            .zip(&result.values)
            .map(|((_, t), v)| (v - t).abs())
            .fold(0.0, f64::max)
    };
    let (robust, plain) = (error(Loss::Cauchy { c: 3.0 * sigma }), error(Loss::Squared));
    let (clean_obs, clean_angles) = observe(80, sigma, 0.0, &mut Noise(23));
    let clean = {
        let result = fit(&problem(clean_obs, &clean_angles, Loss::Squared)).unwrap();
        PATHS
            .iter()
            .zip(&result.values)
            .map(|((_, t), v)| (v - t).abs())
            .fold(0.0, f64::max)
    };
    assert!(robust < plain, "robust {robust} vs plain {plain}");
    // Property 6's bound: within twice the outlier-free error (with a floor at the noise level).
    assert!(
        robust <= 2.0 * clean.max(sigma),
        "robust {robust} vs clean {clean}"
    );
}

#[test]
fn fixed_parameters_hold_and_priors_pull() {
    let (obs, angles) = observe(30, 0.0, 0.0, &mut Noise(5));
    let mut p = problem(obs.clone(), &angles, Loss::Squared);
    p.parameters[0].fixed = true;
    let result = fit(&p).unwrap();
    // Held at its wrong starting value; the others absorb what they can.
    assert!((result.values[0] - 0.31).abs() < 1e-15);
    assert!(result.sigma[0].abs() < 1e-15);
    assert!(!result.mechanism.uncertainty.contains_key(PATHS[0].0));

    // A tight prior on a wrong coupler length wins over exact data; a loose one does not.
    let mut tight = problem(obs.clone(), &angles, Loss::Squared);
    tight.parameters[2].prior = Some((0.27, 1e-9));
    let mut loose = problem(obs, &angles, Loss::Squared);
    loose.parameters[2].prior = Some((0.27, 10.0));
    let (t, l) = (fit(&tight).unwrap(), fit(&loose).unwrap());
    assert!((t.values[2] - 0.27).abs() < 1e-6, "{}", t.values[2]);
    // The loose prior still pulls a little (its weight is small, not zero).
    assert!((l.values[2] - 0.25).abs() < 1e-4, "{}", l.values[2]);
    assert!((l.values[2] - 0.25).abs() < (t.values[2] - 0.25).abs() / 100.0);
}

#[test]
fn bad_inputs_are_typed_errors() {
    let (obs, angles) = observe(5, 0.0, 0.0, &mut Noise(1));
    let mut p = problem(obs.clone(), &angles, Loss::Squared);
    p.parameters.push(Parameter {
        path: "bodies.missing.points.x.local.x".into(),
        fixed: false,
        prior: None,
    });
    assert!(fit(&p).is_err());
    let mut p = problem(obs, &angles, Loss::Squared);
    p.observations[0].point = "nowhere".into();
    assert!(fit(&p).is_err());
}

/// The plane observations mapped to pixels by `map`.
fn to_pixels(obs: &[Observation], map: impl Fn([f64; 2]) -> [f64; 2]) -> Vec<Observation> {
    obs.iter()
        .map(|o| Observation {
            position: map(o.position),
            ..o.clone()
        })
        .collect()
}

#[test]
fn a_homography_camera_is_recovered_with_the_geometry() {
    let h = [1800.0, 120.0, 640.0, -90.0, 1750.0, 360.0, 0.3, -0.2];
    let apply = |p: [f64; 2]| {
        let z = h[6] * p[0] + h[7] * p[1] + 1.0;
        [
            (h[0] * p[0] + h[1] * p[1] + h[2]) / z,
            (h[3] * p[0] + h[4] * p[1] + h[5]) / z,
        ]
    };
    let (obs, angles) = observe(40, 0.0, 0.0, &mut Noise(31));
    let mut p = problem(to_pixels(&obs, apply), &angles, Loss::Squared);
    // The ground length sets the scale the homography would otherwise absorb.
    p.parameters[0].fixed = true;
    p.mechanism = {
        let mut v = serde_json::to_value(&p.mechanism).unwrap();
        v["bodies"][0]["points"][1]["local"]["x"] = 0.3.into();
        mechanism(&v)
    };
    let mut start = h;
    for (k, v) in start.iter_mut().enumerate() {
        *v *= if k % 2 == 0 { 1.02 } else { 0.97 };
    }
    p.camera = Camera::Homography {
        plane: "plane-main".into(),
        initial: vec![start],
    };
    p.max_iterations = 100;
    let result = fit(&p).unwrap();
    for ((path, truth), value) in PATHS.iter().zip(&result.values).skip(1) {
        assert!((value - truth).abs() < 1e-6, "{path}: {value} vs {truth}");
    }
    for (got, want) in result.camera_global.iter().zip(&h) {
        assert!(
            (got - want).abs() < 1e-4 * (1.0 + want.abs()),
            "{got} vs {want}"
        );
    }
    assert!(result.rms < 1e-5, "rms {} px", result.rms);
}

#[test]
fn a_calibrated_pinhole_camera_pose_is_recovered_with_the_geometry() {
    let (f, cx, cy) = (1400.0, 640.0, 360.0);
    // Camera looking down at the mechanism plane from about a meter, slightly tilted.
    let truth = [0.15, -0.1, 0.05, -0.1, 0.05, 1.1];
    let project = |pose: &[f64; 6], w: [f64; 3]| {
        let r = [pose[0], pose[1], pose[2]];
        let angle = (r[0] * r[0] + r[1] * r[1] + r[2] * r[2]).sqrt();
        let k = r.map(|c| c / angle);
        let (s, c) = angle.sin_cos();
        let d = k[0] * w[0] + k[1] * w[1] + k[2] * w[2];
        let x = [
            k[1] * w[2] - k[2] * w[1],
            k[2] * w[0] - k[0] * w[2],
            k[0] * w[1] - k[1] * w[0],
        ];
        let p: Vec<f64> = (0..3)
            .map(|i| w[i] * c + x[i] * s + k[i] * d * (1.0 - c) + pose[3 + i])
            .collect();
        [f * p[0] / p[2] + cx, f * p[1] / p[2] + cy]
    };
    let (obs, angles) = observe(40, 0.0, 0.0, &mut Noise(41));
    let mut p = problem(
        to_pixels(&obs, |q| project(&truth, [q[0], q[1], 0.0])),
        &angles,
        Loss::Squared,
    );
    p.parameters[0].fixed = true;
    p.mechanism = {
        let mut v = serde_json::to_value(&p.mechanism).unwrap();
        v["bodies"][0]["points"][1]["local"]["x"] = 0.3.into();
        mechanism(&v)
    };
    let start = [0.12, -0.08, 0.0, -0.08, 0.03, 1.0];
    p.camera = Camera::Projection {
        intrinsics: [f, cx, cy],
        fixed_intrinsics: true,
        poses: vec![start],
    };
    p.max_iterations = 100;
    let result = fit(&p).unwrap();
    for ((path, want), value) in PATHS.iter().zip(&result.values).skip(1) {
        assert!((value - want).abs() < 1e-6, "{path}: {value} vs {want}");
    }
    for (got, want) in result.camera_global.iter().zip(&truth) {
        assert!((got - want).abs() < 1e-6, "{got} vs {want}");
    }
    assert!(result.rms < 1e-5, "rms {} px", result.rms);
}

#[test]
fn a_moving_camera_gets_one_homography_per_frame() {
    let (mut obs, angles) = observe(30, 0.0, 0.0, &mut Noise(53));
    // The frame's two pivots are visible too, so each frame pins its own homography.
    for t in 0..angles.len() {
        for (point, x) in [("o2", 0.0), ("o4", 0.3)] {
            obs.push(Observation {
                frame: t,
                body: "ground".into(),
                point: point.into(),
                position: [x, 0.0],
                weight: 1.0,
            });
        }
    }
    #[allow(clippy::cast_precision_loss, reason = "frame counts are small")]
    let homography = |t: usize| {
        let s = t as f64 / 30.0;
        [
            1800.0 + 50.0 * s,
            120.0 - 30.0 * s,
            640.0 + 40.0 * s,
            -90.0,
            1750.0,
            360.0 - 25.0 * s,
            0.3,
            -0.2 + 0.1 * s,
        ]
    };
    let pixels: Vec<Observation> = obs
        .iter()
        .map(|o| {
            let h = homography(o.frame);
            let (x, y) = (o.position[0], o.position[1]);
            let z = h[6] * x + h[7] * y + 1.0;
            Observation {
                position: [
                    (h[0] * x + h[1] * y + h[2]) / z,
                    (h[3] * x + h[4] * y + h[5]) / z,
                ],
                ..o.clone()
            }
        })
        .collect();
    let mut p = problem(pixels, &angles, Loss::Squared);
    p.parameters[0].fixed = true;
    p.mechanism = {
        let mut v = serde_json::to_value(&p.mechanism).unwrap();
        v["bodies"][0]["points"][1]["local"]["x"] = 0.3.into();
        mechanism(&v)
    };
    let initial: Vec<[f64; 8]> = (0..angles.len())
        .map(|t| homography(t).map(|v| v * 1.01))
        .collect();
    p.camera = Camera::Homography {
        plane: "plane-main".into(),
        initial,
    };
    p.max_iterations = 100;
    let result = fit(&p).unwrap();
    for ((path, want), value) in PATHS.iter().zip(&result.values).skip(1) {
        assert!((value - want).abs() < 1e-6, "{path}: {value} vs {want}");
    }
    assert_eq!(result.camera_frames.len(), 30);
    for (t, got) in result.camera_frames.iter().enumerate() {
        for (g, w) in got.iter().zip(homography(t)) {
            assert!(
                (g - w).abs() < 1e-4 * (1.0 + w.abs()),
                "frame {t}: {g} vs {w}"
            );
        }
    }
}

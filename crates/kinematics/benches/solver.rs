//! Performance targets (mechanism-core requirements 7.4 and 9.3) on a 20-body mechanism: a chain
//! of nine parallelograms driven by one crank, every rocker turning with it.
//!
//! - fit: 600 frames, every coupler's middle tracked, nine lengths free; target under 5 s on
//!   one core.
//! - assemble: one re-solve from the previous pose after a small drag; target under 2 ms.
//! - cycle: a 360-step simulation; target under 50 ms (requirement 9.3 is measured in the
//!   browser by workbench task 6.2; this is the native figure).

use std::hint::black_box;

use criterion::{Criterion, criterion_group, criterion_main};
use kinematics::AssemblyOptions;
use kinematics::fit::{Camera, FitProblem, Loss, Observation, Parameter, fit};
use kinematics::model::Model;
use kinematics::schema::{Mechanism, parse_mechanism};
use kinematics::simulate::SimulationOptions;
use serde_json::{Value, json};

const STAGES: usize = 9;

fn chain() -> Mechanism {
    let p = |id: &str, x: f64, y: f64| json!({ "id": id, "local": {"x": x, "y": y, "z": 0}, "role": "joint_anchor" });
    let body = |id: String, kind: &str, points: Vec<Value>| {
        json!({ "id": id, "label": id, "kind": kind,
        "planeId": "p", "points": points, "status": "observed", "confidence": 1 })
    };
    let rev = |id: String, a: &str, pa: &str, b: &str, pb: &str| {
        json!({ "id": id, "kind": "revolute", "bodyA": a, "bodyB": b,
        "anchorA": {"bodyId": a, "pointId": pa}, "anchorB": {"bodyId": b, "pointId": pb}, "status": "observed", "confidence": 1 })
    };
    #[allow(clippy::cast_precision_loss, reason = "a small stage count")]
    let pivots: Vec<Value> = (0..=STAGES)
        .map(|k| p(&format!("o{k}"), 0.3 * k as f64, 0.0))
        .collect();
    let mut bodies = vec![body("ground".into(), "ground", pivots)];
    let mut joints = Vec::new();
    for k in 0..=STAGES {
        bodies.push(body(
            format!("rocker-{k}"),
            "link",
            vec![p("pivot", 0.0, 0.0), p("pin", 0.1, 0.0)],
        ));
        joints.push(rev(
            format!("pivot-{k}"),
            "ground",
            &format!("o{k}"),
            &format!("rocker-{k}"),
            "pivot",
        ));
    }
    for k in 0..STAGES {
        let coupler = format!("coupler-{k}");
        bodies.push(body(
            coupler.clone(),
            "link",
            vec![p("a", 0.0, 0.0), p("b", 0.3, 0.0), p("middle", 0.15, 0.02)],
        ));
        joints.push(rev(
            format!("pin-a-{k}"),
            &format!("rocker-{k}"),
            "pin",
            &coupler,
            "a",
        ));
        joints.push(rev(
            format!("pin-b-{k}"),
            &format!("rocker-{}", k + 1),
            "pin",
            &coupler,
            "b",
        ));
    }
    let value = json!({
        "schemaVersion": 1, "id": "chain", "name": "Parallelogram chain",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [{ "id": "p", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": bodies, "joints": joints,
        "drivers": [{ "id": "drive", "jointId": "pivot-0", "coordinate": "angle",
            "profile": { "type": "constant_rate", "rate": 1, "phase0": 0 } }],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    });
    parse_mechanism(&value.to_string()).unwrap_or_else(|e| panic!("chain: {e}"))
}

fn fit_problem(mechanism: &Mechanism) -> FitProblem {
    let m = Model::new(mechanism).unwrap_or_else(|e| panic!("{e}"));
    let frames = 600;
    let mut seed: Option<Vec<f64>> = None;
    let mut observations = Vec::new();
    let mut drive = Vec::new();
    let mut poses = Vec::new();
    for t in 0..frames {
        #[allow(clippy::cast_precision_loss, reason = "frame counts are small")]
        let angle = 0.3 + 2.5 * t as f64 / frames as f64;
        let a = m
            .assemble(&[angle], seed.as_deref(), &AssemblyOptions::default())
            .unwrap_or_else(|e| panic!("{e}"));
        for k in 0..STAGES {
            let body = format!("coupler-{k}");
            let w = m
                .point_world(m.body(&body).unwrap_or(0), "middle", &a.q)
                .unwrap_or([0.0; 3]);
            observations.push(Observation {
                frame: t,
                body,
                point: "middle".into(),
                position: [w[0], w[1]],
                weight: 1.0,
            });
        }
        drive.push(vec![angle + 0.01]);
        poses.push(a.q.clone());
        seed = Some(a.q);
    }
    FitProblem {
        mechanism: mechanism.clone(),
        parameters: (1..=STAGES)
            .map(|k| Parameter {
                path: format!("bodies.rocker-{k}.points.pin.local.x"),
                fixed: false,
                prior: None,
            })
            .collect(),
        drive,
        seeds: Some(poses),
        observations,
        camera: Camera::Plane("p".into()),
        loss: Loss::Squared,
        max_iterations: 10,
    }
}

fn benches(c: &mut Criterion) {
    let mechanism = chain();
    let m = Model::new(&mechanism).unwrap_or_else(|e| panic!("{e}"));
    let base = m
        .assemble(&[1.0], None, &AssemblyOptions::default())
        .unwrap_or_else(|e| panic!("{e}"));
    c.bench_function("assemble 20 bodies after a drag", |b| {
        b.iter(|| {
            m.assemble(
                black_box(&[1.01]),
                Some(&base.q),
                &AssemblyOptions::default(),
            )
        });
    });
    c.bench_function("simulate 360 steps, 20 bodies", |b| {
        b.iter(|| {
            m.simulate(
                0,
                &[0.0],
                (0.3, 2.8, 2.5 / 360.0),
                Some(&base.q),
                &SimulationOptions::default(),
            )
        });
    });
    let problem = fit_problem(&mechanism);
    let mut group = c.benchmark_group("fit");
    group.sample_size(10);
    group.bench_function("600 frames, 20 bodies", |b| {
        b.iter(|| fit(black_box(&problem)))
    });
    group.finish();
}

criterion_group!(solver, benches);
criterion_main!(solver);

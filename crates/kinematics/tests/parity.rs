//! Native reference results for the WebAssembly parity test (mechanism-core requirement 11,
//! property 8), and determinism within the native build.
//!
//! For each golden mechanism, `fixtures/golden/parity/<name>` holds fixed inputs and the native
//! results: an assembly, the positions of every named point (in the order the bindings use), a
//! full-turn sweep of the first driver, and the mobility at the assembled pose. Where the joints
//! and drivers leave a motion free (a rod spinning about the line through its ball joints), the
//! state along it is wherever the iterations left it and differs between builds by more than
//! rounding; the WebAssembly test then compares the point positions, which that motion does not
//! move, and the states only of fully determined mechanisms. One more file
//! holds a fit problem on the four-bar and its native result. `packages/kinematics-wasm` runs the
//! same inputs through the WebAssembly build and compares within 1e-9.
//!
//! This test fails when the native results drift from the files by more than 1e-12 (a different
//! platform `libm` moves the last bits). After an intended solver change, rewrite them with
//! `PARITY_WRITE=1 cargo test -p kinematics --test parity` and commit them.

#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::TAU;
use std::path::{Path, PathBuf};

use kinematics::AssemblyOptions;
use kinematics::fit::{FitProblem, fit};
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use kinematics::simulate::SimulationOptions;
use serde_json::{Value, json};

const STEP: f64 = 0.2;
const NATIVE_TOLERANCE: f64 = 1e-12;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden")
}

fn goldens() -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = std::fs::read_dir(root().join("mechanism"))
        .unwrap()
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    files
}

/// Every named point as `(body index, point id)`, ordered as the bindings order them.
fn point_order(model: &Model) -> Vec<(usize, String)> {
    let mut points: Vec<(usize, String)> = model
        .bodies
        .iter()
        .enumerate()
        .flat_map(|(i, b)| b.points.keys().map(move |p| (i, p.clone())))
        .collect();
    points.sort();
    points
}

fn positions(model: &Model, order: &[(usize, String)], q: &[f64]) -> Vec<f64> {
    order
        .iter()
        .flat_map(|(b, p)| model.point_world(*b, p, q).unwrap_or([f64::NAN; 3]))
        .collect()
}

/// The native results for one golden mechanism.
fn mechanism_case(name: &str, text: &str) -> Value {
    let model = Model::new(&parse_mechanism(text).unwrap()).unwrap();
    let order = point_order(&model);
    let drive = vec![0.0; model.drivers.len()];
    let assembled = model
        .assemble(&drive, None, &AssemblyOptions::default())
        .unwrap();
    let sim = model
        .simulate(
            0,
            &drive,
            (0.0, TAU, STEP),
            Some(&assembled.q),
            &SimulationOptions::default(),
        )
        .unwrap();
    let mobility = model.mobility(&assembled.q, &drive);
    json!({
        "mechanism": name,
        "inputs": {
            "drive": drive,
            "sweep": { "driver": 0, "start": 0.0, "end": TAU, "step": STEP },
        },
        "assembled": assembled.q,
        "points": positions(&model, &order, &assembled.q),
        "simulation": {
            "drive": sim.samples.iter().map(|s| s.drive).collect::<Vec<_>>(),
            "states": sim.samples.iter().flat_map(|s| s.q.clone()).collect::<Vec<_>>(),
            "points": sim
                .samples
                .iter()
                .flat_map(|s| positions(&model, &order, &s.q))
                .collect::<Vec<_>>(),
            "reachable": sim.reachable,
            "singularities": sim.singularities,
        },
        "mobility": {
            "grubler": mobility.grubler,
            "numerical": mobility.numerical,
            "redundant": mobility.redundant,
            "freeMotions": mobility.free_motions.len(),
        },
    })
}

/// A fit of the four-bar from wrong lengths to tracks of the true one.
fn fit_case() -> Value {
    let text =
        std::fs::read_to_string(root().join("mechanism/four-bar-crank-rocker.json")).unwrap();
    let truth = Model::new(&parse_mechanism(&text).unwrap()).unwrap();
    let mut observations = Vec::new();
    let mut drive = Vec::new();
    let mut seed: Option<Vec<f64>> = None;
    for frame in 0..24_u32 {
        let angle = 0.3 + 5.5 * f64::from(frame) / 24.0;
        let q = truth
            .assemble(&[angle], seed.as_deref(), &AssemblyOptions::default())
            .unwrap()
            .q;
        for (body, point) in [("crank", "b"), ("coupler", "trace"), ("rocker", "tip")] {
            let w = truth
                .point_world(truth.body(body).unwrap(), point, &q)
                .unwrap();
            observations.push(json!({
                "frame": frame, "body": body, "point": point,
                "position": [w[0], w[1]], "weight": 1.0,
            }));
        }
        drive.push(vec![angle + 0.03 * (7.0 * angle).sin()]);
        seed = Some(q);
    }
    let mut start: Value = serde_json::from_str(&text).unwrap();
    for (body, x) in [(0, 0.31), (1, 0.104), (2, 0.265), (3, 0.19)] {
        start["bodies"][body]["points"][1]["local"]["x"] = x.into();
    }
    let problem = json!({
        "mechanism": start,
        "parameters": [
            { "path": "bodies.ground.points.o4.local.x" },
            { "path": "bodies.crank.points.b.local.x" },
            { "path": "bodies.coupler.points.c.local.x" },
            { "path": "bodies.rocker.points.c.local.x" },
        ],
        "drive": drive,
        "observations": observations,
        "camera": { "type": "plane", "plane": "plane-main" },
        "loss": { "type": "cauchy", "c": 0.001 },
        "maxIterations": 50,
    });
    let parsed: FitProblem = serde_json::from_value(problem.clone()).unwrap();
    let result = fit(&parsed).unwrap();
    json!({
        "problem": problem,
        "result": {
            "values": result.values,
            "sigma": result.sigma,
            "drive": result.drive,
            "poses": result.poses,
            "iterations": result.iterations,
        },
    })
}

fn cases() -> Vec<(String, Value)> {
    let mut out: Vec<(String, Value)> = goldens()
        .iter()
        .map(|path| {
            let name = path.file_name().unwrap().to_string_lossy().into_owned();
            let case = mechanism_case(&name, &std::fs::read_to_string(path).unwrap());
            (name, case)
        })
        .collect();
    out.push(("fit-four-bar.json".into(), fit_case()));
    out
}

/// Numbers within `tolerance`, everything else equal.
fn close(a: &Value, b: &Value, tolerance: f64, at: &str) -> Result<(), String> {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) => {
            let (x, y) = (x.as_f64().unwrap(), y.as_f64().unwrap());
            if (x - y).abs() <= tolerance {
                Ok(())
            } else {
                Err(format!("{at}: {x} vs {y}"))
            }
        }
        (Value::Array(x), Value::Array(y)) if x.len() == y.len() => x
            .iter()
            .zip(y)
            .enumerate()
            .try_for_each(|(i, (x, y))| close(x, y, tolerance, &format!("{at}[{i}]"))),
        (Value::Object(x), Value::Object(y)) if x.len() == y.len() => {
            x.iter().try_for_each(|(k, v)| {
                y.get(k)
                    .ok_or_else(|| format!("{at}.{k}: missing"))
                    .and_then(|w| close(v, w, tolerance, &format!("{at}.{k}")))
            })
        }
        _ if a == b => Ok(()),
        _ => Err(format!("{at}: {a} vs {b}")),
    }
}

#[test]
fn native_results_match_the_parity_files() {
    let dir = root().join("parity");
    let write = std::env::var_os("PARITY_WRITE").is_some();
    if write {
        std::fs::create_dir_all(&dir).unwrap();
    }
    let cases = cases();
    for (name, case) in &cases {
        let path = dir.join(name);
        if write {
            std::fs::write(&path, serde_json::to_string(case).unwrap() + "\n").unwrap();
            continue;
        }
        let stored: Value =
            serde_json::from_str(&std::fs::read_to_string(&path).unwrap_or_else(|e| {
                panic!(
                    "{} is missing ({e}); run with PARITY_WRITE=1",
                    path.display()
                )
            }))
            .unwrap();
        if let Err(e) = close(case, &stored, NATIVE_TOLERANCE, name) {
            panic!(
                "native results moved from {}: {e}. If intended, run with PARITY_WRITE=1",
                path.display()
            );
        }
    }
    // No stale files from removed goldens.
    let mut stored: Vec<String> = std::fs::read_dir(&dir)
        .unwrap()
        .filter_map(Result::ok)
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .collect();
    stored.sort();
    let mut expected: Vec<String> = cases.into_iter().map(|(n, _)| n).collect();
    expected.sort();
    assert_eq!(stored, expected);
}

#[test]
fn identical_inputs_give_bitwise_identical_results() {
    // Requirement 11.2: run everything twice, on two threads, and compare exactly.
    let first = std::thread::spawn(cases);
    let second = cases();
    let first = first.join().unwrap();
    for ((name, a), (_, b)) in first.iter().zip(&second) {
        assert_eq!(
            serde_json::to_string(a).unwrap(),
            serde_json::to_string(b).unwrap(),
            "{name} differs between runs"
        );
    }
}

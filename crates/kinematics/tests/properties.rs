//! Correctness properties 1 and 2 of the mechanism-core design over generated mechanisms
//! (property 9, gear ratios, is in `planar_joints.rs`).
//!
//! 1. For any valid generated mechanism and reachable driver value, assembly residuals are below
//!    1e-9.
//! 2. For any body and any two of its points, their world distance is constant across a simulated
//!    cycle.
//! 3. For any simulation step where no singularity is reported, the pose change is bounded by a
//!    Lipschitz constant times the driver step.
//! 4. For any mechanism without special geometry, numerical mobility equals Grübler mobility.
//!
//! The families are the ones the synthetic lab draws from: Grashof crank-rocker four-bars,
//! offset slider-cranks, and Watt six-bars (a four-bar with a dyad from its coupler to the
//! frame). Every generated mechanism can turn its crank through a full revolution.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::TAU;

use kinematics::AssemblyOptions;
use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use kinematics::simulate::SimulationOptions;
use proptest::prelude::*;
use serde_json::{Value, json};

fn p(id: &str, x: f64, y: f64) -> Value {
    json!({ "id": id, "local": { "x": x, "y": y, "z": 0 }, "role": "joint_anchor" })
}

fn body(id: &str, kind: &str, points: Vec<Value>) -> Value {
    json!({ "id": id, "label": id, "kind": kind, "planeId": "p", "points": points,
        "status": "observed", "confidence": 1 })
}

fn revolute(id: &str, a: &str, pa: &str, b: &str, pb: &str) -> Value {
    json!({ "id": id, "kind": "revolute", "bodyA": a, "bodyB": b,
        "anchorA": { "bodyId": a, "pointId": pa }, "anchorB": { "bodyId": b, "pointId": pb },
        "status": "observed", "confidence": 1 })
}

fn mechanism(bodies: Vec<Value>, joints: Vec<Value>) -> Value {
    json!({
        "schemaVersion": 1, "id": "generated", "name": "Generated",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [{ "id": "p", "originWorld": {"x":0,"y":0,"z":0},
            "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": bodies, "joints": joints,
        "drivers": [{ "id": "drive", "jointId": "crank-pivot", "coordinate": "angle",
            "profile": { "type": "constant_rate", "rate": 1, "phase0": 0 } }],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    })
}

/// Lengths of a crank-rocker: the crank is the shortest link and s + l < p + q, with a margin so
/// no generated mechanism sits on the Grashof boundary.
#[derive(Debug, Clone)]
struct FourBar {
    ground: f64,
    crank: f64,
    coupler: f64,
    rocker: f64,
    /// A tracked point on the coupler, in its frame.
    trace: (f64, f64),
}

fn four_bar() -> impl Strategy<Value = FourBar> {
    (
        0.02..0.08_f64,
        0.15..0.4_f64,
        0.15..0.4_f64,
        0.15..0.4_f64,
        -0.1..0.1_f64,
        -0.1..0.1_f64,
    )
        .prop_filter(
            "Grashof crank-rocker with a margin",
            |(s, g, c, r, _, _)| {
                let longest = g.max(*c).max(*r);
                let others = g + c + r - longest;
                s + longest < others - 0.02
                // Away from a dead center where the coupler and rocker fold flat.
                && (c - r).abs() < (g - s) - 0.02
                && c + r > g + s + 0.02
            },
        )
        .prop_map(|(crank, ground, coupler, rocker, tx, ty)| FourBar {
            ground,
            crank,
            coupler,
            rocker,
            trace: (coupler * 0.5 + tx, ty),
        })
}

fn four_bar_parts(f: &FourBar) -> (Vec<Value>, Vec<Value>) {
    let bodies = vec![
        body(
            "ground",
            "ground",
            vec![p("o2", 0.0, 0.0), p("o4", f.ground, 0.0)],
        ),
        body(
            "crank",
            "link",
            vec![p("a", 0.0, 0.0), p("b", f.crank, 0.0)],
        ),
        body(
            "coupler",
            "link",
            vec![
                p("b", 0.0, 0.0),
                p("c", f.coupler, 0.0),
                p("trace", f.trace.0, f.trace.1),
            ],
        ),
        body(
            "rocker",
            "link",
            vec![p("d", 0.0, 0.0), p("c", f.rocker, 0.0)],
        ),
    ];
    let joints = vec![
        revolute("crank-pivot", "ground", "o2", "crank", "a"),
        revolute("j-b", "crank", "b", "coupler", "b"),
        revolute("j-c", "coupler", "c", "rocker", "c"),
        revolute("j-d", "ground", "o4", "rocker", "d"),
    ];
    (bodies, joints)
}

/// The coupler trace point over a turn, by closed form, on the branch `side` (±1).
fn coupler_path(f: &FourBar, steps: u32, side: f64) -> Vec<(f64, f64)> {
    (0..steps)
        .map(|i| {
            let t = TAU * f64::from(i) / f64::from(steps);
            let b = (f.crank * t.cos(), f.crank * t.sin());
            let (dx, dy) = (f.ground - b.0, -b.1);
            let d = dx.hypot(dy);
            let a = (f.coupler * f.coupler - f.rocker * f.rocker + d * d) / (2.0 * d);
            let h = side * (f.coupler * f.coupler - a * a).max(0.0).sqrt();
            let (ux, uy) = (dx / d, dy / d);
            let c = (b.0 + a * ux - h * uy, b.1 + a * uy + h * ux);
            let (ex, ey) = ((c.0 - b.0) / f.coupler, (c.1 - b.1) / f.coupler);
            (
                b.0 + ex * f.trace.0 - ey * f.trace.1,
                b.1 + ey * f.trace.0 + ex * f.trace.1,
            )
        })
        .collect()
}

fn slider_crank() -> impl Strategy<Value = Value> {
    (0.02..0.08_f64, 0.2..0.5_f64, -0.03..0.03_f64).prop_map(|(r, l, offset)| {
        mechanism(
            vec![
                body("ground", "ground", vec![p("o", 0.0, 0.0), p("rail", 0.0, offset)]),
                body("crank", "link", vec![p("a", 0.0, 0.0), p("b", r, 0.0)]),
                body("rod", "link", vec![p("b", 0.0, 0.0), p("c", l, 0.0), p("mid", l / 2.0, 0.01)]),
                body("slider", "slider_block", vec![p("c", 0.0, 0.0), p("rail", 0.0, 0.0), p("edge", 0.02, 0.01)]),
            ],
            vec![
                revolute("crank-pivot", "ground", "o", "crank", "a"),
                revolute("j-b", "crank", "b", "rod", "b"),
                revolute("j-c", "rod", "c", "slider", "c"),
                json!({ "id": "rail", "kind": "prismatic", "bodyA": "ground", "bodyB": "slider",
                    "anchorA": {"bodyId":"ground","pointId":"rail"}, "anchorB": {"bodyId":"slider","pointId":"rail"},
                    "axisLocalA": {"x":1,"y":0,"z":0}, "status": "observed", "confidence": 1 }),
            ],
        )
    })
}

fn four_bar_mechanism() -> impl Strategy<Value = Value> {
    four_bar().prop_map(|f| {
        let (bodies, joints) = four_bar_parts(&f);
        mechanism(bodies, joints)
    })
}

/// A Watt six-bar: the four-bar plus a dyad from the coupler trace point to a frame pivot, with
/// lengths chosen so the dyad closes all the way round.
fn six_bar() -> impl Strategy<Value = Value> {
    (four_bar(), -0.3..0.3_f64, 0.2..0.4_f64, 0.3..0.7_f64).prop_filter_map(
        "dyad that closes through a turn",
        |(f, px, py, split)| {
            // The solver may assemble either branch of the four-bar, so the dyad must close on both.
            let path: Vec<(f64, f64)> = coupler_path(&f, 360, 1.0)
                .into_iter()
                .chain(coupler_path(&f, 360, -1.0))
                .collect();
            let dist: Vec<f64> = path.iter().map(|(x, y)| (x - px).hypot(y - py)).collect();
            let (near, far) = dist
                .iter()
                .fold((f64::INFINITY, 0.0_f64), |(n, m), d| (n.min(*d), m.max(*d)));
            // Dyad lengths a + b > far and |a − b| < near, with margins.
            let total = far + 0.05;
            let (a, b) = (total * split, total * (1.0 - split));
            ((a - b).abs() < near - 0.02 && near > 0.03)
                .then(|| {
                    let (mut bodies, mut joints) = four_bar_parts(&f);
                    bodies[0]["points"].as_array_mut()?.push(p("o6", px, py));
                    bodies.push(body(
                        "link5",
                        "link",
                        vec![p("e", 0.0, 0.0), p("f", a, 0.0), p("mark", a / 3.0, 0.02)],
                    ));
                    bodies.push(body(
                        "link6",
                        "link",
                        vec![p("g", 0.0, 0.0), p("f", b, 0.0)],
                    ));
                    joints.push(revolute("j-e", "coupler", "trace", "link5", "e"));
                    joints.push(revolute("j-f", "link5", "f", "link6", "f"));
                    joints.push(revolute("j-g", "ground", "o6", "link6", "g"));
                    Some(mechanism(bodies, joints))
                })
                .flatten()
        },
    )
}

fn any_mechanism() -> impl Strategy<Value = Value> {
    prop_oneof![four_bar_mechanism(), slider_crank(), six_bar()]
}

/// Every pair of named points on every body, with their world distance at `q`.
fn pair_distances(m: &Model, q: &[f64]) -> Vec<f64> {
    let mut out = Vec::new();
    for (i, body) in m.bodies.iter().enumerate() {
        let mut names: Vec<&String> = body.points.keys().collect();
        names.sort();
        for (k, a) in names.iter().enumerate() {
            for b in &names[k + 1..] {
                let (pa, pb) = (
                    m.point_world(i, a, q).unwrap(),
                    m.point_world(i, b, q).unwrap(),
                );
                out.push((pa[0] - pb[0]).hypot(pa[1] - pb[1]));
            }
        }
    }
    out
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 48, ..ProptestConfig::default() })]

    /// Property 1, from no seed at any crank angle.
    #[test]
    fn assembly_meets_the_residual_bound(value in any_mechanism(), angle in 0.0..TAU) {
        let m = Model::new(&parse_mechanism(&value.to_string()).unwrap()).unwrap();
        let a = m.assemble(&[angle], None, &AssemblyOptions::default())
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        prop_assert!(a.max_residual < 1e-9, "residual {}", a.max_residual);
        let r = m.residuals(&a.q, &[angle]);
        prop_assert!(r.iter().all(|v| v.abs() < 1e-9));
    }

    /// Properties 1 and 2 through a full turn with continuation.
    #[test]
    fn bodies_stay_rigid_through_a_cycle(value in any_mechanism()) {
        let m = Model::new(&parse_mechanism(&value.to_string()).unwrap()).unwrap();
        let mut seed: Option<Vec<f64>> = None;
        let mut reference: Option<Vec<f64>> = None;
        for step in 0..=90 {
            let angle = TAU * f64::from(step) / 90.0;
            let a = m.assemble(&[angle], seed.as_deref(), &AssemblyOptions::default())
                .map_err(|e| TestCaseError::fail(format!("at {angle}: {e}")))?;
            prop_assert!(a.max_residual < 1e-9);
            let d = pair_distances(&m, &a.q);
            let first = reference.get_or_insert_with(|| d.clone());
            for (x, y) in d.iter().zip(first.iter()) {
                prop_assert!((x - y).abs() < 1e-9, "a body changed shape at {angle}: {x} vs {y}");
            }
            seed = Some(a.q);
        }
    }

    /// Property 4: generated linkages have no special geometry, so both counts agree, there is
    /// nothing redundant, and once driven nothing is left free.
    #[test]
    fn numerical_mobility_equals_grubler(value in any_mechanism(), angle in 0.0..TAU) {
        let m = Model::new(&parse_mechanism(&value.to_string()).unwrap()).unwrap();
        let a = m.assemble(&[angle], None, &AssemblyOptions::default())
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        let mobility = m.mobility(&a.q, &[angle]);
        prop_assert_eq!(mobility.grubler, 1);
        prop_assert_eq!(mobility.numerical, 1);
        prop_assert!(mobility.redundant.is_empty(), "{:?}", mobility.redundant);
        prop_assert!(mobility.free_motions.is_empty(), "{:?}", mobility.free_motions);
    }

    /// Property 3: between two samples with no singularity, no coordinate moves further than the
    /// larger of its speeds at the two ends allows, with a factor of 2 for the curvature in
    /// between: continuation never jumps branch.
    #[test]
    fn simulation_steps_are_lipschitz(value in any_mechanism(), steps in 36_u32..120) {
        let m = Model::new(&parse_mechanism(&value.to_string()).unwrap()).unwrap();
        let h = TAU / f64::from(steps);
        let sim = m.simulate(0, &[0.0], (0.0, TAU, h), None, &SimulationOptions::default())
            .map_err(|e| TestCaseError::fail(format!("{e}")))?;
        prop_assert_eq!(sim.samples.len(), steps as usize + 1);
        for w in sim.samples.windows(2) {
            let (a, b) = (&w[0], &w[1]);
            if sim.singularities.iter().any(|s| s.drive >= a.drive - 1e-12 && s.drive <= b.drive + 1e-12) {
                continue;
            }
            let (va, vb) = (m.velocity(&a.q, &[a.drive], 0), m.velocity(&b.q, &[b.drive], 0));
            // Only body poses: curve parameters are not part of the pose.
            for (i, body) in m.bodies.iter().enumerate() {
                let kinematics::constraint::BodySlot::Var(start) = body.slot else { continue };
                for c in start..start + 3 {
                    let speed = va[c].abs().max(vb[c].abs());
                    let moved = (b.q[c] - a.q[c]).abs();
                    prop_assert!(moved <= 2.0 * speed * h + 1e-9,
                        "body {} coordinate {} moved {moved} with speed {speed} over {h} at {}", m.bodies[i].id, c - start, a.drive);
                }
            }
        }
    }
}

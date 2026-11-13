//! Plausibility metrics (mechanism-core requirement 8).

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::{PI, TAU};
use std::path::Path;

use kinematics::AssemblyOptions;
use kinematics::model::Model;
use kinematics::planar::V2;
use kinematics::plausibility::{GrashofClass, classify};
use kinematics::schema::parse_mechanism;
use kinematics::simulate::{SimulationOptions, SingularityKind};
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

#[test]
fn grashof_classes() {
    // Frame, input, coupler, output.
    assert_eq!(classify([0.3, 0.1, 0.25, 0.2]), GrashofClass::CrankRocker);
    assert_eq!(classify([0.1, 0.3, 0.25, 0.2]), GrashofClass::DoubleCrank);
    assert_eq!(classify([0.3, 0.25, 0.1, 0.2]), GrashofClass::DoubleRocker);
    assert_eq!(classify([0.3, 0.1, 0.3, 0.1]), GrashofClass::ChangePoint);
    assert_eq!(classify([0.3, 0.2, 0.15, 0.22]), GrashofClass::TripleRocker);
}

#[test]
fn the_golden_four_bar_is_a_crank_rocker_with_its_closed_form_transmission_angle() {
    let m = model(&golden("four-bar-crank-rocker.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 720.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let report = m.plausibility(&sim, 0, &[0.0]);
    assert_eq!(report.loops.len(), 1);
    let four_bar = &report.loops[0];
    assert_eq!(
        four_bar.bodies,
        ["ground", "crank", "coupler", "rocker"].map(String::from)
    );
    for (got, want) in four_bar.lengths.iter().zip([0.3, 0.1, 0.25, 0.2]) {
        assert!((got - want).abs() < 1e-12);
    }
    assert_eq!(four_bar.grashof, GrashofClass::CrankRocker);
    // At the coupler–rocker joint the angle is extreme when B is nearest O4 (θ = 0):
    // cos μ = (k² + r² − (g − c)²) / 2kr = 0.625.
    let coupler_rocker = four_bar
        .transmission
        .iter()
        .find(|t| t.joint_id == "j-c")
        .unwrap();
    assert!(
        (coupler_rocker.min_angle - 0.625_f64.acos()).abs() < 1e-4,
        "{coupler_rocker:?}"
    );
    assert!(coupler_rocker.at.min(TAU - coupler_rocker.at) < 0.02);
    // The coupler outline: 0.27 long, 0.02 wide.
    let slender = report
        .slenderness
        .iter()
        .find(|(b, _)| b == "coupler")
        .unwrap();
    assert!((slender.1 - 13.5).abs() < 1e-9);
}

/// Separating-axis overlap of two convex polygons.
fn convex_overlap(a: &[V2], b: &[V2]) -> bool {
    let separated = |p: &[V2], q: &[V2]| {
        (0..p.len()).any(|i| {
            let n = (p[(i + 1) % p.len()] - p[i]).perp();
            let (pa, pb): (Vec<f64>, Vec<f64>) = (
                p.iter().map(|v| v.dot(n)).collect(),
                q.iter().map(|v| v.dot(n)).collect(),
            );
            pa.iter().copied().fold(f64::NEG_INFINITY, f64::max)
                < pb.iter().copied().fold(f64::INFINITY, f64::min)
                || pb.iter().copied().fold(f64::NEG_INFINITY, f64::max)
                    < pa.iter().copied().fold(f64::INFINITY, f64::min)
        })
    };
    !separated(a, b) && !separated(b, a)
}

#[test]
fn collisions_with_a_frame_block_match_a_brute_force_check() {
    let mut v = golden("four-bar-crank-rocker.json");
    // Put a small block on the frame where the coupler's middle passes at θ = 4.5.
    let probe = model(&v);
    let at = probe
        .assemble(&[4.5], None, &AssemblyOptions::default())
        .unwrap();
    let coupler = probe.body("coupler").unwrap();
    let pose = probe.pose(coupler, &at.q);
    let center = pose.apply(V2::new(0.125, 0.0));
    let half = 0.008;
    let block: Vec<V2> = [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
        .iter()
        .map(|(x, y)| V2::new(center.x + x * half, center.y + y * half))
        .collect();
    v["bodies"][0]["outline"] = json!({
        "polygonLocal": block.iter().map(|p| json!({"x": p.x, "y": p.y})).collect::<Vec<_>>(),
        "thickness": 0.005,
    });
    let m = model(&v);
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 180.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let report = m.plausibility(&sim, 0, &[0.0]);
    let hit = report
        .collisions
        .iter()
        .find(|c| c.bodies == ("ground".into(), "coupler".into()))
        .unwrap();
    assert!(
        hit.ranges.iter().any(|(a, b)| *a < 4.5 && 4.5 < *b),
        "{:?}",
        hit.ranges
    );

    // Brute force over fine steps with an independent overlap test.
    let outline =
        [(-0.01, -0.01), (0.26, -0.01), (0.26, 0.01), (-0.01, 0.01)].map(|(x, y)| V2::new(x, y));
    let steps = 4000;
    let mut seed: Option<Vec<f64>> = None;
    let mut edges = Vec::new();
    let mut previous = None;
    for i in 0..=steps {
        let d = TAU * f64::from(i) / f64::from(steps);
        let a = m
            .assemble(&[d], seed.as_deref(), &AssemblyOptions::default())
            .unwrap();
        let pose = m.pose(coupler, &a.q);
        let placed: Vec<V2> = outline.iter().map(|p| pose.apply(*p)).collect();
        let now = convex_overlap(&placed, &block);
        if previous.is_some_and(|p| p != now) {
            edges.push(d);
        }
        previous = Some(now);
        seed = Some(a.q);
    }
    let reported: Vec<f64> = hit
        .ranges
        .iter()
        .flat_map(|(a, b)| [*a, *b])
        .filter(|x| *x > 1e-9 && *x < TAU - 1e-9)
        .collect();
    assert_eq!(reported.len(), edges.len(), "{reported:?} vs {edges:?}");
    for (r, e) in reported.iter().zip(&edges) {
        assert!(
            (r - e).abs() < 2.0 * TAU / f64::from(steps),
            "boundary {r} vs {e}"
        );
    }
    // Joined bodies are never reported, however their outlines meet at the pins.
    assert!(
        report
            .collisions
            .iter()
            .all(|c| c.bodies != ("ground".into(), "crank".into()))
    );
}

#[test]
fn reactions_reverse_where_the_rocker_turns_back() {
    let m = model(&golden("four-bar-crank-rocker.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 360.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let lockups: Vec<f64> = sim
        .singularities
        .iter()
        .filter(|s| s.kind == SingularityKind::Lockup)
        .map(|s| s.drive)
        .collect();
    let report = m.plausibility(&sim, 0, &[0.0]);
    let pivot = report
        .reaction_reversals
        .iter()
        .find(|r| r.joint_id == "j-o4")
        .unwrap();
    assert!(pivot.peak > 0.0);
    // The unit load opposes the rocker tip's motion, so it flips where the motion does. The
    // load and the coupler force both act at C, so the pivot's reaction along the rocker also
    // passes through zero where the transmission angle crosses 90°.
    for l in &lockups {
        assert!(
            pivot.at.iter().any(|r| (r - l).abs() < TAU / 360.0),
            "no reversal at lockup {l}: {:?}",
            pivot.at
        );
    }
}

/// Two bars in perpendicular planes, each pinned to a spatial ground and driven: bar A turns in
/// the XY plane about the origin; bar B lies along world x from 0.05 to 0.15 in the XZ plane.
fn crossing_bars() -> Value {
    let bar = |id: &str, plane: &str| {
        json!({ "id": id, "label": id, "kind": "link", "planeId": plane,
        "status": "observed", "confidence": 1,
        "points": [{ "id": "pivot", "local": {"x": 0, "y": 0, "z": 0}, "role": "joint_anchor" }],
        "outline": { "polygonLocal": [{"x": 0, "y": -0.005}, {"x": 0.1, "y": -0.005}, {"x": 0.1, "y": 0.005}, {"x": 0, "y": 0.005}], "thickness": 0.01 } })
    };
    let pin = |id: &str, ground: &str, body: &str| {
        json!({ "id": id, "kind": "revolute", "bodyA": "ground", "bodyB": body,
        "anchorA": {"bodyId": "ground", "pointId": ground}, "anchorB": {"bodyId": body, "pointId": "pivot"},
        "status": "observed", "confidence": 1 })
    };
    let drive = |id: &str, joint: &str| {
        json!({ "id": id, "jointId": joint, "coordinate": "angle",
        "profile": { "type": "constant_rate", "rate": 1, "phase0": 0 } })
    };
    json!({
        "schemaVersion": 1, "id": "crossing", "name": "Bars in crossing planes",
        "scale": { "source": "unscaled", "metersPerUnit": 1 },
        "planes": [
            { "id": "xy", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":0,"z":1}, "xAxisWorld": {"x":1,"y":0,"z":0} },
            { "id": "xz", "originWorld": {"x":0,"y":0,"z":0}, "normalWorld": {"x":0,"y":1,"z":0}, "xAxisWorld": {"x":1,"y":0,"z":0} }],
        "bodies": [
            { "id": "ground", "label": "G", "kind": "ground", "planeId": null, "status": "observed", "confidence": 1,
              "points": [{ "id": "a", "local": {"x":0,"y":0,"z":0}, "role": "joint_anchor" },
                         { "id": "b", "local": {"x":0.05,"y":0,"z":0}, "role": "joint_anchor" }] },
            bar("bar-a", "xy"), bar("bar-b", "xz")],
        "joints": [pin("pin-a", "a", "bar-a"), pin("pin-b", "b", "bar-b")],
        "drivers": [drive("turn-a", "pin-a"), drive("turn-b", "pin-b")],
        "provenance": { "createdBy": "lab", "footageIds": [] }
    })
}

#[test]
fn bars_in_crossing_planes_collide_where_their_prisms_meet() {
    let m = model(&crossing_bars());
    let sim = m
        .simulate(
            0,
            &[0.0, 0.0],
            (-PI, PI, TAU / 180.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let report = m.plausibility(&sim, 0, &[0.0, 0.0]);
    let hit = report
        .collisions
        .iter()
        .find(|c| c.bodies == ("bar-a".into(), "bar-b".into()));
    let hit = hit.unwrap_or_else(|| panic!("no collision: {:?}", report.collisions));
    assert_eq!(hit.ranges.len(), 1, "{:?}", hit.ranges);
    // Both prisms span z in [−0.005, 0.005] here, so they meet exactly where their footprints
    // in the XY plane do: A's rectangle against B's (x 0.05 to 0.15, y ±0.005).
    let a_outline =
        [(0.0, -0.005), (0.1, -0.005), (0.1, 0.005), (0.0, 0.005)].map(|(x, y)| V2::new(x, y));
    let b_footprint =
        [(0.05, -0.005), (0.15, -0.005), (0.15, 0.005), (0.05, 0.005)].map(|(x, y)| V2::new(x, y));
    let overlaps = |theta: f64| {
        let (s, c) = theta.sin_cos();
        let placed: Vec<V2> = a_outline
            .iter()
            .map(|p| V2::new(c * p.x - s * p.y, s * p.x + c * p.y))
            .collect();
        convex_overlap(&placed, &b_footprint)
    };
    let edge = |mut inside: f64, mut outside: f64| {
        for _ in 0..60 {
            let mid = 0.5 * (inside + outside);
            if overlaps(mid) {
                inside = mid
            } else {
                outside = mid
            }
        }
        0.5 * (inside + outside)
    };
    let (lo, hi) = (edge(0.0, -1.0), edge(0.0, 1.0));
    assert!(
        (hit.ranges[0].0 - lo).abs() < 1e-6 && (hit.ranges[0].1 - hi).abs() < 1e-6,
        "{:?} vs ({lo}, {hi})",
        hit.ranges
    );
}

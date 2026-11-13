//! Cycle simulation and singularities (mechanism-core requirements 5.1 to 5.4), against
//! closed-form four-bar geometry.

#![allow(
    clippy::unwrap_used,
    reason = "test helpers: a panic is the test failing"
)]

use std::f64::consts::{PI, TAU};
use std::path::Path;

use kinematics::model::Model;
use kinematics::schema::parse_mechanism;
use kinematics::simulate::{SimulationOptions, SingularityKind};
use serde_json::Value;

fn golden(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/golden/mechanism")
        .join(name);
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

/// The golden four-bar with new link lengths (ground, crank, coupler, rocker).
fn four_bar(g: f64, c: f64, k: f64, r: f64) -> Value {
    let mut v = golden("four-bar-crank-rocker.json");
    v["bodies"][0]["points"][1]["local"]["x"] = g.into();
    v["bodies"][1]["points"][1]["local"]["x"] = c.into();
    v["bodies"][2]["points"][1]["local"]["x"] = k.into();
    v["bodies"][2]["points"][2]["local"]["x"] = (k / 2.0).into();
    v["bodies"][3]["points"][1]["local"]["x"] = r.into();
    v["bodies"][3]["points"][2]["local"]["x"] = r.into();
    v
}

fn model(v: &Value) -> Model {
    Model::new(&parse_mechanism(&v.to_string()).unwrap()).unwrap()
}

/// Distance between two angles, modulo a turn.
fn angle_gap(a: f64, b: f64) -> f64 {
    ((a - b + PI).rem_euclid(TAU) - PI).abs()
}

/// Directions from the crank pivot at which a point `d` from it is also `r` from the rocker
/// pivot: where C lies when the crank and coupler line up.
fn collinear_crank_angles(g: f64, d: f64, r: f64) -> [f64; 2] {
    let alpha = ((d * d + g * g - r * r) / (2.0 * d * g)).acos();
    [alpha, -alpha]
}

#[test]
fn crank_rocker_turns_fully_with_two_output_reversals() {
    let m = model(&golden("four-bar-crank-rocker.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 72.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    assert_eq!(sim.samples.len(), 73);
    assert_eq!(sim.reachable, vec![(0.0, TAU)]);
    let lockups: Vec<f64> = sim
        .singularities
        .iter()
        .filter(|s| s.kind == SingularityKind::Lockup)
        .map(|s| s.drive)
        .collect();
    assert!(
        sim.singularities
            .iter()
            .all(|s| s.kind == SingularityKind::Lockup),
        "{:?}",
        sim.singularities
    );
    assert_eq!(lockups.len(), 2, "{lockups:?}");
    // The rocker reverses where the crank and coupler line up, extended and folded.
    let candidates: Vec<f64> = collinear_crank_angles(0.3, 0.35, 0.2)
        .into_iter()
        // Folded, C lies opposite the crank pin, so the crank points the other way.
        .chain(collinear_crank_angles(0.3, 0.15, 0.2).map(|a| a + PI))
        .collect();
    for at in &lockups {
        let off = candidates
            .iter()
            .map(|c| angle_gap(*at, *c))
            .fold(f64::INFINITY, f64::min);
        assert!(
            off < 1e-6,
            "lockup at {at} is {off} from a collinear position"
        );
    }
    // Trajectories: one world position per sample for every named point.
    let paths = m.trajectories(&sim);
    assert!(paths.values().all(|p| p.len() == 73));
    assert!(paths.contains_key(&("coupler".to_owned(), "trace".to_owned())));
}

#[test]
fn driving_the_rocker_past_its_swing_is_a_dead_center() {
    let mut v = golden("four-bar-crank-rocker.json");
    v["drivers"][0]["jointId"] = "j-o4".into();
    let m = model(&v);
    // The rocker's swing limits: C at 0.35 (crank and coupler extended) or 0.15 (folded) from O2.
    let limit = |d: f64| {
        // C on circle(O4, 0.2) at distance d from O2: angle at O4 between O4→O2 and O4→C.
        let beta = ((0.2_f64 * 0.2 + 0.3 * 0.3 - d * d) / (2.0 * 0.2 * 0.3)).acos();
        [PI - beta, PI + beta]
    };
    let ends: Vec<f64> = limit(0.35).into_iter().chain(limit(0.15)).collect();
    // Start mid-swing on the upper branch and sweep up past the limit.
    let start = 0.5 * (limit(0.35)[0] + limit(0.15)[0]);
    let sim = m
        .simulate(
            0,
            &[0.0],
            (start, start + 1.5, 0.05),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let (_, reached) = sim.reachable[0];
    let gap = ends
        .iter()
        .map(|e| angle_gap(reached, *e))
        .fold(f64::INFINITY, f64::min);
    assert!(
        gap < 1e-4,
        "range ends at {reached}, {gap} from a swing limit"
    );
    let dead = sim
        .singularities
        .iter()
        .find(|s| s.kind == SingularityKind::DeadCenter)
        .unwrap();
    assert!((dead.drive - reached).abs() < 1e-12);
    assert!(!dead.joints.is_empty());
}

#[test]
fn a_non_grashof_crank_has_two_reachable_ranges() {
    // s + l > p + q: the crank rocks. |B − O4| reaches coupler + rocker at cos θ = −0.0575.
    let m = model(&four_bar(0.3, 0.2, 0.15, 0.22));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, TAU / 360.0),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let limit = (-0.0575_f64).acos();
    assert_eq!(sim.reachable.len(), 2, "{:?}", sim.reachable);
    assert!(
        (sim.reachable[0].1 - limit).abs() < 1e-4,
        "{:?}",
        sim.reachable
    );
    assert!(
        sim.reachable[1].0 >= TAU - limit - 1e-9 && sim.reachable[1].0 < TAU - limit + TAU / 360.0
    );
    assert!(
        sim.singularities
            .iter()
            .any(|s| s.kind == SingularityKind::DeadCenter && (s.drive - limit).abs() < 1e-4)
    );
    // No sample is reported inside the unreachable gap.
    assert!(
        sim.samples
            .iter()
            .all(|s| s.drive <= limit + 1e-9 || s.drive >= TAU - limit - 1e-9)
    );
}

#[test]
fn a_parallelogram_reports_its_change_point() {
    // Ground and coupler equal, crank and rocker equal: at θ = π all four links line up and the
    // parallelogram and antiparallelogram branches meet.
    let m = model(&four_bar(0.3, 0.1, 0.3, 0.1));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.5, 2.0 * PI - 0.5, 0.02),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let event = sim
        .singularities
        .iter()
        .find(|s| s.kind == SingularityKind::Bifurcation);
    let event = event.unwrap_or_else(|| panic!("no bifurcation: {:?}", sim.singularities));
    assert!(
        (event.drive - PI).abs() < 1e-3,
        "bifurcation at {}",
        event.drive
    );
}

#[test]
fn an_output_at_rest_reports_no_lockups() {
    // The golden cam's output is the free end of a leaf the cam never touches. Its velocity is
    // rounding noise, whose sign once flipped often enough to report lockups (found by the
    // native versus WebAssembly parity test, where the two builds disagreed on how many).
    let m = model(&golden("cam-followers-and-spring.json"));
    let sim = m
        .simulate(
            0,
            &[0.0],
            (0.0, TAU, 0.05),
            None,
            &SimulationOptions::default(),
        )
        .unwrap();
    let leaf = m.body("leaf").unwrap();
    let ends: Vec<[f64; 3]> = sim
        .samples
        .iter()
        .map(|s| m.point_world(leaf, "free-end", &s.q).unwrap())
        .collect();
    assert!(
        ends.iter()
            .all(|e| e.iter().zip(&ends[0]).all(|(a, b)| (a - b).abs() < 1e-12)),
        "the leaf moved"
    );
    let lockups: Vec<f64> = sim
        .singularities
        .iter()
        .filter(|s| s.kind == SingularityKind::Lockup)
        .map(|s| s.drive)
        .collect();
    assert!(lockups.is_empty(), "{lockups:?}");
}

//! Golden mechanism files shared with the TypeScript and Python suites (mechanism-core
//! requirements 2.2 to 2.4). Property 7: parse → serialize → parse is the identity, compared as
//! JSON values with numbers compared by value (`1` and `1.0` are the same number). Property 10:
//! each invalid file fails validation for the rule it breaks.

use std::fs;
use std::path::{Path, PathBuf};

use kinematics::schema::{parse_mechanism, to_json};
use kinematics::validate::validate;
use serde_json::Value;

fn golden_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/golden/mechanism")
}

fn json_files(dir: &Path) -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()))
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    files
}

fn read(path: &Path) -> String {
    fs::read_to_string(path).unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()))
}

/// JSON equality with numbers compared as values.
fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) => x.as_f64() == y.as_f64(),
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| same(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| same(v, w)))
        }
        _ => a == b,
    }
}

#[test]
fn every_golden_file_round_trips_and_validates() {
    let files = json_files(&golden_dir());
    assert!(
        files.len() >= 7,
        "expected the golden set, found {}",
        files.len()
    );
    for path in files {
        let text = read(&path);
        let original: Value = serde_json::from_str(&text).expect("golden file is JSON");
        let parsed = parse_mechanism(&text)
            .unwrap_or_else(|e| panic!("{} does not parse: {e}", path.display()));
        validate(&parsed)
            .unwrap_or_else(|issues| panic!("{} is invalid: {issues:?}", path.display()));
        let serialized = to_json(&parsed).expect("mechanism serializes");
        let round: Value = serde_json::from_str(&serialized).expect("output is JSON");
        assert!(
            same(&original, &round),
            "{} changed in a round trip",
            path.display()
        );
        let again = parse_mechanism(&serialized).expect("serialized output parses");
        assert!(
            same(&round, &serde_json::to_value(&again).expect("serializes")),
            "{} is not stable across two round trips",
            path.display()
        );
    }
}

#[test]
fn every_invalid_file_fails_for_the_rule_it_breaks() {
    let expected = [
        (
            "dangling-body.json",
            "references non-existent body missing-body",
        ),
        (
            "dangling-driver-joint.json",
            "references non-existent joint missing-joint",
        ),
        (
            "dangling-plane.json",
            "references non-existent plane missing-plane",
        ),
        (
            "dangling-point.json",
            "references non-existent point missing-point",
        ),
        ("duplicate-body-id.json", "Duplicate body IDs"),
        ("duplicate-joint-id.json", "Duplicate joint IDs"),
        ("self-joint.json", "connects body coupler to itself"),
        ("two-grounds.json", "exactly one ground body, found 2"),
    ];
    let files = json_files(&golden_dir().join("invalid"));
    let names: Vec<String> = files
        .iter()
        .filter_map(|p| p.file_name().map(|n| n.to_string_lossy().into_owned()))
        .collect();
    assert_eq!(
        names,
        expected
            .iter()
            .map(|(n, _)| (*n).to_owned())
            .collect::<Vec<_>>()
    );
    for (path, (_, message)) in files.iter().zip(expected) {
        let parsed = parse_mechanism(&read(path)).expect("invalid files are structurally sound");
        let issues = validate(&parsed).expect_err("the file breaks a rule");
        assert!(
            issues.iter().any(|i| i.message.contains(message)),
            "{}: expected \"{message}\", got {issues:?}",
            path.display()
        );
    }
}

"""The `orrery-lab` command line, run as a subprocess the way developers and CI run it."""

import json
import subprocess
import sys
from pathlib import Path

from orrery_lab.generated.mechanism import Mechanism


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orrery_lab", *args], capture_output=True, text=True, check=False
    )


def test_lists_the_families() -> None:
    result = run("families")
    assert result.returncode == 0
    assert "four-bar-crank-rocker" in result.stdout.split()


def test_writes_a_sample(tmp_path: Path) -> None:
    out = tmp_path / "sample.json"
    result = run("sample", "four-bar-crank-rocker", "--seed", "4", "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert "four-bar-crank-rocker-4: accepted" in result.stderr
    document = json.loads(out.read_text())
    assert Mechanism.model_validate(document).id == "four-bar-crank-rocker-4"


def test_an_unknown_family_is_a_usage_error() -> None:
    result = run("sample", "orrery")
    assert result.returncode == 2
    assert "unknown family" in result.stderr


def test_hashes_a_real_suite_manifest() -> None:
    manifest = Path(__file__).parents[1] / "suites" / "smoke.toml"
    first = run("suite-hash", str(manifest))
    second = run("suite-hash", str(manifest))

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert len(first.stdout.strip()) == 64

"""Golden mechanism files, shared with packages/schema and crates/kinematics (mechanism-core
requirements 2.2 and 2.3). Property 7: parse, serialize, and parse again is the identity.

Python compares `1` and `1.0` as equal, so the documents are compared as parsed JSON.
"""

import json
from pathlib import Path

import pytest
from orrery_engine.generated.mechanism import Mechanism

GOLDEN = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "mechanism"
FILES = sorted(GOLDEN.glob("*.json"))


def test_the_golden_set_is_present() -> None:
    assert len(FILES) >= 7


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_golden_mechanism_round_trips(path: Path) -> None:
    text = path.read_text()
    original = json.loads(text)
    parsed = Mechanism.model_validate_json(text)
    dumped = parsed.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert dumped == original
    again = Mechanism.model_validate(dumped)
    assert again.model_dump(mode="json", by_alias=True, exclude_unset=True) == dumped


def test_joint_variants_are_read_by_kind() -> None:
    mechanism = Mechanism.model_validate_json((GOLDEN / "slider-crank.json").read_text())
    kinds = {type(j.root).__name__ for j in mechanism.joints}
    assert kinds == {"RevoluteJoint", "PrismaticJoint"}

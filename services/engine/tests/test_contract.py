import json
from pathlib import Path

import pytest
from orrery_engine.generated.contract import ProbeRequest, ProbeResponse
from pydantic import ValidationError

GOLDEN = Path(__file__).resolve().parents[3] / "fixtures" / "golden" / "engine-contract"


def golden(name: str) -> dict[str, object]:
    return json.loads((GOLDEN / name).read_text())


def test_generated_models_accept_the_golden_messages() -> None:
    request = ProbeRequest.model_validate(golden("probe-request.json"))
    assert request.max_bytes == 1_000_000_000
    accepted = ProbeResponse.model_validate(golden("probe-accepted.json")).root
    assert accepted.outcome == "accepted"
    rejected = ProbeResponse.model_validate(golden("probe-rejected.json")).root
    assert rejected.outcome == "rejected"


def test_serialization_round_trips_to_the_wire_format() -> None:
    message = golden("probe-accepted.json")
    parsed = ProbeResponse.model_validate(message)
    assert parsed.model_dump(by_alias=True, mode="json") == message


def test_generated_models_reject_unknown_fields_and_bad_values() -> None:
    message = golden("probe-accepted.json")
    with pytest.raises(ValidationError):
        ProbeResponse.model_validate({**message, "extra": 1})
    with pytest.raises(ValidationError):
        ProbeResponse.model_validate({**message, "rotationQuarterTurns": 4})

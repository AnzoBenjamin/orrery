import hashlib
from pathlib import Path
from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st
from orrery_engine.probe import ProbeResult, Rejection, _is_vfr, inspect  # pyright: ignore[reportPrivateUsage]


def run(path: Path, max_duration_s: float = 300) -> ProbeResult | Rejection:
    data = path.read_bytes()
    return inspect(
        path,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        max_duration_s=max_duration_s,
    )


def test_accepts_h264_mp4_and_reads_its_properties(clips: dict[str, Path]) -> None:
    result = run(clips["h264"])
    assert isinstance(result, ProbeResult)
    assert result.codec == "h264"
    assert (result.width, result.height) == (320, 240)
    assert result.duration_s == pytest.approx(2.0, abs=0.1)
    assert result.fps_nominal == pytest.approx(30.0)
    assert result.is_vfr is False
    assert result.rotation_quarter_turns == 0


def test_reads_display_rotation_as_counter_clockwise_quarter_turns(
    clips: dict[str, Path],
) -> None:
    result = run(clips["rotated"])
    assert isinstance(result, ProbeResult)
    assert result.rotation_quarter_turns == 1


def test_accepts_vp9_webm(clips: dict[str, Path]) -> None:
    result = run(clips["webm"])
    assert isinstance(result, ProbeResult)
    assert result.codec == "vp9"


@pytest.mark.parametrize(
    ("clip", "code"),
    [
        ("disguised", "not_video"),
        ("audio", "not_video"),
        ("gif", "unsupported_container"),
    ],
)
def test_rejects_by_content_not_by_name(clips: dict[str, Path], clip: str, code: str) -> None:
    result = run(clips[clip])
    assert isinstance(result, Rejection)
    assert result.code == code
    assert result.reason.endswith(".")


def test_rejects_clips_over_the_duration_limit(clips: dict[str, Path]) -> None:
    result = run(clips["h264"], max_duration_s=1.0)
    assert isinstance(result, Rejection)
    assert result.code == "too_long"
    assert "Trim" in result.reason


def test_rejects_empty_files(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    result = run(empty)
    assert isinstance(result, Rejection)
    assert result.code == "empty"


@given(
    start=st.integers(min_value=-(10**6), max_value=10**6),
    step=st.integers(min_value=1, max_value=10**5),
    count=st.integers(min_value=0, max_value=400),
    shuffle=st.randoms(use_true_random=False),
)
def test_constant_frame_intervals_are_never_variable_rate(
    start: int, step: int, count: int, shuffle: Random
) -> None:
    pts = [start + i * step for i in range(count)]
    shuffle.shuffle(pts)
    assert _is_vfr(pts) is False


@given(
    step=st.integers(min_value=100, max_value=10_000),
    count=st.integers(min_value=10, max_value=200),
)
def test_a_frame_held_twice_as_long_marks_variable_rate(step: int, count: int) -> None:
    pts = [i * step for i in range(count)]
    middle = count // 2
    pts = pts[:middle] + [p + step for p in pts[middle:]]
    assert _is_vfr(pts) is True

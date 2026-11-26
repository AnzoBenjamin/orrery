"""Strict, versioned TOML suite manifests and canonical suite identities."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self, cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orrery_lab.families import FAMILIES
from orrery_lab.family import PartKind

MANIFEST_FORMAT = "orrery.synthetic.suite"
MANIFEST_VERSION = 1
_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

CaptureTier = Literal["clean", "phone", "hostile", "archival"]
RenderMode = Literal["2d", "3d"]
SuiteCodec = Literal["h264", "h265"]
BreakageSelection = Literal[
    "none", "any", "binary_link", "slider_block", "gear", "belt", "adjacent_links"
]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CaptureProfile(_FrozenModel):
    """A real generation profile; every field changes generated clip content."""

    name: str
    tier: CaptureTier
    render_mode: RenderMode = "2d"
    width: int = Field(ge=16, le=4096)
    height: int = Field(ge=16, le=4096)
    frame_rate: int = Field(ge=1, le=120)
    frame_count: int = Field(ge=2, le=36_000)
    codec: SuiteCodec = "h264"
    variable_frame_rate: bool = False
    drop_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    clutter_count: int = Field(default=0, ge=0, le=100)
    shadows: bool = True
    cycles_samples: int = Field(default=1, ge=1, le=4096)
    camera_path: Literal["orbit", "handheld"] = "orbit"

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if not _NAME.fullmatch(self.name):
            raise ValueError("capture profile name must be a lowercase kebab-case identifier")
        if self.width % 2 or self.height % 2:
            raise ValueError("suite video dimensions must be even for yuv420p encoding")
        if not math.isfinite(self.drop_probability):
            raise ValueError("drop probability must be finite")
        return self


class ClipSpec(_FrozenModel):
    """One deterministic clip in manifest order."""

    id: str
    family: str
    profile: str
    breakage: BreakageSelection = "none"
    sample_seed: int | None = Field(default=None, ge=0, le=(1 << 63) - 1)
    breakage_index: int | None = Field(default=None, ge=0)
    source_clip: str | None = None

    @model_validator(mode="after")
    def validate_clip(self) -> Self:
        if not _NAME.fullmatch(self.id):
            raise ValueError("clip id must be a lowercase kebab-case identifier")
        if self.family not in FAMILIES:
            raise ValueError(f"unknown mechanism family {self.family!r}")
        if self.breakage == "none" and self.breakage_index is not None:
            raise ValueError("an intact clip cannot select a breakage index")
        if self.source_clip is not None and not _NAME.fullmatch(self.source_clip):
            raise ValueError("source clip must be a lowercase kebab-case identifier")
        return self


class SuiteManifest(_FrozenModel):
    """Canonical in-memory form of a versioned TOML suite manifest."""

    schema_version: Literal[1]
    name: str
    seed: int = Field(ge=0, le=(1 << 63) - 1)
    runtime_budget_seconds: int = Field(gt=0)
    profiles: tuple[CaptureProfile, ...]
    clips: tuple[ClipSpec, ...]

    @field_validator("profiles", "clips", mode="before")
    @classmethod
    def accept_toml_arrays(cls, value: object) -> object:
        # TOML and JSON arrays decode as lists; normalize explicitly while all scalar fields stay
        # strict and all nested objects still reject unknown keys.
        return tuple(cast(list[object], value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_suite(self) -> Self:
        if not _NAME.fullmatch(self.name):
            raise ValueError("suite name must be a lowercase kebab-case identifier")
        if not self.profiles:
            raise ValueError("suite must declare at least one capture profile")
        if not self.clips:
            raise ValueError("suite must declare at least one clip")
        profile_names = [profile.name for profile in self.profiles]
        if len(profile_names) != len(set(profile_names)):
            raise ValueError("capture profile names must be unique")
        clip_ids = [clip.id for clip in self.clips]
        if len(clip_ids) != len(set(clip_ids)):
            raise ValueError("clip ids must be unique")
        known_profiles = set(profile_names)
        for clip in self.clips:
            if clip.profile not in known_profiles:
                raise ValueError(f"clip {clip.id!r} names unknown profile {clip.profile!r}")
            profile = self.profile(clip.profile)
            if clip.family in {"spatial-rssr", "two-plane-cardan"} and profile.render_mode != "3d":
                raise ValueError(f"spatial clip {clip.id!r} requires a 3d capture profile")
        _validate_source_relations(self.clips)
        return self

    def profile(self, name: str) -> CaptureProfile:
        return next(profile for profile in self.profiles if profile.name == name)

    def canonical_record(self) -> dict[str, object]:
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class ClipPlan:
    index: int
    spec: ClipSpec
    profile: CaptureProfile
    seed: int


def _validate_source_relations(clips: tuple[ClipSpec, ...]) -> None:
    prior_clips: dict[str, ClipSpec] = {}
    for clip in clips:
        if clip.source_clip is not None:
            source = prior_clips.get(clip.source_clip)
            if source is None:
                raise ValueError(f"clip {clip.id!r} names an unknown or later source clip")
            if clip.breakage != "none" or source.breakage == "none":
                raise ValueError("a repaired source relation must point from intact to broken")
            if clip.family != source.family:
                raise ValueError("repaired and broken source clips must use the same family")
            if clip.sample_seed is None or clip.sample_seed != source.sample_seed:
                raise ValueError(
                    "repaired and broken source clips must share an explicit sample seed"
                )
        prior_clips[clip.id] = clip


def load_manifest(path: Path) -> SuiteManifest:
    """Parse and fully validate one suite TOML file."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"invalid suite TOML {path}: {error}") from error
    return SuiteManifest.model_validate(raw)


def canonical_manifest_bytes(manifest: SuiteManifest) -> bytes:
    """Canonical JSON representation independent of TOML formatting and key order."""
    return (
        json.dumps(
            manifest.canonical_record(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def manifest_hash(manifest: SuiteManifest, lab_version: str) -> str:
    """Hash the canonical manifest and lab version with an unambiguous versioned envelope."""
    if not lab_version or lab_version.strip() != lab_version:
        raise ValueError("lab version must be non-empty and have no surrounding whitespace")
    envelope = {
        "format": MANIFEST_FORMAT,
        "labVersion": lab_version,
        "manifest": manifest.canonical_record(),
        "schemaVersion": MANIFEST_VERSION,
    }
    canonical = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def derive_clip_seed(suite_seed: int, clip_index: int) -> int:
    """Derive the clip-local seed through NumPy SeedSequence, independent of run order."""
    if suite_seed < 0 or clip_index < 0:
        raise ValueError("suite seed and clip index must be nonnegative")
    sequence = np.random.SeedSequence((suite_seed, clip_index))
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


def plan_clips(manifest: SuiteManifest) -> tuple[ClipPlan, ...]:
    return tuple(
        ClipPlan(
            index,
            spec,
            manifest.profile(spec.profile),
            spec.sample_seed
            if spec.sample_seed is not None
            else derive_clip_seed(manifest.seed, index),
        )
        for index, spec in enumerate(manifest.clips)
    )


def part_kind(selection: BreakageSelection) -> PartKind | None:
    if selection in {"none", "any"}:
        return None
    return cast(PartKind, selection)


__all__ = [
    "MANIFEST_FORMAT",
    "MANIFEST_VERSION",
    "BreakageSelection",
    "CaptureProfile",
    "ClipPlan",
    "ClipSpec",
    "SuiteManifest",
    "canonical_manifest_bytes",
    "derive_clip_seed",
    "load_manifest",
    "manifest_hash",
    "part_kind",
    "plan_clips",
]

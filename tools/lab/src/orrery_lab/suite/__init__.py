"""Reproducible suite manifests, generation, content hashes, and caches."""

from __future__ import annotations

from typing import TYPE_CHECKING

from orrery_lab.suite.cache import LocalSuiteCache, S3SuiteCache, SuiteCache
from orrery_lab.suite.content import DecodedFrameHash, decoded_frame_hash
from orrery_lab.suite.manifest import (
    MANIFEST_FORMAT,
    MANIFEST_VERSION,
    CaptureProfile,
    ClipPlan,
    ClipSpec,
    SuiteManifest,
    canonical_manifest_bytes,
    derive_clip_seed,
    load_manifest,
    manifest_hash,
    plan_clips,
)

if TYPE_CHECKING:
    from orrery_lab.suite.generator import (
        GeneratedClip,
        SuiteResult,
        generate_suite,
        read_suite,
    )

_GENERATOR_EXPORTS = {"GeneratedClip", "SuiteResult", "generate_suite", "read_suite"}


def __getattr__(name: str) -> object:
    """Keep manifest-only commands from importing Blender through the generation pipeline."""
    if name not in _GENERATOR_EXPORTS:
        raise AttributeError(name)
    from orrery_lab.suite import generator  # noqa: PLC0415 -- intentional lazy Blender import

    return getattr(generator, name)


__all__ = [
    "MANIFEST_FORMAT",
    "MANIFEST_VERSION",
    "CaptureProfile",
    "ClipPlan",
    "ClipSpec",
    "DecodedFrameHash",
    "GeneratedClip",
    "LocalSuiteCache",
    "S3SuiteCache",
    "SuiteCache",
    "SuiteManifest",
    "SuiteResult",
    "canonical_manifest_bytes",
    "decoded_frame_hash",
    "derive_clip_seed",
    "generate_suite",
    "load_manifest",
    "manifest_hash",
    "plan_clips",
    "read_suite",
]

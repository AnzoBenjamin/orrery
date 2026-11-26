"""Shared array validation for the linear-light degradation pipeline."""

from __future__ import annotations

import math
from itertools import pairwise

import numpy as np
import numpy.typing as npt

LinearRGB = npt.NDArray[np.float32]
RGB_CHANNELS = 3


def validate_linear_rgb(image: LinearRGB, *, sequence: bool = False) -> None:
    """Validate float32 linear RGB in [0, 1], with rows ordered top to bottom.

    Intermediate operations retain float32 linear light. Only the sensor output is a declared
    clipping boundary; callers must provide unclipped scene values in the displayable range.
    """
    expected_dimensions = 4 if sequence else 3
    if image.ndim != expected_dimensions or image.shape[-1] != RGB_CHANNELS:
        shape = "(frames, height, width, 3)" if sequence else "(height, width, 3)"
        raise ValueError(f"linear RGB must have shape {shape}")
    if any(dimension <= 0 for dimension in image.shape):
        raise ValueError("linear RGB dimensions must be positive")
    if image.dtype != np.float32:
        raise ValueError("linear RGB must be float32")
    if not np.all(np.isfinite(image)):
        raise ValueError("linear RGB must contain only finite values")
    if np.any(image < 0.0) or np.any(image > 1.0):
        raise ValueError("linear RGB must be in the closed interval [0, 1]")


def validate_timestamps(timestamps: tuple[float, ...], expected_count: int) -> None:
    if len(timestamps) != expected_count:
        raise ValueError("timestamp count must equal frame count")
    if not timestamps or not all(math.isfinite(timestamp) for timestamp in timestamps):
        raise ValueError("timestamps must be finite and non-empty")
    if any(right <= left for left, right in pairwise(timestamps)):
        raise ValueError("timestamps must be strictly increasing")


__all__ = ["LinearRGB", "validate_linear_rgb", "validate_timestamps"]

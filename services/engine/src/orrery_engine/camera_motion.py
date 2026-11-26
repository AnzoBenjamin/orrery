"""Planar camera-motion estimation and stabilized preview generation.

OpenCV is intentionally isolated in this typed adapter. Homographies always map reference-frame
pixels to source-frame pixels. Consumers stabilize with the inverse mapping.
"""

# OpenCV's generated stubs leave several array and factory return types unknown.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnnecessaryComparison=false

from __future__ import annotations

import base64
import hashlib
import math
import statistics
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import cast

import av
import cv2
import numpy as np
import numpy.typing as npt

CancelCheck = Callable[[], None]
ProgressCallback = Callable[[float, str], None]
Image = npt.NDArray[np.uint8]
Matrix = npt.NDArray[np.float64]
Points = npt.NDArray[np.float32]
MIN_STATIC_FRACTION = 0.15
MATCH_PAIR_SIZE = 2
SECOND_PLANE_INLIER_RATIO = 0.55


class CameraMotionError(RuntimeError):
    """The normalized footage cannot support a reliable planar camera estimate."""


@dataclass(frozen=True)
class CameraMotionConfig:
    ransac_threshold_px: float = 1.5
    parallax_threshold_px: float = 2.5
    min_matches: int = 8
    preview_long_side: int = 720


@dataclass(frozen=True)
class FrameMotion:
    frame_index: int
    reference_to_frame: Matrix
    residuals_px: tuple[float, ...]
    inlier_ratio: float
    match_count: int
    parallax_evidence: bool


@dataclass(frozen=True)
class MotionEstimate:
    frames: tuple[FrameMotion, ...]
    static_masks: tuple[Image, ...]
    stabilized_rms_px: float
    median_residual_px: float
    p95_residual_px: float
    mean_inlier_ratio: float
    valid_frame_fraction: float
    static_pixel_fraction: float
    parallax_evidence_frames: int
    requires_spatial: bool
    routing_reason: str | None


@dataclass(frozen=True)
class CameraMotionResult:
    motions: tuple[dict[str, object], ...]
    manifest: dict[str, object]
    estimate: MotionEstimate
    preview_path: Path


def analyze_camera_motion(
    analysis_path: Path,
    output_dir: Path,
    *,
    footage_id: str,
    config: CameraMotionConfig,
    check_canceled: CancelCheck,
    progress: ProgressCallback,
) -> CameraMotionResult:
    """Estimate one normalized clip and encode a real stabilized H.264 preview."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames, rate = decode_frames(analysis_path, check_canceled)
    progress(0.15, "Computing dense Farneback motion and static-scene masks.")
    estimate = estimate_camera_motion(frames, config=config, check_canceled=check_canceled)
    progress(0.75, "Encoding the stabilized preview.")
    preview_path = output_dir / "stabilized-preview.mp4"
    encode_stabilized_preview(frames, estimate.frames, preview_path, rate, check_canceled)
    mask_path = output_dir / "static-mask.png"
    reference_mask = estimate.static_masks[0]
    encoded, content = cv2.imencode(".png", reference_mask)
    if not encoded:
        raise CameraMotionError("OpenCV could not encode the static-scene mask.")
    mask_path.write_bytes(content.tobytes())
    motions: tuple[dict[str, object], ...] = tuple(
        {
            "frameIndex": frame.frame_index,
            "footageId": footage_id,
            "referenceToFrame": frame.reference_to_frame.reshape(-1).tolist(),
        }
        for frame in estimate.frames
    )
    manifest: dict[str, object] = {
        "footageId": footage_id,
        "referenceFrameIndex": 0,
        "referenceSource": "static_scene",
        "groundRefinementAvailable": True,
        "requiresSpatial": estimate.requires_spatial,
        "staticMask": _embedded(mask_path, "image/png"),
        "stabilizedPreview": _embedded(preview_path, "video/mp4"),
        "quality": {
            "stabilizedRmsPx": estimate.stabilized_rms_px,
            "medianResidualPx": estimate.median_residual_px,
            "p95ResidualPx": estimate.p95_residual_px,
            "meanInlierRatio": estimate.mean_inlier_ratio,
            "validFrameFraction": estimate.valid_frame_fraction,
            "staticPixelFraction": estimate.static_pixel_fraction,
            "parallaxEvidenceFrames": estimate.parallax_evidence_frames,
        },
    }
    if estimate.routing_reason is not None:
        manifest["routingReason"] = estimate.routing_reason
    progress(1.0, "Camera motion estimated and stabilized preview encoded.")
    return CameraMotionResult(motions, manifest, estimate, preview_path)


def decode_frames(path: Path, check_canceled: CancelCheck) -> tuple[tuple[Image, ...], Fraction]:
    """Decode the normalized lossless analysis copy as BGR images."""
    images: list[Image] = []
    with av.open(str(path)) as container:
        if not container.streams.video:
            raise CameraMotionError("The analysis copy contains no video stream.")
        stream = container.streams.video[0]
        raw_rate = stream.average_rate or stream.guessed_rate or Fraction(30, 1)
        rate = Fraction(int(raw_rate.numerator), int(raw_rate.denominator))
        for frame in container.decode(stream):
            check_canceled()
            images.append(cast(Image, frame.to_ndarray(format="bgr24")))
    if len(images) < 2:  # noqa: PLR2004 - motion needs two frames
        raise CameraMotionError("Camera motion needs at least two decoded frames.")
    return tuple(images), rate


def estimate_camera_motion(
    frames: Sequence[Image],
    *,
    config: CameraMotionConfig = CameraMotionConfig(),
    check_canceled: CancelCheck = lambda: None,
) -> MotionEstimate:
    """Estimate reference-to-frame homographies from Farneback-masked static ORB features."""
    _validate_frames(frames)
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    grays = tuple(cast(Image, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)) for frame in frames)
    masks = _farneback_static_masks(grays, check_canceled)
    scale = min(3.0, max(1.0, 180.0 / min(grays[0].shape)))
    scaled_grays = tuple(_scaled(gray, scale, cv2.INTER_LINEAR) for gray in grays)
    scaled_masks = tuple(_scaled(mask, scale, cv2.INTER_NEAREST) for mask in masks)
    reference = scaled_grays[0]
    reference_mask = scaled_masks[0]
    identity = np.eye(3, dtype=np.float64)
    motions: list[FrameMotion] = [FrameMotion(0, identity, (0.0,), 1.0, 0, False)]
    valid = 1
    for index in range(1, len(frames)):
        check_canceled()
        source, target = _correspondences(
            reference,
            scaled_grays[index],
            reference_mask,
            scaled_masks[index],
            config.min_matches,
        )
        matrix_scaled, inliers = _magsac(
            source,
            target,
            threshold=config.ransac_threshold_px * scale,
            min_matches=config.min_matches,
        )
        if matrix_scaled is None:
            raise CameraMotionError(
                f"Frame {index} has too few consistent static features for camera stabilization. "
                "Record a steadier clip with more visible background texture."
            )
        valid += 1
        matrix = _unscale_homography(matrix_scaled, scale)
        residuals_scaled = _residuals(matrix_scaled, source, target)
        residuals = residuals_scaled / scale
        inlier_ratio = float(np.mean(inliers)) if len(inliers) else 0.0
        parallax = _has_parallax(
            source,
            target,
            matrix_scaled,
            residuals_scaled,
            threshold=config.parallax_threshold_px * scale,
            min_matches=config.min_matches,
            shape=reference.shape,
        )
        motions.append(
            FrameMotion(
                index,
                matrix,
                tuple(float(value) for value in residuals),
                inlier_ratio,
                len(source),
                parallax,
            )
        )
    all_residuals = [value for frame in motions[1:] for value in frame.residuals_px]
    inlier_residuals = [
        value
        for frame in motions[1:]
        for value in frame.residuals_px
        if value <= config.ransac_threshold_px
    ]
    evidence = sum(frame.parallax_evidence for frame in motions)
    required_evidence = max(2, math.ceil((len(motions) - 1) * 0.35))
    requires_spatial = evidence >= required_evidence
    reason = (
        f"Static-scene residuals support multiple coherent planes in {evidence} of "
        f"{len(motions) - 1} compared frames; planar stabilization is unsafe."
        if requires_spatial
        else None
    )
    return MotionEstimate(
        tuple(motions),
        masks,
        math.sqrt(float(np.mean(np.square(inlier_residuals)))) if inlier_residuals else 0.0,
        float(np.median(all_residuals)) if all_residuals else 0.0,
        float(np.percentile(all_residuals, 95)) if all_residuals else 0.0,
        statistics.fmean(frame.inlier_ratio for frame in motions),
        valid / len(motions),
        statistics.fmean(float(np.mean(mask > 0)) for mask in masks),
        evidence,
        requires_spatial,
        reason,
    )


def refine_with_ground_tracks(
    reference_points: Points,
    points_by_frame: Mapping[int, Points],
    *,
    config: CameraMotionConfig = CameraMotionConfig(),
) -> dict[int, Matrix]:
    """Ground-relative refinement hook for the body-grouping stage.

    The caller supplies the same ground-body track IDs in reference and frame order. No grouping
    assumptions live in camera motion, so the later grouping stage can call this deterministically.
    """
    refined: dict[int, Matrix] = {0: np.eye(3, dtype=np.float64)}
    for frame_index in sorted(points_by_frame):
        target = points_by_frame[frame_index]
        matrix, _ = _magsac(
            reference_points,
            target,
            threshold=config.ransac_threshold_px,
            min_matches=config.min_matches,
        )
        if matrix is None:
            raise CameraMotionError(
                "Ground-track refinement has too few robust correspondences in "
                f"frame {frame_index}."
            )
        refined[frame_index] = matrix
    return refined


def encode_stabilized_preview(
    frames: Sequence[Image],
    motions: Sequence[FrameMotion],
    path: Path,
    rate: Fraction,
    check_canceled: CancelCheck,
) -> None:
    """Warp every real frame to the reference view and encode deterministic H.264."""
    height, width = frames[0].shape[:2]
    with av.open(str(path), "w", format="mp4") as output:
        stream = output.add_stream("libx264", rate=rate)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.time_base = 1 / rate
        stream.options = {
            "bf": "0",
            "crf": "20",
            "g": "6",
            "preset": "medium",
            "threads": "1",
            "tune": "zerolatency",
        }
        for index, (image, motion) in enumerate(zip(frames, motions, strict=True)):
            check_canceled()
            stabilized = cast(
                Image,
                cv2.warpPerspective(
                    image,
                    motion.reference_to_frame,
                    (width, height),
                    flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                    borderMode=cv2.BORDER_CONSTANT,
                ),
            )
            frame = av.VideoFrame.from_ndarray(stabilized, format="bgr24")
            frame.pts = index
            frame.time_base = stream.time_base
            output.mux(stream.encode(frame))
        output.mux(stream.encode())


def _farneback_static_masks(
    grays: Sequence[Image], check_canceled: CancelCheck
) -> tuple[Image, ...]:
    magnitudes: list[list[npt.NDArray[np.float32]]] = [[] for _ in grays]
    for index in range(1, len(grays)):
        check_canceled()
        flow = cv2.calcOpticalFlowFarneback(
            grays[index - 1], grays[index], None, 0.5, 4, 21, 4, 7, 1.5, 0
        )
        magnitude = np.hypot(flow[..., 0], flow[..., 1]).astype(np.float32)
        magnitudes[index - 1].append(magnitude)
        magnitudes[index].append(magnitude)
    masks: list[Image] = []
    kernel = np.ones((3, 3), dtype=np.uint8)
    for samples in magnitudes:
        score = np.median(np.stack(samples), axis=0)
        finite = score[np.isfinite(score)]
        threshold = max(1.0, float(np.percentile(finite, 72)))
        mask = np.where(score <= threshold, 255, 0).astype(np.uint8)
        mask = cast(Image, cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel))
        mask = cast(Image, cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel))
        if float(np.mean(mask > 0)) < MIN_STATIC_FRACTION:
            mask.fill(255)
        masks.append(mask)
    return tuple(masks)


def _correspondences(
    reference: Image,
    current: Image,
    reference_mask: Image,
    current_mask: Image,
    minimum: int,
) -> tuple[Points, Points]:
    orb = cv2.ORB.create(
        nfeatures=3000, scaleFactor=1.2, nlevels=8, edgeThreshold=5, patchSize=15, fastThreshold=5
    )
    first, descriptors_first = orb.detectAndCompute(reference, reference_mask)
    second, descriptors_second = orb.detectAndCompute(current, current_mask)
    source: list[tuple[float, float]] = []
    target: list[tuple[float, float]] = []
    if descriptors_first is not None and descriptors_second is not None:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        for pair in matcher.knnMatch(descriptors_first, descriptors_second, k=2):
            if len(pair) == MATCH_PAIR_SIZE and pair[0].distance < 0.78 * pair[1].distance:
                first_point = first[pair[0].queryIdx].pt
                second_point = second[pair[0].trainIdx].pt
                source.append((float(first_point[0]), float(first_point[1])))
                target.append((float(second_point[0]), float(second_point[1])))
    if len(source) >= minimum:
        return np.asarray(source, dtype=np.float32), np.asarray(target, dtype=np.float32)
    corners = cv2.goodFeaturesToTrack(
        reference, maxCorners=1500, qualityLevel=0.003, minDistance=3, mask=reference_mask
    )
    if corners is None:
        return _empty_points(), _empty_points()
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(
        reference,
        current,
        corners,
        None,
        winSize=(31, 31),
        maxLevel=4,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if tracked is None or status is None:
        return _empty_points(), _empty_points()
    original = corners.reshape(-1, 2)
    moved = tracked.reshape(-1, 2)
    valid = status.reshape(-1).astype(bool)
    rows = np.clip(np.rint(moved[:, 1]).astype(int), 0, current.shape[0] - 1)
    columns = np.clip(np.rint(moved[:, 0]).astype(int), 0, current.shape[1] - 1)
    valid &= current_mask[rows, columns] > 0
    return original[valid].astype(np.float32), moved[valid].astype(np.float32)


def _magsac(
    source: Points, target: Points, *, threshold: float, min_matches: int
) -> tuple[Matrix | None, npt.NDArray[np.bool_]]:
    if len(source) < max(4, min_matches):
        return None, np.zeros(len(source), dtype=bool)
    matrix, raw_mask = cv2.findHomography(
        source,
        target,
        method=cv2.USAC_MAGSAC,
        ransacReprojThreshold=threshold,
        maxIters=10_000,
        confidence=0.999,
    )
    if matrix is None or raw_mask is None or not np.all(np.isfinite(matrix)):
        return None, np.zeros(len(source), dtype=bool)
    normalized = np.asarray(matrix, dtype=np.float64)
    normalized /= normalized[2, 2]
    return normalized, raw_mask.reshape(-1).astype(bool)


def _has_parallax(
    source: Points,
    target: Points,
    primary: Matrix,
    residuals: npt.NDArray[np.float64],
    *,
    threshold: float,
    min_matches: int,
    shape: tuple[int, int],
) -> bool:
    high = residuals > threshold
    if int(np.sum(high)) < max(min_matches, math.ceil(len(source) * 0.18)):
        return False
    second, inliers = _magsac(
        source[high], target[high], threshold=threshold * 0.75, min_matches=min_matches
    )
    if second is None or float(np.mean(inliers)) < SECOND_PLANE_INLIER_RATIO:
        return False
    height, width = shape
    probes = np.asarray(
        [[0, 0], [width - 1, 0], [0, height - 1], [width - 1, height - 1], [width / 2, height / 2]],
        dtype=np.float32,
    )
    separation = _residuals(primary, probes, _project(second, probes))
    return float(np.median(separation)) > threshold


def _residuals(matrix: Matrix, source: Points, target: Points) -> npt.NDArray[np.float64]:
    return np.linalg.norm(_project(matrix, source) - target, axis=1).astype(np.float64)


def _project(matrix: Matrix, points: Points) -> Points:
    transformed = cv2.perspectiveTransform(points.reshape(1, -1, 2), matrix)
    return cast(Points, transformed.reshape(-1, 2))


def _unscale_homography(matrix: Matrix, scale: float) -> Matrix:
    scaling = np.diag([scale, scale, 1.0])
    result = np.linalg.inv(scaling) @ matrix @ scaling
    return result / result[2, 2]


def _scaled(image: Image, scale: float, interpolation: int) -> Image:
    if scale == 1.0:
        return image
    return cast(Image, cv2.resize(image, None, fx=scale, fy=scale, interpolation=interpolation))


def _validate_frames(frames: Sequence[Image]) -> None:
    if len(frames) < 2:  # noqa: PLR2004
        raise ValueError("camera motion requires at least two frames")
    shape = frames[0].shape
    if len(shape) != 3 or shape[2] != 3:  # noqa: PLR2004
        raise ValueError("camera-motion frames must be BGR images")
    if any(frame.shape != shape or frame.dtype != np.uint8 for frame in frames):
        raise ValueError("camera-motion frames must share one uint8 shape")


def _empty_points() -> Points:
    return np.empty((0, 2), dtype=np.float32)


def _embedded(path: Path, media_type: str) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "filename": path.name,
        "mediaType": media_type,
        "encoding": "base64",
        "byteSize": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "data": base64.b64encode(content).decode("ascii"),
    }

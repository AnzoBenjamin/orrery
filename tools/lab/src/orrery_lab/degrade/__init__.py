"""Deterministic camera, temporal, sensor, and video encoding degradation."""

from orrery_lab.degrade.camera import (
    CameraDegradeConfig,
    CameraDegradeMetadata,
    CameraDegradeResult,
    CameraFourierTerm,
    CameraSampleMetadata,
    degrade_camera,
)
from orrery_lab.degrade.encoding import encode_video
from orrery_lab.degrade.encoding_profile import select_codec_profile
from orrery_lab.degrade.encoding_types import (
    CodecName,
    CodecProfile,
    ContainerName,
    EncodingConfig,
    EncodingError,
    EncodingMetadata,
    EncodingResult,
    EncodingTimingMetadata,
    PixelFormat,
    ProbeMetadata,
)
from orrery_lab.degrade.ffmpeg import FFmpegAdapter
from orrery_lab.degrade.sensor import (
    ExposureFourierTerm,
    SensorDegradeConfig,
    SensorDegradeMetadata,
    SensorDegradeResult,
    SensorFrameMetadata,
    degrade_sensor,
)
from orrery_lab.degrade.temporal import (
    TemporalDegradeConfig,
    TemporalDegradeMetadata,
    TemporalDegradeResult,
    degrade_temporal,
)

__all__ = [
    "CameraDegradeConfig",
    "CameraDegradeMetadata",
    "CameraDegradeResult",
    "CameraFourierTerm",
    "CameraSampleMetadata",
    "CodecName",
    "CodecProfile",
    "ContainerName",
    "EncodingConfig",
    "EncodingError",
    "EncodingMetadata",
    "EncodingResult",
    "EncodingTimingMetadata",
    "ExposureFourierTerm",
    "FFmpegAdapter",
    "PixelFormat",
    "ProbeMetadata",
    "SensorDegradeConfig",
    "SensorDegradeMetadata",
    "SensorDegradeResult",
    "SensorFrameMetadata",
    "TemporalDegradeConfig",
    "TemporalDegradeMetadata",
    "TemporalDegradeResult",
    "degrade_camera",
    "degrade_sensor",
    "degrade_temporal",
    "encode_video",
    "select_codec_profile",
]

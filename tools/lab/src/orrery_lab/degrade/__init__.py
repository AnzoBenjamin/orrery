"""Deterministic linear-light camera, temporal, and sensor degradation."""

from orrery_lab.degrade.camera import (
    CameraDegradeConfig,
    CameraDegradeMetadata,
    CameraDegradeResult,
    CameraFourierTerm,
    CameraSampleMetadata,
    degrade_camera,
)
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
    "ExposureFourierTerm",
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
]

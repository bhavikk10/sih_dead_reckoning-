"""Deterministic quality checks for cleaned vehicle-frame IMU data.

This module reports observable timing, plausibility, and calibration problems.
It does not estimate velocity uncertainty or covariance; downstream uncertainty
and fusion components consume these explicit quality facts and apply their own
policies.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, sqrt

from .types import SensorSource, Vector3, VehicleImuSample


class QualityFlag(StrEnum):
    """Observable reasons why one cleaned IMU sample may be unsafe to use."""

    NONFINITE_LINEAR_ACCELERATION = "nonfinite_linear_acceleration"
    NONFINITE_ANGULAR_VELOCITY = "nonfinite_angular_velocity"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    SENSOR_GAP = "sensor_gap"
    LINEAR_ACCELERATION_LIMIT_EXCEEDED = (
        "linear_acceleration_limit_exceeded"
    )
    ANGULAR_VELOCITY_LIMIT_EXCEEDED = (
        "angular_velocity_limit_exceeded"
    )
    CALIBRATION_CONFIDENCE_INVALID = "calibration_confidence_invalid"
    CALIBRATION_CONFIDENCE_LOW = "calibration_confidence_low"


@dataclass(frozen=True, slots=True)
class VehicleImuQuality:
    """Quality facts associated with one cleaned vehicle-frame IMU sample."""

    timestamp_ns: int
    source: SensorSource
    source_id: str

    flags: frozenset[QualityFlag]
    sample_interval_ns: int | None

    # Transparent deterministic summary: zero for hard failures; otherwise
    # derived from calibration confidence. It is not an uncertainty variance.
    score: float

    # True only when no configured deterministic gate has failed.
    is_acceptable: bool


@dataclass(frozen=True, slots=True)
class VehicleImuQualityLimits:
    """Configured physical and timing boundaries for one IMU source."""

    max_gap_ns: int
    max_linear_acceleration_mps2: float
    max_angular_velocity_radps: float
    minimum_calibration_confidence: float


def _vector_is_finite(vector: Vector3) -> bool:
    """Return whether every component of a vector is finite."""

    return all(isfinite(component) for component in vector)


def _vector_magnitude(vector: Vector3) -> float:
    """Return the Euclidean magnitude of a finite vector."""

    if not _vector_is_finite(vector):
        raise ValueError("Vector components must all be finite.")

    x, y, z = vector
    return sqrt(x * x + y * y + z * z)


def _quality_score(
    flags: frozenset[QualityFlag],
    calibration_confidence: float,
) -> float:
    """Return a transparent deterministic score from flags and confidence."""

    hard_failure_flags = {
        QualityFlag.NONFINITE_LINEAR_ACCELERATION,
        QualityFlag.NONFINITE_ANGULAR_VELOCITY,
        QualityFlag.TIMESTAMP_REGRESSION,
        QualityFlag.SENSOR_GAP,
        QualityFlag.LINEAR_ACCELERATION_LIMIT_EXCEEDED,
        QualityFlag.ANGULAR_VELOCITY_LIMIT_EXCEEDED,
        QualityFlag.CALIBRATION_CONFIDENCE_INVALID,
    }

    if flags & hard_failure_flags:
        return 0.0

    return calibration_confidence


class VehicleImuQualityMonitor:
    """Assess one chronological stream of cleaned vehicle-frame IMU samples."""

    def __init__(
        self,
        limits: VehicleImuQualityLimits,
    ) -> None:
        """Create a monitor with explicit device-specific limits."""

        if limits.max_gap_ns <= 0:
            raise ValueError("max_gap_ns must be positive.")

        if (
            not isfinite(limits.max_linear_acceleration_mps2)
            or limits.max_linear_acceleration_mps2 <= 0.0
        ):
            raise ValueError(
                "max_linear_acceleration_mps2 must be finite and positive."
            )

        if (
            not isfinite(limits.max_angular_velocity_radps)
            or limits.max_angular_velocity_radps <= 0.0
        ):
            raise ValueError(
                "max_angular_velocity_radps must be finite and positive."
            )

        if (
            not isfinite(limits.minimum_calibration_confidence)
            or not 0.0 <= limits.minimum_calibration_confidence <= 1.0
        ):
            raise ValueError(
                "minimum_calibration_confidence must be between 0.0 and 1.0."
            )

        self._limits = limits
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None


    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind the monitor to one device and reject accidental stream mixing."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one "
                "VehicleImuQualityMonitor."
            )

    def assess(
        self,
        sample: VehicleImuSample,
    ) -> VehicleImuQuality:
        """Assess one cleaned vehicle-frame sample without altering its values."""

        self._register_or_validate_stream(sample)

        flags: set[QualityFlag] = set()
        sample_interval_ns: int | None = None

        if not _vector_is_finite(sample.linear_acceleration_mps2):
            flags.add(QualityFlag.NONFINITE_LINEAR_ACCELERATION)
        elif (
            _vector_magnitude(sample.linear_acceleration_mps2)
            > self._limits.max_linear_acceleration_mps2
        ):
            flags.add(QualityFlag.LINEAR_ACCELERATION_LIMIT_EXCEEDED)

        if not _vector_is_finite(sample.angular_velocity_radps):
            flags.add(QualityFlag.NONFINITE_ANGULAR_VELOCITY)
        elif (
            _vector_magnitude(sample.angular_velocity_radps)
            > self._limits.max_angular_velocity_radps
        ):
            flags.add(QualityFlag.ANGULAR_VELOCITY_LIMIT_EXCEEDED)

        if self._last_timestamp_ns is not None:
            if sample.timestamp_ns <= self._last_timestamp_ns:
                flags.add(QualityFlag.TIMESTAMP_REGRESSION)
            else:
                sample_interval_ns = (
                    sample.timestamp_ns - self._last_timestamp_ns
                )
                if sample_interval_ns > self._limits.max_gap_ns:
                    flags.add(QualityFlag.SENSOR_GAP)

        # Do not move the reference time backward after an invalid timestamp.
        if (
            self._last_timestamp_ns is None
            or sample.timestamp_ns > self._last_timestamp_ns
        ):
            self._last_timestamp_ns = sample.timestamp_ns

        calibration_confidence = sample.calibration_confidence
        if (
            not isfinite(calibration_confidence)
            or not 0.0 <= calibration_confidence <= 1.0
        ):
            flags.add(QualityFlag.CALIBRATION_CONFIDENCE_INVALID)
            calibration_confidence = 0.0
        elif (
            calibration_confidence
            < self._limits.minimum_calibration_confidence
        ):
            flags.add(QualityFlag.CALIBRATION_CONFIDENCE_LOW)

        frozen_flags = frozenset(flags)

        return VehicleImuQuality(
            timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            flags=frozen_flags,
            sample_interval_ns=sample_interval_ns,
            score=_quality_score(
                frozen_flags,
                calibration_confidence,
            ),
            is_acceptable=not frozen_flags,
        )


    def reset(self) -> None:
        """Forget timing and source state after a confirmed session restart."""

        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
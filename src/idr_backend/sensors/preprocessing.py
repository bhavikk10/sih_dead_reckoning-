"""Causal deterministic IMU preprocessing pipeline.

One preprocessor instance owns one chronological IMU stream and its associated
GNSS receiver stream. It publishes a clean vehicle-frame IMU sample only when
mounting calibration and deterministic quality checks permit it.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .calibration import (
    CalibrationPhase,
    DynamicVehicleCalibrator,
    rotate_imu_to_vehicle,
)
from .calibration_evidence import (
    CalibrationEvidenceLimits,
    build_calibration_evidence,
)
from .gnss import (
    GnssFixQuality,
    GnssQualityFlag,
    GnssQualityLimits,
    GnssQualityMonitor,
)
from .gravity_removal import remove_gravity_from_vehicle_imu
from .normalization import normalize_raw_sample
from .orientation import ImuOrientationEstimator
from .quality import (
    VehicleImuQuality,
    VehicleImuQualityLimits,
    VehicleImuQualityMonitor,
)
from .synchronization import ImuSynchronizer
from .types import (
    GnssFix,
    OrientationEstimate,
    RawSensorSample,
    SynchronizedImuSample,
    VehicleCalibration,
    VehicleImuSample,
)


@dataclass(frozen=True, slots=True)
class DeterministicPreprocessorConfig:
    """Configuration for one phone/external-IMU preprocessing stream."""

    # Accel/gyro synchronization.
    max_imu_skew_ns: int
    max_pending_imu_samples: int

    # Orientation filter.
    accelerometer_correction_gain_per_s: float
    acceleration_trust_tolerance_mps2: float

    # Dynamic mounting calibration.
    minimum_calibration_evidence_count: int
    minimum_calibration_evidence_confidence: float
    maximum_calibration_disagreement_rad: float
    remount_evidence_count: int
    minimum_calibration_confidence_for_output: float

    # Nested configuration owned by their respective modules.
    gnss_quality_limits: GnssQualityLimits
    calibration_evidence_limits: CalibrationEvidenceLimits
    vehicle_imu_quality_limits: VehicleImuQualityLimits


class PreprocessingDisposition(StrEnum):
    """Why a synchronized IMU sample was or was not published to the model."""

    ACCEPTED = "accepted"

    # No stable phone-to-vehicle rotation is available yet.
    CALIBRATION_WARMING_UP = "calibration_warming_up"

    # A calibration exists but is too weak, degraded, or being recalibrated.
    CALIBRATION_UNTRUSTED = "calibration_untrusted"

    # A clean vehicle-frame sample existed but failed deterministic checks.
    QUALITY_REJECTED = "quality_rejected"


@dataclass(frozen=True, slots=True)
class PreprocessedImuResult:
    """One deterministic preprocessing decision for a synchronized IMU sample."""

    timestamp_ns: int
    source_id: str

    # Orientation is available immediately after synchronized IMU processing.
    orientation: OrientationEstimate

    # May be None while calibration is still warming up.
    calibration: VehicleCalibration | None
    calibration_phase: CalibrationPhase

    # Present only when a vehicle-frame sample could be produced.
    vehicle_imu_sample: VehicleImuSample | None
    quality: VehicleImuQuality | None

    disposition: PreprocessingDisposition


class DeterministicImuPreprocessor:
    """Process one causal IMU stream and its nearby GNSS observations."""

    def __init__(self, config: DeterministicPreprocessorConfig) -> None:
        """Create stateful components for one physical IMU session."""

        if (
            not isfinite(
                config.minimum_calibration_confidence_for_output
            )
            or not 0.0
            <= config.minimum_calibration_confidence_for_output
            <= 1.0
        ):
            raise ValueError(
                "minimum_calibration_confidence_for_output must be "
                "between 0.0 and 1.0."
            )

        self._config = config

        self._synchronizer = ImuSynchronizer(
            max_skew_ns=config.max_imu_skew_ns,
            max_pending_samples=config.max_pending_imu_samples,
        )

        self._orientation_estimator = ImuOrientationEstimator(
            accelerometer_correction_gain_per_s=(
                config.accelerometer_correction_gain_per_s
            ),
            acceleration_trust_tolerance_mps2=(
                config.acceleration_trust_tolerance_mps2
            ),
            expected_gravity_mps2=(
                config.calibration_evidence_limits.gravity_mps2
            ),
        )

        self._calibrator = DynamicVehicleCalibrator(
            minimum_evidence_count=(
                config.minimum_calibration_evidence_count
            ),
            minimum_evidence_confidence=(
                config.minimum_calibration_evidence_confidence
            ),
            maximum_disagreement_rad=(
                config.maximum_calibration_disagreement_rad
            ),
            remount_evidence_count=config.remount_evidence_count,
        )

        self._gnss_quality_monitor = GnssQualityMonitor(
            config.gnss_quality_limits
        )

        self._vehicle_imu_quality_monitor = VehicleImuQualityMonitor(
            config.vehicle_imu_quality_limits
        )

        self._previous_gnss_fix: GnssFix | None = None
        self._previous_gnss_quality: GnssFixQuality | None = None
        self._current_gnss_fix: GnssFix | None = None
        self._current_gnss_quality: GnssFixQuality | None = None

        # One GNSS interval should create at most one calibration observation.
        self._pending_gnss_interval = False


    def push_gnss_fix(self, fix: GnssFix) -> GnssFixQuality:
        """Assess and retain one chronological GNSS observation."""

        quality = self._gnss_quality_monitor.assess(fix)

        # Invalid/backward timestamps must not overwrite our usable GNSS cache.
        if quality.flags & {
            GnssQualityFlag.TIMESTAMP_INVALID,
            GnssQualityFlag.TIMESTAMP_REGRESSION,
        }:
            return quality

        if self._current_gnss_fix is None:
            self._current_gnss_fix = fix
            self._current_gnss_quality = quality
            return quality

        self._previous_gnss_fix = self._current_gnss_fix
        self._previous_gnss_quality = self._current_gnss_quality

        self._current_gnss_fix = fix
        self._current_gnss_quality = quality
        self._pending_gnss_interval = True

        return quality


    def push_raw_sample(
        self,
        raw_sample: RawSensorSample,
    ) -> tuple[PreprocessedImuResult, ...]:
        """Process one raw accel or gyro callback causally."""

        normalized_sample = normalize_raw_sample(raw_sample)

        synchronized_samples = self._synchronizer.push(
            normalized_sample
        )

        return tuple(
            self._process_synchronized_sample(sample)
            for sample in synchronized_samples
        )


    def _process_synchronized_sample(
        self,
        synchronized_sample: SynchronizedImuSample,
    ) -> PreprocessedImuResult:
        """Run deterministic stages after accel/gyro synchronization."""

        orientation = self._orientation_estimator.update(
            synchronized_sample
        )

        self._maybe_update_calibration(
            synchronized_sample=synchronized_sample,
            orientation=orientation,
        )

        calibration = self._calibrator.calibration

        if calibration is None:
            return PreprocessedImuResult(
                timestamp_ns=synchronized_sample.timestamp_ns,
                source_id=synchronized_sample.source_id,
                orientation=orientation,
                calibration=None,
                calibration_phase=self._calibrator.phase,
                vehicle_imu_sample=None,
                quality=None,
                disposition=(
                    PreprocessingDisposition.CALIBRATION_WARMING_UP
                ),
            )

        if (
            calibration.confidence
            < self._config.minimum_calibration_confidence_for_output
        ):
            return PreprocessedImuResult(
                timestamp_ns=synchronized_sample.timestamp_ns,
                source_id=synchronized_sample.source_id,
                orientation=orientation,
                calibration=calibration,
                calibration_phase=self._calibrator.phase,
                vehicle_imu_sample=None,
                quality=None,
                disposition=(
                    PreprocessingDisposition.CALIBRATION_UNTRUSTED
                ),
            )

        vehicle_frame_sample = rotate_imu_to_vehicle(
            sample=synchronized_sample,
            calibration=calibration,
            minimum_confidence=(
                self._config.minimum_calibration_confidence_for_output
            ),
        )

        vehicle_imu_sample = remove_gravity_from_vehicle_imu(
            vehicle_sample=vehicle_frame_sample,
            orientation=orientation,
            calibration=calibration,
            gravity_mps2=(
                self._config.calibration_evidence_limits.gravity_mps2
            ),
        )

        quality = self._vehicle_imu_quality_monitor.assess(
            vehicle_imu_sample
        )

        return PreprocessedImuResult(
            timestamp_ns=synchronized_sample.timestamp_ns,
            source_id=synchronized_sample.source_id,
            orientation=orientation,
            calibration=calibration,
            calibration_phase=self._calibrator.phase,
            vehicle_imu_sample=vehicle_imu_sample,
            quality=quality,
            disposition=(
                PreprocessingDisposition.ACCEPTED
                if quality.is_acceptable
                else PreprocessingDisposition.QUALITY_REJECTED
            ),
        )


    def _maybe_update_calibration(
        self,
        *,
        synchronized_sample: SynchronizedImuSample,
        orientation: OrientationEstimate,
    ) -> None:
        """Use a fresh GNSS interval once, at the first causal IMU opportunity."""

        if not self._pending_gnss_interval:
            return

        if (
            self._previous_gnss_fix is None
            or self._previous_gnss_quality is None
            or self._current_gnss_fix is None
            or self._current_gnss_quality is None
        ):
            return

        # Do not use an IMU reading from before the newer GNSS fix.
        if (
            synchronized_sample.timestamp_ns
            < self._current_gnss_fix.timestamp_ns
        ):
            return

        # Consume it now. Later IMU samples are farther from this GNSS interval,
        # so they must not repeatedly reuse the same evidence.
        self._pending_gnss_interval = False

        evidence = build_calibration_evidence(
            imu_sample=synchronized_sample,
            orientation=orientation,
            previous_gnss_fix=self._previous_gnss_fix,
            previous_gnss_quality=self._previous_gnss_quality,
            current_gnss_fix=self._current_gnss_fix,
            current_gnss_quality=self._current_gnss_quality,
            limits=self._config.calibration_evidence_limits,
        )

        if evidence is not None:
            self._calibrator.update(evidence)

"""Causal deterministic IMU preprocessing pipeline.

One preprocessor instance owns one chronological IMU stream and its associated
GNSS receiver stream. It publishes a clean vehicle-frame IMU sample only when
mounting calibration and deterministic quality checks permit it.
"""

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .calibration import (
    CalibrationEvidence,
    CalibrationPhase,
    DynamicVehicleCalibrator,
    rotate_imu_to_vehicle,
)
from .calibration_evidence import (
    CalibrationHistorySample,
    CalibrationEvidenceLimits,
    build_calibration_evidence,
    build_rolling_calibration_evidence,
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
from .resampling import FixedRateVehicleImuResampler
from .synchronization import ImuSynchronizer
from .types import (
    GnssFix,
    OrientationEstimate,
    RawSensorSample,
    SynchronizedImuSample,
    VehicleCalibration,
    VehicleImuSample,
)
from .windowing import CausalVehicleImuWindowBuilder, VelocityModelInputWindow


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

    # Fixed-rate model input. A discontinuity clears both stages so no model
    # window can bridge low-quality or uncalibrated data.
    velocity_model_sample_period_ns: int
    velocity_model_window_size: int

    # Nested configuration owned by their respective modules.
    gnss_quality_limits: GnssQualityLimits
    calibration_evidence_limits: CalibrationEvidenceLimits
    vehicle_imu_quality_limits: VehicleImuQualityLimits

    # A securely mounted device does not lose its physical mounting merely
    # because a later rolling estimate is temporarily inconclusive. Retain a
    # trusted rotation briefly while a possible remount is checked, but publish
    # it at only the configured acceptance boundary for conservative downstream
    # quality and uncertainty handling.
    maximum_held_calibration_age_ns: int = 300_000_000_000


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

    # A raw IMU callback can generate several fixed-rate samples, each of
    # which may finish a causal model window. Empty means not model-ready.
    velocity_windows: tuple[VelocityModelInputWindow, ...]

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
        if config.maximum_held_calibration_age_ns <= 0:
            raise ValueError("maximum_held_calibration_age_ns must be positive.")

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

        self._velocity_resampler = FixedRateVehicleImuResampler(
            config.velocity_model_sample_period_ns
        )
        self._velocity_window_builder = CausalVehicleImuWindowBuilder(
            window_size=config.velocity_model_window_size,
            sample_period_ns=config.velocity_model_sample_period_ns,
        )

        self._previous_gnss_fix: GnssFix | None = None
        self._previous_gnss_quality: GnssFixQuality | None = None
        self._current_gnss_fix: GnssFix | None = None
        self._current_gnss_quality: GnssFixQuality | None = None

        # One GNSS interval should create at most one calibration observation.
        self._pending_gnss_interval = False
        # The rolling path keeps only synchronized IMU plus already-observed,
        # still-fresh GNSS speed. It is deliberately separate from model
        # windowing and is pruned by elapsed time, not callback count.
        self._rolling_calibration_history: deque[CalibrationHistorySample] = deque()
        self._last_rolling_calibration_attempt_timestamp_ns: int | None = None
        self._last_rolling_calibration_gnss_timestamp_ns: int | None = None
        self._last_trusted_calibration: VehicleCalibration | None = None


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

        self._append_rolling_calibration_history(synchronized_sample)

        self._maybe_update_calibration(
            synchronized_sample=synchronized_sample,
            orientation=orientation,
        )

        calibration = self._effective_calibration(synchronized_sample.timestamp_ns)

        if calibration is None:
            self._reset_velocity_windowing()
            return PreprocessedImuResult(
                timestamp_ns=synchronized_sample.timestamp_ns,
                source_id=synchronized_sample.source_id,
                orientation=orientation,
                calibration=None,
                calibration_phase=self._calibrator.phase,
                vehicle_imu_sample=None,
                quality=None,
                velocity_windows=(),
                disposition=(
                    PreprocessingDisposition.CALIBRATION_WARMING_UP
                ),
            )

        if (
            calibration.confidence
            < self._config.minimum_calibration_confidence_for_output
        ):
            self._reset_velocity_windowing()
            return PreprocessedImuResult(
                timestamp_ns=synchronized_sample.timestamp_ns,
                source_id=synchronized_sample.source_id,
                orientation=orientation,
                calibration=calibration,
                calibration_phase=self._calibrator.phase,
                vehicle_imu_sample=None,
                quality=None,
                velocity_windows=(),
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

        velocity_windows = self._velocity_windows_from_accepted_sample(
            vehicle_imu_sample,
            quality,
        )

        return PreprocessedImuResult(
            timestamp_ns=synchronized_sample.timestamp_ns,
            source_id=synchronized_sample.source_id,
            orientation=orientation,
            calibration=calibration,
            calibration_phase=self._calibrator.phase,
            vehicle_imu_sample=vehicle_imu_sample,
            quality=quality,
            velocity_windows=velocity_windows,
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

        quick_evidence = self._consume_single_interval_calibration_evidence(
            synchronized_sample=synchronized_sample,
            orientation=orientation,
        )
        if quick_evidence is not None:
            self._calibrator.update(quick_evidence)
            self._remember_trusted_calibration()
            return
        self._maybe_update_rolling_calibration()

    def _consume_single_interval_calibration_evidence(
        self,
        *,
        synchronized_sample: SynchronizedImuSample,
        orientation: OrientationEstimate,
    ) -> CalibrationEvidence | None:
        """Consume one due GNSS interval and return its direct evidence, if any."""

        if not self._pending_gnss_interval:
            return None
        if (
            self._previous_gnss_fix is None
            or self._previous_gnss_quality is None
            or self._current_gnss_fix is None
            or self._current_gnss_quality is None
            or synchronized_sample.timestamp_ns < self._current_gnss_fix.timestamp_ns
        ):
            return None

        # One interval is consumed once even when it is weak. The rolling path
        # below can still accumulate longer-term evidence without reusing it.
        self._pending_gnss_interval = False
        return build_calibration_evidence(
            imu_sample=synchronized_sample,
            orientation=orientation,
            previous_gnss_fix=self._previous_gnss_fix,
            previous_gnss_quality=self._previous_gnss_quality,
            current_gnss_fix=self._current_gnss_fix,
            current_gnss_quality=self._current_gnss_quality,
            limits=self._config.calibration_evidence_limits,
        )

    def _append_rolling_calibration_history(
        self,
        synchronized_sample: SynchronizedImuSample,
    ) -> None:
        """Retain only fresh GNSS-anchored sensor history for robust calibration."""

        fix = self._current_gnss_fix
        quality = self._current_gnss_quality
        if (
            fix is None
            or quality is None
            or not quality.speed_is_acceptable
            or fix.speed_mps is None
        ):
            return
        self._rolling_calibration_history.append(
            CalibrationHistorySample(
                timestamp_ns=synchronized_sample.timestamp_ns,
                source=synchronized_sample.source,
                source_id=synchronized_sample.source_id,
                acceleration_mps2=synchronized_sample.acceleration_mps2,
                angular_velocity_radps=synchronized_sample.angular_velocity_radps,
                gnss_speed_mps=fix.speed_mps,
            )
        )
        history_start_ns = (
            synchronized_sample.timestamp_ns
            - self._config.calibration_evidence_limits.rolling_history_ns
        )
        while (
            self._rolling_calibration_history
            and self._rolling_calibration_history[0].timestamp_ns < history_start_ns
        ):
            self._rolling_calibration_history.popleft()

    def _maybe_update_rolling_calibration(self) -> None:
        """Use robust history only at a bounded rate and only with new samples."""

        if not self._rolling_calibration_history:
            return
        current_fix = self._current_gnss_fix
        if current_fix is None:
            return
        if (
            self._last_rolling_calibration_gnss_timestamp_ns is not None
            and current_fix.timestamp_ns
            <= self._last_rolling_calibration_gnss_timestamp_ns
        ):
            return
        latest_timestamp_ns = self._rolling_calibration_history[-1].timestamp_ns
        previous_attempt = self._last_rolling_calibration_attempt_timestamp_ns
        if (
            previous_attempt is not None
            and latest_timestamp_ns - previous_attempt
            < self._config.calibration_evidence_limits.rolling_update_interval_ns
        ):
            return
        self._last_rolling_calibration_attempt_timestamp_ns = latest_timestamp_ns
        self._last_rolling_calibration_gnss_timestamp_ns = current_fix.timestamp_ns
        evidence = build_rolling_calibration_evidence(
            history=tuple(self._rolling_calibration_history),
            limits=self._config.calibration_evidence_limits,
        )
        if evidence is not None:
            self._calibrator.update(evidence)
            self._remember_trusted_calibration()

    def _remember_trusted_calibration(self) -> None:
        """Save only a fresh rotation that cleared the public output threshold."""

        calibration = self._calibrator.calibration
        if (
            calibration is not None
            and calibration.confidence
            >= self._config.minimum_calibration_confidence_for_output
        ):
            self._last_trusted_calibration = calibration

    def _effective_calibration(self, timestamp_ns: int) -> VehicleCalibration | None:
        """Return fresh calibration, or a visibly low-confidence bounded hold.

        A hold is never used during first-session warm-up. It only preserves a
        formerly trusted same-device rotation while the dynamic calibrator is
        temporarily degraded/recalibrating, and expires rather than bridging
        an arbitrarily long missing-evidence period.
        """

        current = self._calibrator.calibration
        if (
            current is not None
            and current.confidence
            >= self._config.minimum_calibration_confidence_for_output
        ):
            self._last_trusted_calibration = current
            return current
        held = self._last_trusted_calibration
        if (
            current is None
            or held is None
            or timestamp_ns - held.timestamp_ns
            > self._config.maximum_held_calibration_age_ns
            or current.source != held.source
            or current.source_id != held.source_id
        ):
            return current
        return VehicleCalibration(
            timestamp_ns=timestamp_ns,
            source=held.source,
            source_id=held.source_id,
            sensor_to_vehicle_wxyz=held.sensor_to_vehicle_wxyz,
            confidence=self._config.minimum_calibration_confidence_for_output,
        )

    def _velocity_windows_from_accepted_sample(
        self,
        sample: VehicleImuSample,
        quality: VehicleImuQuality,
    ) -> tuple[VelocityModelInputWindow, ...]:
        """Resample one quality-gated sample and emit completed causal windows."""

        if not quality.is_acceptable:
            self._reset_velocity_windowing()
            return ()

        windows: list[VelocityModelInputWindow] = []
        for resampled_sample in self._velocity_resampler.push(sample, quality):
            window = self._velocity_window_builder.push(resampled_sample)
            if window is not None:
                windows.append(window)

        return tuple(windows)

    def _reset_velocity_windowing(self) -> None:
        """Prevent a model window from crossing an unavailable pipeline phase."""

        self._velocity_resampler.reset()
        self._velocity_window_builder.reset()

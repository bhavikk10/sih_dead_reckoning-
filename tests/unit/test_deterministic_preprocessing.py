"""Replay-focused tests for the deterministic IMU path and window safeguards."""

import pytest

from idr_backend.sensors.calibration_evidence import CalibrationEvidenceLimits
from idr_backend.sensors.gnss import GnssQualityLimits
from idr_backend.sensors.preprocessing import (
    DeterministicImuPreprocessor,
    DeterministicPreprocessorConfig,
    PreprocessingDisposition,
)
from idr_backend.sensors.quality import (
    VehicleImuQuality,
    VehicleImuQualityLimits,
)
from idr_backend.sensors.resampling import FixedRateVehicleImuResampler
from idr_backend.sensors.types import (
    CoordinateFrame,
    GnssFix,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
    VehicleImuSample,
)
from idr_backend.sensors.windowing import CausalVehicleImuWindowBuilder


def _vehicle_sample(timestamp_ns: int) -> VehicleImuSample:
    return VehicleImuSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        linear_acceleration_mps2=(1.0, 0.0, 0.0),
        angular_velocity_radps=(0.0, 0.0, 0.0),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        calibration_confidence=1.0,
    )


def _quality(sample: VehicleImuSample, acceptable: bool = True) -> VehicleImuQuality:
    return VehicleImuQuality(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        flags=frozenset(),
        sample_interval_ns=None,
        score=1.0 if acceptable else 0.0,
        is_acceptable=acceptable,
    )


def _preprocessor() -> DeterministicImuPreprocessor:
    return DeterministicImuPreprocessor(
        DeterministicPreprocessorConfig(
            max_imu_skew_ns=1_000_000,
            max_pending_imu_samples=8,
            accelerometer_correction_gain_per_s=0.0,
            acceleration_trust_tolerance_mps2=1.0,
            minimum_calibration_evidence_count=1,
            minimum_calibration_evidence_confidence=0.1,
            maximum_calibration_disagreement_rad=0.5,
            remount_evidence_count=2,
            minimum_calibration_confidence_for_output=0.1,
            velocity_model_sample_period_ns=100_000_000,
            velocity_model_window_size=2,
            gnss_quality_limits=GnssQualityLimits(
                max_gap_ns=2_000_000_000,
                max_horizontal_accuracy_m=10.0,
                max_speed_accuracy_mps=1.0,
                min_course_speed_mps=3.0,
                max_course_accuracy_rad=0.5,
            ),
            calibration_evidence_limits=CalibrationEvidenceLimits(
                max_imu_gnss_skew_ns=1_000_000,
                min_gnss_interval_ns=500_000_000,
                max_gnss_interval_ns=2_000_000_000,
                min_gnss_longitudinal_acceleration_mps2=0.5,
                min_sensor_linear_acceleration_mps2=0.5,
                max_course_rate_radps=0.2,
            ),
            vehicle_imu_quality_limits=VehicleImuQualityLimits(
                max_gap_ns=1_000_000_000,
                max_linear_acceleration_mps2=20.0,
                max_angular_velocity_radps=10.0,
                minimum_calibration_confidence=0.1,
            ),
        )
    )


def _gnss_fix(timestamp_ns: int, speed_mps: float) -> GnssFix:
    return GnssFix(
        timestamp_ns=timestamp_ns,
        receiver_id="phone-primary",
        latitude_deg=12.0,
        longitude_deg=77.0,
        altitude_m=None,
        horizontal_accuracy_m=3.0,
        vertical_accuracy_m=None,
        speed_mps=speed_mps,
        speed_accuracy_mps=0.2,
        course_over_ground_rad=0.0,
        course_accuracy_rad=0.05,
    )


def _raw(timestamp_ns: int, kind: SensorKind, value: tuple[float, float, float]) -> RawSensorSample:
    return RawSensorSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=kind,
        value=value,
        unit=(
            MeasurementUnit.METERS_PER_SECOND_SQUARED
            if kind is SensorKind.ACCELEROMETER
            else MeasurementUnit.RADIANS_PER_SECOND
        ),
        frame=CoordinateFrame.SENSOR,
    )


def test_resampler_and_window_builder_do_not_bridge_a_quality_failure() -> None:
    """An invalid input clears the preceding sequence before model windowing."""

    resampler = FixedRateVehicleImuResampler(target_period_ns=100)
    builder = CausalVehicleImuWindowBuilder(window_size=3, sample_period_ns=100)

    first = _vehicle_sample(0)
    second = _vehicle_sample(100)
    failed = _vehicle_sample(200)
    third = _vehicle_sample(300)
    fourth = _vehicle_sample(400)

    assert builder.push(resampler.push(first, _quality(first))[0]) is None
    assert builder.push(resampler.push(second, _quality(second))[0]) is None
    assert resampler.push(failed, _quality(failed, acceptable=False)) == ()
    builder.reset()
    assert builder.push(resampler.push(third, _quality(third))[0]) is None
    assert builder.push(resampler.push(fourth, _quality(fourth))[0]) is None


def test_straight_gnss_aided_event_produces_clean_vehicle_frame_imu() -> None:
    """The composed path publishes only after one trusted calibration event."""

    preprocessor = _preprocessor()
    timestamp_ns = 2_000_000_000
    preprocessor.push_gnss_fix(_gnss_fix(1_000_000_000, 10.0))

    # Initialise roll/pitch from a stationary, gravity-only reading before the
    # acceleration event.  Otherwise a cold-start attitude estimate could
    # mistake the real forward acceleration for a slight device tilt.
    assert preprocessor.push_raw_sample(
        _raw(1_900_000_000, SensorKind.ACCELEROMETER, (0.0, 0.0, 9.80665))
    ) == ()
    warmup = preprocessor.push_raw_sample(
        _raw(1_900_000_000, SensorKind.GYROSCOPE, (0.0, 0.0, 0.0))
    )
    assert len(warmup) == 1
    assert warmup[0].disposition is PreprocessingDisposition.CALIBRATION_WARMING_UP

    preprocessor.push_gnss_fix(_gnss_fix(timestamp_ns, 12.0))

    assert preprocessor.push_raw_sample(
        _raw(timestamp_ns, SensorKind.ACCELEROMETER, (1.0, 0.0, 9.80665))
    ) == ()

    results = preprocessor.push_raw_sample(
        _raw(timestamp_ns, SensorKind.GYROSCOPE, (0.0, 0.0, 0.0))
    )

    assert len(results) == 1
    result = results[0]
    assert result.disposition is PreprocessingDisposition.ACCEPTED
    assert result.vehicle_imu_sample is not None
    assert result.quality is not None and result.quality.is_acceptable
    assert result.vehicle_imu_sample.linear_acceleration_mps2 == pytest.approx(
        (1.0, 0.0, 0.0)
    )
    assert result.velocity_windows == ()

"""Tests for GNSS/IMU evidence used by dynamic mounting calibration."""

import pytest

from idr_backend.sensors.calibration_evidence import (
    CalibrationEvidenceLimits,
    build_calibration_evidence,
)
from idr_backend.sensors.gnss import (
    GnssFixQuality,
    GnssQualityLimits,
    GnssQualityMonitor,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    GnssFix,
    OrientationEstimate,
    SensorSource,
    SynchronizedImuSample,
)


def _fix(timestamp_ns: int, speed_mps: float, course_rad: float) -> GnssFix:
    return GnssFix(
        timestamp_ns=timestamp_ns,
        receiver_id="phone-primary",
        latitude_deg=12.0,
        longitude_deg=77.0,
        altitude_m=None,
        horizontal_accuracy_m=4.0,
        vertical_accuracy_m=None,
        speed_mps=speed_mps,
        speed_accuracy_mps=0.2,
        course_over_ground_rad=course_rad,
        course_accuracy_rad=0.05,
    )


def _quality_pair(
    previous: GnssFix, current: GnssFix
) -> tuple[GnssFixQuality, GnssFixQuality]:
    monitor = GnssQualityMonitor(
        GnssQualityLimits(
            max_gap_ns=2_000_000_000,
            max_horizontal_accuracy_m=10.0,
            max_speed_accuracy_mps=1.0,
            min_course_speed_mps=3.0,
            max_course_accuracy_rad=0.5,
        )
    )
    return monitor.assess(previous), monitor.assess(current)


def _limits() -> CalibrationEvidenceLimits:
    return CalibrationEvidenceLimits(
        max_imu_gnss_skew_ns=50_000_000,
        min_gnss_interval_ns=500_000_000,
        max_gnss_interval_ns=2_000_000_000,
        min_gnss_longitudinal_acceleration_mps2=0.5,
        min_sensor_linear_acceleration_mps2=0.5,
        max_course_rate_radps=0.2,
    )


def _imu_and_orientation(timestamp_ns: int) -> tuple[SynchronizedImuSample, OrientationEstimate]:
    imu = SynchronizedImuSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        frame=CoordinateFrame.SENSOR,
        # Specific force: 1 m/s² forward plus upward +g while level.
        acceleration_mps2=(1.0, 0.0, 9.80665),
        angular_velocity_radps=(0.0, 0.0, 0.0),
        accelerometer_timestamp_ns=timestamp_ns,
        gyroscope_timestamp_ns=timestamp_ns,
    )
    orientation = OrientationEstimate(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        sensor_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
    )
    return imu, orientation


def test_straight_acceleration_produces_nonzero_calibration_evidence() -> None:
    """Forward acceleration plus increasing GNSS speed reveals the forward axis."""

    previous = _fix(1_000_000_000, 10.0, 0.3)
    current = _fix(2_000_000_000, 12.0, 0.3)
    previous_quality, current_quality = _quality_pair(previous, current)
    imu, orientation = _imu_and_orientation(current.timestamp_ns)

    evidence = build_calibration_evidence(
        imu_sample=imu,
        orientation=orientation,
        previous_gnss_fix=previous,
        previous_gnss_quality=previous_quality,
        current_gnss_fix=current,
        current_gnss_quality=current_quality,
        limits=_limits(),
    )

    assert evidence is not None
    assert evidence.confidence > 0.0
    assert evidence.vehicle_forward_in_sensor == pytest.approx((1.0, 0.0, 0.0))
    assert evidence.vehicle_up_in_sensor == pytest.approx((0.0, 0.0, 1.0))


def test_turning_interval_does_not_teach_the_mounting_calibrator() -> None:
    """Lateral acceleration during a turn must not be mislabelled as forward."""

    previous = _fix(1_000_000_000, 10.0, 0.0)
    current = _fix(2_000_000_000, 12.0, 0.8)
    previous_quality, current_quality = _quality_pair(previous, current)
    imu, orientation = _imu_and_orientation(current.timestamp_ns)

    evidence = build_calibration_evidence(
        imu_sample=imu,
        orientation=orientation,
        previous_gnss_fix=previous,
        previous_gnss_quality=previous_quality,
        current_gnss_fix=current,
        current_gnss_quality=current_quality,
        limits=_limits(),
    )

    assert evidence is None

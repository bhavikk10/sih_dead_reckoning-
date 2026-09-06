"""Focused invariants for each deterministic sensor-processing stage."""

from math import pi

import pytest

from idr_backend.sensors.calibration import (
    derive_sensor_to_vehicle_quaternion,
    rotate_imu_to_vehicle,
)
from idr_backend.sensors.gravity_removal import remove_gravity_from_vehicle_imu
from idr_backend.sensors.normalization import STD_GRAV, normalize_raw_sample
from idr_backend.sensors.orientation import propagate_orientation, rotate_vector
from idr_backend.sensors.quality import (
    QualityFlag,
    VehicleImuQuality,
    VehicleImuQualityLimits,
    VehicleImuQualityMonitor,
)
from idr_backend.sensors.resampling import FixedRateVehicleImuResampler
from idr_backend.sensors.synchronization import synchronize_pair
from idr_backend.sensors.types import (
    CoordinateFrame,
    MeasurementUnit,
    NormalizedSensorSample,
    OrientationEstimate,
    RawSensorSample,
    SensorKind,
    SensorSource,
    SynchronizedImuSample,
    VehicleCalibration,
    VehicleImuSample,
)
from idr_backend.sensors.windowing import CausalVehicleImuWindowBuilder


def _normalized(
    *,
    timestamp_ns: int,
    kind: SensorKind,
    value: tuple[float, float, float],
    frame: CoordinateFrame = CoordinateFrame.SENSOR,
) -> NormalizedSensorSample:
    """Make a short SI sample for synchronizer tests."""

    return NormalizedSensorSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=kind,
        value=value,
        frame=frame,
    )


def _vehicle(timestamp_ns: int) -> VehicleImuSample:
    """Make a clean vehicle-frame sample for quality/resampling tests."""

    return VehicleImuSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        linear_acceleration_mps2=(1.0, 0.0, 0.0),
        angular_velocity_radps=(0.0, 0.0, 0.0),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        calibration_confidence=1.0,
    )


def _quality(sample: VehicleImuSample, score: float) -> VehicleImuQuality:
    """Make an accepted quality report with an intentionally visible score."""

    return VehicleImuQuality(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        flags=frozenset(),
        sample_interval_ns=100,
        score=score,
        is_acceptable=True,
    )


def test_normalization_converts_supported_non_si_units_once() -> None:
    """No stage after normalization needs to reason about g or degrees/s."""

    acceleration = normalize_raw_sample(
        RawSensorSample(
            timestamp_ns=0,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            kind=SensorKind.ACCELEROMETER,
            value=(1.0, 0.0, 0.0),
            unit=MeasurementUnit.STANDARD_GRAVITY,
            frame=CoordinateFrame.SENSOR,
        )
    )
    rotation = normalize_raw_sample(
        RawSensorSample(
            timestamp_ns=1,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            kind=SensorKind.GYROSCOPE,
            value=(0.0, 0.0, 180.0),
            unit=MeasurementUnit.DEGREES_PER_SECOND,
            frame=CoordinateFrame.SENSOR,
        )
    )

    assert acceleration.value == pytest.approx((STD_GRAV, 0.0, 0.0))
    assert rotation.value == pytest.approx((0.0, 0.0, pi))


def test_synchronization_preserves_frame_and_rejects_frame_mixing() -> None:
    """A matched pair has one frame; a cross-frame pair is always invalid."""

    acceleration = _normalized(
        timestamp_ns=100,
        kind=SensorKind.ACCELEROMETER,
        value=(0.0, 0.0, STD_GRAV),
    )
    gyroscope = _normalized(
        timestamp_ns=105,
        kind=SensorKind.GYROSCOPE,
        value=(0.0, 0.0, 0.0),
    )
    synchronized = synchronize_pair(acceleration, gyroscope, max_skew_ns=5)

    assert synchronized.timestamp_ns == 105
    assert synchronized.frame is CoordinateFrame.SENSOR
    with pytest.raises(ValueError, match="diff frames"):
        synchronize_pair(
            acceleration,
            _normalized(
                timestamp_ns=105,
                kind=SensorKind.GYROSCOPE,
                value=(0.0, 0.0, 0.0),
                frame=CoordinateFrame.VEHICLE_FLU,
            ),
            max_skew_ns=5,
        )


def test_orientation_propagation_rotates_sensor_axes_into_navigation() -> None:
    """A one-second +z yaw rate rotates sensor forward toward navigation north."""

    quarter_turn = propagate_orientation(
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, pi / 2.0),
        delta_time_s=1.0,
    )

    assert rotate_vector(quarter_turn, (1.0, 0.0, 0.0)) == pytest.approx(
        (0.0, 1.0, 0.0),
        abs=1e-12,
    )


def test_calibration_rotation_then_gravity_removal_recovers_linear_motion() -> None:
    """Level identity mounting maps specific force +g back to zero acceleration."""

    calibration = VehicleCalibration(
        timestamp_ns=0,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        sensor_to_vehicle_wxyz=derive_sensor_to_vehicle_quaternion(
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        ),
        confidence=1.0,
    )
    synchronized = SynchronizedImuSample(
        timestamp_ns=100,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        frame=CoordinateFrame.SENSOR,
        acceleration_mps2=(0.0, 0.0, STD_GRAV),
        angular_velocity_radps=(0.0, 0.0, 0.0),
        accelerometer_timestamp_ns=100,
        gyroscope_timestamp_ns=100,
    )
    vehicle = rotate_imu_to_vehicle(synchronized, calibration, 0.5)
    cleaned = remove_gravity_from_vehicle_imu(
        vehicle,
        OrientationEstimate(
            timestamp_ns=100,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            sensor_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
        calibration,
    )

    assert cleaned.linear_acceleration_mps2 == pytest.approx((0.0, 0.0, 0.0))


def test_quality_gap_resets_resampling_and_interpolation_is_conservative() -> None:
    """Gaps reject the stream; valid interpolation inherits its weaker score."""

    monitor = VehicleImuQualityMonitor(
        VehicleImuQualityLimits(
            max_gap_ns=100,
            max_linear_acceleration_mps2=10.0,
            max_angular_velocity_radps=10.0,
            minimum_calibration_confidence=0.5,
        )
    )
    assert monitor.assess(_vehicle(0)).is_acceptable
    gapped = monitor.assess(_vehicle(101))
    assert QualityFlag.SENSOR_GAP in gapped.flags
    assert not gapped.is_acceptable

    resampler = FixedRateVehicleImuResampler(target_period_ns=100)
    builder = CausalVehicleImuWindowBuilder(window_size=2, sample_period_ns=100)
    first = _vehicle(0)
    second = _vehicle(200)
    first_output = resampler.push(first, _quality(first, score=0.9))[0]
    later_outputs = resampler.push(second, _quality(second, score=0.6))
    assert builder.push(first_output) is None
    window = builder.push(later_outputs[0])

    assert window is not None
    assert window.end_timestamp_ns == 100
    assert window.final_quality.score == pytest.approx(0.6)

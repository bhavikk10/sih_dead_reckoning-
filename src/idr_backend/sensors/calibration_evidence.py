"""Build safe phone-to-vehicle calibration evidence from IMU and GNSS motion."""

from dataclasses import dataclass
from math import atan2, isfinite, sin, cos
from typing import Sequence

import numpy as np
from .calibration import CalibrationEvidence, derive_sensor_to_vehicle_quaternion
from .gnss import GnssFixQuality
from .orientation import (
    normalize_vector,
    quaternion_conjugate,
    rotate_vector,
    vector_magnitude,
)
from .types import (
    CoordinateFrame,
    GnssFix,
    OrientationEstimate,
    SensorSource,
    SynchronizedImuSample,
    Vector3,
)


@dataclass(frozen=True, slots=True)
class CalibrationEvidenceLimits:
    """Explicit conditions required before GNSS may aid mounting calibration."""

    max_imu_gnss_skew_ns: int
    min_gnss_interval_ns: int
    max_gnss_interval_ns: int

    # Avoid treating tiny GPS-speed fluctuations as real acceleration.
    min_gnss_longitudinal_acceleration_mps2: float

    # Avoid deriving a direction from nearly-zero IMU acceleration.
    min_sensor_linear_acceleration_mps2: float

    # During a turn, acceleration includes a lateral component. We use GNSS
    # course only to reject such intervals, not to infer absolute phone yaw.
    max_course_rate_radps: float

    # Used while removing gravity in the sensor frame.
    gravity_mps2: float = 9.80665

    # A single one-second GNSS speed difference is often quantised/noisy. The
    # rolling fallback correlates a past-only history of sensor motion against
    # smoothed GNSS speed changes before publishing evidence. These defaults
    # leave the immediate single-interval path available for clear maneuvers.
    rolling_history_ns: int = 30_000_000_000
    rolling_update_interval_ns: int = 1_000_000_000
    rolling_minimum_correlation: float = 0.20
    rolling_minimum_useful_samples: int = 5
    rolling_quiet_acceleration_tolerance_mps2: float = 2.0
    rolling_maximum_angular_velocity_radps: float = 1.5
    rolling_maximum_speed_delay_ns: int = 2_000_000_000
    rolling_speed_smoothing_ns: int = 1_500_000_000
    rolling_speed_derivative_ns: int = 1_000_000_000


@dataclass(frozen=True, slots=True)
class CalibrationHistorySample:
    """One synchronized IMU point with its latest still-fresh GNSS speed.

    This is mounting-calibration evidence, not a fusion measurement. The
    speed was observed at or before the timestamp and CAN labels never enter
    the structure.
    """

    timestamp_ns: int
    source: SensorSource
    source_id: str
    acceleration_mps2: Vector3
    angular_velocity_radps: Vector3
    gnss_speed_mps: float



def build_calibration_evidence(*, imu_sample: SynchronizedImuSample, orientation: OrientationEstimate, previous_gnss_fix: GnssFix, previous_gnss_quality: GnssFixQuality, current_gnss_fix: GnssFix, current_gnss_quality: GnssFixQuality, limits: CalibrationEvidenceLimits,) -> CalibrationEvidence | None:
    """Build one calibration observation, or return None when evidence is weak.

    The caller must select the synchronized IMU sample nearest the current GNSS
    fix. Returning None is normal: most samples should not alter calibration.
    """

    _validate_inputs(
        imu_sample=imu_sample,
        orientation=orientation,
        previous_gnss_fix=previous_gnss_fix,
        current_gnss_fix=current_gnss_fix,
        limits=limits,
    )

    # Both ends of the GNSS interval must have reliable speed and course.
    # Course is only used to detect turning; it is not treated as phone yaw.
    if not (
        previous_gnss_quality.speed_is_acceptable
        and current_gnss_quality.speed_is_acceptable
        and previous_gnss_quality.course_is_acceptable
        and current_gnss_quality.course_is_acceptable
    ):
        return None

    imu_gnss_skew_ns = abs(
        imu_sample.timestamp_ns - current_gnss_fix.timestamp_ns
    )
    if imu_gnss_skew_ns > limits.max_imu_gnss_skew_ns:
        return None

    gnss_interval_ns = (
        current_gnss_fix.timestamp_ns - previous_gnss_fix.timestamp_ns
    )
    if not (
        limits.min_gnss_interval_ns
        <= gnss_interval_ns
        <= limits.max_gnss_interval_ns
    ):
        return None

    interval_s = gnss_interval_ns * 1e-9

    # Positive means the car sped up; negative means it braked.
    gnss_longitudinal_acceleration_mps2 = (
        current_gnss_fix.speed_mps - previous_gnss_fix.speed_mps
    ) / interval_s

    if (
        abs(gnss_longitudinal_acceleration_mps2)
        < limits.min_gnss_longitudinal_acceleration_mps2
    ):
        return None

    course_rate_radps = _wrapped_angle_difference(
        current_gnss_fix.course_over_ground_rad,
        previous_gnss_fix.course_over_ground_rad,
    ) / interval_s

    if abs(course_rate_radps) > limits.max_course_rate_radps:
        return None

    sensor_linear_acceleration = _remove_gravity_in_sensor_frame(
        imu_sample=imu_sample,
        orientation=orientation,
        gravity_mps2=limits.gravity_mps2,
    )

    if (
        vector_magnitude(sensor_linear_acceleration)
        < limits.min_sensor_linear_acceleration_mps2
    ):
        return None

    # During straight acceleration, the linear-acceleration direction is the
    # vehicle forward direction. During braking it points backward, so invert it.
    forward_sign = (
        1.0 if gnss_longitudinal_acceleration_mps2 > 0.0 else -1.0
    )
    vehicle_forward_in_sensor = normalize_vector(
        tuple(
            forward_sign * component
            for component in sensor_linear_acceleration
        )
    )

    # Gravity gives vehicle-up without needing absolute yaw.
    vehicle_up_in_sensor = _navigation_up_in_sensor_frame(orientation)

    return CalibrationEvidence(
        timestamp_ns=imu_sample.timestamp_ns,
        source=imu_sample.source,
        source_id=imu_sample.source_id,
        vehicle_up_in_sensor=vehicle_up_in_sensor,
        vehicle_forward_in_sensor=vehicle_forward_in_sensor,
        confidence=_evidence_confidence(
            imu_gnss_skew_ns=imu_gnss_skew_ns,
            gnss_longitudinal_acceleration_mps2=(
                gnss_longitudinal_acceleration_mps2
            ),
            sensor_linear_acceleration=sensor_linear_acceleration,
            limits=limits,
        ),
    )


def build_rolling_calibration_evidence(
    *,
    history: Sequence[CalibrationHistorySample],
    limits: CalibrationEvidenceLimits,
) -> CalibrationEvidence | None:
    """Derive robust mounting evidence from a causal IMU/GNSS-speed history.

    This complements single-interval evidence when phone speed is staircase-
    like. It finds the sensor direction which repeatedly co-varies with past
    smoothed GNSS speed changes. CAN labels and future fixes never enter it.
    """

    if len(history) < limits.rolling_minimum_useful_samples:
        return None
    _validate_rolling_limits(limits)
    latest = history[-1]
    if not latest.source_id.strip():
        return None
    selected = tuple(
        sample
        for sample in history
        if sample.timestamp_ns >= latest.timestamp_ns - limits.rolling_history_ns
    )
    if len(selected) < limits.rolling_minimum_useful_samples:
        return None
    if any(
        sample.source is not latest.source
        or sample.source_id != latest.source_id
        or sample.timestamp_ns < 0
        or not all(isfinite(value) for value in sample.acceleration_mps2)
        or not all(isfinite(value) for value in sample.angular_velocity_radps)
        or not isfinite(sample.gnss_speed_mps)
        or sample.gnss_speed_mps < 0.0
        for sample in selected
    ):
        return None

    timestamps_ns = np.asarray([sample.timestamp_ns for sample in selected], dtype=np.int64)
    if not np.all(np.diff(timestamps_ns) > 0):
        return None
    acceleration = np.asarray([sample.acceleration_mps2 for sample in selected], dtype=float)
    angular_velocity = np.asarray(
        [sample.angular_velocity_radps for sample in selected], dtype=float
    )
    speeds = np.asarray([sample.gnss_speed_mps for sample in selected], dtype=float)
    sample_period_s = float(np.median(np.diff(timestamps_ns) * 1e-9))
    if not isfinite(sample_period_s) or sample_period_s <= 0.0:
        return None

    acceleration_norm = np.linalg.norm(acceleration, axis=1)
    angular_velocity_norm = np.linalg.norm(angular_velocity, axis=1)
    quiet = (
        np.abs(acceleration_norm - limits.gravity_mps2)
        <= limits.rolling_quiet_acceleration_tolerance_mps2
    ) & (angular_velocity_norm <= limits.rolling_maximum_angular_velocity_radps)
    if int(quiet.sum()) < limits.rolling_minimum_useful_samples:
        return None
    try:
        vehicle_up_in_sensor = normalize_vector(
            tuple(float(value) for value in np.median(acceleration[quiet], axis=0))
        )
    except ValueError:
        return None

    smoothing_steps = max(3, round(limits.rolling_speed_smoothing_ns * 1e-9 / sample_period_s))
    derivative_steps = max(1, round(limits.rolling_speed_derivative_ns * 1e-9 / sample_period_s))
    cumulative = np.concatenate(([0.0], np.cumsum(speeds)))
    positions = np.arange(len(speeds))
    starts = np.maximum(0, positions - smoothing_steps + 1)
    counts = positions - starts + 1
    smoothed_speed = (cumulative[positions + 1] - cumulative[starts]) / counts
    speed_acceleration = np.full(len(smoothed_speed), np.nan)
    elapsed_s = (timestamps_ns[derivative_steps:] - timestamps_ns[:-derivative_steps]) * 1e-9
    speed_acceleration[derivative_steps:] = (
        smoothed_speed[derivative_steps:] - smoothed_speed[:-derivative_steps]
    ) / elapsed_s
    linear_sensor = acceleration - limits.gravity_mps2 * np.asarray(vehicle_up_in_sensor)
    maximum_delay_steps = max(
        0, round(limits.rolling_maximum_speed_delay_ns * 1e-9 / sample_period_s)
    )
    best_vector: np.ndarray | None = None
    best_score = 0.0
    for delay_steps in range(maximum_delay_steps + 1):
        if delay_steps:
            sensor_values = linear_sensor[:-delay_steps]
            candidate_speed_acceleration = speed_acceleration[delay_steps:]
            candidate_gyro = angular_velocity_norm[:-delay_steps]
        else:
            sensor_values = linear_sensor
            candidate_speed_acceleration = speed_acceleration
            candidate_gyro = angular_velocity_norm
        useful = (
            np.isfinite(candidate_speed_acceleration)
            & (np.abs(candidate_speed_acceleration) >= limits.min_gnss_longitudinal_acceleration_mps2)
            & (np.abs(candidate_speed_acceleration) <= 5.0)
            & (candidate_gyro <= limits.rolling_maximum_angular_velocity_radps)
        )
        if int(useful.sum()) < limits.rolling_minimum_useful_samples:
            continue
        centred_sensor = sensor_values[useful] - np.median(sensor_values[useful], axis=0)
        centred_speed = candidate_speed_acceleration[useful] - np.median(candidate_speed_acceleration[useful])
        candidate_vector = centred_sensor.T @ centred_speed
        denominator = float(np.sqrt(np.sum(centred_sensor**2) * np.sum(centred_speed**2)))
        score = float(np.linalg.norm(candidate_vector) / max(denominator, 1e-12))
        if score > best_score:
            best_vector = candidate_vector
            best_score = score

    if best_vector is None or best_score < limits.rolling_minimum_correlation:
        return None
    try:
        vehicle_forward_in_sensor = normalize_vector(
            tuple(float(value) for value in best_vector)
        )
        derive_sensor_to_vehicle_quaternion(vehicle_up_in_sensor, vehicle_forward_in_sensor)
    except ValueError:
        return None
    return CalibrationEvidence(
        timestamp_ns=latest.timestamp_ns,
        source=latest.source,
        source_id=latest.source_id,
        vehicle_up_in_sensor=vehicle_up_in_sensor,
        vehicle_forward_in_sensor=vehicle_forward_in_sensor,
        # A just-accepted correlation maps to 0.60; repeated strong evidence
        # approaches one and remains visible to later quality/uncertainty code.
        confidence=min(1.0, 0.5 + 0.5 * best_score),
    )


def _validate_inputs(
    *,
    imu_sample: SynchronizedImuSample,
    orientation: OrientationEstimate,
    previous_gnss_fix: GnssFix,
    current_gnss_fix: GnssFix,
    limits: CalibrationEvidenceLimits,
) -> None:
    """Reject programming/configuration errors before evaluating evidence."""

    if imu_sample.frame is not CoordinateFrame.SENSOR:
        raise ValueError(
            "Calibration evidence requires SENSOR-frame IMU data."
        )

    if orientation.timestamp_ns != imu_sample.timestamp_ns:
        raise ValueError(
            "Orientation and IMU sample must have the same timestamp."
        )

    if (
        orientation.source != imu_sample.source
        or orientation.source_id != imu_sample.source_id
    ):
        raise ValueError(
            "Orientation and IMU sample must belong to the same device."
        )

    if previous_gnss_fix.receiver_id != current_gnss_fix.receiver_id:
        raise ValueError("GNSS fixes must come from the same receiver.")

    if current_gnss_fix.timestamp_ns <= previous_gnss_fix.timestamp_ns:
        raise ValueError("GNSS fixes must be chronological.")

    if limits.max_imu_gnss_skew_ns < 0:
        raise ValueError("max_imu_gnss_skew_ns must be non-negative.")

    if (
        limits.min_gnss_interval_ns <= 0
        or limits.max_gnss_interval_ns < limits.min_gnss_interval_ns
    ):
        raise ValueError("GNSS interval limits are invalid.")

    if (
        not isfinite(limits.min_gnss_longitudinal_acceleration_mps2)
        or limits.min_gnss_longitudinal_acceleration_mps2 <= 0.0
    ):
        raise ValueError(
            "min_gnss_longitudinal_acceleration_mps2 must be positive."
        )

    if (
        not isfinite(limits.min_sensor_linear_acceleration_mps2)
        or limits.min_sensor_linear_acceleration_mps2 <= 0.0
    ):
        raise ValueError(
            "min_sensor_linear_acceleration_mps2 must be positive."
        )

    if (
        not isfinite(limits.max_course_rate_radps)
        or limits.max_course_rate_radps <= 0.0
    ):
        raise ValueError("max_course_rate_radps must be positive.")

    if (
        not isfinite(limits.gravity_mps2)
        or limits.gravity_mps2 <= 0.0
    ):
        raise ValueError("gravity_mps2 must be finite and positive.")


def _validate_rolling_limits(limits: CalibrationEvidenceLimits) -> None:
    """Validate rolling-history policy before examining source data."""

    positive_ints = (
        limits.rolling_history_ns,
        limits.rolling_update_interval_ns,
        limits.rolling_minimum_useful_samples,
        limits.rolling_maximum_speed_delay_ns,
        limits.rolling_speed_smoothing_ns,
        limits.rolling_speed_derivative_ns,
    )
    if any(value <= 0 for value in positive_ints):
        raise ValueError("Rolling calibration duration/count limits must be positive.")
    scalars = (
        limits.rolling_minimum_correlation,
        limits.rolling_quiet_acceleration_tolerance_mps2,
        limits.rolling_maximum_angular_velocity_radps,
    )
    if not all(isfinite(value) and value > 0.0 for value in scalars):
        raise ValueError("Rolling calibration scalar limits must be finite and positive.")


def _remove_gravity_in_sensor_frame(
    *,
    imu_sample: SynchronizedImuSample,
    orientation: OrientationEstimate,
    gravity_mps2: float,
) -> Vector3:
    """Recover linear acceleration while data is still in the sensor frame."""

    navigation_to_sensor = quaternion_conjugate(
        orientation.sensor_to_navigation_wxyz
    )

    gravity_in_sensor = rotate_vector(
        navigation_to_sensor,
        (0.0, 0.0, -gravity_mps2),
    )

    return tuple(
        measured + gravity
        for measured, gravity in zip(
            imu_sample.acceleration_mps2,
            gravity_in_sensor,
            strict=True,
        )
    )


def _navigation_up_in_sensor_frame(
    orientation: OrientationEstimate,
) -> Vector3:
    """Express vehicle-up in the sensor frame using gravity/tilt only."""

    navigation_to_sensor = quaternion_conjugate(
        orientation.sensor_to_navigation_wxyz
    )

    return normalize_vector(
        rotate_vector(
            navigation_to_sensor,
            (0.0, 0.0, 1.0),
        )
    )


def _wrapped_angle_difference(
    current_angle_rad: float,
    previous_angle_rad: float,
) -> float:
    """Return the shortest signed difference between two angles."""

    return atan2(
        sin(current_angle_rad - previous_angle_rad),
        cos(current_angle_rad - previous_angle_rad),
    )


def _evidence_confidence(
    *,
    imu_gnss_skew_ns: int,
    gnss_longitudinal_acceleration_mps2: float,
    sensor_linear_acceleration: Vector3,
    limits: CalibrationEvidenceLimits,
) -> float:
    """Calculate a conservative 0-to-1 evidence confidence."""

    timing_score = 1.0 - (
        imu_gnss_skew_ns / max(1, limits.max_imu_gnss_skew_ns)
    )

    acceleration_score = min(
        1.0,
        abs(gnss_longitudinal_acceleration_mps2)
        / (2.0 * limits.min_gnss_longitudinal_acceleration_mps2),
    )

    imu_signal_score = min(
        1.0,
        vector_magnitude(sensor_linear_acceleration)
        / (2.0 * limits.min_sensor_linear_acceleration_mps2),
    )

    return max(
        0.0,
        min(
            timing_score,
            acceleration_score,
            imu_signal_score,
        ),
    )



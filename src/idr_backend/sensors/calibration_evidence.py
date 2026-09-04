"""Build safe phone-to-vehicle calibration evidence from IMU and GNSS motion."""

from dataclasses import dataclass
from math import atan2, isfinite, sin, cos
from .calibration import CalibrationEvidence
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



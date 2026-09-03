"""Quaternion helpers and IMU-only orientation estimation.

Quaternion convention:
- quaternions use (w, x, y, z) ordering;
- sensor_to_navigation maps a sensor-frame vector into navigation ENU:
  v_navigation = q * (0, v_sensor) * conjugate(q);
- orientation is distinct from phone-to-vehicle mounting calibration.
- Rotate a vector by a source-to-target quaternion.
"""

from math import cos, isfinite, sin, sqrt
from .types import ( QuaternionWxyz, OrientationEstimate, CoordinateFrame, SensorSource, SynchronizedImuSample, Vector3)
_NAVIGATION_UP: Vector3 = (0.0, 0.0, 1.0)

def normalize_quaternion(quaternion: QuaternionWxyz) -> QuaternionWxyz:
    """Return a unit quaternion in the project's (w, x, y, z) convention."""

    w,x,y,z = quaternion

    if not all(isfinite(component) for component in quaternion):
        raise ValueError("quaternion components must all be finite")

    norm_squared = (w * w) + (x * x) + (y * y) + (z * z)
    if norm_squared<= 1e-24:
        raise ValueError("cannot normalise a zero or near zero quaternion")

    norm = sqrt(norm_squared)
    return (w/norm, x/norm, y/norm, z/norm)


def quaternion_multiply(left: QuaternionWxyz, right: QuaternionWxyz) -> QuaternionWxyz:
    """return left x right, applying right before left"""

    if not all(isfinite(component) for component in (*left, *right)):
        raise ValueError("All quaternion componrntd must be finite")

    left_w, left_x, left_y, left_z = left
    right_w, right_x, right_y, right_z = right

    return (
        left_w * right_w - left_x * right_x - left_y * right_y - left_z * right_z,
        left_w * right_x + left_x * right_w + left_y * right_z - left_z * right_y,
        left_w * right_y - left_x * right_z + left_y * right_w + left_z * right_x,
        left_w * right_z + left_x * right_y - left_y * right_x + left_z * right_w,
    )


def quaternion_conjugate(quaternion: QuaternionWxyz,) -> QuaternionWxyz:
    """Return the conjugate of a quaternion"""


    if not all(isfinite(component) for component in quaternion):
        raise ValueError("Quaternion components must all be finite.")

    w, x, y, z = quaternion
    return (w, -x, -y, -z)


def vector_magnitude(vector: Vector3) -> float:
    """Return the eucl length of a finite 3d vec"""

    if not all(isfinite(component) for component in vector):
        raise ValueError("Quaternion components must all be finite.")

    x, y, z = vector
    return sqrt(x*x + y*y + z*z)


def normalize_vector(vector: Vector3) -> Vector3:
    """Return a unit vector with the same direction as the input vector."""
    magnitude  = vector_magnitude(vector)
    if magnitude <= 1e-12:
        raise ValueError("Cannot normalize a zero or near-zero vector. ")
    x,y,z = vector
    return (x / magnitude, y / magnitude, z / magnitude)


def quaternion_from_vector_alignment(
    from_vector: Vector3,
    to_vector: Vector3,
)-> QuaternionWxyz:
    """Return the shortest rotation that maps from_vector onto to_vector."""

    from_x, from_y, from_z = normalize_vector(from_vector)
    to_x, to_y, to_z = normalize_vector(to_vector)

    dot_product = ( from_x * to_x + from_y * to_y + from_z * to_z)
    dot_product = max(-1, min(1.0, dot_product))

    if dot_product >= 1.0 - 1e-12:
        return (1.0, 0.0, 0.0, 0.0)
    if dot_product <= -1.0 + 1e-12:
        # For opposite vectors, choose any stable axis perpendicular to
        # from_vector, then rotate 180 degrees about that axis. 
        if abs(from_x) <= abs(from_y) and abs(from_x) <= abs(from_z):
            reference = (1.0, 0.0, 0.0)
        elif abs(from_y) <= abs(from_z):
            reference = (0.0, 1.0, 0.0)
        else:
            reference = (0.0, 0.0, 1.0)
        reference_x, reference_y, reference_z = reference
        axis = normalize_vector((
                from_y * reference_z - from_z * reference_y,
                from_z * reference_x - from_x * reference_z,
                from_x * reference_y - from_y * reference_x,
            )
        )
        return (0.0, axis[0], axis[1], axis[2])


    cross_x = from_y * to_z - from_z * to_y
    cross_y = from_z * to_x - from_x * to_z
    cross_z = from_x * to_y - from_y * to_x


    return normalize_quaternion((1.0 + dot_product, cross_x, cross_y, cross_z))

def quaternion_from_rotation_vector(rotation_vector_rad: Vector3,) -> QuaternionWxyz:
    """Convert an axis-angle rotation vector in radians into a quaternion."""

    angle_rad = vector_magnitude(rotation_vector_rad)
    if angle_rad <= 1e-12:
        return (1.0, 0.0, 0.0, 0.0)

    half_angle_rad = angle_rad / 2.0
    scale = sin(half_angle_rad) / angle_rad

    rotation_x, rotation_y, rotation_z = rotation_vector_rad
    return normalize_quaternion(
        (
            cos(half_angle_rad),
            rotation_x * scale,
            rotation_y * scale,
            rotation_z * scale,
        )
    )


def rotate_vector(
        quaternion: QuaternionWxyz, vector: Vector3,) -> Vector3:
    """Rotate a vector by a sensor-to-navigation quaternion"""
    unit_quaternion = normalize_quaternion(quaternion)
    vector_quaternion: QuaternionWxyz = (0.0, vector[0], vector[1], vector[2])

    rotated = quaternion_multiply(quaternion_multiply(unit_quaternion, vector_quaternion),quaternion_conjugate(unit_quaternion),)

    return (rotated[1], rotated[2], rotated[3])


def propagate_orientation(orientation_wxyz: QuaternionWxyz, angular_velocity_radps: Vector3, delta_time_s: float, ) -> QuaternionWxyz:
    """Propagate sensor-to-navigation orientation using gyroscope motion."""

    if not isfinite(delta_time_s) or delta_time_s <= 0.0:
        raise ValueError("delta_time_s must be finite and positive.")

    angular_x, angular_y, angular_z = angular_velocity_radps
    rotation_vector_rad = ( angular_x * delta_time_s, angular_y * delta_time_s, angular_z * delta_time_s)

    delta_rotation = quaternion_from_rotation_vector(rotation_vector_rad)

    #the gyro is experssed in sensor axes, so its incremental rotation is applied on the right of the current sesnor to nav orientation

    return normalize_quaternion(quaternion_multiply(orientation_wxyz, delta_rotation))


def is_acceleration_trustworthy(acceleration_mps2: Vector3, expected_gravity_mps2: float, tolerance_mps2: float,) -> bool:
    """Return whether acceleration magnitude is close enough to gravity."""

    if not isfinite(expected_gravity_mps2) or expected_gravity_mps2 <= 0.0:
        raise ValueError("expected_gravity_mps2 must be finite and positive.")

    if not isfinite(tolerance_mps2) or tolerance_mps2 < 0.0:
        raise ValueError("tolerance_mps2 must be finite and non-negative.")

    return (
        abs(vector_magnitude(acceleration_mps2) - expected_gravity_mps2)
        <= tolerance_mps2
    )


class ImuOrientationEstimator:
    """Estimate tilt with gyroscope propagation and gated accelerometer correction."""

    def __init__(
        self,
        *,
        accelerometer_correction_gain_per_s: float,
        acceleration_trust_tolerance_mps2: float,
        expected_gravity_mps2: float = 9.80665,
        initial_orientation_wxyz: QuaternionWxyz = (1.0, 0.0, 0.0, 0.0),
    ) -> None:
        """Create an estimator for one physical IMU stream."""

        if (
            not isfinite(accelerometer_correction_gain_per_s)
            or accelerometer_correction_gain_per_s < 0.0
        ):
            raise ValueError(
                "accelerometer_correction_gain_per_s must be finite and non-negative."
            )

        if (
            not isfinite(acceleration_trust_tolerance_mps2)
            or acceleration_trust_tolerance_mps2 < 0.0
        ):
            raise ValueError(
                "acceleration_trust_tolerance_mps2 must be finite and non-negative."
            )

        if not isfinite(expected_gravity_mps2) or expected_gravity_mps2 <= 0.0:
            raise ValueError("expected_gravity_mps2 must be finite and positive.")

        self._accelerometer_correction_gain_per_s = (
            accelerometer_correction_gain_per_s
        )
        self._acceleration_trust_tolerance_mps2 = (
            acceleration_trust_tolerance_mps2
        )
        self._expected_gravity_mps2 = expected_gravity_mps2

        self._initial_orientation_wxyz = normalize_quaternion(
            initial_orientation_wxyz
        )
        self._orientation_wxyz = self._initial_orientation_wxyz
        self._last_timestamp_ns: int | None = None

        self._source: SensorSource | None = None
        self._source_id: str | None = None


    def _register_or_validate_stream(
        self,
        sample: SynchronizedImuSample,
    ) -> None:
        """Bind the estimator to its first IMU source and device identifier."""

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
                "ImuOrientationEstimator."
            )


    def update(self, sample: SynchronizedImuSample) -> OrientationEstimate:
        """Update orientation from one synchronized IMU sample."""

        if sample.frame is not CoordinateFrame.SENSOR:
            raise ValueError(
                "ImuOrientationEstimator expects synchronized SENSOR-frame data."
            )

        self._register_or_validate_stream(sample)

        if (
            self._last_timestamp_ns is not None
            and sample.timestamp_ns <= self._last_timestamp_ns
        ):
            raise ValueError(
                "Orientation timestamps must be strictly increasing."
            )

        acceleration_is_trusted = is_acceleration_trustworthy(
            sample.acceleration_mps2,
            self._expected_gravity_mps2,
            self._acceleration_trust_tolerance_mps2,
        )

        if self._last_timestamp_ns is None:
            # On the first trustworthy sample, correct initial roll/pitch by
            # mapping measured specific force toward navigation up. Yaw remains
            # whatever was supplied by initial_orientation_wxyz.
            if acceleration_is_trusted:
                measured_up_navigation = rotate_vector(
                    self._orientation_wxyz,
                    normalize_vector(sample.acceleration_mps2),
                )
                tilt_correction = quaternion_from_vector_alignment(
                    measured_up_navigation,
                    _NAVIGATION_UP,
                )
                self._orientation_wxyz = normalize_quaternion(
                    quaternion_multiply(
                        tilt_correction,
                        self._orientation_wxyz,
                    )
                )

            self._last_timestamp_ns = sample.timestamp_ns
            return OrientationEstimate(
                timestamp_ns=sample.timestamp_ns,
                source=sample.source,
                source_id=sample.source_id,
                sensor_to_navigation_wxyz=self._orientation_wxyz,
            )

        delta_time_s = (
            sample.timestamp_ns - self._last_timestamp_ns
        ) * 1e-9

        updated_orientation = propagate_orientation(
            self._orientation_wxyz,
            sample.angular_velocity_radps,
            delta_time_s,
        )

        if acceleration_is_trusted:
            measured_up_navigation = rotate_vector(
                updated_orientation,
                normalize_vector(sample.acceleration_mps2),
            )

            # Cross(measured_up, desired_up): the small navigation-frame
            # rotation that moves the measured gravity direction toward up.
            correction_axis_navigation = (
                measured_up_navigation[1],
                -measured_up_navigation[0],
                0.0,
            )
            correction_rotation_vector = tuple(
                self._accelerometer_correction_gain_per_s
                * delta_time_s
                * component
                for component in correction_axis_navigation
            )

            correction = quaternion_from_rotation_vector(
                correction_rotation_vector
            )
            updated_orientation = normalize_quaternion(
                quaternion_multiply(correction, updated_orientation)
            )

        self._orientation_wxyz = updated_orientation
        self._last_timestamp_ns = sample.timestamp_ns

        return OrientationEstimate(
            timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            sensor_to_navigation_wxyz=self._orientation_wxyz,
        )


    def reset(self, initial_orientation_wxyz: QuaternionWxyz | None = None,) -> None:
        """Clear timing and source state after a confirmed sensor-session reset."""

        if initial_orientation_wxyz is not None:
            self._initial_orientation_wxyz = normalize_quaternion(
                initial_orientation_wxyz
            )

        self._orientation_wxyz = self._initial_orientation_wxyz
        self._last_timestamp_ns = None
        self._source = None
        self._source_id = None

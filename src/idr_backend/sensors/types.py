"""Sensor data contracts and coordinate-frame conventions for IDR.

These definitions describe what data is allowed to enter and leave the sensor
pipeline. They intentionally contain no validation or transformation logic:
normalization, synchronization, orientation, calibration, and gravity removal
own that behavior in their respective modules.
"""

from dataclasses import dataclass
from enum import StrEnum


class CoordinateFrame(StrEnum):
    """Supported coordinate frames for vector-valued sensor data.

    Every acceleration and angular-velocity vector must carry one of these
    frames. There is deliberately no ``UNKNOWN`` member: observations with an
    unknown frame must be rejected at ingestion instead of guessed later.
    """

    # Raw axes reported by the physical phone or external IMU. Their physical
    # orientation is source-specific and is resolved by calibration.
    SENSOR = "sensor"

    # Vehicle body axes: x=forward, y=left, z=up. This right-handed frame is
    # used by the velocity model, non-holonomic constraints, and vehicle motion.
    VEHICLE_FLU = "vehicle_flu"

    # Local world axes: x=east, y=north, z=up. GNSS positions and the EKF
    # navigation state are represented relative to this frame.
    NAVIGATION_ENU = "navigation_enu"


class SensorKind(StrEnum):
    """Kinds of vector-valued inertial sensor readings used by IDR.

    Sensor kind answers *what was measured*; it is distinct from the physical
    device that produced the reading.
    """

    # Measures specific force: vehicle motion plus gravity while in the sensor
    # frame. Gravity removal happens later, after orientation is known.
    ACCELEROMETER = "accelerometer"

    # Measures angular velocity around the sensor axes. It is rotated into the
    # vehicle frame later but is never gravity-compensated.
    GYROSCOPE = "gyroscope"


class SensorSource(StrEnum):
    """Physical source supplying an inertial sensor reading.

    Source answers *where the reading came from*. A phone and an external IMU
    can both supply accelerometer and gyroscope readings, but their noise,
    sampling rate, clock behavior, and mounting can differ.
    """

    PHONE = "phone"
    EXTERNAL_IMU = "external_imu"


class MeasurementUnit(StrEnum):
    """Units accepted at the raw sensor boundary.

    Phone APIs usually already use SI units, but external IMUs may report
    standard gravity or degrees per second. The normalizer converts every
    accepted raw reading into SI before any filter or model sees it.
    """

    METERS_PER_SECOND_SQUARED = "m/s^2"
    RADIANS_PER_SECOND = "rad/s"
    STANDARD_GRAVITY = "g"
    DEGREES_PER_SECOND = "deg/s"


# A 3D vector is always ordered as (x, y, z) in the sample's declared frame.
Vector3 = tuple[float, float, float]

# Quaternion ordering is explicitly (w, x, y, z). Some libraries use a
# different ordering, so the alias makes accidental mixing visible in reviews.
QuaternionWxyz = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class RawSensorSample:
    """One unmodified vector reading received from a physical sensor.

    This mirrors one native accelerometer or gyroscope callback. Its unit and
    frame are preserved so that the normalizer can convert and validate rather
    than assume. Raw samples are not supplied to the EKF or final GRU model.
    """

    # Monotonic session timestamp in nanoseconds, not wall-clock time. Filters
    # use elapsed time; a wall clock can jump because of timezone/NTP changes.
    timestamp_ns: int

    # ``source_id`` distinguishes physical devices of the same source type,
    # such as "phone-primary" and "fog-imu-01".
    source: SensorSource
    source_id: str
    kind: SensorKind

    # Raw x/y/z measurement, with its unit and coordinate frame stated below.
    value: Vector3
    unit: MeasurementUnit
    frame: CoordinateFrame

    # Preserved opaque platform metadata; its meaning is adapter-specific and
    # must not be treated as a universal confidence score.
    vendor_accuracy: int | None = None


@dataclass(frozen=True, slots=True)
class NormalizedSensorSample:
    """One validated sensor reading expressed in IDR's SI-unit convention.

    The unit field is intentionally absent: accelerometer values are guaranteed
    to be m/s^2 and gyroscope values are guaranteed to be rad/s. The frame can
    still be SENSOR because normalization does not estimate orientation.
    """

    timestamp_ns: int
    source: SensorSource
    source_id: str
    kind: SensorKind
    value: Vector3
    frame: CoordinateFrame


@dataclass(frozen=True, slots=True)
class SynchronizedImuSample:
    """Aligned SI-unit accelerometer and gyroscope readings in one frame.

    Phones emit the two sensors as independent callbacks. The synchronizer
    creates this sample only after it finds a sufficiently close pair from the
    same physical source and frame.
    """

    # Pipeline timestamp selected by the synchronizer for this paired sample.
    timestamp_ns: int
    source: SensorSource
    source_id: str
    frame: CoordinateFrame
    acceleration_mps2: Vector3
    angular_velocity_radps: Vector3

    # Kept for auditability and later skew checks; large separation means the
    # pair may be rejected even though each individual reading is valid.
    accelerometer_timestamp_ns: int
    gyroscope_timestamp_ns: int


@dataclass(frozen=True, slots=True)
class OrientationEstimate:
    """Estimated rotation from the sensor frame into navigation ENU.

    Orientation answers "where is the sensor relative to the world?" It is
    distinct from mounting calibration, which answers "how is the sensor
    attached relative to the vehicle?"
    """

    timestamp_ns: int
    source: SensorSource
    source_id: str
    sensor_to_navigation_wxyz: QuaternionWxyz


@dataclass(frozen=True, slots=True)
class VehicleCalibration:
    """Estimated rotation from the sensor frame into vehicle Forward-Left-Up.

    Dynamic calibration identifies the vehicle's forward axis despite arbitrary
    phone mounting. It may begin with low confidence and improve only after
    braking, acceleration, and turning provide enough driving evidence.
    """

    timestamp_ns: int
    source: SensorSource
    source_id: str
    sensor_to_vehicle_wxyz: QuaternionWxyz

    # Intended range: 0.0 (untrusted) through 1.0 (high confidence). Future
    # validation will enforce the range and define the threshold for use.
    confidence: float


@dataclass(frozen=True, slots=True)
class VehicleImuSample:
    """Calibrated, vehicle-frame IMU data ready for velocity prediction and fusion.

    This is the cleaned output of the deterministic preprocessing pipeline. The
    acceleration vector has been rotated into FLU and had gravity removed. The
    gyroscope has been rotated into FLU but is not gravity-compensated.
    """

    timestamp_ns: int
    source: SensorSource
    source_id: str

    # These two vectors form the six clean channels used to retrain the GRU.
    linear_acceleration_mps2: Vector3
    angular_velocity_radps: Vector3

    # Needed by navigation fusion; the velocity GRU itself mainly consumes the
    # two cleaned vectors above.
    vehicle_to_navigation_wxyz: QuaternionWxyz
    calibration_confidence: float


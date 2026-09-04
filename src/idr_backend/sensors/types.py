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

# A 2D point in local East-North coordinates, ordered as (east, north).
Vector2 = tuple[float, float]

# A fixed 3×3 covariance matrix. Rows and columns follow the vector's frame.
Matrix3 = tuple[Vector3, Vector3, Vector3]


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


@dataclass(frozen=True, slots=True)
class GnssFix:
    """One raw position and motion observation from a GNSS receiver.

    GNSS arrives slower than IMU and may disappear during a tunnel or urban
    canyon. Missing GNSS must stay missing: dead reckoning is estimated later
    by fusion, not fabricated in this input contract.
    """

    # Same monotonic session-time clock used by IMU. This lets us associate a
    # nearby GNSS reading with sensor samples without relying on wall-clock time.
    timestamp_ns: int

    # Physical receiver identity, usually something like "phone-primary".
    # This stays separate from SensorSource because a future external GNSS
    # receiver is not necessarily an IMU device.
    receiver_id: str

    # Raw WGS-84 coordinates from the receiver. We keep degrees here; the GNSS
    # adapter/fusion layer will project them into local ENU metres when needed.
    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None

    # Receiver-reported position quality. None means the source did not supply
    # it, not that accuracy is perfect or zero.
    horizontal_accuracy_m: float | None
    vertical_accuracy_m: float | None

    # Optional receiver motion observations. Speed is SI m/s. Course is the
    # usual GNSS course-over-ground: clockwise from true north, in radians.
    # It describes movement direction, not phone orientation.
    speed_mps: float | None = None
    speed_accuracy_mps: float | None = None
    course_over_ground_rad: float | None = None
    course_accuracy_rad: float | None = None


@dataclass(frozen=True, slots=True)
class VelocityObservation:
    """One scalar speed prediction produced from a clean IMU window.

    This is the velocity engine's estimate only. Its uncertainty is deliberately
    separate, because the uncertainty engine owns variance estimation.
    """

    # Timestamp at the end of the causal IMU window used for this prediction.
    timestamp_ns: int

    # Identifies the IMU device whose clean samples formed the input window.
    source_id: str

    # Makes the model input interval auditable during replay and debugging.
    window_start_timestamp_ns: int

    # Predicted ground-speed magnitude, never a three-dimensional velocity.
    speed_mps: float

    # Versioned model identity, for example "gru-v1" or "cnn-v1".
    model_id: str


@dataclass(frozen=True, slots=True)
class UncertaintyEstimate:
    """Calibrated uncertainty associated with one velocity prediction.

    The uncertainty engine publishes the final usable variance after applying
    learned heteroscedastic prediction and deterministic safety bounds.
    """

    timestamp_ns: int

    # Must point to the exact VelocityObservation this variance belongs to.
    velocity_observation_timestamp_ns: int
    model_id: str

    # Variance of scalar speed, with units (m/s)^2 = m²/s².
    speed_variance_m2ps2: float

    # Lets replay/debugging distinguish a calibrated learned value from a
    # temporary fallback before the uncertainty model is ready.
    is_calibrated: bool
    used_heuristic_bound: bool


class TravelDirection(StrEnum):
    """Allowed travel direction along a directed road-graph edge."""

    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True, slots=True)
class RoadCandidate:
    """One nearby directed road-edge hypothesis for map matching."""

    timestamp_ns: int

    # Stable identity within one candidate-generation step.
    candidate_id: str

    # Identifies the offline graph and the directed OSM-derived edge.
    graph_id: str
    edge_id: str
    travel_direction: TravelDirection

    # Nearest point on that road in the local ENU map frame.
    snap_position_enu_m: Vector2

    # Geometric evidence before HMM emission scoring.
    lateral_distance_m: float
    road_heading_enu_rad: float


@dataclass(frozen=True, slots=True)
class RoadContextPrior:
    """Road-derived speed prior for one candidate, using prior-cycle HMM belief.

    It is produced from road rules and future quantile ML. Its belief timestamp
    must be older than the current step, avoiding a same-timestep feedback loop.
    """

    timestamp_ns: int
    source_belief_timestamp_ns: int

    candidate_id: str
    edge_id: str

    # Quantile-model speed outputs. The later rules/model layer must guarantee
    # p10 <= p50 <= p90 before publishing this object.
    speed_p10_mps: float
    speed_p50_mps: float
    speed_p90_mps: float

    # Explicit legal/rule bound when known; None means no usable map rule.
    rule_speed_limit_mps: float | None

    # Confidence in this road hypothesis/prior, from 0.0 to 1.0.
    confidence: float


class NavigationMode(StrEnum):
    """How strongly the navigation estimate is currently GNSS-aided."""

    GNSS_AIDED = "gnss_aided"
    DEAD_RECKONING = "dead_reckoning"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class NavigationEstimate:
    """Navigation state published after fusion and optional map matching."""

    timestamp_ns: int
    mode: NavigationMode

    # Local East-North-Up position and velocity estimated by the EKF.
    position_enu_m: Vector3
    velocity_enu_mps: Vector3

    # Vehicle orientation relative to ENU, ordered as (w, x, y, z).
    vehicle_to_navigation_wxyz: QuaternionWxyz

    # Small output covariance summaries. The full 15×15 EKF covariance remains
    # internal to fusion; callers normally need these physically meaningful parts.
    position_covariance_enu_m2: Matrix3
    velocity_covariance_enu_m2ps2: Matrix3
    heading_variance_rad2: float

    # Filled only when map matching has enough belief to publish a road result.
    matched_road_edge_id: str | None
    map_match_confidence: float | None
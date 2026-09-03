"""Dynamic phone-to-vehicle calibration for the vehicle FLU frame.

Calibration is a mostly fixed SENSOR-to-vehicle rotation. It is estimated from
trusted mounting evidence, held while stable, and invalidated during a likely
phone remount. It never guesses a vehicle forward direction from arbitrary
single IMU readings.
"""


from dataclasses import dataclass
from enum import StrEnum
from math import acos, isfinite, pi

from .orientation import (
    normalize_quaternion,
    normalize_vector,
    quaternion_from_vector_alignment,
    quaternion_multiply,
    rotate_vector,
    vector_magnitude,
)


from .types import (
    CoordinateFrame,
    QuaternionWxyz,
    SensorSource,
    SynchronizedImuSample,
    Vector3,
    VehicleCalibration,
)


_VEHICLE_FORWARD: Vector3 = (1.0, 0.0, 0.0)
_VEHICLE_UP: Vector3 = (0.0, 0.0, 1.0)


def rotate_imu_to_vehicle(sample: SynchronizedImuSample, calibration: VehicleCalibration, minimum_confidence: float) -> SynchronizedImuSample:
    """Rotate one synchronized SENSOR-frame IMU sample into vehicle FLU."""

    if not isfinite(minimum_confidence) or not 0.0 <= minimum_confidence <= 1.0:
        raise ValueError(
            "minimum_confidence must be finite and between 0.0 and 1.0."
        )

    if sample.frame is not CoordinateFrame.SENSOR:
        raise ValueError(
            "rotate_imu_to_vehicle expects a SENSOR-frame IMU sample."
        )

    if sample.source != calibration.source:
        raise ValueError(
            "Sample and calibration must belong to the same sensor source."
        )

    if sample.source_id != calibration.source_id:
        raise ValueError(
            "Sample and calibration must belong to the same physical device."
        )

    if calibration.timestamp_ns > sample.timestamp_ns:
        raise ValueError(
            "Cannot apply a calibration estimate to an earlier IMU sample."
        )

    if not isfinite(calibration.confidence) or not 0.0 <= calibration.confidence <= 1.0:
        raise ValueError(
            "Calibration confidence must be finite and between 0.0 and 1.0."
        )

    if calibration.confidence < minimum_confidence:
        raise ValueError(
            "Calibration confidence is below the required threshold."
        )

    return SynchronizedImuSample(
        timestamp_ns=sample.timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        frame=CoordinateFrame.VEHICLE_FLU,
        acceleration_mps2=rotate_vector(
            calibration.sensor_to_vehicle_wxyz,
            sample.acceleration_mps2,
        ),
        angular_velocity_radps=rotate_vector(
            calibration.sensor_to_vehicle_wxyz,
            sample.angular_velocity_radps,
        ),
        accelerometer_timestamp_ns=sample.accelerometer_timestamp_ns,
        gyroscope_timestamp_ns=sample.gyroscope_timestamp_ns,
    )


def derive_sensor_to_vehicle_quaternion(vehicle_up_in_sensor: Vector3, vehicle_forward_in_sensor: Vector3) -> QuaternionWxyz:
    """Derive a SENSOR-to-vehicle-FLU rotation from known mounting axes."""

    normalized_up_in_sensor = normalize_vector(vehicle_up_in_sensor)

    # First level the sensor: map the vehicle's up direction onto FLU up.
    sensor_to_level = quaternion_from_vector_alignment(
        normalized_up_in_sensor,
        _VEHICLE_UP,
    )

    # Express the known forward direction after leveling, then discard its
    # small remaining vertical component before resolving yaw.
    forward_in_level = rotate_vector(
        sensor_to_level,
        vehicle_forward_in_sensor,
    )
    horizontal_forward_in_level = (
        forward_in_level[0],
        forward_in_level[1],
        0.0,
    )

    if vector_magnitude(horizontal_forward_in_level) <= 1e-12:
        raise ValueError(
            "vehicle_forward_in_sensor must not be parallel to vehicle up."
        )

    normalized_horizontal_forward = normalize_vector(
        horizontal_forward_in_level
    )

    # A yaw-only rotation maps the leveled forward direction onto FLU forward.
    level_to_vehicle = quaternion_from_vector_alignment(
        normalized_horizontal_forward,
        _VEHICLE_FORWARD,
    )

    return normalize_quaternion(
        quaternion_multiply(level_to_vehicle, sensor_to_level)
    )


class CalibrationPhase(StrEnum):
    """Current confidence state of one physical device's mounting estimate."""

    WARMING_UP = "warming_up"
    TRACKING = "tracking"
    DEGRADED = "degraded"
    RECALIBRATING = "recalibrating"


@dataclass(frozen=True, slots=True)
class CalibrationEvidence:
    """One trustworthy observation of vehicle axes in sensor coordinates."""

    timestamp_ns: int
    source: SensorSource
    source_id: str

    # Vehicle up and known positive vehicle forward, both expressed in SENSOR
    # coordinates. They are not arbitrary raw acceleration vectors.
    vehicle_up_in_sensor: Vector3
    vehicle_forward_in_sensor: Vector3

    # Confidence in this individual observation, from 0.0 through 1.0.
    confidence: float


def quaternion_angular_distance(
    left: QuaternionWxyz,
    right: QuaternionWxyz,
) -> float:
    """Return the smallest rotational difference between two quaternions."""

    left_unit = normalize_quaternion(left)
    right_unit = normalize_quaternion(right)

    alignment = abs(
        left_unit[0] * right_unit[0]
        + left_unit[1] * right_unit[1]
        + left_unit[2] * right_unit[2]
        + left_unit[3] * right_unit[3]
    )
    alignment = max(-1.0, min(1.0, alignment))

    return 2.0 * acos(alignment)


def average_quaternions(
    weighted_quaternions: list[tuple[QuaternionWxyz, float]],
) -> QuaternionWxyz:
    """Return a confidence-weighted mean of mutually similar rotations."""

    if not weighted_quaternions:
        raise ValueError("At least one quaternion is required.")

    reference = normalize_quaternion(weighted_quaternions[0][0])

    total_w = 0.0
    total_x = 0.0
    total_y = 0.0
    total_z = 0.0
    total_weight = 0.0

    for quaternion, weight in weighted_quaternions:
        if not isfinite(weight) or weight <= 0.0:
            raise ValueError("Quaternion weights must be finite and positive.")

        w, x, y, z = normalize_quaternion(quaternion)

        # q and -q are identical rotations. Align signs before averaging so
        # they reinforce each other instead of cancelling toward zero.
        if (
            reference[0] * w
            + reference[1] * x
            + reference[2] * y
            + reference[3] * z
        ) < 0.0:
            w, x, y, z = -w, -x, -y, -z

        total_w += weight * w
        total_x += weight * x
        total_y += weight * y
        total_z += weight * z
        total_weight += weight

    if total_weight <= 0.0:
        raise ValueError("Total quaternion weight must be positive.")

    return normalize_quaternion(
        (
            total_w / total_weight,
            total_x / total_weight,
            total_y / total_weight,
            total_z / total_weight,
        )
    )


class DynamicVehicleCalibrator:
    """Collect stable mounting evidence and publish safe vehicle calibration."""

    def __init__(
        self,
        *,
        minimum_evidence_count: int,
        minimum_evidence_confidence: float,
        maximum_disagreement_rad: float,
        remount_evidence_count: int,
    ) -> None:
        """Create a stateful calibrator for one physical IMU."""

        if minimum_evidence_count <= 0:
            raise ValueError("minimum_evidence_count must be positive.")

        if remount_evidence_count <= 0:
            raise ValueError("remount_evidence_count must be positive.")

        if (
            not isfinite(minimum_evidence_confidence)
            or not 0.0 <= minimum_evidence_confidence <= 1.0
        ):
            raise ValueError(
                "minimum_evidence_confidence must be between 0.0 and 1.0."
            )

        if (
            not isfinite(maximum_disagreement_rad)
            or not 0.0 < maximum_disagreement_rad <= pi
        ):
            raise ValueError(
                "maximum_disagreement_rad must be in the range (0, pi]."
            )

        self._minimum_evidence_count = minimum_evidence_count
        self._minimum_evidence_confidence = minimum_evidence_confidence
        self._maximum_disagreement_rad = maximum_disagreement_rad
        self._remount_evidence_count = remount_evidence_count
        self._maximum_retained_candidates = max(
            minimum_evidence_count,
            remount_evidence_count,
        ) * 2

        self._phase = CalibrationPhase.WARMING_UP
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None

        self._warmup_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._stable_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._remount_candidates: list[tuple[QuaternionWxyz, float]] = []
        self._calibration: VehicleCalibration | None = None


    @property
    def phase(self) -> CalibrationPhase:
        """Return the current calibration state."""

        return self._phase


    @property
    def calibration(self) -> VehicleCalibration | None:
        """Return the latest calibration, or None while still warming up."""

        return self._calibration


    def _register_or_validate_evidence(
        self,
        evidence: CalibrationEvidence,
    ) -> None:
        """Validate ordering and bind this calibrator to one physical device."""

        if evidence.timestamp_ns < 0:
            raise ValueError("Calibration evidence timestamp must be non-negative.")

        if not evidence.source_id.strip():
            raise ValueError("Calibration evidence source_id must not be blank.")

        if (
            not isfinite(evidence.confidence)
            or not 0.0 <= evidence.confidence <= 1.0
        ):
            raise ValueError(
                "Calibration evidence confidence must be between 0.0 and 1.0."
            )

        if (
            self._last_timestamp_ns is not None
            and evidence.timestamp_ns <= self._last_timestamp_ns
        ):
            raise ValueError(
                "Calibration evidence timestamps must be strictly increasing."
            )

        if self._source is None:
            self._source = evidence.source
            self._source_id = evidence.source_id
        elif (
            evidence.source != self._source
            or evidence.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMUs in one DynamicVehicleCalibrator."
            )

        self._last_timestamp_ns = evidence.timestamp_ns


    def _append_if_consistent(
        self,
        candidates: list[tuple[QuaternionWxyz, float]],
        candidate: QuaternionWxyz,
        confidence: float,
    ) -> bool:
        """Append a candidate only if it agrees with its existing cluster."""

        if candidates:
            cluster_orientation = average_quaternions(candidates)
            disagreement_rad = quaternion_angular_distance(
                candidate,
                cluster_orientation,
            )
            if disagreement_rad > self._maximum_disagreement_rad:
                return False

        candidates.append((candidate, confidence))

        if len(candidates) > self._maximum_retained_candidates:
            candidates.pop(0)

        return True


    def _confidence_from_candidates(self, candidates: list[tuple[QuaternionWxyz, float]],) -> float:
        """Calculate calibration confidence from evidence quality and agreement."""

        if not candidates:
            return 0.0

        mean_orientation = average_quaternions(candidates)
        total_weight = sum(weight for _, weight in candidates)

        mean_input_confidence = total_weight / len(candidates)
        mean_disagreement_rad = (
            sum(
                weight
                * quaternion_angular_distance(quaternion, mean_orientation)
                for quaternion, weight in candidates
            )
            / total_weight
        )

        agreement = max(
            0.0,
            1.0 - mean_disagreement_rad / self._maximum_disagreement_rad,
        )
        evidence_support = min(
            1.0,
            len(candidates) / self._minimum_evidence_count,
        )

        return min(
            1.0,
            mean_input_confidence * agreement * evidence_support,
        )
    

    def _publish_calibration(
        self,
        timestamp_ns: int,
    ) -> VehicleCalibration:
        """Build and retain a calibration from the current stable cluster."""

        if self._source is None or self._source_id is None:
            raise RuntimeError("Cannot publish calibration before source binding.")

        sensor_to_vehicle = average_quaternions(self._stable_candidates)
        confidence = self._confidence_from_candidates(
            self._stable_candidates
        )

        self._calibration = VehicleCalibration(
            timestamp_ns=timestamp_ns,
            source=self._source,
            source_id=self._source_id,
            sensor_to_vehicle_wxyz=sensor_to_vehicle,
            confidence=confidence,
        )
        return self._calibration


    def _degrade_calibration(self, timestamp_ns: int) -> VehicleCalibration | None:
        """Mark the latest calibration unusable while retaining its rotation."""

        if self._calibration is None:
            return None

        self._calibration = VehicleCalibration(
            timestamp_ns=timestamp_ns,
            source=self._calibration.source,
            source_id=self._calibration.source_id,
            sensor_to_vehicle_wxyz=self._calibration.sensor_to_vehicle_wxyz,
            confidence=0.0,
        )
        return self._calibration

    def update(self, evidence: CalibrationEvidence) -> VehicleCalibration | None:
        """Consume one evidence item and return the latest calibration state."""

        self._register_or_validate_evidence(evidence)

        if evidence.confidence < self._minimum_evidence_confidence:
            return self._degrade_calibration(evidence.timestamp_ns)

        candidate = derive_sensor_to_vehicle_quaternion(
            evidence.vehicle_up_in_sensor,
            evidence.vehicle_forward_in_sensor,
        )

        if self._calibration is None:
            accepted = self._append_if_consistent(
                self._warmup_candidates,
                candidate,
                evidence.confidence,
            )

            if not accepted:
                # Start a new possible initial cluster rather than mixing
                # incompatible mounting hypotheses.
                self._warmup_candidates = [(candidate, evidence.confidence)]

            if len(self._warmup_candidates) < self._minimum_evidence_count:
                self._phase = CalibrationPhase.WARMING_UP
                return None

            self._stable_candidates = list(self._warmup_candidates)
            self._warmup_candidates.clear()
            self._phase = CalibrationPhase.TRACKING
            return self._publish_calibration(evidence.timestamp_ns)

        disagreement_rad = quaternion_angular_distance(
            candidate,
            self._calibration.sensor_to_vehicle_wxyz,
        )

        if disagreement_rad <= self._maximum_disagreement_rad:
            self._append_if_consistent(
                self._stable_candidates,
                candidate,
                evidence.confidence,
            )
            self._remount_candidates.clear()
            self._phase = CalibrationPhase.TRACKING
            return self._publish_calibration(evidence.timestamp_ns)

        # A new candidate disagrees with the known mounting orientation.
        accepted_as_remount = self._append_if_consistent(
            self._remount_candidates,
            candidate,
            evidence.confidence,
        )

        if not accepted_as_remount:
            self._remount_candidates = [(candidate, evidence.confidence)]

        if len(self._remount_candidates) < self._remount_evidence_count:
            self._phase = (
                CalibrationPhase.RECALIBRATING
                if len(self._remount_candidates) > 1
                else CalibrationPhase.DEGRADED
            )
            return self._degrade_calibration(evidence.timestamp_ns)

        # Several mutually consistent observations support a new mounting.
        self._stable_candidates = list(self._remount_candidates)
        self._remount_candidates.clear()
        self._phase = CalibrationPhase.TRACKING
        return self._publish_calibration(evidence.timestamp_ns)


    def reset(self) -> None:
        """Forget calibration state after a confirmed device-session restart."""

        self._phase = CalibrationPhase.WARMING_UP
        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
        self._warmup_candidates.clear()
        self._stable_candidates.clear()
        self._remount_candidates.clear()
        self._calibration = None
    

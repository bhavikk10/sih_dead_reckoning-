"""Concrete GNSS and learned-speed observations for the generic EKF boundary.

``measurements.py`` deliberately knows only the algebra of a linearised EKF
measurement.  This module owns the domain conversion from WGS-84 GNSS and a
scalar learned-speed prediction into that generic boundary, keeping coordinate
frames and covariance assumptions visible in one reviewable place.
"""

from dataclasses import dataclass
from math import cos, isfinite, radians, sin

import numpy as np

from ..sensors.types import GnssFix, UncertaintyEstimate, VelocityObservation
from .measurements import LinearisedMeasurement, MeasurementKind
from .propagation import skew_symmetric, vehicle_to_navigation_rotation
from .state import ATTITUDE, POSITION, VELOCITY, ErrorStateEkfState


_WGS84_SEMI_MAJOR_AXIS_M = 6_378_137.0
_WGS84_FLATTENING = 1.0 / 298.257_223_563
_WGS84_ECCENTRICITY_SQUARED = _WGS84_FLATTENING * (2.0 - _WGS84_FLATTENING)


@dataclass(frozen=True, slots=True)
class FusionMeasurementConfig:
    """Innovation gates and GNSS association policy for a live EKF stream."""

    # The GNSS fix is associated with the first later IMU state.  This keeps
    # the current no-replay EKF causal; an old fix is safer to omit than apply
    # at the wrong state time.
    maximum_gnss_association_age_ns: int

    # Chi-square gates: 2D GNSS position/velocity and 1D learned speed.
    gnss_position_nis_gate: float
    gnss_velocity_nis_gate: float
    velocity_model_nis_gate: float

    # Fixed-rate resampling can finish a model window just before the raw IMU
    # callback that advances the EKF. Associate only that first later state,
    # within this bounded causal delay; never replay a stale model output.
    maximum_velocity_model_association_age_ns: int = 150_000_000

    # After a long honest GNSS blackout, inertial drift can make even a good
    # returning fix fail the ordinary innovation gate. Do not reset on one
    # possibly multipath fix: require this much accepted-GNSS silence and this
    # many mutually nearby, receiver-quality-accepted positions first.
    recovery_reinitialization_silence_ns: int = 15_000_000_000
    recovery_required_consecutive_fixes: int = 2
    recovery_maximum_interfix_distance_m: float = 80.0

    def __post_init__(self) -> None:
        """Keep timing and innovation policies explicit and valid."""

        if self.maximum_gnss_association_age_ns <= 0:
            raise ValueError("maximum_gnss_association_age_ns must be positive.")
        if self.maximum_velocity_model_association_age_ns <= 0:
            raise ValueError(
                "maximum_velocity_model_association_age_ns must be positive."
            )
        if self.recovery_reinitialization_silence_ns <= 0:
            raise ValueError("recovery_reinitialization_silence_ns must be positive.")
        if self.recovery_required_consecutive_fixes < 2:
            raise ValueError("recovery_required_consecutive_fixes must be at least two.")
        if (
            not isfinite(self.recovery_maximum_interfix_distance_m)
            or self.recovery_maximum_interfix_distance_m <= 0.0
        ):
            raise ValueError("recovery_maximum_interfix_distance_m must be positive.")
        gates = (
            self.gnss_position_nis_gate,
            self.gnss_velocity_nis_gate,
            self.velocity_model_nis_gate,
        )
        if not all(isfinite(gate) and gate > 0.0 for gate in gates):
            raise ValueError("All measurement NIS gates must be finite and positive.")


@dataclass(frozen=True, slots=True)
class LocalEnuReference:
    """WGS-84 origin used to express one session in local ENU metres."""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0

    @classmethod
    def from_gnss_fix(cls, fix: GnssFix) -> "LocalEnuReference":
        """Anchor the session at a checked GNSS position, using sea level if needed."""

        return cls(
            latitude_deg=fix.latitude_deg,
            longitude_deg=fix.longitude_deg,
            altitude_m=0.0 if fix.altitude_m is None else fix.altitude_m,
        )

    def __post_init__(self) -> None:
        """Reject invalid WGS-84 values instead of projecting a guessed location."""

        if not (
            isfinite(self.latitude_deg)
            and -90.0 <= self.latitude_deg <= 90.0
            and isfinite(self.longitude_deg)
            and -180.0 <= self.longitude_deg <= 180.0
            and isfinite(self.altitude_m)
        ):
            raise ValueError("Local ENU reference must contain finite WGS-84 coordinates.")

    def project(self, fix: GnssFix) -> np.ndarray:
        """Convert a WGS-84 GNSS fix to [east, north, up] near this origin.

        ECEF-to-ENU retains correct local geometry without selecting a UTM zone
        or depending on a platform-specific projection database.  It is a local
        tangent-plane representation, so the session origin must be reset for a
        genuinely distant trip.
        """

        altitude_m = self.altitude_m if fix.altitude_m is None else fix.altitude_m
        point = _wgs84_ecef(fix.latitude_deg, fix.longitude_deg, altitude_m)
        origin = _wgs84_ecef(self.latitude_deg, self.longitude_deg, self.altitude_m)
        delta = point - origin

        latitude_rad = radians(self.latitude_deg)
        longitude_rad = radians(self.longitude_deg)
        rotation_ecef_to_enu = np.asarray(
            (
                (-sin(longitude_rad), cos(longitude_rad), 0.0),
                (
                    -sin(latitude_rad) * cos(longitude_rad),
                    -sin(latitude_rad) * sin(longitude_rad),
                    cos(latitude_rad),
                ),
                (
                    cos(latitude_rad) * cos(longitude_rad),
                    cos(latitude_rad) * sin(longitude_rad),
                    sin(latitude_rad),
                ),
            )
        )
        return rotation_ecef_to_enu @ delta


def _wgs84_ecef(
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
) -> np.ndarray:
    """Convert one finite WGS-84 coordinate to Earth-centred Cartesian metres."""

    if not (
        isfinite(latitude_deg)
        and -90.0 <= latitude_deg <= 90.0
        and isfinite(longitude_deg)
        and -180.0 <= longitude_deg <= 180.0
        and isfinite(altitude_m)
    ):
        raise ValueError("GNSS coordinate must be finite valid WGS-84 data.")

    latitude_rad = radians(latitude_deg)
    longitude_rad = radians(longitude_deg)
    sin_latitude = sin(latitude_rad)
    prime_vertical_radius = _WGS84_SEMI_MAJOR_AXIS_M / np.sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    return np.asarray(
        (
            (prime_vertical_radius + altitude_m) * cos(latitude_rad) * cos(longitude_rad),
            (prime_vertical_radius + altitude_m) * cos(latitude_rad) * sin(longitude_rad),
            (
                prime_vertical_radius * (1.0 - _WGS84_ECCENTRICITY_SQUARED)
                + altitude_m
            )
            * sin_latitude,
        )
    )


def build_gnss_position_measurement(
    *,
    state: ErrorStateEkfState,
    fix: GnssFix,
    local_enu_reference: LocalEnuReference,
    nis_gate: float,
) -> LinearisedMeasurement:
    """Build a horizontal GNSS position update around the current IMU state.

    Vertical GNSS quality is optional in the public data contract, so this is
    deliberately a two-dimensional update.  The filter's vertical component is
    instead regularised by the NHC until a qualified altitude source is added.
    """

    if fix.horizontal_accuracy_m is None or fix.horizontal_accuracy_m <= 0.0:
        raise ValueError("A positive GNSS horizontal accuracy is required.")

    observed_position_enu = local_enu_reference.project(fix)
    residual = observed_position_enu[:2] - state.nominal.position_enu_m[:2]
    jacobian = np.zeros((2, 15))
    jacobian[:, POSITION] = np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))

    # Receiver horizontal accuracy is treated conservatively as the standard
    # deviation of each local horizontal component, not as a perfect radius.
    covariance = np.eye(2) * fix.horizontal_accuracy_m**2
    return LinearisedMeasurement(
        timestamp_ns=state.nominal.timestamp_ns,
        kind=MeasurementKind.GNSS_POSITION,
        residual=residual,
        jacobian=jacobian,
        covariance=covariance,
        nis_gate=nis_gate,
    )


def build_gnss_velocity_measurement(
    *,
    state: ErrorStateEkfState,
    fix: GnssFix,
    nis_gate: float,
) -> LinearisedMeasurement:
    """Build a 2D course-over-ground velocity measurement in ENU.

    Course is clockwise from north, hence east is ``speed * sin(course)`` and
    north is ``speed * cos(course)``.  Course error becomes cross-track speed
    error and is therefore included in the covariance instead of discarded.
    """

    values = (
        fix.speed_mps,
        fix.speed_accuracy_mps,
        fix.course_over_ground_rad,
        fix.course_accuracy_rad,
    )
    if not all(value is not None and isfinite(value) for value in values):
        raise ValueError("GNSS velocity update requires finite speed and course metadata.")
    if fix.speed_mps < 0.0 or fix.speed_accuracy_mps <= 0.0 or fix.course_accuracy_rad <= 0.0:
        raise ValueError("GNSS speed and its accuracy values must be positive.")

    direction = np.asarray(
        (sin(fix.course_over_ground_rad), cos(fix.course_over_ground_rad))
    )
    left_normal = np.asarray((-direction[1], direction[0]))
    observed_velocity = fix.speed_mps * direction
    residual = observed_velocity - state.nominal.velocity_enu_mps[:2]
    jacobian = np.zeros((2, 15))
    jacobian[:, VELOCITY] = np.asarray(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))

    # First-order course uncertainty produces a cross-track speed standard
    # deviation of v * sigma_heading.  Keep both components positive definite.
    along_track_variance = fix.speed_accuracy_mps**2
    cross_track_variance = max(
        1e-6,
        (max(fix.speed_mps, 0.1) * fix.course_accuracy_rad) ** 2,
    )
    covariance = (
        along_track_variance * np.outer(direction, direction)
        + cross_track_variance * np.outer(left_normal, left_normal)
    )
    return LinearisedMeasurement(
        timestamp_ns=state.nominal.timestamp_ns,
        kind=MeasurementKind.GNSS_VELOCITY,
        residual=residual,
        jacobian=jacobian,
        covariance=covariance,
        nis_gate=nis_gate,
    )


def build_velocity_model_measurement(
    *,
    state: ErrorStateEkfState,
    observation: VelocityObservation,
    uncertainty: UncertaintyEstimate,
    nis_gate: float,
    maximum_association_age_ns: int = 0,
) -> LinearisedMeasurement:
    """Turn a scalar learned ground-speed output into a vehicle-forward update.

    The velocity model predicts speed magnitude rather than ENU components.
    Applying it to the current forward velocity keeps the model frame-correct;
    lateral/vertical components are independently handled by the NHC.
    """

    if (
        uncertainty.timestamp_ns != observation.timestamp_ns
        or uncertainty.velocity_observation_timestamp_ns != observation.timestamp_ns
        or uncertainty.model_id != observation.model_id
    ):
        raise ValueError("Velocity observation and uncertainty must align.")
    association_age_ns = state.nominal.timestamp_ns - observation.timestamp_ns
    if association_age_ns < 0:
        raise ValueError("Velocity observation cannot be newer than the EKF state.")
    if association_age_ns > maximum_association_age_ns:
        raise ValueError("Velocity observation is too old for causal EKF association.")
    if not (
        isfinite(observation.speed_mps)
        and observation.speed_mps >= 0.0
        and isfinite(uncertainty.speed_variance_m2ps2)
        and uncertainty.speed_variance_m2ps2 > 0.0
    ):
        raise ValueError("Velocity model speed and variance must be physically valid.")

    rotation_enu_to_vehicle = vehicle_to_navigation_rotation(
        state.nominal.vehicle_to_navigation_wxyz
    ).T
    velocity_vehicle = rotation_enu_to_vehicle @ state.nominal.velocity_enu_mps
    forward_selector = np.asarray((1.0, 0.0, 0.0))
    residual = np.asarray((observation.speed_mps - velocity_vehicle[0],))
    jacobian = np.zeros((1, 15))
    jacobian[:, VELOCITY] = forward_selector @ rotation_enu_to_vehicle
    jacobian[:, ATTITUDE] = forward_selector @ skew_symmetric(velocity_vehicle)

    return LinearisedMeasurement(
        timestamp_ns=state.nominal.timestamp_ns,
        kind=MeasurementKind.VELOCITY_MODEL,
        residual=residual,
        jacobian=jacobian,
        covariance=np.asarray(((uncertainty.speed_variance_m2ps2,),)),
        nis_gate=nis_gate,
    )

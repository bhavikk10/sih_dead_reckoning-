from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

import numpy as np

from ..sensors.types import VehicleImuSample
from .measurements import (
    LinearisedMeasurement,
    MeasurementKind,
)
from .propagation import (
    skew_symmetric,
    vehicle_to_navigation_rotation,
)
from .state import ATTITUDE, VELOCITY, ErrorStateEkfState


@dataclass(frozen=True, slots=True)
class NonHolonomicConstraintConfig:
    """Policy for using lateral/vertical near-zero velocity constraints."""

    # A weak phone-to-vehicle rotation makes vehicle-left/up meaningless.
    minimum_calibration_confidence: float

    # Moderate turns retain NHC but receive less trust. Beyond this bound, an
    # unmodelled phone offset or aggressive manoeuvre makes NHC unsafe.
    soft_yaw_rate_radps: float
    maximum_yaw_rate_radps: float

    # These are standard deviations, not variances.
    lateral_velocity_std_mps: float
    vertical_velocity_std_mps: float

    # 2D chi-square gate; normally selected outside this module, e.g. 9.21 for
    # a 99% gate. It remains explicit and auditable.
    nis_gate: float

    def __post_init__(self) -> None:
        """Reject a physically meaningless policy before a live update."""

        positive = (
            self.soft_yaw_rate_radps,
            self.maximum_yaw_rate_radps,
            self.lateral_velocity_std_mps,
            self.vertical_velocity_std_mps,
            self.nis_gate,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("NHC rates, standard deviations, and gate must be positive.")
        if not (
            isfinite(self.minimum_calibration_confidence)
            and 0.0 <= self.minimum_calibration_confidence <= 1.0
        ):
            raise ValueError("minimum_calibration_confidence must be in [0, 1].")
        if self.maximum_yaw_rate_radps < self.soft_yaw_rate_radps:
            raise ValueError("maximum_yaw_rate_radps must be at least soft_yaw_rate_radps.")


class NonHolonomicDisposition(StrEnum):
    """Why an NHC measurement was or was not constructed."""

    ELIGIBLE = "eligible"
    CALIBRATION_UNTRUSTED = "calibration_untrusted"
    YAW_RATE_TOO_HIGH = "yaw_rate_too_high"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"


@dataclass(frozen=True, slots=True)
class NonHolonomicDecision:
    """Eligibility evidence plus an optional soft EKF measurement."""

    disposition: NonHolonomicDisposition
    measurement: LinearisedMeasurement | None


def nhc_is_eligible(
    state: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: NonHolonomicConstraintConfig,
) -> NonHolonomicDisposition:
    """Check frame trust, timing, and turn rate before constructing NHC."""

    if sample.timestamp_ns != state.nominal.timestamp_ns:
        return NonHolonomicDisposition.TIMESTAMP_MISMATCH
    if sample.calibration_confidence < config.minimum_calibration_confidence:
        return NonHolonomicDisposition.CALIBRATION_UNTRUSTED

    corrected_yaw_rate_radps = (
        sample.angular_velocity_radps[2]
        - state.nominal.gyroscope_bias_vehicle_radps[2]
    )
    if abs(corrected_yaw_rate_radps) > config.maximum_yaw_rate_radps:
        return NonHolonomicDisposition.YAW_RATE_TOO_HIGH
    return NonHolonomicDisposition.ELIGIBLE


def nhc_measurement_covariance(
    *,
    corrected_yaw_rate_radps: float,
    calibration_confidence: float,
    config: NonHolonomicConstraintConfig,
) -> np.ndarray:
    """Return a conservative 2x2 covariance for [lateral, vertical] velocity."""

    turn_scale = 1.0 + (
        abs(corrected_yaw_rate_radps)
        / max(config.soft_yaw_rate_radps, 1e-6)
    ) ** 2

    # As calibration weakens, an apparent side/up velocity could be a frame
    # error. Inflate R instead of claiming an overly precise constraint.
    calibration_scale = 1.0 / max(calibration_confidence, 1e-3)

    lateral_std = (
        config.lateral_velocity_std_mps
        * turn_scale
        * calibration_scale
    )
    vertical_std = (
        config.vertical_velocity_std_mps
        * turn_scale
        * calibration_scale
    )

    return np.diag((lateral_std**2, vertical_std**2))


def build_non_holonomic_measurement(
    state: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: NonHolonomicConstraintConfig,
) -> NonHolonomicDecision:
    """Create z = [0, 0] for vehicle lateral and vertical velocity."""

    disposition = nhc_is_eligible(state, sample, config)
    if disposition is not NonHolonomicDisposition.ELIGIBLE:
        return NonHolonomicDecision(
            disposition=disposition,
            measurement=None,
        )

    rotation_vehicle_to_enu = vehicle_to_navigation_rotation(
        state.nominal.vehicle_to_navigation_wxyz
    )
    rotation_enu_to_vehicle = rotation_vehicle_to_enu.T

    velocity_vehicle = (
        rotation_enu_to_vehicle @ state.nominal.velocity_enu_mps
    )

    # Observation is always zero. The prediction is the nominal vehicle-frame
    # [left, up] velocity, so residual is z - h(x) = -h(x).
    residual = -velocity_vehicle[[1, 2]]

    select_left_and_up = np.asarray(
        (
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    )

    jacobian = np.zeros((2, 15))

    # h(x) = S R(q)^T v_ENU
    # Velocity error changes vehicle-frame velocity directly.
    jacobian[:, VELOCITY] = (
        select_left_and_up @ rotation_enu_to_vehicle
    )

    # With the right-multiplicative vehicle-frame attitude error selected in
    # state.py, attitude error changes vehicle velocity by [v_vehicle]x δθ.
    jacobian[:, ATTITUDE] = (
        select_left_and_up @ skew_symmetric(velocity_vehicle)
    )

    corrected_yaw_rate_radps = (
        sample.angular_velocity_radps[2]
        - state.nominal.gyroscope_bias_vehicle_radps[2]
    )

    return NonHolonomicDecision(
        disposition=NonHolonomicDisposition.ELIGIBLE,
        measurement=LinearisedMeasurement(
            timestamp_ns=sample.timestamp_ns,
            kind=MeasurementKind.NON_HOLONOMIC_CONSTRAINT,
            residual=residual,
            jacobian=jacobian,
            covariance=nhc_measurement_covariance(
                corrected_yaw_rate_radps=corrected_yaw_rate_radps,
                calibration_confidence=sample.calibration_confidence,
                config=config,
            ),
            nis_gate=config.nis_gate,
        ),
    )


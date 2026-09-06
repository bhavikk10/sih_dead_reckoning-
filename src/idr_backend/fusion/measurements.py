from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from .covariance import (
    joseph_covariance_update,
    reset_covariance_after_injection,
)
from .state import (
    ERROR_STATE_DIM,
    ErrorStateEkfState,
    inject_nominal_error,
)

Matrix = NDArray[np.float64]
Vector = NDArray[np.float64]


class MeasurementKind(StrEnum):
    """Names used for diagnostics and measurement-specific policy."""

    GNSS_POSITION = "gnss_position"
    GNSS_VELOCITY = "gnss_velocity"
    VELOCITY_MODEL = "velocity_model"
    NON_HOLONOMIC_CONSTRAINT = "non_holonomic_constraint"
    ROAD_CONTEXT_SPEED_PRIOR = "road_context_speed_prior"


class MeasurementDisposition(StrEnum):
    """Whether the update changed the filter state."""

    ACCEPTED = "accepted"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
    INNOVATION_REJECTED = "innovation_rejected"


@dataclass(frozen=True, slots=True)
class LinearisedMeasurement:
    """One measurement expressed around the current nominal EKF state.

    The residual convention is fixed:
        residual = observed_value - predicted_value

    The Jacobian maps the 15-state error vector into measurement space.
    """

    timestamp_ns: int
    kind: MeasurementKind

    residual: Vector                 # shape (m,)
    jacobian: Matrix                 # shape (m, 15)
    covariance: Matrix               # R, shape (m, m)

    # Normalized Innovation Squared threshold. Builders choose this from the
    # measurement dimension and desired rejection confidence, e.g. chi-square.
    nis_gate: float


@dataclass(frozen=True, slots=True)
class MeasurementUpdateTrace:
    """Evidence retained whether an update is accepted or rejected."""

    kind: MeasurementKind
    timestamp_ns: int
    disposition: MeasurementDisposition
    nis: float | None
    nis_gate: float | None
    correction: Vector | None


@dataclass(frozen=True, slots=True)
class MeasurementUpdateResult:
    """The unchanged prior or corrected posterior state plus audit trace."""

    state: ErrorStateEkfState
    trace: MeasurementUpdateTrace


def validate_linearised_measurement(
    measurement: LinearisedMeasurement,
) -> tuple[Vector, Matrix, Matrix]:
    """Validate dimensions, finiteness, symmetry, and positive R covariance."""

    residual = np.asarray(measurement.residual, dtype=float)
    jacobian = np.asarray(measurement.jacobian, dtype=float)
    covariance = np.asarray(measurement.covariance, dtype=float)

    if residual.ndim != 1 or len(residual) == 0:
        raise ValueError("Measurement residual must be a non-empty vector.")

    dimension = len(residual)
    if jacobian.shape != (dimension, ERROR_STATE_DIM):
        raise ValueError(
            f"Measurement Jacobian must have shape ({dimension}, 15)."
        )
    if covariance.shape != (dimension, dimension):
        raise ValueError(
            f"Measurement covariance must have shape ({dimension}, {dimension})."
        )

    if not (
        np.all(np.isfinite(residual))
        and np.all(np.isfinite(jacobian))
        and np.all(np.isfinite(covariance))
        and np.isfinite(measurement.nis_gate)
        and measurement.nis_gate > 0.0
    ):
        raise ValueError("Measurement values, covariance, and gate must be finite.")

    symmetric_covariance = 0.5 * (covariance + covariance.T)

    # R must be positive definite, not merely semidefinite: an EKF must never
    # treat any real observation as perfectly certain or invert a singular S.
    if np.linalg.eigvalsh(symmetric_covariance)[0] <= 0.0:
        raise ValueError("Measurement covariance must be positive definite.")

    return residual, jacobian, symmetric_covariance


def innovation_statistics(
    prior: ErrorStateEkfState,
    residual: Vector,
    jacobian: Matrix,
    measurement_covariance: Matrix,
) -> tuple[Matrix, Matrix, float]:
    """Return innovation covariance S, gain K, and normalized innovation squared."""

    innovation_covariance = (
        jacobian @ prior.covariance @ jacobian.T
        + measurement_covariance
    )
    innovation_covariance = 0.5 * (
        innovation_covariance + innovation_covariance.T
    )

    # Solve linear systems instead of calculating inv(S). Explicit inversion is
    # slower and amplifies numerical error when observations are uncertain.
    solved_residual = np.linalg.solve(innovation_covariance, residual)
    kalman_gain = np.linalg.solve(
        innovation_covariance,
        (prior.covariance @ jacobian.T).T,
    ).T

    nis = float(residual.T @ solved_residual)
    return innovation_covariance, kalman_gain, nis


def apply_linearised_measurement(
    prior: ErrorStateEkfState,
    measurement: LinearisedMeasurement,
) -> MeasurementUpdateResult:
    """Gate and, if credible, apply one asynchronous EKF measurement update."""

    if measurement.timestamp_ns != prior.nominal.timestamp_ns:
        return MeasurementUpdateResult(
            state=prior,
            trace=MeasurementUpdateTrace(
                kind=measurement.kind,
                timestamp_ns=measurement.timestamp_ns,
                disposition=MeasurementDisposition.TIMESTAMP_MISMATCH,
                nis=None,
                nis_gate=measurement.nis_gate,
                correction=None,
            ),
        )

    residual, jacobian, covariance = validate_linearised_measurement(measurement)
    _, gain, nis = innovation_statistics(
        prior,
        residual,
        jacobian,
        covariance,
    )

    if nis > measurement.nis_gate:
        return MeasurementUpdateResult(
            state=prior,
            trace=MeasurementUpdateTrace(
                kind=measurement.kind,
                timestamp_ns=measurement.timestamp_ns,
                disposition=MeasurementDisposition.INNOVATION_REJECTED,
                nis=nis,
                nis_gate=measurement.nis_gate,
                correction=None,
            ),
        )

    correction = gain @ residual
    corrected_nominal = inject_nominal_error(prior.nominal, correction)

    # Joseph form preserves PSD behavior. The following reset converts P from
    # the old local attitude-error coordinates to the corrected nominal frame.
    posterior_covariance = joseph_covariance_update(
        prior.covariance,
        gain,
        jacobian,
        covariance,
    )
    posterior_covariance = reset_covariance_after_injection(
        posterior_covariance,
        correction[6:9],
    )

    posterior = ErrorStateEkfState(
        nominal=corrected_nominal,
        covariance=posterior_covariance,
    )
    return MeasurementUpdateResult(
        state=posterior,
        trace=MeasurementUpdateTrace(
            kind=measurement.kind,
            timestamp_ns=measurement.timestamp_ns,
            disposition=MeasurementDisposition.ACCEPTED,
            nis=nis,
            nis_gate=measurement.nis_gate,
            correction=correction,
        ),
    )



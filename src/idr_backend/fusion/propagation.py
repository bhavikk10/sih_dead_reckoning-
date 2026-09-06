from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from ..sensors.orientation import (
    propagate_orientation,
    rotate_vector,
)
from ..sensors.types import VehicleImuSample
from .covariance import (
    ImuNoiseDensity,
    continuous_imu_noise_covariance,
    discretise_error_dynamics,
    require_positive_semidefinite,
)
from .state import (
    ACCEL_BIAS,
    ATTITUDE,
    ERROR_STATE_DIM,
    GYRO_BIAS,
    POSITION,
    VELOCITY,
    ErrorStateEkfState,
    NominalNavigationState,
)

Matrix = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class PropagationConfig:
    """Safety limits and physical IMU-noise settings for one IMU source."""

    noise: ImuNoiseDensity

    # A larger gap means the filter did not observe enough inertial data to
    # honestly integrate through it. Recovery must be explicit.
    maximum_delta_time_s: float = 0.25


class PropagationDisposition(StrEnum):
    """Whether this IMU sample safely advanced the navigation state."""

    # The first trusted GNSS/IMU pair creates a state but has no preceding IMU
    # interval to propagate. Keeping this separate makes runtime traces honest.
    INITIALISED = "initialised"
    PROPAGATED = "propagated"
    TIMING_GAP_REQUIRES_RECOVERY = "timing_gap_requires_recovery"


@dataclass(frozen=True, slots=True)
class PropagationDiagnostics:
    """Audit record for one attempted inertial propagation step."""

    delta_time_s: float
    corrected_acceleration_vehicle_mps2: np.ndarray
    corrected_angular_velocity_vehicle_radps: np.ndarray
    acceleration_navigation_enu_mps2: np.ndarray


@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Result of advancing the prior state with one accepted IMU sample."""

    disposition: PropagationDisposition
    state: ErrorStateEkfState
    diagnostics: PropagationDiagnostics | None


def skew_symmetric(vector: np.ndarray) -> Matrix:
    """Return [v]x such that [v]x @ w == v cross w."""

    x, y, z = np.asarray(vector, dtype=float)
    return np.asarray(
        (
            (0.0, -z, y),
            (z, 0.0, -x),
            (-y, x, 0.0),
        ),
        dtype=float,
    )


def vehicle_to_navigation_rotation(
    vehicle_to_navigation_wxyz: tuple[float, float, float, float],
) -> Matrix:
    """Build the 3x3 matrix that maps vehicle-FLU vectors into ENU."""

    return np.column_stack(
        (
            rotate_vector(vehicle_to_navigation_wxyz, (1.0, 0.0, 0.0)),
            rotate_vector(vehicle_to_navigation_wxyz, (0.0, 1.0, 0.0)),
            rotate_vector(vehicle_to_navigation_wxyz, (0.0, 0.0, 1.0)),
        )
    )


def propagate_nominal_state(
    nominal: NominalNavigationState,
    sample: VehicleImuSample,
    delta_time_s: float,
) -> tuple[NominalNavigationState, np.ndarray, np.ndarray, np.ndarray]:
    """Advance nominal position, velocity, and attitude by one IMU interval."""

    corrected_acceleration_vehicle = (
        np.asarray(sample.linear_acceleration_mps2, dtype=float)
        - nominal.accelerometer_bias_vehicle_mps2
    )
    corrected_angular_velocity_vehicle = (
        np.asarray(sample.angular_velocity_radps, dtype=float)
        - nominal.gyroscope_bias_vehicle_radps
    )

    # Midpoint attitude reduces acceleration-rotation error during turns.
    midpoint_attitude = propagate_orientation(
        nominal.vehicle_to_navigation_wxyz,
        tuple(corrected_angular_velocity_vehicle),
        0.5 * delta_time_s,
    )
    rotation_midpoint = vehicle_to_navigation_rotation(midpoint_attitude)
    acceleration_navigation = (
        rotation_midpoint @ corrected_acceleration_vehicle
    )

    next_position = (
        nominal.position_enu_m
        + nominal.velocity_enu_mps * delta_time_s
        + 0.5 * acceleration_navigation * delta_time_s**2
    )
    next_velocity = (
        nominal.velocity_enu_mps
        + acceleration_navigation * delta_time_s
    )
    next_attitude = propagate_orientation(
        nominal.vehicle_to_navigation_wxyz,
        tuple(corrected_angular_velocity_vehicle),
        delta_time_s,
    )

    return (
        NominalNavigationState(
            timestamp_ns=sample.timestamp_ns,
            position_enu_m=next_position,
            velocity_enu_mps=next_velocity,
            vehicle_to_navigation_wxyz=next_attitude,
            # Bias values evolve in the covariance during propagation. Their
            # nominal estimate changes only after a later measurement update.
            accelerometer_bias_vehicle_mps2=(
                nominal.accelerometer_bias_vehicle_mps2
            ),
            gyroscope_bias_vehicle_radps=(
                nominal.gyroscope_bias_vehicle_radps
            ),
        ),
        corrected_acceleration_vehicle,
        corrected_angular_velocity_vehicle,
        acceleration_navigation,
    )


def build_continuous_error_dynamics(
    *,
    vehicle_to_navigation: Matrix,
    corrected_acceleration_vehicle_mps2: np.ndarray,
    corrected_angular_velocity_vehicle_radps: np.ndarray,
) -> tuple[Matrix, Matrix]:
    """Build continuous-time F and G for the 15-state right-error EKF."""

    f = np.zeros((ERROR_STATE_DIM, ERROR_STATE_DIM))
    g = np.zeros((ERROR_STATE_DIM, 12))

    # Position error grows from velocity error.
    f[POSITION, VELOCITY] = np.eye(3)

    # Attitude and accelerometer-bias error create ENU velocity error.
    f[VELOCITY, ATTITUDE] = (
        -vehicle_to_navigation
        @ skew_symmetric(corrected_acceleration_vehicle_mps2)
    )
    f[VELOCITY, ACCEL_BIAS] = -vehicle_to_navigation

    # Right-multiplicative attitude error is expressed in vehicle coordinates.
    f[ATTITUDE, ATTITUDE] = -skew_symmetric(
        corrected_angular_velocity_vehicle_radps
    )
    f[ATTITUDE, GYRO_BIAS] = -np.eye(3)

    # Noise order: accel noise, gyro noise, accel-bias random walk,
    # gyro-bias random walk.
    g[VELOCITY, 0:3] = -vehicle_to_navigation
    g[ATTITUDE, 3:6] = -np.eye(3)
    g[ACCEL_BIAS, 6:9] = np.eye(3)
    g[GYRO_BIAS, 9:12] = np.eye(3)

    return f, g


def propagate_ekf(
    prior: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: PropagationConfig,
) -> PropagationResult:
    """Propagate nominal state and covariance with one accepted IMU sample."""

    delta_time_s = (
        sample.timestamp_ns - prior.nominal.timestamp_ns
    ) * 1e-9

    if (
        not np.isfinite(delta_time_s)
        or delta_time_s <= 0.0
        or delta_time_s > config.maximum_delta_time_s
    ):
        return PropagationResult(
            disposition=PropagationDisposition.TIMING_GAP_REQUIRES_RECOVERY,
            state=prior,
            diagnostics=None,
        )

    propagated_nominal, corrected_accel, corrected_gyro, acceleration_enu = (
        propagate_nominal_state(prior.nominal, sample, delta_time_s)
    )

    rotation = vehicle_to_navigation_rotation(
        prior.nominal.vehicle_to_navigation_wxyz
    )
    continuous_f, noise_mapping = build_continuous_error_dynamics(
        vehicle_to_navigation=rotation,
        corrected_acceleration_vehicle_mps2=corrected_accel,
        corrected_angular_velocity_vehicle_radps=corrected_gyro,
    )
    phi, process_covariance = discretise_error_dynamics(
        continuous_f,
        noise_mapping,
        continuous_imu_noise_covariance(config.noise),
        delta_time_s,
    )

    propagated_covariance = (
        phi @ prior.covariance @ phi.T + process_covariance
    )

    return PropagationResult(
        disposition=PropagationDisposition.PROPAGATED,
        state=ErrorStateEkfState(
            nominal=propagated_nominal,
            covariance=require_positive_semidefinite(
                propagated_covariance
            ),
        ),
        diagnostics=PropagationDiagnostics(
            delta_time_s=delta_time_s,
            corrected_acceleration_vehicle_mps2=corrected_accel,
            corrected_angular_velocity_vehicle_radps=corrected_gyro,
            acceleration_navigation_enu_mps2=acceleration_enu,
        ),
    )


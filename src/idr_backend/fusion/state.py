# δx = [δp_ENU, δv_ENU, δθ_vehicle, δb_acc_vehicle, δb_gyro_vehicle]
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..sensors.orientation import (
    normalize_quaternion,
    quaternion_multiply,
)
from ..sensors.types import (
    QuaternionWxyz,
    Vector3,
)


ERROR_STATE_DIM = 15

POSITION = slice(0, 3)
VELOCITY = slice(3, 6)
ATTITUDE = slice(6, 9)
ACCEL_BIAS = slice(9, 12)
GYRO_BIAS = slice(12, 15)


@dataclass(frozen=True, slots=True)
class NominalNavigationState:
    timestamp_ns: int
    position_enu_m: np.ndarray
    velocity_enu_mps: np.ndarray
    vehicle_to_navigation_wxyz: QuaternionWxyz
    accelerometer_bias_vehicle_mps2: np.ndarray
    gyroscope_bias_vehicle_radps: np.ndarray


@dataclass(frozen=True, slots=True)
class ErrorStateEkfState:
    nominal: NominalNavigationState
    covariance: np.ndarray  # shape: (15, 15)


def initialise_filter_state(
    *,
    timestamp_ns: int,
    position_enu_m: Vector3,
    velocity_enu_mps: Vector3,
    vehicle_to_navigation_wxyz: QuaternionWxyz,
    initial_error_std: np.ndarray,
) -> ErrorStateEkfState:
    """Create a fully initialized filter with zero IMU-bias estimates."""

    std = np.asarray(initial_error_std, dtype=float)
    if std.shape != (ERROR_STATE_DIM,) or not np.all(np.isfinite(std)):
        raise ValueError("initial_error_std must be a finite 15-vector.")
    if np.any(std <= 0.0):
        raise ValueError("All initial error standard deviations must be positive.")

    nominal = NominalNavigationState(
        timestamp_ns=timestamp_ns,
        position_enu_m=np.asarray(position_enu_m, dtype=float),
        velocity_enu_mps=np.asarray(velocity_enu_mps, dtype=float),
        vehicle_to_navigation_wxyz=normalize_quaternion(
            vehicle_to_navigation_wxyz
        ),
        accelerometer_bias_vehicle_mps2=np.zeros(3),
        gyroscope_bias_vehicle_radps=np.zeros(3),
    )
    return ErrorStateEkfState(nominal=nominal, covariance=np.diag(std**2))


def small_angle_quaternion(
    rotation_vector_vehicle_rad: np.ndarray,
) -> QuaternionWxyz:
    """Convert a vehicle-frame rotation vector into a correction quaternion."""

    angle = float(np.linalg.norm(rotation_vector_vehicle_rad))
    if angle < 1e-12:
        return (1.0, 0.0, 0.0, 0.0)

    axis = rotation_vector_vehicle_rad / angle
    half_angle = 0.5 * angle
    return (
        float(np.cos(half_angle)),
        float(axis[0] * np.sin(half_angle)),
        float(axis[1] * np.sin(half_angle)),
        float(axis[2] * np.sin(half_angle)),
    )


def inject_nominal_error(
    nominal: NominalNavigationState,
    delta_x: np.ndarray,
) -> NominalNavigationState:
    """Apply one estimated 15-state correction to the nominal navigation state."""

    correction = np.asarray(delta_x, dtype=float)
    if correction.shape != (ERROR_STATE_DIM,) or not np.all(np.isfinite(correction)):
        raise ValueError("delta_x must be a finite 15-vector.")

    corrected_attitude = normalize_quaternion(
        quaternion_multiply(
            nominal.vehicle_to_navigation_wxyz,
            small_angle_quaternion(correction[ATTITUDE]),
        )
    )

    return NominalNavigationState(
        timestamp_ns=nominal.timestamp_ns,
        position_enu_m=nominal.position_enu_m + correction[POSITION],
        velocity_enu_mps=nominal.velocity_enu_mps + correction[VELOCITY],
        vehicle_to_navigation_wxyz=corrected_attitude,
        accelerometer_bias_vehicle_mps2=(
            nominal.accelerometer_bias_vehicle_mps2 + correction[ACCEL_BIAS]
        ),
        gyroscope_bias_vehicle_radps=(
            nominal.gyroscope_bias_vehicle_radps + correction[GYRO_BIAS]
        ),
    )
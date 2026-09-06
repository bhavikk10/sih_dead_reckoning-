from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

from .state import ATTITUDE, ERROR_STATE_DIM

Matrix = NDArray[np.float64]


class CovarianceHealthError(ValueError):
    """Raised when covariance is non-finite, asymmetric, or meaningfully non-PSD."""


@dataclass(frozen=True, slots=True)
class ImuNoiseDensity:
    """Continuous-time white-noise and bias-random-walk densities.

    These values are sensor-characterization inputs, not parameters learned
    during a drive. Phone and external-IMU profiles will provide different
    instances later through configuration.
    """

    accelerometer_mps2_per_sqrt_hz: float
    gyroscope_radps_per_sqrt_hz: float
    accelerometer_bias_rw_mps2_per_sqrt_s: float
    gyroscope_bias_rw_radps_per_sqrt_s: float


def symmetrise_covariance(covariance: Matrix) -> Matrix:
    """Remove floating-point asymmetry without hiding invalid uncertainty."""

    matrix = np.asarray(covariance, dtype=float)
    if matrix.shape != (ERROR_STATE_DIM, ERROR_STATE_DIM):
        raise CovarianceHealthError("Covariance must have shape (15, 15).")
    if not np.all(np.isfinite(matrix)):
        raise CovarianceHealthError("Covariance contains NaN or infinity.")

    return 0.5 * (matrix + matrix.T)


def require_positive_semidefinite(
    covariance: Matrix,
    *,
    negative_eigenvalue_tolerance: float = 1e-10,
) -> Matrix:
    """Return a symmetric PSD covariance or raise a visible health failure."""

    symmetric = symmetrise_covariance(covariance)
    eigenvalues = np.linalg.eigvalsh(symmetric)

    if eigenvalues[0] < -negative_eigenvalue_tolerance:
        raise CovarianceHealthError(
            "Covariance is not positive semidefinite; "
            f"minimum eigenvalue is {eigenvalues[0]:.3e}."
        )

    # A tiny negative eigenvalue can arise purely from rounding. Clip only that
    # near-zero numerical residue; a materially invalid matrix already raised.
    eigenvalues = np.maximum(eigenvalues, 0.0)
    vectors = np.linalg.eigh(symmetric)[1]
    repaired = (vectors * eigenvalues) @ vectors.T
    return symmetrise_covariance(repaired)


def continuous_imu_noise_covariance(noise: ImuNoiseDensity) -> Matrix:
    """Build Qc for [accelerometer noise, gyro noise, accel-bias RW, gyro-bias RW]."""

    densities = np.asarray(
        (
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
        ),
        dtype=float,
    )
    if not np.all(np.isfinite(densities)) or np.any(densities <= 0.0):
        raise ValueError("All IMU noise densities must be finite and positive.")

    return np.diag(densities**2)


def discretise_error_dynamics(
    continuous_jacobian: Matrix,
    noise_mapping: Matrix,
    continuous_noise_covariance: Matrix,
    delta_time_s: float,
) -> tuple[Matrix, Matrix]:
    """Return discrete transition Phi and discrete process covariance Qd.

    Uses Van Loan discretisation, avoiding the inaccurate shortcut Qd = Qc * dt
    when attitude, position, and bias errors are coupled.
    """

    if not np.isfinite(delta_time_s) or delta_time_s <= 0.0:
        raise ValueError("delta_time_s must be finite and positive.")

    f = np.asarray(continuous_jacobian, dtype=float)
    g = np.asarray(noise_mapping, dtype=float)
    qc = np.asarray(continuous_noise_covariance, dtype=float)

    if f.shape != (ERROR_STATE_DIM, ERROR_STATE_DIM):
        raise ValueError("continuous_jacobian must have shape (15, 15).")
    if g.shape != (ERROR_STATE_DIM, 12) or qc.shape != (12, 12):
        raise ValueError("Expected G shape (15, 12) and Qc shape (12, 12).")

    driven_noise = g @ qc @ g.T
    van_loan = np.zeros((2 * ERROR_STATE_DIM, 2 * ERROR_STATE_DIM))
    van_loan[:ERROR_STATE_DIM, :ERROR_STATE_DIM] = f
    van_loan[:ERROR_STATE_DIM, ERROR_STATE_DIM:] = driven_noise
    van_loan[ERROR_STATE_DIM:, ERROR_STATE_DIM:] = -f.T

    block_exponential = expm(van_loan * delta_time_s)
    phi = block_exponential[:ERROR_STATE_DIM, :ERROR_STATE_DIM]
    qd = block_exponential[:ERROR_STATE_DIM, ERROR_STATE_DIM:] @ phi.T

    return phi, require_positive_semidefinite(qd)


def joseph_covariance_update(
    prior_covariance: Matrix,
    kalman_gain: Matrix,
    measurement_jacobian: Matrix,
    measurement_covariance: Matrix,
) -> Matrix:
    """Perform a numerically stable EKF measurement covariance update."""

    prior = require_positive_semidefinite(prior_covariance)
    gain = np.asarray(kalman_gain, dtype=float)
    h = np.asarray(measurement_jacobian, dtype=float)
    r = np.asarray(measurement_covariance, dtype=float)

    identity = np.eye(ERROR_STATE_DIM)
    residual_projection = identity - gain @ h

    # Joseph form is safer than P = (I - K H) P. It preserves PSD behavior
    # even when numerical round-off makes the simple form unstable.
    posterior = (
        residual_projection @ prior @ residual_projection.T
        + gain @ r @ gain.T
    )
    return require_positive_semidefinite(posterior)


def reset_covariance_after_injection(
    covariance: Matrix,
    attitude_correction_vehicle_rad: np.ndarray,
) -> Matrix:
    """Reset covariance after applying the estimated attitude error to nominal state."""

    delta_theta = np.asarray(attitude_correction_vehicle_rad, dtype=float)
    if delta_theta.shape != (3,):
        raise ValueError("attitude_correction_vehicle_rad must have shape (3,).")

    x, y, z = delta_theta
    skew = np.asarray(
        (
            (0.0, -z, y),
            (z, 0.0, -x),
            (-y, x, 0.0),
        )
    )

    reset_jacobian = np.eye(ERROR_STATE_DIM)
    reset_jacobian[ATTITUDE, ATTITUDE] = np.eye(3) - 0.5 * skew

    reset_covariance = (
        reset_jacobian @ covariance @ reset_jacobian.T
    )
    return require_positive_semidefinite(reset_covariance)
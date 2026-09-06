"""Held-out calibration and diagnostics for predicted speed variances."""

from dataclasses import dataclass
from math import erf, isfinite, sqrt
from typing import Sequence


# A calibrated variance must remain strictly positive even for a perfectly
# predicted (and therefore zero-residual) finite calibration slice.  This is
# deliberately tiny relative to speed units; it only protects downstream
# Gaussian math from a singular covariance.
_MINIMUM_VARIANCE_SCALE = 1e-12


@dataclass(frozen=True, slots=True)
class VarianceScaleCalibration:
    """One multiplicative scale fitted only on a held-out calibration split."""

    scale: float

    def __post_init__(self) -> None:
        """Reject a scale that could turn a valid variance non-positive."""

        if not isfinite(self.scale) or self.scale <= 0.0:
            raise ValueError("Variance scale must be finite and positive.")

    def apply(self, variance_m2ps2: float) -> float:
        """Apply the positive global correction to one predicted variance."""

        if not isfinite(variance_m2ps2) or variance_m2ps2 <= 0.0:
            raise ValueError("Variance must be finite and positive.")
        return self.scale * variance_m2ps2


def fit_variance_scale(
    *,
    residuals_mps: Sequence[float],
    predicted_variances_m2ps2: Sequence[float],
) -> VarianceScaleCalibration:
    """Moment-match average predicted variance to average held-out squared error."""

    if len(residuals_mps) != len(predicted_variances_m2ps2):
        raise ValueError("Residuals and predicted variances must have equal length.")
    if not residuals_mps:
        raise ValueError("Calibration requires at least one held-out observation.")
    if not all(isfinite(value) for value in residuals_mps):
        raise ValueError("Residuals must be finite.")
    if not all(
        isfinite(value) and value > 0.0
        for value in predicted_variances_m2ps2
    ):
        raise ValueError("Predicted variances must be finite and positive.")

    mean_squared_error = sum(value * value for value in residuals_mps) / len(
        residuals_mps
    )
    mean_variance = sum(predicted_variances_m2ps2) / len(
        predicted_variances_m2ps2
    )
    return VarianceScaleCalibration(
        scale=max(_MINIMUM_VARIANCE_SCALE, mean_squared_error / mean_variance)
    )


def gaussian_interval_coverage(
    *,
    residuals_mps: Sequence[float],
    predicted_variances_m2ps2: Sequence[float],
    standard_deviations: float = 1.0,
) -> float:
    """Return empirical coverage for symmetric Gaussian prediction intervals."""

    if len(residuals_mps) != len(predicted_variances_m2ps2):
        raise ValueError("Residuals and predicted variances must have equal length.")
    if not residuals_mps:
        raise ValueError("Coverage requires at least one observation.")
    if not isfinite(standard_deviations) or standard_deviations <= 0.0:
        raise ValueError("standard_deviations must be finite and positive.")

    covered = 0
    for residual, variance in zip(residuals_mps, predicted_variances_m2ps2, strict=True):
        if not isfinite(residual) or not isfinite(variance) or variance <= 0.0:
            raise ValueError("Residuals must be finite and variances positive.")
        if abs(residual) <= standard_deviations * sqrt(variance):
            covered += 1
    return covered / len(residuals_mps)


def expected_gaussian_coverage(standard_deviations: float) -> float:
    """Return theoretical central coverage for a zero-mean unit Gaussian."""

    if not isfinite(standard_deviations) or standard_deviations <= 0.0:
        raise ValueError("standard_deviations must be finite and positive.")
    return erf(standard_deviations / sqrt(2.0))

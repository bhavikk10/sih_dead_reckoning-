"""Conservative deterministic uncertainty for the selected velocity model.

The selected windowed GRU has cross-fitted residuals at fixed GNSS-blackout
horizons.  This module turns those residual statistics into a versioned,
monotone uncertainty schedule.  It is intentionally simpler than the rejected
learned variance experiment: every input, interpolation rule, and safety
inflation is inspectable and reproducible.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite

from idr_backend.sensors.types import UncertaintyEstimate, VelocityObservation

from .features import VelocityUncertaintyFeatures


@dataclass(frozen=True, slots=True)
class DeterministicVelocityUncertaintyProfile:
    """A calibrated base schedule plus conservative live-data inflation.

    ``horizon_seconds`` and ``base_standard_deviation_mps`` are fitted from
    development-only, cross-fitted velocity residuals.  The base standard
    deviations are monotone, so merely losing GNSS never makes the reported
    speed observation more precise.  Roughness, turn rate, mounting confidence,
    and live quality may only increase that base uncertainty.
    """

    model_id: str
    horizon_seconds: tuple[float, ...]
    base_standard_deviation_mps: tuple[float, ...]
    variance_ceiling_m2ps2: float
    reference_acceleration_std_mps2: float
    reference_angular_velocity_rms_radps: float
    reference_minimum_calibration_confidence: float
    reference_final_quality_score: float
    roughness_std_multiplier: float
    turn_std_multiplier: float
    calibration_std_multiplier: float
    quality_std_multiplier: float

    def __post_init__(self) -> None:
        """Reject a profile that could imply nonphysical covariance."""

        if not self.model_id.strip():
            raise ValueError("Deterministic uncertainty model_id must not be blank.")
        if len(self.horizon_seconds) == 0 or (
            len(self.horizon_seconds) != len(self.base_standard_deviation_mps)
        ):
            raise ValueError("Uncertainty horizons and standard deviations must align.")
        if not all(
            isfinite(value) and value >= 0.0 for value in self.horizon_seconds
        ):
            raise ValueError("Uncertainty horizons must be finite and non-negative.")
        if any(
            right <= left
            for left, right in zip(self.horizon_seconds, self.horizon_seconds[1:])
        ):
            raise ValueError("Uncertainty horizons must increase strictly.")
        if not all(
            isfinite(value) and value > 0.0
            for value in self.base_standard_deviation_mps
        ):
            raise ValueError("Base uncertainty standard deviations must be positive.")
        if any(
            right < left
            for left, right in zip(
                self.base_standard_deviation_mps,
                self.base_standard_deviation_mps[1:],
            )
        ):
            raise ValueError("Base uncertainty must not decrease with GNSS age.")
        positive_references = (
            self.variance_ceiling_m2ps2,
            self.reference_acceleration_std_mps2,
            self.reference_angular_velocity_rms_radps,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive_references):
            raise ValueError("Uncertainty ceiling and references must be positive.")
        confidence_references = (
            self.reference_minimum_calibration_confidence,
            self.reference_final_quality_score,
        )
        if not all(
            isfinite(value) and 0.0 < value <= 1.0
            for value in confidence_references
        ):
            raise ValueError("Uncertainty confidence references must be in (0, 1].")
        multipliers = (
            self.roughness_std_multiplier,
            self.turn_std_multiplier,
            self.calibration_std_multiplier,
            self.quality_std_multiplier,
        )
        if not all(isfinite(value) and value >= 0.0 for value in multipliers):
            raise ValueError("Uncertainty inflation multipliers must be non-negative.")

    def estimate(
        self,
        *,
        observation: VelocityObservation,
        features: VelocityUncertaintyFeatures,
    ) -> UncertaintyEstimate:
        """Return a model-bound, calibrated speed variance for EKF fusion."""

        if (
            observation.timestamp_ns != features.timestamp_ns
            or observation.source_id != features.source_id
            or observation.model_id != features.model_id
        ):
            raise ValueError("Observation and uncertainty features must align.")
        if observation.model_id != self.model_id:
            raise ValueError("Deterministic uncertainty belongs to another velocity model.")

        variance = self.variance_m2ps2(
            seconds_since_anchor=features.seconds_since_anchor,
            linear_acceleration_magnitude_std_mps2=(
                features.linear_acceleration_magnitude_std_mps2
            ),
            angular_velocity_rms_radps=features.angular_velocity_rms_radps,
            minimum_calibration_confidence=(
                features.minimum_calibration_confidence
            ),
            final_quality_score=features.final_quality_score,
        )
        return UncertaintyEstimate(
            timestamp_ns=observation.timestamp_ns,
            velocity_observation_timestamp_ns=observation.timestamp_ns,
            model_id=observation.model_id,
            speed_variance_m2ps2=variance,
            is_calibrated=True,
            used_heuristic_bound=False,
        )

    def variance_m2ps2(
        self,
        *,
        seconds_since_anchor: float,
        linear_acceleration_magnitude_std_mps2: float,
        angular_velocity_rms_radps: float,
        minimum_calibration_confidence: float,
        final_quality_score: float,
    ) -> float:
        """Calculate profile variance from causal runtime facts only.

        This lower-level operation is used by offline grouped validation as
        well as runtime inference.  It has no access to actual speed, GNSS
        future data, EKF innovations, or a training label.
        """

        non_negative = (
            seconds_since_anchor,
            linear_acceleration_magnitude_std_mps2,
            angular_velocity_rms_radps,
        )
        if not all(isfinite(value) and value >= 0.0 for value in non_negative):
            raise ValueError("Deterministic uncertainty inputs must be non-negative.")
        confidences = (minimum_calibration_confidence, final_quality_score)
        if not all(isfinite(value) and 0.0 <= value <= 1.0 for value in confidences):
            raise ValueError("Confidence and quality scores must be in [0, 1].")

        base_std = self._base_standard_deviation(seconds_since_anchor)
        roughness = min(
            1.0,
            max(
                0.0,
                linear_acceleration_magnitude_std_mps2
                / self.reference_acceleration_std_mps2
                - 1.0,
            ),
        )
        turning = min(
            1.0,
            max(
                0.0,
                angular_velocity_rms_radps
                / self.reference_angular_velocity_rms_radps
                - 1.0,
            ),
        )
        calibration_deficit = min(
            1.0,
            max(
                0.0,
                (
                    self.reference_minimum_calibration_confidence
                    - minimum_calibration_confidence
                )
                / self.reference_minimum_calibration_confidence,
            ),
        )
        quality_deficit = min(
            1.0,
            max(
                0.0,
                (self.reference_final_quality_score - final_quality_score)
                / self.reference_final_quality_score,
            ),
        )
        inflation = 1.0 + (
            self.roughness_std_multiplier * roughness
            + self.turn_std_multiplier * turning
            + self.calibration_std_multiplier * calibration_deficit
            + self.quality_std_multiplier * quality_deficit
        )
        return min(self.variance_ceiling_m2ps2, (base_std * inflation) ** 2)

    def _base_standard_deviation(self, seconds_since_anchor: float) -> float:
        """Linearly interpolate the monotone development-only schedule."""

        if seconds_since_anchor <= self.horizon_seconds[0]:
            return self.base_standard_deviation_mps[0]
        if seconds_since_anchor >= self.horizon_seconds[-1]:
            return self.base_standard_deviation_mps[-1]

        right_index = bisect_right(self.horizon_seconds, seconds_since_anchor)
        left_index = right_index - 1
        left_horizon = self.horizon_seconds[left_index]
        right_horizon = self.horizon_seconds[right_index]
        interpolation = (
            (seconds_since_anchor - left_horizon)
            / (right_horizon - left_horizon)
        )
        left_std = self.base_standard_deviation_mps[left_index]
        right_std = self.base_standard_deviation_mps[right_index]
        return left_std + interpolation * (right_std - left_std)

"""Bounded deterministic fallback for velocity-observation variance."""

from dataclasses import dataclass
from math import isfinite

from idr_backend.sensors.types import UncertaintyEstimate, VelocityObservation

from .features import VelocityUncertaintyFeatures


@dataclass(frozen=True, slots=True)
class HeuristicUncertaintyConfig:
    """Conservative variance floor, ceiling, and observable risk scales."""

    variance_floor_m2ps2: float
    variance_ceiling_m2ps2: float
    reference_acceleration_rms_mps2: float
    reference_angular_velocity_rms_radps: float
    roughness_weight: float
    turn_weight: float
    calibration_weight: float
    quality_weight: float


def heuristic_uncertainty(
    *,
    observation: VelocityObservation,
    features: VelocityUncertaintyFeatures,
    config: HeuristicUncertaintyConfig,
) -> UncertaintyEstimate:
    """Publish bounded variance when no learned calibrated model is available."""

    _validate_config(config)
    if (
        observation.timestamp_ns != features.timestamp_ns
        or observation.source_id != features.source_id
        or observation.model_id != features.model_id
    ):
        raise ValueError("Observation and uncertainty features must describe one output.")

    roughness = min(
        1.0,
        features.linear_acceleration_magnitude_std_mps2
        / config.reference_acceleration_rms_mps2,
    )
    turning = min(
        1.0,
        features.angular_velocity_rms_radps
        / config.reference_angular_velocity_rms_radps,
    )
    calibration_penalty = 1.0 - features.minimum_calibration_confidence
    quality_penalty = 1.0 - features.final_quality_score

    multiplier = 1.0 + (
        config.roughness_weight * roughness
        + config.turn_weight * turning
        + config.calibration_weight * calibration_penalty
        + config.quality_weight * quality_penalty
    )
    variance = min(
        config.variance_ceiling_m2ps2,
        max(config.variance_floor_m2ps2, config.variance_floor_m2ps2 * multiplier),
    )

    return UncertaintyEstimate(
        timestamp_ns=observation.timestamp_ns,
        velocity_observation_timestamp_ns=observation.timestamp_ns,
        model_id=observation.model_id,
        speed_variance_m2ps2=variance,
        is_calibrated=False,
        used_heuristic_bound=True,
    )


def _validate_config(config: HeuristicUncertaintyConfig) -> None:
    """Fail early for invalid variance configuration rather than clipping it."""

    positive_values = (
        config.variance_floor_m2ps2,
        config.variance_ceiling_m2ps2,
        config.reference_acceleration_rms_mps2,
        config.reference_angular_velocity_rms_radps,
    )
    if not all(isfinite(value) and value > 0.0 for value in positive_values):
        raise ValueError("Variance floors, ceilings, and reference scales must be positive.")
    if config.variance_ceiling_m2ps2 < config.variance_floor_m2ps2:
        raise ValueError("variance_ceiling_m2ps2 must be at least the floor.")
    weights = (
        config.roughness_weight,
        config.turn_weight,
        config.calibration_weight,
        config.quality_weight,
    )
    if not all(isfinite(weight) and weight >= 0.0 for weight in weights):
        raise ValueError("Heuristic uncertainty weights must be finite and non-negative.")

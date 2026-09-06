"""Causal feature construction for velocity-observation uncertainty."""

from dataclasses import dataclass
from math import isfinite, sqrt

from idr_backend.sensors.quality import VehicleImuQuality
from idr_backend.sensors.types import VelocityObservation
from idr_backend.sensors.windowing import VelocityModelInputWindow


UNCERTAINTY_FEATURE_NAMES = (
    "linear_acceleration_rms_mps2",
    "linear_acceleration_magnitude_std_mps2",
    "angular_velocity_rms_radps",
    "minimum_calibration_confidence",
    "final_quality_score",
    "window_duration_s",
    # These distinguish a fresh, trusted anchor from a long GNSS blackout and
    # let the variance model condition on the speed regime it is estimating.
    "seconds_since_anchor",
    "predicted_speed_mps",
)


@dataclass(frozen=True, slots=True)
class VelocityUncertaintyFeatures:
    """Observable, label-free facts about one velocity-model prediction."""

    timestamp_ns: int
    source_id: str
    model_id: str
    linear_acceleration_rms_mps2: float
    linear_acceleration_magnitude_std_mps2: float
    angular_velocity_rms_radps: float
    minimum_calibration_confidence: float
    final_quality_score: float
    window_duration_s: float
    seconds_since_anchor: float
    predicted_speed_mps: float

    def as_tuple(self) -> tuple[float, float, float, float, float, float, float, float]:
        """Return features in the stable order used by a learned variance model."""

        return (
            self.linear_acceleration_rms_mps2,
            self.linear_acceleration_magnitude_std_mps2,
            self.angular_velocity_rms_radps,
            self.minimum_calibration_confidence,
            self.final_quality_score,
            self.window_duration_s,
            self.seconds_since_anchor,
            self.predicted_speed_mps,
        )


def build_velocity_uncertainty_features(
    *,
    observation: VelocityObservation,
    window: VelocityModelInputWindow,
    final_quality: VehicleImuQuality,
    seconds_since_anchor: float,
) -> VelocityUncertaintyFeatures:
    """Build model inputs using only data available by the window end time."""

    if observation.timestamp_ns != window.end_timestamp_ns:
        raise ValueError("Observation timestamp must equal the window end time.")
    if observation.source_id != window.source_id:
        raise ValueError("Observation and window must belong to the same device.")
    if (
        final_quality.timestamp_ns != window.end_timestamp_ns
        or final_quality.source_id != window.source_id
    ):
        raise ValueError("Final quality must describe the window's final sample.")
    if not final_quality.is_acceptable:
        raise ValueError("Uncertainty features require a quality-accepted window.")

    acceleration_magnitudes = tuple(
        _magnitude(sample.linear_acceleration_mps2)
        for sample in window.samples
    )
    angular_velocity_magnitudes = tuple(
        _magnitude(sample.angular_velocity_radps)
        for sample in window.samples
    )
    acceleration_components = tuple(
        component
        for sample in window.samples
        for component in sample.linear_acceleration_mps2
    )

    feature_values = (
        _rms(acceleration_components),
        _population_standard_deviation(acceleration_magnitudes),
        _rms(angular_velocity_magnitudes),
        min(sample.calibration_confidence for sample in window.samples),
        final_quality.score,
        (window.samples[-1].timestamp_ns - window.samples[0].timestamp_ns)
        * 1e-9,
        seconds_since_anchor,
        observation.speed_mps,
    )
    if not all(isfinite(value) and value >= 0.0 for value in feature_values):
        raise ValueError("Uncertainty features must be finite and non-negative.")

    return VelocityUncertaintyFeatures(
        timestamp_ns=observation.timestamp_ns,
        source_id=observation.source_id,
        model_id=observation.model_id,
        linear_acceleration_rms_mps2=feature_values[0],
        linear_acceleration_magnitude_std_mps2=feature_values[1],
        angular_velocity_rms_radps=feature_values[2],
        minimum_calibration_confidence=feature_values[3],
        final_quality_score=feature_values[4],
        window_duration_s=feature_values[5],
        seconds_since_anchor=feature_values[6],
        predicted_speed_mps=feature_values[7],
    )


def _magnitude(vector: tuple[float, float, float]) -> float:
    """Return a finite three-dimensional vector magnitude."""

    if not all(isfinite(component) for component in vector):
        raise ValueError("Window vectors must be finite.")
    return sqrt(sum(component * component for component in vector))


def _rms(values: tuple[float, ...]) -> float:
    """Return root-mean-square magnitude for a non-empty finite sequence."""

    if not values or not all(isfinite(value) for value in values):
        raise ValueError("RMS values must be non-empty and finite.")
    return sqrt(sum(value * value for value in values) / len(values))


def _population_standard_deviation(values: tuple[float, ...]) -> float:
    """Return population spread; a one-sample window has zero spread."""

    if not values or not all(isfinite(value) for value in values):
        raise ValueError("Standard-deviation values must be non-empty and finite.")
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))

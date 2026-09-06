"""Runtime uncertainty estimators for one causal velocity observation.

The deterministic fallback is usable before a residual-variance model has
been trained.  The learned estimator is intentionally artifact-agnostic: a
caller supplies the trained network and its separately fitted held-out
calibration scale rather than embedding notebook or checkpoint behaviour here.
"""

from dataclasses import dataclass
from math import isfinite

import torch

from idr_backend.sensors.types import UncertaintyEstimate, VelocityObservation

from .calibration import VarianceScaleCalibration
from .features import UNCERTAINTY_FEATURE_NAMES, VelocityUncertaintyFeatures
from .heuristics import HeuristicUncertaintyConfig, heuristic_uncertainty
from .model import HeteroscedasticVarianceNetwork
from .protocol import (
    HeuristicVelocityUncertaintyEstimator,
    VelocityUncertaintyEstimator,
)


@dataclass(frozen=True, slots=True)
class LearnedVelocityUncertaintyEstimator:
    """Run a trained variance network and held-out calibration at inference time."""

    network: HeteroscedasticVarianceNetwork
    calibration: VarianceScaleCalibration
    variance_floor_m2ps2: float
    variance_ceiling_m2ps2: float
    # Learned training commonly standardizes heterogeneous physical features.
    # ``None`` preserves the original raw-feature behaviour for hand-built
    # tests and callers; exported artifacts provide both tuples explicitly.
    feature_mean: tuple[float, ...] | None = None
    feature_scale: tuple[float, ...] | None = None
    # A versioned artifact may deliberately use a strict subset of the full
    # runtime feature contract.  For example, replay data can preserve the
    # accepted/rejected quality state but not a trustworthy continuous quality
    # score.  That score is still used by the heuristic guard, never invented
    # for the learned network.
    feature_names: tuple[str, ...] | None = None
    heuristic_config: HeuristicUncertaintyConfig | None = None

    def __post_init__(self) -> None:
        """Keep the runtime safety bounds physically meaningful."""

        if (
            not isfinite(self.variance_floor_m2ps2)
            or self.variance_floor_m2ps2 <= 0.0
        ):
            raise ValueError("variance_floor_m2ps2 must be finite and positive.")
        if (
            not isfinite(self.variance_ceiling_m2ps2)
            or self.variance_ceiling_m2ps2 < self.variance_floor_m2ps2
        ):
            raise ValueError(
                "variance_ceiling_m2ps2 must be finite and at least the floor."
            )
        if (self.feature_mean is None) != (self.feature_scale is None):
            raise ValueError("Feature mean and scale must be supplied together.")
        names = self.feature_names or UNCERTAINTY_FEATURE_NAMES
        if not names or len(set(names)) != len(names):
            raise ValueError("Learned uncertainty feature names must be unique.")
        if not set(names).issubset(UNCERTAINTY_FEATURE_NAMES):
            raise ValueError("Learned uncertainty artifact has unsupported features.")
        if self.feature_mean is not None and self.feature_scale is not None:
            if (
                len(self.feature_mean) != len(self.feature_scale)
                or len(self.feature_mean) != len(names)
            ):
                raise ValueError("Feature mean and scale dimensions must match.")
            if not all(isfinite(value) for value in self.feature_mean):
                raise ValueError("Feature means must be finite.")
            if not all(isfinite(value) and value > 0.0 for value in self.feature_scale):
                raise ValueError("Feature scales must be finite and positive.")

    def estimate(
        self,
        *,
        observation: VelocityObservation,
        features: VelocityUncertaintyFeatures,
    ) -> UncertaintyEstimate:
        """Return a calibrated, bounded variance without changing network state."""

        _validate_alignment(observation=observation, features=features)
        parameters = tuple(self.network.parameters())
        device = parameters[0].device if parameters else torch.device("cpu")
        all_feature_values = dict(
            zip(
                UNCERTAINTY_FEATURE_NAMES,
                features.as_tuple(),
                strict=True,
            )
        )
        names = self.feature_names or UNCERTAINTY_FEATURE_NAMES
        feature_values = tuple(all_feature_values[name] for name in names)
        if self.feature_mean is not None and self.feature_scale is not None:
            if len(feature_values) != len(self.feature_mean):
                raise ValueError("Runtime uncertainty features differ from artifact scaler.")
            feature_values = tuple(
                (value - mean) / scale
                for value, mean, scale in zip(
                    feature_values,
                    self.feature_mean,
                    self.feature_scale,
                    strict=True,
                )
            )
        feature_tensor = torch.tensor(
            (feature_values,),
            dtype=torch.float32,
            device=device,
        )

        was_training = self.network.training
        self.network.eval()
        try:
            with torch.no_grad():
                uncalibrated = float(self.network(feature_tensor).item())
        finally:
            self.network.train(was_training)

        calibrated = self.calibration.apply(uncalibrated)
        bounded = min(
            self.variance_ceiling_m2ps2,
            max(self.variance_floor_m2ps2, calibrated),
        )
        if self.heuristic_config is not None:
            heuristic = heuristic_uncertainty(
                observation=observation,
                features=features,
                config=self.heuristic_config,
            )
            used_heuristic_bound = heuristic.speed_variance_m2ps2 > bounded
            bounded = max(bounded, heuristic.speed_variance_m2ps2)
        else:
            used_heuristic_bound = False
        return UncertaintyEstimate(
            timestamp_ns=observation.timestamp_ns,
            velocity_observation_timestamp_ns=observation.timestamp_ns,
            model_id=observation.model_id,
            speed_variance_m2ps2=bounded,
            is_calibrated=True,
            used_heuristic_bound=used_heuristic_bound,
        )


def _validate_alignment(
    *,
    observation: VelocityObservation,
    features: VelocityUncertaintyFeatures,
) -> None:
    """Prevent a variance from being attached to a different model output."""

    if (
        observation.timestamp_ns != features.timestamp_ns
        or observation.source_id != features.source_id
        or observation.model_id != features.model_id
    ):
        raise ValueError("Observation and features must describe one output.")

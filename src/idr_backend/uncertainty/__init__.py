"""Causal velocity-observation uncertainty estimates for later fusion.

The committed selected-model path is a deterministic, horizon-aware profile
calibrated from grouped out-of-fold residuals. The earlier learned artifact
targets the unselected stateful-GRU experiment and remains non-public.
"""

from .artifacts import load_anchor_delta_gru_deterministic_uncertainty_estimator
from .deterministic import DeterministicVelocityUncertaintyProfile
from .features import (
    UNCERTAINTY_FEATURE_NAMES,
    VelocityUncertaintyFeatures,
    build_velocity_uncertainty_features,
)
from .heuristics import HeuristicUncertaintyConfig, heuristic_uncertainty
from .protocol import (
    HeuristicVelocityUncertaintyEstimator,
    VelocityUncertaintyEstimator,
)

__all__ = [
    "HeuristicUncertaintyConfig",
    "HeuristicVelocityUncertaintyEstimator",
    "DeterministicVelocityUncertaintyProfile",
    "UNCERTAINTY_FEATURE_NAMES",
    "load_anchor_delta_gru_deterministic_uncertainty_estimator",
    "VelocityUncertaintyFeatures",
    "VelocityUncertaintyEstimator",
    "build_velocity_uncertainty_features",
    "heuristic_uncertainty",
]

"""Torch-free runtime protocol for velocity-observation uncertainty.

The selected deterministic profile must be importable on a deployment target
that intentionally has no PyTorch runtime.  Learned experimental estimators
live in ``inference.py`` and implement this small structural contract without
making the production composition import their heavyweight dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from idr_backend.sensors.types import UncertaintyEstimate, VelocityObservation

from .features import VelocityUncertaintyFeatures
from .heuristics import HeuristicUncertaintyConfig, heuristic_uncertainty


class VelocityUncertaintyEstimator(Protocol):
    """Publish variance for one already-computed, aligned speed observation."""

    def estimate(
        self,
        *,
        observation: VelocityObservation,
        features: VelocityUncertaintyFeatures,
    ) -> UncertaintyEstimate:
        """Estimate a positive scalar variance for the supplied observation."""


@dataclass(frozen=True, slots=True)
class HeuristicVelocityUncertaintyEstimator:
    """Explicit wrapper around the conservative pre-training fallback."""

    config: HeuristicUncertaintyConfig

    def estimate(
        self,
        *,
        observation: VelocityObservation,
        features: VelocityUncertaintyFeatures,
    ) -> UncertaintyEstimate:
        """Publish bounded non-learned variance from observable risk facts."""

        return heuristic_uncertainty(
            observation=observation,
            features=features,
            config=self.config,
        )

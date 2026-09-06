"""Small heteroscedastic variance network for an externally supplied speed model."""

import torch
from torch import nn


class HeteroscedasticVarianceNetwork(nn.Module):
    """Map causal uncertainty features to a bounded positive speed variance."""

    def __init__(
        self,
        *,
        feature_count: int,
        hidden_size: int,
        variance_floor_m2ps2: float,
        variance_ceiling_m2ps2: float,
    ) -> None:
        """Create a phone-sized MLP with an explicit output variance range."""

        super().__init__()
        if feature_count <= 0 or hidden_size <= 0:
            raise ValueError("feature_count and hidden_size must be positive.")
        if variance_floor_m2ps2 <= 0.0:
            raise ValueError("variance_floor_m2ps2 must be positive.")
        if variance_ceiling_m2ps2 < variance_floor_m2ps2:
            raise ValueError("variance ceiling must be at least the floor.")

        self._variance_floor_m2ps2 = variance_floor_m2ps2
        self._variance_ceiling_m2ps2 = variance_ceiling_m2ps2
        self._network = nn.Sequential(
            nn.Linear(feature_count, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """Return one strictly positive bounded variance per feature row."""

        if features.ndim != 2:
            raise ValueError("Uncertainty features must have shape (batch, features).")
        raw_variance = torch.nn.functional.softplus(
            self._network(features).squeeze(-1)
        )
        return torch.clamp(
            raw_variance + self._variance_floor_m2ps2,
            min=self._variance_floor_m2ps2,
            max=self._variance_ceiling_m2ps2,
        )

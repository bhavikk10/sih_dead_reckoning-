"""Training utility for the small heteroscedastic uncertainty network."""

from dataclasses import dataclass

import torch

from .losses import gaussian_negative_log_likelihood
from .model import HeteroscedasticVarianceNetwork


@dataclass(frozen=True, slots=True)
class UncertaintyTrainingConfig:
    """Explicit, deliberately small training configuration."""

    learning_rate: float
    epochs: int
    batch_size: int


def train_variance_network(
    *,
    model: HeteroscedasticVarianceNetwork,
    features: torch.Tensor,
    residuals_mps: torch.Tensor,
    config: UncertaintyTrainingConfig,
) -> tuple[float, ...]:
    """Fit variance to residuals and return mean NLL for each epoch.

    Split construction is intentionally outside this helper: callers must form
    journey/device-safe train and held-out calibration partitions before this
    function receives tensors.
    """

    if features.ndim != 2 or residuals_mps.ndim != 1:
        raise ValueError("Features must be 2D and residuals must be 1D.")
    if features.shape[0] != residuals_mps.shape[0] or features.shape[0] == 0:
        raise ValueError("Features and residuals must be non-empty and aligned.")
    if config.learning_rate <= 0.0 or config.epochs <= 0 or config.batch_size <= 0:
        raise ValueError("Learning rate, epochs, and batch size must be positive.")
    if not torch.isfinite(features).all() or not torch.isfinite(residuals_mps).all():
        raise ValueError("Training tensors must be finite.")

    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    losses: list[float] = []
    sample_count = features.shape[0]

    model.train()
    for _ in range(config.epochs):
        total_loss = 0.0
        examples_seen = 0
        for start in range(0, sample_count, config.batch_size):
            stop = min(start + config.batch_size, sample_count)
            batch_features = features[start:stop]
            batch_residuals = residuals_mps[start:stop]

            optimizer.zero_grad(set_to_none=True)
            variance = model(batch_features)
            loss = gaussian_negative_log_likelihood(
                batch_residuals,
                variance,
            )
            loss.backward()
            optimizer.step()

            batch_size = stop - start
            total_loss += float(loss.detach()) * batch_size
            examples_seen += batch_size

        losses.append(total_loss / examples_seen)

    return tuple(losses)

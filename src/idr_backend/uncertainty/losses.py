"""Numerically safe objectives for heteroscedastic velocity uncertainty."""

from math import log, pi
from typing import Literal

import torch


Reduction = Literal["mean", "sum", "none"]


def gaussian_negative_log_likelihood(
    residual_mps: torch.Tensor,
    variance_m2ps2: torch.Tensor,
    *,
    reduction: Reduction = "mean",
) -> torch.Tensor:
    """Return Gaussian NLL for residuals and strictly positive variances."""

    if residual_mps.shape != variance_m2ps2.shape:
        raise ValueError("Residuals and variances must have the same shape.")
    if not torch.isfinite(residual_mps).all() or not torch.isfinite(variance_m2ps2).all():
        raise ValueError("Residuals and variances must be finite.")
    if torch.any(variance_m2ps2 <= 0.0):
        raise ValueError("Variance must be strictly positive.")

    loss = 0.5 * (
        torch.log(variance_m2ps2)
        + residual_mps.square() / variance_m2ps2
        + log(2.0 * pi)
    )
    if reduction == "none":
        return loss
    if reduction == "mean":
        return loss.mean()
    if reduction == "sum":
        return loss.sum()
    raise ValueError("reduction must be 'mean', 'sum', or 'none'.")

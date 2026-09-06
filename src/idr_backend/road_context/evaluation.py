"""Offline quantile evaluation and calibration gates for road context."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import numpy as np

from .splits import RoadContextFold, RoadContextSplitStrategy
from .rules import RoadContextQuantilePrediction


@dataclass(frozen=True, slots=True)
class RoadContextQuantileMetrics:
    """Aggregate offline metrics for p10/p50/p90 speed predictions."""

    sample_count: int
    median_mae_mps: float
    mean_pinball_loss_mps: float
    observed_interval_coverage: float
    expected_interval_coverage: float
    mean_interval_width_mps: float

    def __post_init__(self) -> None:
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive.")

        finite_nonnegative = (
            self.median_mae_mps,
            self.mean_pinball_loss_mps,
            self.observed_interval_coverage,
            self.expected_interval_coverage,
            self.mean_interval_width_mps,
        )
        if not all(isfinite(value) and value >= 0.0 for value in finite_nonnegative):
            raise ValueError("Road-context metrics must be finite and non-negative.")
        if self.observed_interval_coverage > 1.0:
            raise ValueError("observed_interval_coverage must not exceed one.")
        if not 0.0 < self.expected_interval_coverage < 1.0:
            raise ValueError("expected_interval_coverage must lie strictly between zero and one.")

    @property
    def median_mae_kph(self) -> float:
        return self.median_mae_mps * 3.6

    @property
    def mean_interval_width_kph(self) -> float:
        return self.mean_interval_width_mps * 3.6

    @property
    def coverage_error(self) -> float:
        """Positive means the prediction intervals are over-conservative."""

        return self.observed_interval_coverage - self.expected_interval_coverage


@dataclass(frozen=True, slots=True)
class RoadContextFoldEvaluation:
    """Metrics for one validation fold, never for its training rows."""

    fold_index: int
    strategy: RoadContextSplitStrategy
    validation_indices: tuple[int, ...]
    metrics: RoadContextQuantileMetrics

    def __post_init__(self) -> None:
        if self.fold_index < 0:
            raise ValueError("fold_index must be non-negative.")
        if not self.validation_indices:
            raise ValueError("Fold evaluation requires validation rows.")
        if len(self.validation_indices) != self.metrics.sample_count:
            raise ValueError(
                "Validation indices must align with the evaluated sample count."
            )


@dataclass(frozen=True, slots=True)
class RoadContextEvaluationReport:
    """Combined out-of-fold metrics for one grouped split strategy."""

    strategy: RoadContextSplitStrategy
    folds: tuple[RoadContextFoldEvaluation, ...]
    overall_metrics: RoadContextQuantileMetrics

    def __post_init__(self) -> None:
        if not self.folds:
            raise ValueError("Evaluation report requires at least one fold.")
        if any(fold.strategy is not self.strategy for fold in self.folds):
            raise ValueError("Every fold must use the report strategy.")

        fold_sample_count = sum(fold.metrics.sample_count for fold in self.folds)
        if fold_sample_count != self.overall_metrics.sample_count:
            raise ValueError("Overall sample_count must equal the sum of fold counts.")


def evaluate_road_context_quantiles(
    *,
    target_speed_mps: Sequence[float] | np.ndarray,
    predictions: Sequence[RoadContextQuantilePrediction],
    expected_interval_coverage: float = 0.80,
) -> RoadContextQuantileMetrics:
    """Evaluate p10/p50/p90 predictions against offline CAN speed only."""

    if not 0.0 < expected_interval_coverage < 1.0:
        raise ValueError("expected_interval_coverage must lie strictly between zero and one.")

    targets = np.asarray(target_speed_mps, dtype=float)
    if targets.ndim != 1 or not len(targets):
        raise ValueError("target_speed_mps must be a non-empty one-dimensional sequence.")
    if not np.isfinite(targets).all() or np.any(targets < 0.0):
        raise ValueError("Offline targets must be finite and non-negative.")
    if len(predictions) != len(targets):
        raise ValueError("Predictions must align one-to-one with targets.")

    p10 = np.asarray([prediction.speed_p10_mps for prediction in predictions], dtype=float)
    p50 = np.asarray([prediction.speed_p50_mps for prediction in predictions], dtype=float)
    p90 = np.asarray([prediction.speed_p90_mps for prediction in predictions], dtype=float)

    interval_contains_target = (targets >= p10) & (targets <= p90)
    pinball_losses = np.stack(
        (
            _pinball_loss(targets, p10, quantile=0.10),
            _pinball_loss(targets, p50, quantile=0.50),
            _pinball_loss(targets, p90, quantile=0.90),
        ),
        axis=1,
    )

    return RoadContextQuantileMetrics(
        sample_count=len(targets),
        median_mae_mps=float(np.mean(np.abs(targets - p50))),
        mean_pinball_loss_mps=float(np.mean(pinball_losses)),
        observed_interval_coverage=float(np.mean(interval_contains_target)),
        expected_interval_coverage=expected_interval_coverage,
        mean_interval_width_mps=float(np.mean(p90 - p10)),
    )


def evaluate_validation_fold(
    *,
    fold: RoadContextFold,
    target_speed_mps: Sequence[float] | np.ndarray,
    predictions: Sequence[RoadContextQuantilePrediction],
) -> RoadContextFoldEvaluation:
    """Wrap validation-only metrics with the split identity that produced them."""

    return RoadContextFoldEvaluation(
        fold_index=fold.fold_index,
        strategy=fold.strategy,
        validation_indices=fold.validation_indices,
        metrics=evaluate_road_context_quantiles(
            target_speed_mps=target_speed_mps,
            predictions=predictions,
        ),
    )


def _pinball_loss(
    targets: np.ndarray,
    predictions: np.ndarray,
    *,
    quantile: float,
) -> np.ndarray:
    residual = targets - predictions
    return np.maximum(quantile * residual, (quantile - 1.0) * residual)


@dataclass(frozen=True, slots=True)
class RoadContextCalibrationGate:
    """Minimum evidence required before uncertainty may be trusted downstream."""

    minimum_sample_count: int = 100
    maximum_absolute_coverage_error: float = 0.05

    def __post_init__(self) -> None:
        if self.minimum_sample_count <= 0:
            raise ValueError("minimum_sample_count must be positive.")
        if (
            not isfinite(self.maximum_absolute_coverage_error)
            or self.maximum_absolute_coverage_error < 0.0
        ):
            raise ValueError(
                "maximum_absolute_coverage_error must be finite and non-negative."
            )

    def accepts(self, metrics: RoadContextQuantileMetrics) -> bool:
        return (
            metrics.sample_count >= self.minimum_sample_count
            and abs(metrics.coverage_error)
            <= self.maximum_absolute_coverage_error
        )


def build_evaluation_report(
    fold_evaluations: Sequence[RoadContextFoldEvaluation],
) -> RoadContextEvaluationReport:
    """Aggregate separate validation folds into true out-of-fold metrics."""

    if not fold_evaluations:
        raise ValueError("At least one fold evaluation is required.")

    folds = tuple(sorted(fold_evaluations, key=lambda fold: fold.fold_index))
    strategy = folds[0].strategy
    if any(fold.strategy is not strategy for fold in folds):
        raise ValueError("Cannot aggregate different split strategies.")

    total_samples = sum(fold.metrics.sample_count for fold in folds)

    def weighted_mean(attribute: str) -> float:
        return float(
            sum(
                getattr(fold.metrics, attribute) * fold.metrics.sample_count
                for fold in folds
            )
            / total_samples
        )

    overall_metrics = RoadContextQuantileMetrics(
        sample_count=total_samples,
        median_mae_mps=weighted_mean("median_mae_mps"),
        mean_pinball_loss_mps=weighted_mean("mean_pinball_loss_mps"),
        observed_interval_coverage=weighted_mean("observed_interval_coverage"),
        expected_interval_coverage=weighted_mean("expected_interval_coverage"),
        mean_interval_width_mps=weighted_mean("mean_interval_width_mps"),
    )

    return RoadContextEvaluationReport(
        strategy=strategy,
        folds=folds,
        overall_metrics=overall_metrics,
    )


__all__ = [
    "RoadContextCalibrationGate",
    "RoadContextEvaluationReport",
    "RoadContextFoldEvaluation",
    "RoadContextQuantileMetrics",
    "build_evaluation_report",
    "evaluate_road_context_quantiles",
    "evaluate_validation_fold",
]
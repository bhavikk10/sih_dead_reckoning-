"""Leakage-safe offline experiments for road-context quantile models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .evaluation import (
    RoadContextEvaluationReport,
    RoadContextFoldEvaluation,
    build_evaluation_report,
    evaluate_validation_fold,
)
from .features import RoadContextFeatureDataset
from .quantile_model import (
    RoadClassEmpiricalQuantileBaseline,
    fit_road_class_empirical_quantile_baseline,
)
from .splits import (
    FoldTrainingWeights,
    RoadContextFold,
    RoadContextSplitPlan,
    RoadContextWeightConfig,
    build_fold_training_weights,
)


@dataclass(frozen=True, slots=True)
class RoadContextFittedFold:
    """One training-only fitted model and its independent validation result."""

    fold: RoadContextFold
    model: RoadClassEmpiricalQuantileBaseline
    training_weights: FoldTrainingWeights
    evaluation: RoadContextFoldEvaluation

    def __post_init__(self) -> None:
        if self.training_weights.fold_index != self.fold.fold_index:
            raise ValueError("Training weights must belong to the fitted fold.")
        if self.evaluation.fold_index != self.fold.fold_index:
            raise ValueError("Evaluation must belong to the fitted fold.")
        if self.evaluation.strategy is not self.fold.strategy:
            raise ValueError("Evaluation strategy must match the fitted fold.")


@dataclass(frozen=True, slots=True)
class RoadContextExperimentResult:
    """Complete out-of-fold result for one split strategy and model family."""

    split_plan: RoadContextSplitPlan
    fitted_folds: tuple[RoadContextFittedFold, ...]
    evaluation_report: RoadContextEvaluationReport
    oof_predictions: pd.DataFrame

    def __post_init__(self) -> None:
        if len(self.fitted_folds) != len(self.split_plan.folds):
            raise ValueError("Every split-plan fold must have one fitted result.")
        if self.evaluation_report.strategy is not self.split_plan.strategy:
            raise ValueError("Evaluation report strategy must match the split plan.")

        required_columns = {
            "source_row_index",
            "fold_index",
            "split_strategy",
            "target_speed_mps",
            "speed_p10_mps",
            "speed_p50_mps",
            "speed_p90_mps",
            "model_id",
        }
        missing_columns = required_columns.difference(self.oof_predictions.columns)
        if missing_columns:
            raise ValueError(
                f"OOF predictions lack required columns: {sorted(missing_columns)!r}."
            )

        source_row_indices = sorted(
            self.oof_predictions["source_row_index"].astype(int).tolist()
        )
        if source_row_indices != list(range(self.split_plan.row_count)):
            raise ValueError(
                "OOF predictions must contain every source row exactly once."
            )


def run_road_class_empirical_quantile_experiment(
    *,
    dataset: RoadContextFeatureDataset,
    split_plan: RoadContextSplitPlan,
    model_id_prefix: str = "road_class_empirical_quantiles_v1",
    weight_config: RoadContextWeightConfig = RoadContextWeightConfig(),
) -> RoadContextExperimentResult:
    """Run a fully leakage-safe empirical-baseline experiment.

    Each fold fits only on its training rows and their fold-local weights.
    Validation targets are used only after prediction, for offline metrics.
    """

    if split_plan.graph_id != dataset.graph_id:
        raise ValueError("Split plan graph_id must match the feature dataset.")
    if split_plan.row_count != len(dataset.frame):
        raise ValueError("Split plan row count must match the feature dataset.")
    if not model_id_prefix.strip():
        raise ValueError("model_id_prefix must not be blank.")

    fitted_folds: list[RoadContextFittedFold] = []
    oof_frames: list[pd.DataFrame] = []

    for fold in split_plan.folds:
        train_dataset = _subset_dataset(dataset, fold.train_indices)
        validation_dataset = _subset_dataset(dataset, fold.validation_indices)

        training_weights = build_fold_training_weights(
            dataset,
            fold,
            config=weight_config,
        )
        model = fit_road_class_empirical_quantile_baseline(
            train_dataset,
            model_id=f"{model_id_prefix}_fold_{fold.fold_index}",
            sample_weight=training_weights.weights,
        )

        predictions = model.predict(validation_dataset.model_features)
        evaluation = evaluate_validation_fold(
            fold=fold,
            target_speed_mps=validation_dataset.targets_mps,
            predictions=predictions,
        )

        fitted_folds.append(
            RoadContextFittedFold(
                fold=fold,
                model=model,
                training_weights=training_weights,
                evaluation=evaluation,
            )
        )
        oof_frames.append(
            _build_fold_oof_frame(
                dataset=dataset,
                fold=fold,
                model_id=model.metadata.model_id,
                predictions=predictions,
            )
        )

    evaluation_report = build_evaluation_report(
        tuple(fitted_fold.evaluation for fitted_fold in fitted_folds)
    )
    oof_predictions = (
        pd.concat(oof_frames, ignore_index=True)
        .sort_values("source_row_index", kind="stable")
        .reset_index(drop=True)
    )

    return RoadContextExperimentResult(
        split_plan=split_plan,
        fitted_folds=tuple(fitted_folds),
        evaluation_report=evaluation_report,
        oof_predictions=oof_predictions,
    )


def _subset_dataset(
    dataset: RoadContextFeatureDataset,
    row_indices: tuple[int, ...],
) -> RoadContextFeatureDataset:
    return RoadContextFeatureDataset(
        frame=dataset.frame.iloc[list(row_indices)].reset_index(drop=True),
        graph_id=dataset.graph_id,
    )


def _build_fold_oof_frame(
    *,
    dataset: RoadContextFeatureDataset,
    fold: RoadContextFold,
    model_id: str,
    predictions: tuple,
) -> pd.DataFrame:
    if len(predictions) != len(fold.validation_indices):
        raise ValueError("Predictions must align with validation indices.")

    validation_frame = dataset.frame.iloc[list(fold.validation_indices)]
    retained_columns = [
        column_name
        for column_name in (
            "journey_id",
            "timestamp_ns",
            "graph_id",
            "matched_edge_id",
            "matched_travel_direction",
            "target_speed_mps",
        )
        if column_name in validation_frame.columns
    ]

    oof_frame = validation_frame.loc[:, retained_columns].reset_index(drop=True).copy()
    oof_frame.insert(
        0,
        "source_row_index",
        np.asarray(fold.validation_indices, dtype=int),
    )
    oof_frame.insert(1, "fold_index", fold.fold_index)
    oof_frame.insert(2, "split_strategy", fold.strategy.value)
    oof_frame["model_id"] = model_id
    oof_frame["speed_p10_mps"] = [
        prediction.speed_p10_mps for prediction in predictions
    ]
    oof_frame["speed_p50_mps"] = [
        prediction.speed_p50_mps for prediction in predictions
    ]
    oof_frame["speed_p90_mps"] = [
        prediction.speed_p90_mps for prediction in predictions
    ]

    return oof_frame


__all__ = [
    "RoadContextExperimentResult",
    "RoadContextFittedFold",
    "run_road_class_empirical_quantile_experiment",
]



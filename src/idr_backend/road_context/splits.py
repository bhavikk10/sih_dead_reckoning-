"""Leakage-safe offline split and sample-weight utilities for road context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Sequence

import numpy as np
import pandas as pd

from .features import RoadContextFeatureDataset


_JOURNEY_COLUMN = "journey_id"
_EDGE_COLUMN = "matched_edge_id"
_DIRECTION_COLUMN = "matched_travel_direction"


class RoadContextSplitStrategy(StrEnum):
    JOURNEY_HELD_OUT = "journey_held_out"
    DIRECTED_EDGE_HELD_OUT = "directed_edge_held_out"


@dataclass(frozen=True, slots=True)
class RoadContextSplitConfig:
    """Configuration shared by journey and directed-edge held-out splits."""

    n_splits: int = 5
    seed: int = 42

    def __post_init__(self) -> None:
        if self.n_splits < 2:
            raise ValueError("n_splits must be at least 2.")
        if self.seed < 0:
            raise ValueError("seed must be non-negative.")


@dataclass(frozen=True, slots=True)
class RoadContextFold:
    """One fold, represented by original row positions in the feature dataset."""

    fold_index: int
    strategy: RoadContextSplitStrategy
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    train_group_ids: tuple[str, ...]
    validation_group_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.fold_index < 0:
            raise ValueError("fold_index must be non-negative.")
        if not self.train_indices or not self.validation_indices:
            raise ValueError("Every fold must contain training and validation rows.")
        if any(index < 0 for index in self.train_indices + self.validation_indices):
            raise ValueError("Fold indices must be non-negative.")
        if len(set(self.train_indices)) != len(self.train_indices):
            raise ValueError("train_indices must not contain duplicates.")
        if len(set(self.validation_indices)) != len(self.validation_indices):
            raise ValueError("validation_indices must not contain duplicates.")
        if set(self.train_indices).intersection(self.validation_indices):
            raise ValueError("Training and validation rows must not overlap.")
        if set(self.train_group_ids).intersection(self.validation_group_ids):
            raise ValueError("Training and validation groups must not overlap.")


@dataclass(frozen=True, slots=True)
class RoadContextSplitPlan:
    """A reproducible grouped split plan for one immutable feature dataset."""

    graph_id: str
    strategy: RoadContextSplitStrategy
    row_count: int
    group_column: str
    folds: tuple[RoadContextFold, ...]

    def __post_init__(self) -> None:
        if self.row_count <= 0:
            raise ValueError("row_count must be positive.")
        if len(self.folds) < 2:
            raise ValueError("A split plan requires at least two folds.")

        all_rows = set(range(self.row_count))
        observed_validation_rows: list[int] = []

        for fold in self.folds:
            if fold.strategy is not self.strategy:
                raise ValueError("Every fold must use the split plan strategy.")

            train_rows = set(fold.train_indices)
            validation_rows = set(fold.validation_indices)

            if not train_rows.issubset(all_rows) or not validation_rows.issubset(all_rows):
                raise ValueError("Fold contains row positions outside the dataset.")
            if train_rows.union(validation_rows) != all_rows:
                raise ValueError("Each fold must partition every dataset row.")

            observed_validation_rows.extend(fold.validation_indices)

        if sorted(observed_validation_rows) != list(range(self.row_count)):
            raise ValueError(
                "Validation folds must cover each dataset row exactly once."
            )


def build_journey_holdout_split_plan(
    dataset: RoadContextFeatureDataset,
    config: RoadContextSplitConfig = RoadContextSplitConfig(),
) -> RoadContextSplitPlan:
    """Build folds where whole journeys are withheld from training."""

    journey_ids = _required_text_column(dataset.frame, _JOURNEY_COLUMN)
    return _build_grouped_split_plan(
        dataset=dataset,
        config=config,
        strategy=RoadContextSplitStrategy.JOURNEY_HELD_OUT,
        group_column=_JOURNEY_COLUMN,
        group_ids=journey_ids,
    )


def build_directed_edge_holdout_split_plan(
    dataset: RoadContextFeatureDataset,
    config: RoadContextSplitConfig = RoadContextSplitConfig(),
) -> RoadContextSplitPlan:
    """Build spatially conservative folds where directed road edges are withheld."""

    directed_edge_ids = _directed_edge_group_ids(dataset.frame)
    return _build_grouped_split_plan(
        dataset=dataset,
        config=config,
        strategy=RoadContextSplitStrategy.DIRECTED_EDGE_HELD_OUT,
        group_column=f"{_EDGE_COLUMN}+{_DIRECTION_COLUMN}",
        group_ids=directed_edge_ids,
    )


def _build_grouped_split_plan(
    *,
    dataset: RoadContextFeatureDataset,
    config: RoadContextSplitConfig,
    strategy: RoadContextSplitStrategy,
    group_column: str,
    group_ids: Sequence[str],
) -> RoadContextSplitPlan:
    if len(group_ids) != len(dataset.frame):
        raise ValueError("group_ids must contain exactly one value per dataset row.")

    group_to_rows: dict[str, list[int]] = {}
    for row_index, group_id in enumerate(group_ids):
        group_to_rows.setdefault(group_id, []).append(row_index)

    if len(group_to_rows) < config.n_splits:
        raise ValueError(
            f"{strategy.value} requires at least {config.n_splits} distinct groups; "
            f"only found {len(group_to_rows)}."
        )

    rng = np.random.default_rng(config.seed)
    group_ids_sorted = sorted(group_to_rows)
    shuffled_group_ids = rng.permutation(np.asarray(group_ids_sorted, dtype=object))
    tie_break_rank = {
        str(group_id): rank
        for rank, group_id in enumerate(shuffled_group_ids.tolist())
    }

    ordered_group_ids = sorted(
        group_to_rows,
        key=lambda group_id: (
            -len(group_to_rows[group_id]),
            tie_break_rank[group_id],
            group_id,
        ),
    )

    groups_per_fold: list[list[str]] = [[] for _ in range(config.n_splits)]
    row_count_per_fold = [0 for _ in range(config.n_splits)]

    for group_id in ordered_group_ids:
        destination_fold = min(
            range(config.n_splits),
            key=lambda fold_index: (
                row_count_per_fold[fold_index],
                len(groups_per_fold[fold_index]),
                fold_index,
            ),
        )
        groups_per_fold[destination_fold].append(group_id)
        row_count_per_fold[destination_fold] += len(group_to_rows[group_id])

    all_group_ids = set(group_to_rows)
    folds: list[RoadContextFold] = []

    for fold_index, validation_groups_unsorted in enumerate(groups_per_fold):
        validation_group_ids = tuple(sorted(validation_groups_unsorted))
        validation_group_set = set(validation_group_ids)
        train_group_ids = tuple(sorted(all_group_ids - validation_group_set))

        validation_indices = tuple(
            row_index
            for row_index, group_id in enumerate(group_ids)
            if group_id in validation_group_set
        )
        train_indices = tuple(
            row_index
            for row_index, group_id in enumerate(group_ids)
            if group_id not in validation_group_set
        )

        folds.append(
            RoadContextFold(
                fold_index=fold_index,
                strategy=strategy,
                train_indices=train_indices,
                validation_indices=validation_indices,
                train_group_ids=train_group_ids,
                validation_group_ids=validation_group_ids,
            )
        )

    return RoadContextSplitPlan(
        graph_id=dataset.graph_id,
        strategy=strategy,
        row_count=len(dataset.frame),
        group_column=group_column,
        folds=tuple(folds),
    )


def _required_text_column(frame: pd.DataFrame, column_name: str) -> tuple[str, ...]:
    if column_name not in frame.columns:
        raise ValueError(f"Road-context feature frame lacks required '{column_name}'.")

    values: list[str] = []
    for value in frame[column_name].tolist():
        if pd.isna(value):
            raise ValueError(f"'{column_name}' must not contain null values.")
        text = str(value).strip()
        if not text:
            raise ValueError(f"'{column_name}' must not contain blank values.")
        values.append(text)

    return tuple(values)


def _directed_edge_group_ids(frame: pd.DataFrame) -> tuple[str, ...]:
    edge_ids = _required_text_column(frame, _EDGE_COLUMN)
    directions = _required_text_column(frame, _DIRECTION_COLUMN)

    return tuple(
        f"{edge_id}::{direction}"
        for edge_id, direction in zip(edge_ids, directions, strict=True)
    )


@dataclass(frozen=True, slots=True)
class RoadContextWeightConfig:
    """Limits for leakage-safe, journey-balanced training sample weights."""

    minimum_weight: float = 0.25
    maximum_weight: float = 4.0

    def __post_init__(self) -> None:
        if not isfinite(self.minimum_weight) or not isfinite(self.maximum_weight):
            raise ValueError("Weight limits must be finite.")
        if self.minimum_weight <= 0.0:
            raise ValueError("minimum_weight must be positive.")
        if self.minimum_weight > 1.0 or self.maximum_weight < 1.0:
            raise ValueError("Weight limits must contain 1.0.")
        if self.maximum_weight < self.minimum_weight:
            raise ValueError("maximum_weight must be at least minimum_weight.")


@dataclass(frozen=True, slots=True)
class FoldTrainingWeights:
    """Weights aligned positionally with one fold's train_indices."""

    fold_index: int
    training_indices: tuple[int, ...]
    weights: tuple[float, ...]
    journey_weight_sums: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if len(self.training_indices) != len(self.weights):
            raise ValueError("Weights must align with training_indices.")
        if not self.weights:
            raise ValueError("At least one training weight is required.")
        if any(not isfinite(weight) or weight <= 0.0 for weight in self.weights):
            raise ValueError("Training weights must be finite and positive.")

        mean_weight = float(np.mean(np.asarray(self.weights, dtype=float)))
        if not np.isclose(mean_weight, 1.0, rtol=1e-8, atol=1e-8):
            raise ValueError("Training weights must have mean one.")


def build_fold_training_weights(
    dataset: RoadContextFeatureDataset,
    fold: RoadContextFold,
    config: RoadContextWeightConfig = RoadContextWeightConfig(),
) -> FoldTrainingWeights:
    """Create weights using only rows available inside ``fold``'s training set.

    Each journey receives equal total influence. Within a journey, frequently
    repeated directed edges are down-weighted by inverse square-root exposure.
    """

    if any(index >= len(dataset.frame) for index in fold.train_indices):
        raise ValueError("Fold training indices exceed the feature dataset size.")

    train_frame = dataset.frame.iloc[list(fold.train_indices)]
    journey_ids = _required_text_column(train_frame, _JOURNEY_COLUMN)
    directed_edge_ids = _directed_edge_group_ids(train_frame)

    exposure_frame = pd.DataFrame(
        {
            "journey_id": journey_ids,
            "directed_edge_id": directed_edge_ids,
        }
    )

    journey_row_counts = (
        exposure_frame.groupby("journey_id", sort=False)["journey_id"]
        .transform("size")
        .to_numpy(dtype=float)
    )
    directed_edge_counts = (
        exposure_frame.groupby(
            ["journey_id", "directed_edge_id"],
            sort=False,
        )["journey_id"]
        .transform("size")
        .to_numpy(dtype=float)
    )

    raw_weights = 1.0 / journey_row_counts
    raw_weights /= np.sqrt(directed_edge_counts)

    journey_raw_totals = (
        pd.Series(raw_weights)
        .groupby(exposure_frame["journey_id"], sort=False)
        .transform("sum")
        .to_numpy(dtype=float)
    )
    journey_balanced_weights = raw_weights / journey_raw_totals

    bounded_weights = _bounded_mean_one(
        journey_balanced_weights,
        minimum_weight=config.minimum_weight,
        maximum_weight=config.maximum_weight,
    )

    summary_frame = pd.DataFrame(
        {
            "journey_id": journey_ids,
            "weight": bounded_weights,
        }
    )
    journey_weight_sums = tuple(
        (str(journey_id), float(weight_sum))
        for journey_id, weight_sum in summary_frame.groupby(
            "journey_id",
            sort=True,
        )["weight"].sum().items()
    )

    return FoldTrainingWeights(
        fold_index=fold.fold_index,
        training_indices=fold.train_indices,
        weights=tuple(float(weight) for weight in bounded_weights),
        journey_weight_sums=journey_weight_sums,
    )


def _bounded_mean_one(
    raw_weights: np.ndarray,
    *,
    minimum_weight: float,
    maximum_weight: float,
) -> np.ndarray:
    """Clip positive weights while preserving an exact mean of one."""

    values = np.asarray(raw_weights, dtype=float)
    if values.ndim != 1 or not len(values):
        raise ValueError("raw_weights must be a non-empty one-dimensional array.")
    if not np.isfinite(values).all() or np.any(values <= 0.0):
        raise ValueError("raw_weights must be finite and positive.")

    lower_scale = 0.0
    upper_scale = 1.0

    while float(
        np.mean(np.clip(upper_scale * values, minimum_weight, maximum_weight))
    ) < 1.0:
        upper_scale *= 2.0
        if upper_scale > 1e12:
            raise RuntimeError("Could not normalize bounded training weights.")

    for _ in range(80):
        candidate_scale = (lower_scale + upper_scale) / 2.0
        candidate_mean = float(
            np.mean(
                np.clip(
                    candidate_scale * values,
                    minimum_weight,
                    maximum_weight,
                )
            )
        )
        if candidate_mean < 1.0:
            lower_scale = candidate_scale
        else:
            upper_scale = candidate_scale

    return np.clip(
        upper_scale * values,
        minimum_weight,
        maximum_weight,
    )


__all__ = [
    "FoldTrainingWeights",
    "RoadContextFold",
    "RoadContextSplitConfig",
    "RoadContextSplitPlan",
    "RoadContextSplitStrategy",
    "RoadContextWeightConfig",
    "build_directed_edge_holdout_split_plan",
    "build_fold_training_weights",
    "build_journey_holdout_split_plan",
]
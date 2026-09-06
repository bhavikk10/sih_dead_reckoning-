"""Model-neutral road-context quantile contracts and empirical baselines.

No runtime fusion code belongs here. The first model is intentionally simple:
road-class empirical speed quantiles, fitted only on a training partition.
Later LightGBM/XGBoost predictors must implement the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from .features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextFeatureDataset,
)
from .rules import RoadContextQuantilePrediction


QUANTILE_LEVELS = (0.10, 0.50, 0.90)
_TARGET_COLUMN = "target_speed_mps"
_ROAD_CLASS_COLUMN = "road_class"


@dataclass(frozen=True, slots=True)
class RoadContextQuantileModelMetadata:
    """Versioned identity and permitted runtime feature schema for one model."""

    model_id: str
    graph_id: str
    feature_names: tuple[str, ...]
    training_kind: str

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.graph_id.strip():
            raise ValueError("Quantile-model model_id and graph_id must not be blank.")
        if not self.training_kind.strip():
            raise ValueError("Quantile-model training_kind must not be blank.")
        if not self.feature_names:
            raise ValueError("Quantile-model feature_names must not be empty.")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("Quantile-model feature_names must be unique.")
        if not set(self.feature_names).issubset(ROAD_CONTEXT_FEATURE_NAMES):
            raise ValueError(
                "Quantile-model feature schema includes target or forbidden fields."
            )


@dataclass(frozen=True, slots=True)
class RoadContextQuantileTriplet:
    """Validated q10/q50/q90 speed distribution in metres per second."""

    speed_p10_mps: float
    speed_p50_mps: float
    speed_p90_mps: float

    def __post_init__(self) -> None:
        values = (
            self.speed_p10_mps,
            self.speed_p50_mps,
            self.speed_p90_mps,
        )
        if not all(isfinite(value) and value >= 0.0 for value in values):
            raise ValueError("Quantile triplets must be finite and non-negative.")
        if self.speed_p10_mps > self.speed_p50_mps:
            raise ValueError("q10 must not exceed q50.")
        if self.speed_p50_mps > self.speed_p90_mps:
            raise ValueError("q50 must not exceed q90.")


class RoadContextQuantilePredictor(Protocol):
    """Backend-neutral candidate quantile predictor contract."""

    @property
    def metadata(self) -> RoadContextQuantileModelMetadata:
        """Return model identity, graph version, and accepted feature names."""

    def predict(
        self,
        features: pd.DataFrame,
    ) -> tuple[RoadContextQuantilePrediction, ...]:
        """Predict one raw q10/q50/q90 row per runtime candidate."""


@dataclass(frozen=True, slots=True)
class RoadClassEmpiricalQuantileBaseline:
    """Training-side road-class baseline with a global fallback.

    This baseline is intentionally limited to the runtime-permitted road class.
    It is useful for verifying grouped splits, calibration, and downstream
    mixture logic before training boosted quantile regressors.
    """

    metadata: RoadContextQuantileModelMetadata
    global_quantiles: RoadContextQuantileTriplet
    quantiles_by_road_class: Mapping[str, RoadContextQuantileTriplet]

    def __post_init__(self) -> None:
        if self.metadata.feature_names != (_ROAD_CLASS_COLUMN,):
            raise ValueError(
                "Road-class empirical baseline must declare only the road_class feature."
            )
        if not self.quantiles_by_road_class:
            raise ValueError("Road-class empirical baseline requires at least one class.")

        for road_class, quantiles in self.quantiles_by_road_class.items():
            if not road_class.strip():
                raise ValueError("Road-class baseline keys must not be blank.")
            if not isinstance(quantiles, RoadContextQuantileTriplet):
                raise ValueError("Road-class baseline values must be quantile triplets.")

    def predict(
        self,
        features: pd.DataFrame,
    ) -> tuple[RoadContextQuantilePrediction, ...]:
        """Return valid empirical quantiles without accessing offline targets."""

        _require_runtime_feature_columns(
            features=features,
            feature_names=self.metadata.feature_names,
        )

        predictions: list[RoadContextQuantilePrediction] = []
        for raw_road_class in features[_ROAD_CLASS_COLUMN]:
            road_class = _normalise_road_class(raw_road_class)
            quantiles = self.quantiles_by_road_class.get(
                road_class,
                self.global_quantiles,
            )
            predictions.append(
                RoadContextQuantilePrediction(
                    model_id=self.metadata.model_id,
                    speed_p10_mps=quantiles.speed_p10_mps,
                    speed_p50_mps=quantiles.speed_p50_mps,
                    speed_p90_mps=quantiles.speed_p90_mps,
                )
            )
        return tuple(predictions)


def fit_road_class_empirical_quantile_baseline(
    dataset: RoadContextFeatureDataset,
    *,
    model_id: str = "road_class_empirical_quantiles_v1",
    sample_weight: Sequence[float] | np.ndarray | pd.Series | None = None,
) -> RoadClassEmpiricalQuantileBaseline:
    """Fit the baseline on one already-selected training partition only.

    The caller owns splitting. Never pass a frame containing validation or
    spatial-holdout rows here, because even this simple baseline would leak
    road-class speed distributions across the boundary.
    """

    frame = dataset.frame.reset_index(drop=True)
    targets = frame[_TARGET_COLUMN].to_numpy(dtype=float)
    weights = _validated_sample_weights(sample_weight, expected_length=len(frame))

    global_quantiles = _weighted_quantile_triplet(
        values=targets,
        weights=weights,
    )

    by_class: dict[str, RoadContextQuantileTriplet] = {}
    for road_class, group in frame.groupby(_ROAD_CLASS_COLUMN, sort=True):
        row_positions = group.index.to_numpy()
        class_targets = group[_TARGET_COLUMN].to_numpy(dtype=float)

        if weights is None:
            class_weights = None
        else:
            class_weights = weights[row_positions]

        by_class[_normalise_road_class(road_class)] = _weighted_quantile_triplet(
            values=class_targets,
            weights=class_weights,
        )

    return RoadClassEmpiricalQuantileBaseline(
        metadata=RoadContextQuantileModelMetadata(
            model_id=model_id,
            graph_id=dataset.graph_id,
            feature_names=(_ROAD_CLASS_COLUMN,),
            training_kind="road_class_empirical_quantile_baseline",
        ),
        global_quantiles=global_quantiles,
        quantiles_by_road_class=by_class,
    )


def _require_runtime_feature_columns(
    *,
    features: pd.DataFrame,
    feature_names: tuple[str, ...],
) -> None:
    """Reject target leakage and schema drift before inference."""

    if _TARGET_COLUMN in features.columns:
        raise ValueError(
            "Quantile prediction features must not contain the offline CAN target."
        )

    missing = set(feature_names).difference(features.columns)
    if missing:
        raise ValueError(
            f"Quantile prediction frame is missing required features: {sorted(missing)!r}."
        )


def _validated_sample_weights(
    sample_weight: Sequence[float] | np.ndarray | pd.Series | None,
    *,
    expected_length: int,
) -> np.ndarray | None:
    """Validate fold-local weights without deriving them from holdout data."""

    if sample_weight is None:
        return None

    weights = np.asarray(sample_weight, dtype=float)
    if weights.shape != (expected_length,):
        raise ValueError("Sample weights must contain exactly one value per training row.")
    if not np.isfinite(weights).all() or (weights <= 0.0).any():
        raise ValueError("Sample weights must be finite and strictly positive.")
    return weights


def _weighted_quantile_triplet(
    *,
    values: np.ndarray,
    weights: np.ndarray | None,
) -> RoadContextQuantileTriplet:
    """Compute q10/q50/q90 deterministically for one training-only group."""

    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not len(values):
        raise ValueError("Empirical quantiles require at least one one-dimensional value.")
    if not np.isfinite(values).all() or (values < 0.0).any():
        raise ValueError("Empirical quantile targets must be finite and non-negative.")

    if weights is None:
        q10, q50, q90 = np.quantile(values, QUANTILE_LEVELS)
    else:
        ordered = np.argsort(values, kind="stable")
        ordered_values = values[ordered]
        ordered_weights = weights[ordered]
        cumulative_weights = np.cumsum(ordered_weights)
        probabilities = (
            cumulative_weights - 0.5 * ordered_weights
        ) / cumulative_weights[-1]
        q10, q50, q90 = np.interp(
            QUANTILE_LEVELS,
            probabilities,
            ordered_values,
        )

    return RoadContextQuantileTriplet(
        speed_p10_mps=float(q10),
        speed_p50_mps=float(q50),
        speed_p90_mps=float(q90),
    )


def _normalise_road_class(value: object) -> str:
    """Map missing/blank categories to the same explicit unknown bucket."""

    if value is None or pd.isna(value):
        return "<unknown>"

    normalised = str(value).strip().lower()
    return normalised or "<unknown>"



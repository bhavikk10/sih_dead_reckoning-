"""Static-feature LightGBM quantile predictor for offline road context."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextFeatureDataset,
)
from .quantile_model import (
    QUANTILE_LEVELS,
    RoadContextQuantileModelMetadata,
    RoadContextQuantilePredictor,
)
from .rules import RoadContextQuantilePrediction


_TARGET_COLUMN = "target_speed_mps"
_ROAD_CLASS_COLUMN = "road_class"


@dataclass(frozen=True, slots=True)
class RoadContextLightGBMConfig:
    """Fixed, reproducible hyperparameters for three quantile regressors."""

    n_estimators: int = 400
    learning_rate: float = 0.04
    num_leaves: int = 15
    min_child_samples: int = 40
    reg_alpha: float = 0.05
    reg_lambda: float = 3.0
    random_state: int = 42
    n_jobs: int = 1

    def __post_init__(self) -> None:
        if self.n_estimators <= 0:
            raise ValueError("n_estimators must be positive.")
        if not isfinite(self.learning_rate) or self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be finite and positive.")
        if self.num_leaves < 2:
            raise ValueError("num_leaves must be at least two.")
        if self.min_child_samples <= 0:
            raise ValueError("min_child_samples must be positive.")
        if not isfinite(self.reg_alpha) or self.reg_alpha < 0.0:
            raise ValueError("reg_alpha must be finite and non-negative.")
        if not isfinite(self.reg_lambda) or self.reg_lambda < 0.0:
            raise ValueError("reg_lambda must be finite and non-negative.")
        if self.random_state < 0:
            raise ValueError("random_state must be non-negative.")
        if self.n_jobs <= 0:
            raise ValueError("n_jobs must be positive.")


@dataclass(frozen=True, slots=True)
class RoadContextLightGBMQuantileModel:
    """Three LightGBM quantile models using only runtime-permitted features."""

    metadata: RoadContextQuantileModelMetadata
    config: RoadContextLightGBMConfig
    road_class_codes: dict[str, int]
    estimators: tuple[Any, Any, Any]

    def __post_init__(self) -> None:
        if self.metadata.feature_names != ROAD_CONTEXT_FEATURE_NAMES:
            raise ValueError(
                "LightGBM road-context model must use the complete static schema."
            )
        if len(self.estimators) != len(QUANTILE_LEVELS):
            raise ValueError("One estimator is required for each declared quantile.")
        if not self.road_class_codes:
            raise ValueError("road_class_codes must not be empty.")
        if any(not road_class.strip() for road_class in self.road_class_codes):
            raise ValueError("Road-class vocabulary must not contain blank values.")
        if len(set(self.road_class_codes.values())) != len(self.road_class_codes):
            raise ValueError("Road-class codes must be unique.")

    def predict(
        self,
        features: pd.DataFrame,
    ) -> tuple[RoadContextQuantilePrediction, ...]:
        """Predict non-crossing q10/q50/q90 values from static road features."""

        encoded_features = _encode_features(
            features=features,
            feature_names=self.metadata.feature_names,
            road_class_codes=self.road_class_codes,
        )

        raw_quantiles = np.column_stack(
            [
                np.asarray(estimator.predict(encoded_features), dtype=float)
                for estimator in self.estimators
            ]
        )
        if not np.isfinite(raw_quantiles).all():
            raise RuntimeError("LightGBM quantile prediction produced non-finite values.")

        nonnegative_quantiles = np.maximum(raw_quantiles, 0.0)
        ordered_quantiles = np.sort(nonnegative_quantiles, axis=1)

        return tuple(
            RoadContextQuantilePrediction(
                model_id=self.metadata.model_id,
                speed_p10_mps=float(row[0]),
                speed_p50_mps=float(row[1]),
                speed_p90_mps=float(row[2]),
            )
            for row in ordered_quantiles
        )


def fit_road_context_lightgbm_quantile_model(
    dataset: RoadContextFeatureDataset,
    *,
    model_id: str = "road_context_lightgbm_quantiles_v1",
    config: RoadContextLightGBMConfig = RoadContextLightGBMConfig(),
    sample_weight: Sequence[float] | np.ndarray | pd.Series | None = None,
) -> RoadContextLightGBMQuantileModel:
    """Fit q10/q50/q90 regressors on one already-selected training partition."""

    if not model_id.strip():
        raise ValueError("model_id must not be blank.")

    weights = _validated_sample_weights(
        sample_weight,
        expected_length=len(dataset.frame),
    )
    road_class_codes = _build_road_class_codes(dataset.frame[_ROAD_CLASS_COLUMN])
    encoded_features = _encode_features(
        features=dataset.model_features,
        feature_names=ROAD_CONTEXT_FEATURE_NAMES,
        road_class_codes=road_class_codes,
    )
    targets = dataset.targets_mps.to_numpy(dtype=float)

    LGBMRegressor = _require_lightgbm_regressor()
    estimators: list[Any] = []

    for quantile_level in QUANTILE_LEVELS:
        estimator = LGBMRegressor(
            objective="quantile",
            alpha=quantile_level,
            n_estimators=config.n_estimators,
            learning_rate=config.learning_rate,
            num_leaves=config.num_leaves,
            min_child_samples=config.min_child_samples,
            reg_alpha=config.reg_alpha,
            reg_lambda=config.reg_lambda,
            random_state=config.random_state,
            n_jobs=config.n_jobs,
            verbosity=-1,
        )
        estimator.fit(
            encoded_features,
            targets,
            sample_weight=weights,
        )
        estimators.append(estimator)

    return RoadContextLightGBMQuantileModel(
        metadata=RoadContextQuantileModelMetadata(
            model_id=model_id,
            graph_id=dataset.graph_id,
            feature_names=ROAD_CONTEXT_FEATURE_NAMES,
            training_kind="lightgbm_static_road_context_quantiles",
        ),
        config=config,
        road_class_codes=road_class_codes,
        estimators=tuple(estimators),
    )


def _encode_features(
    *,
    features: pd.DataFrame,
    feature_names: tuple[str, ...],
    road_class_codes: dict[str, int],
) -> pd.DataFrame:
    if _TARGET_COLUMN in features.columns:
        raise ValueError("Quantile prediction features must not contain CAN target.")

    missing_features = set(feature_names).difference(features.columns)
    if missing_features:
        raise ValueError(
            f"Feature frame is missing required columns: {sorted(missing_features)!r}."
        )

    encoded = pd.DataFrame(index=features.index)

    for feature_name in feature_names:
        if feature_name == _ROAD_CLASS_COLUMN:
            encoded[feature_name] = [
                road_class_codes.get(_normalise_road_class(value), -1)
                for value in features[feature_name]
            ]
            continue

        numeric_values = pd.to_numeric(
            features[feature_name],
            errors="raise",
        ).to_numpy(dtype=float)

        if np.isinf(numeric_values).any():
            raise ValueError(
                f"Feature '{feature_name}' contains positive or negative infinity."
            )

        encoded[feature_name] = numeric_values

    return encoded


def _build_road_class_codes(values: pd.Series) -> dict[str, int]:
    road_classes = sorted({_normalise_road_class(value) for value in values})
    return {
        road_class: code
        for code, road_class in enumerate(road_classes)
    }


def _validated_sample_weights(
    sample_weight: Sequence[float] | np.ndarray | pd.Series | None,
    *,
    expected_length: int,
) -> np.ndarray | None:
    if sample_weight is None:
        return None

    weights = np.asarray(sample_weight, dtype=float)
    if weights.shape != (expected_length,):
        raise ValueError("Sample weights must contain one value per training row.")
    if not np.isfinite(weights).all() or np.any(weights <= 0.0):
        raise ValueError("Sample weights must be finite and strictly positive.")
    return weights


def _normalise_road_class(value: object) -> str:
    if value is None or pd.isna(value):
        return "<unknown>"

    normalised = str(value).strip().lower()
    return normalised or "<unknown>"


def _require_lightgbm_regressor() -> Any:
    try:
        from lightgbm import LGBMRegressor
    except ImportError as error:
        raise RuntimeError(
            "LightGBM is required for road-context quantile training. "
            "Install the project's declared dependencies first."
        ) from error

    return LGBMRegressor


assert _TARGET_COLUMN not in ROAD_CONTEXT_FEATURE_NAMES


__all__ = [
    "RoadContextLightGBMConfig",
    "RoadContextLightGBMQuantileModel",
    "fit_road_context_lightgbm_quantile_model",
]



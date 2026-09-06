from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextFeatureDataset,
)
from idr_backend.road_context.lightgbm_quantile import (
    RoadContextLightGBMConfig,
    fit_road_context_lightgbm_quantile_model,
)


def _dataset() -> RoadContextFeatureDataset:
    road_classes = ("residential", "tertiary", "primary", "secondary")
    rows: list[dict[str, object]] = []

    for journey_index, road_class in enumerate(road_classes):
        for observation_index in range(10):
            row = {feature_name: 0.0 for feature_name in ROAD_CONTEXT_FEATURE_NAMES}
            row.update(
                {
                    "graph_id": "test-graph",
                    "journey_id": f"journey-{journey_index}",
                    "matched_edge_id": f"edge-{journey_index}",
                    "matched_travel_direction": "forward",
                    "target_speed_mps": (
                        7.0 + journey_index * 3.0 + observation_index * 0.4
                    ),
                    "road_class": road_class,
                    "road_class_known": 1.0,
                    "speed_limit_mps": 8.3 + journey_index * 4.2,
                    "speed_limit_known": 1.0,
                    "lane_count": float(1 + journey_index % 3),
                    "lane_count_known": 1.0,
                    "is_oneway": float(journey_index % 2),
                    "edge_length_m": 80.0 + observation_index * 10.0,
                    "mean_abs_curvature_rad_per_m": observation_index * 0.001,
                    "p95_abs_curvature_rad_per_m": observation_index * 0.002,
                    "from_node_degree": 2.0,
                    "to_node_degree": 3.0,
                }
            )
            rows.append(row)

    return RoadContextFeatureDataset(
        frame=pd.DataFrame(rows),
        graph_id="test-graph",
    )


def _small_test_config() -> RoadContextLightGBMConfig:
    return RoadContextLightGBMConfig(
        n_estimators=20,
        learning_rate=0.1,
        num_leaves=4,
        min_child_samples=2,
        reg_alpha=0.0,
        reg_lambda=0.0,
        random_state=11,
        n_jobs=1,
    )


def test_lightgbm_quantile_model_predicts_valid_non_crossing_quantiles() -> None:
    dataset = _dataset()
    sample_weights = np.linspace(0.5, 1.5, len(dataset.frame))

    model = fit_road_context_lightgbm_quantile_model(
        dataset,
        model_id="test-road-context-lightgbm",
        config=_small_test_config(),
        sample_weight=sample_weights,
    )
    predictions = model.predict(dataset.model_features)

    assert model.metadata.graph_id == "test-graph"
    assert model.metadata.training_kind == "lightgbm_static_road_context_quantiles"
    assert len(predictions) == len(dataset.frame)

    for prediction in predictions:
        assert prediction.model_id == "test-road-context-lightgbm"
        assert prediction.speed_p10_mps >= 0.0
        assert prediction.speed_p10_mps <= prediction.speed_p50_mps
        assert prediction.speed_p50_mps <= prediction.speed_p90_mps


def test_lightgbm_model_rejects_target_leakage_and_accepts_unknown_road_classes() -> None:
    dataset = _dataset()
    model = fit_road_context_lightgbm_quantile_model(
        dataset,
        config=_small_test_config(),
    )

    with pytest.raises(ValueError, match="CAN target"):
        model.predict(dataset.frame)

    unseen_features = dataset.model_features.iloc[:3].copy()
    unseen_features["road_class"] = "brand-new-road-class"

    predictions = model.predict(unseen_features)

    assert len(predictions) == 3
    assert all(
        prediction.speed_p10_mps <= prediction.speed_p50_mps <= prediction.speed_p90_mps
        for prediction in predictions
    )
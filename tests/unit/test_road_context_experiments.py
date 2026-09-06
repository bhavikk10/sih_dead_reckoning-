from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from idr_backend.road_context.experiments import (
    run_road_class_empirical_quantile_experiment,
)
from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextFeatureDataset,
)
from idr_backend.road_context.splits import (
    RoadContextSplitConfig,
    build_journey_holdout_split_plan,
)


def _dataset() -> RoadContextFeatureDataset:
    journey_rows = (
        ("journey-a", "edge-a", "forward", "residential", 10.0),
        ("journey-a", "edge-a", "forward", "residential", 11.0),
        ("journey-a", "edge-b", "forward", "residential", 12.0),
        ("journey-a", "edge-b", "forward", "residential", 13.0),
        ("journey-b", "edge-c", "forward", "primary", 15.0),
        ("journey-b", "edge-c", "forward", "primary", 16.0),
        ("journey-b", "edge-d", "reverse", "primary", 17.0),
        ("journey-b", "edge-d", "reverse", "primary", 18.0),
        ("journey-c", "edge-e", "forward", "tertiary", 20.0),
        ("journey-c", "edge-e", "forward", "tertiary", 21.0),
        ("journey-c", "edge-f", "reverse", "tertiary", 22.0),
        ("journey-c", "edge-f", "reverse", "tertiary", 23.0),
    )

    rows: list[dict[str, object]] = []
    for journey_id, edge_id, direction, road_class, target_speed_mps in journey_rows:
        row = {feature_name: 0.0 for feature_name in ROAD_CONTEXT_FEATURE_NAMES}
        row.update(
            {
                "graph_id": "test-graph",
                "journey_id": journey_id,
                "matched_edge_id": edge_id,
                "matched_travel_direction": direction,
                "target_speed_mps": target_speed_mps,
                "road_class": road_class,
                "road_class_known": 1.0,
                "speed_limit_mps": 13.9,
                "speed_limit_known": 1.0,
                "lane_count": 1.0,
                "lane_count_known": 1.0,
                "edge_length_m": 100.0,
                "from_node_degree": 2.0,
                "to_node_degree": 2.0,
            }
        )
        rows.append(row)

    return RoadContextFeatureDataset(
        frame=pd.DataFrame(rows),
        graph_id="test-graph",
    )


def test_experiment_fits_only_fold_training_rows_and_returns_full_oof_output() -> None:
    dataset = _dataset()
    split_plan = build_journey_holdout_split_plan(
        dataset,
        RoadContextSplitConfig(n_splits=3, seed=13),
    )

    result = run_road_class_empirical_quantile_experiment(
        dataset=dataset,
        split_plan=split_plan,
        model_id_prefix="test-empirical-road-context",
    )

    assert len(result.fitted_folds) == 3
    assert result.evaluation_report.overall_metrics.sample_count == len(dataset.frame)
    assert result.oof_predictions["source_row_index"].tolist() == list(
        range(len(dataset.frame))
    )

    for fitted_fold in result.fitted_folds:
        fold_oof = result.oof_predictions.loc[
            result.oof_predictions["fold_index"] == fitted_fold.fold.fold_index
        ]

        assert fitted_fold.training_weights.training_indices == (
            fitted_fold.fold.train_indices
        )
        assert fitted_fold.evaluation.metrics.sample_count == len(
            fitted_fold.fold.validation_indices
        )
        assert sorted(fold_oof["source_row_index"].tolist()) == list(
            fitted_fold.fold.validation_indices
        )
        assert fold_oof["model_id"].nunique() == 1
        assert fold_oof["model_id"].iloc[0] == fitted_fold.model.metadata.model_id

    repeated_result = run_road_class_empirical_quantile_experiment(
        dataset=dataset,
        split_plan=split_plan,
        model_id_prefix="test-empirical-road-context",
    )
    pd.testing.assert_frame_equal(
        result.oof_predictions,
        repeated_result.oof_predictions,
    )


def test_experiment_rejects_a_split_plan_for_the_wrong_graph() -> None:
    dataset = _dataset()
    valid_plan = build_journey_holdout_split_plan(
        dataset,
        RoadContextSplitConfig(n_splits=3),
    )
    invalid_plan = replace(valid_plan, graph_id="different-graph")

    with pytest.raises(ValueError, match="graph_id"):
        run_road_class_empirical_quantile_experiment(
            dataset=dataset,
            split_plan=invalid_plan,
        )



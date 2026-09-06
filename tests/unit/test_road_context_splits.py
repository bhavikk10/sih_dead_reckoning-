from __future__ import annotations

import numpy as np
import pandas as pd

from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextFeatureDataset,
)
from idr_backend.road_context.splits import (
    RoadContextSplitConfig,
    RoadContextWeightConfig,
    build_directed_edge_holdout_split_plan,
    build_fold_training_weights,
    build_journey_holdout_split_plan,
)


def _dataset() -> RoadContextFeatureDataset:
    rows: list[dict[str, object]] = []

    journey_edge_rows = (
        ("journey-a", "edge-a", "forward", 11.0),
        ("journey-a", "edge-a", "forward", 12.0),
        ("journey-a", "edge-a", "forward", 13.0),
        ("journey-a", "edge-b", "forward", 14.0),
        ("journey-b", "edge-b", "forward", 15.0),
        ("journey-b", "edge-b", "forward", 16.0),
        ("journey-b", "edge-c", "reverse", 17.0),
        ("journey-b", "edge-c", "reverse", 18.0),
        ("journey-c", "edge-c", "reverse", 19.0),
        ("journey-c", "edge-d", "forward", 20.0),
        ("journey-c", "edge-d", "forward", 21.0),
        ("journey-c", "edge-d", "forward", 22.0),
    )

    for journey_id, edge_id, direction, target_speed_mps in journey_edge_rows:
        row = {feature_name: 0.0 for feature_name in ROAD_CONTEXT_FEATURE_NAMES}
        row.update(
            {
                "graph_id": "test-graph",
                "journey_id": journey_id,
                "matched_edge_id": edge_id,
                "matched_travel_direction": direction,
                "target_speed_mps": target_speed_mps,
                "road_class": "residential",
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


def _journeys_for_indices(
    dataset: RoadContextFeatureDataset,
    indices: tuple[int, ...],
) -> set[str]:
    return set(dataset.frame.iloc[list(indices)]["journey_id"].astype(str))


def _directed_edges_for_indices(
    dataset: RoadContextFeatureDataset,
    indices: tuple[int, ...],
) -> set[tuple[str, str]]:
    rows = dataset.frame.iloc[list(indices)]
    return {
        (str(row.matched_edge_id), str(row.matched_travel_direction))
        for row in rows.itertuples(index=False)
    }


def test_journey_holdout_is_deterministic_and_has_no_journey_leakage() -> None:
    dataset = _dataset()
    config = RoadContextSplitConfig(n_splits=3, seed=17)

    first_plan = build_journey_holdout_split_plan(dataset, config)
    second_plan = build_journey_holdout_split_plan(dataset, config)

    assert first_plan == second_plan
    assert first_plan.row_count == len(dataset.frame)

    observed_validation_rows: set[int] = set()

    for fold in first_plan.folds:
        train_journeys = _journeys_for_indices(dataset, fold.train_indices)
        validation_journeys = _journeys_for_indices(
            dataset,
            fold.validation_indices,
        )

        assert train_journeys.isdisjoint(validation_journeys)
        observed_validation_rows.update(fold.validation_indices)

    assert observed_validation_rows == set(range(len(dataset.frame)))


def test_directed_edge_holdout_has_no_spatial_group_leakage() -> None:
    dataset = _dataset()

    plan = build_directed_edge_holdout_split_plan(
        dataset,
        RoadContextSplitConfig(n_splits=3, seed=5),
    )

    for fold in plan.folds:
        train_edges = _directed_edges_for_indices(dataset, fold.train_indices)
        validation_edges = _directed_edges_for_indices(
            dataset,
            fold.validation_indices,
        )

        assert train_edges.isdisjoint(validation_edges)


def test_fold_training_weights_are_fold_local_and_journey_balanced() -> None:
    dataset = _dataset()
    fold = build_journey_holdout_split_plan(
        dataset,
        RoadContextSplitConfig(n_splits=3, seed=3),
    ).folds[0]

    wide_limits = RoadContextWeightConfig(
        minimum_weight=0.01,
        maximum_weight=100.0,
    )
    result = build_fold_training_weights(
        dataset,
        fold,
        config=wide_limits,
    )

    weights = np.asarray(result.weights, dtype=float)
    journey_sums = dict(result.journey_weight_sums)

    assert result.training_indices == fold.train_indices
    assert len(weights) == len(fold.train_indices)
    assert np.isclose(weights.mean(), 1.0)
    assert weights.min() >= wide_limits.minimum_weight
    assert weights.max() <= wide_limits.maximum_weight

    assert len(journey_sums) == 2
    assert np.isclose(*journey_sums.values())

    bounded_result = build_fold_training_weights(dataset, fold)
    bounded_weights = np.asarray(bounded_result.weights, dtype=float)

    assert np.isclose(bounded_weights.mean(), 1.0)
    assert bounded_weights.min() >= 0.25
    assert bounded_weights.max() <= 4.0



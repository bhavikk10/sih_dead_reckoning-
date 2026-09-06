from __future__ import annotations

import numpy as np

from idr_backend.road_context.evaluation import (
    RoadContextCalibrationGate,
    build_evaluation_report,
    evaluate_road_context_quantiles,
    evaluate_validation_fold,
)
from idr_backend.road_context.rules import RoadContextQuantilePrediction
from idr_backend.road_context.splits import (
    RoadContextFold,
    RoadContextSplitStrategy,
)


def _prediction(
    p10: float,
    p50: float,
    p90: float,
) -> RoadContextQuantilePrediction:
    return RoadContextQuantilePrediction(
        model_id="test-road-context-model",
        speed_p10_mps=p10,
        speed_p50_mps=p50,
        speed_p90_mps=p90,
    )


def test_quantile_metrics_measure_mae_coverage_and_interval_width() -> None:
    metrics = evaluate_road_context_quantiles(
        target_speed_mps=(10.0, 10.0, 10.0, 10.0, 20.0),
        predictions=(
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
        ),
    )

    assert metrics.sample_count == 5
    assert np.isclose(metrics.median_mae_mps, 2.0)
    assert np.isclose(metrics.mean_interval_width_mps, 4.0)
    assert np.isclose(metrics.observed_interval_coverage, 0.80)
    assert np.isclose(metrics.expected_interval_coverage, 0.80)
    assert np.isclose(metrics.coverage_error, 0.0)
    assert metrics.mean_pinball_loss_mps > 0.0


def test_calibration_gate_requires_enough_well_calibrated_examples() -> None:
    metrics = evaluate_road_context_quantiles(
        target_speed_mps=(10.0, 10.0, 10.0, 10.0, 20.0),
        predictions=(
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
        ),
    )

    assert RoadContextCalibrationGate(
        minimum_sample_count=5,
        maximum_absolute_coverage_error=0.01,
    ).accepts(metrics)

    assert not RoadContextCalibrationGate(
        minimum_sample_count=6,
        maximum_absolute_coverage_error=0.01,
    ).accepts(metrics)


def test_fold_reports_aggregate_as_true_out_of_fold_metrics() -> None:
    first_fold = RoadContextFold(
        fold_index=0,
        strategy=RoadContextSplitStrategy.JOURNEY_HELD_OUT,
        train_indices=(2, 3),
        validation_indices=(0, 1),
        train_group_ids=("journey-b",),
        validation_group_ids=("journey-a",),
    )
    second_fold = RoadContextFold(
        fold_index=1,
        strategy=RoadContextSplitStrategy.JOURNEY_HELD_OUT,
        train_indices=(0, 1),
        validation_indices=(2, 3),
        train_group_ids=("journey-a",),
        validation_group_ids=("journey-b",),
    )

    first_evaluation = evaluate_validation_fold(
        fold=first_fold,
        target_speed_mps=(10.0, 10.0),
        predictions=(
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
        ),
    )
    second_evaluation = evaluate_validation_fold(
        fold=second_fold,
        target_speed_mps=(10.0, 20.0),
        predictions=(
            _prediction(8.0, 10.0, 12.0),
            _prediction(8.0, 10.0, 12.0),
        ),
    )

    report = build_evaluation_report((second_evaluation, first_evaluation))

    assert [fold.fold_index for fold in report.folds] == [0, 1]
    assert report.overall_metrics.sample_count == 4
    assert np.isclose(report.overall_metrics.observed_interval_coverage, 0.75)



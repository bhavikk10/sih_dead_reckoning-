"""Focused tests for the notebook's leakage and feature-building machinery."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import torch


# The experiment helper deliberately lives beside the notebook and is not a
# stable idr_backend API. Add that local directory only for these tests.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "notebooks"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from velocity_experiment import (  # noqa: E402
    BlackoutDataset,
    ExperimentConfig,
    assert_group_isolation,
    build_neural_model,
    make_grouped_cv_folds,
    rf_imu_features,
)


def synthetic_dataset() -> BlackoutDataset:
    """Create small deterministic examples with six independent journeys."""

    generator = np.random.default_rng(7)
    examples_per_group = 14
    groups = np.repeat(np.asarray(list("ABCDEF")), examples_per_group)
    count = len(groups)
    horizons = np.tile(np.asarray([5, 10, 20, 30, 60, 90, 120]), count // 7)
    targets = np.linspace(2.0, 30.0, count, dtype=np.float32)
    context = np.column_stack(
        [targets - 0.5, targets - 0.2, horizons, np.full(count, 0.8), np.full(count, 0.6)]
    ).astype(np.float32)
    return BlackoutDataset(
        clean_windows=generator.normal(size=(count, 50, 6)).astype(np.float32),
        raw_windows=generator.normal(size=(count, 50, 6)).astype(np.float32),
        context=context,
        target_speed_mps=targets,
        residual_target_mps=(targets - context[:, 1]).astype(np.float32),
        journey_ids=groups,
        anchor_timestamps_ns=np.arange(count, dtype=np.int64) * 2_000_000_000,
        end_timestamps_ns=np.arange(count, dtype=np.int64) * 2_000_000_000 + 1,
        horizons_s=horizons.astype(np.int16),
    )


def test_rf_features_are_finite_and_have_documented_width() -> None:
    """Eight features by six channels plus four magnitude features equals 52."""

    windows = np.random.default_rng(1).normal(size=(9, 50, 6)).astype(np.float32)
    features = rf_imu_features(windows, sample_period_s=0.1)

    assert features.shape == (9, 52)
    assert np.isfinite(features).all()


def test_grouped_folds_never_split_a_journey() -> None:
    """Overlapping relatives from one drive must remain on one fold side."""

    dataset = synthetic_dataset()
    config = ExperimentConfig(cv_folds=3, search_profile="smoke")
    development = np.arange(len(dataset))
    folds = make_grouped_cv_folds(dataset, development, config)

    assert_group_isolation(dataset, folds)
    for train, validation in folds:
        assert set(dataset.journey_ids[train]).isdisjoint(dataset.journey_ids[validation])
        assert len(validation) > 0


def test_leakage_assertion_rejects_a_shared_journey() -> None:
    """The guard must fail even when the example indices themselves differ."""

    dataset = synthetic_dataset()
    with pytest.raises(AssertionError, match="leaks journeys"):
        assert_group_isolation(dataset, [(np.asarray([0]), np.asarray([1]))])


@pytest.mark.parametrize(
    ("family", "parameters"),
    [
        (
            "gru",
            {
                "hidden_size": 32,
                "num_layers": 1,
                "bidirectional": True,
                "dropout": 0.1,
                "learning_rate": 1e-3,
            },
        ),
        (
            "cnn",
            {
                "conv_blocks": 2,
                "filter_base": 16,
                "kernel_size": 3,
                "dropout": 0.1,
                "learning_rate": 1e-3,
            },
        ),
    ],
)
def test_models_emit_one_value_per_past_window(
    family: str, parameters: dict[str, object]
) -> None:
    """Both architectures accept a 50x6 window and five context values."""

    model = build_neural_model(family, parameters, context_dim=5)
    output = model(torch.zeros(4, 50, 6), torch.zeros(4, 5))

    assert output.shape == (4,)

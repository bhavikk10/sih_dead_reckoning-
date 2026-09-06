"""Small deterministic checks for final velocity-search dataset helpers."""

from __future__ import annotations

import numpy as np

from idr_backend.evaluation.production_velocity import (
    ProductionVelocityDataset,
    fold_balanced_sample_weights,
    production_velocity_eda_frame,
)


def _dataset() -> ProductionVelocityDataset:
    """Build a tiny, finite windowed dataset without raw replay fixtures."""

    count = 8
    windows = np.zeros((count, 50, 6), dtype=np.float32)
    windows[:, :, 0] = np.arange(count, dtype=np.float32)[:, None] * 0.1
    windows[:, :, 5] = 0.05
    return ProductionVelocityDataset(
        sequence_windows=windows,
        context_features=np.column_stack(
            (
                np.full(count, 10.0),
                np.linspace(10.0, 13.5, count),
                np.tile(np.asarray((5.0, 10.0, 20.0, 60.0)), 2),
                np.full(count, 0.8),
                np.full(count, 0.7),
            )
        ).astype(np.float32),
        target_delta_mps=np.asarray((0.0, 0.2, -0.4, 1.0, 0.0, 0.3, -0.8, 1.3), dtype=np.float32),
        target_speed_mps=np.asarray((10.0, 10.2, 9.6, 11.0, 10.0, 10.3, 9.2, 11.3), dtype=np.float32),
        anchor_speed_mps=np.full(count, 10.0, dtype=np.float32),
        journey_ids=np.asarray(("A", "A", "A", "A", "B", "B", "C", "C")),
        anchor_timestamps_ns=np.arange(count, dtype=np.int64) * 1_000_000_000,
        end_timestamps_ns=(np.arange(count, dtype=np.int64) + 1) * 1_000_000_000,
        horizons_s=np.tile(np.asarray((5.0, 10.0, 20.0, 60.0), dtype=np.float32), 2),
        uncertainty_base_features=np.ones((count, 7), dtype=np.float32),
    )


def test_fold_weights_are_bounded_and_derive_only_from_training_rows() -> None:
    """Sparse strata receive finite bounded sampling mass without a val lookup."""

    dataset = _dataset()
    weights = fold_balanced_sample_weights(dataset, np.asarray((0, 1, 2, 4, 5, 6)))

    assert weights.shape == (6,)
    assert np.isfinite(weights).all()
    assert (weights >= 0.25).all()
    assert (weights <= 4.0).all()
    # Journey C has one training endpoint while journey A has three, so equal
    # journey mass requires C's representative to carry more sampler weight.
    assert weights[-1] > weights[0]


def test_eda_frame_exposes_offline_diagnostics_not_runtime_features() -> None:
    """EDA emits aligned target diagnostics for a notebook, not a predictor API."""

    frame = production_velocity_eda_frame(_dataset())

    assert len(frame) == 8
    assert {
        "journey_id",
        "target_speed_kmh",
        "speed_delta_kmh",
        "forward_acceleration_rms_mps2",
        "yaw_rate_rms_radps",
        "minimum_calibration_confidence",
    }.issubset(frame.columns)
    assert np.isfinite(frame.select_dtypes("number").to_numpy()).all()

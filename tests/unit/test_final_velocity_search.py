"""Regression tests for interruption-safe, journey-macro model ranking."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


NOTEBOOKS_DIRECTORY = Path(__file__).resolve().parents[2] / "notebooks"
if str(NOTEBOOKS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS_DIRECTORY))

from final_velocity_experiment import (  # noqa: E402
    FINAL_SEARCH_SEED,
    FoldOutcome,
    run_successive_halving,
)


def test_successive_halving_ranks_concatenated_journey_oof_predictions(
    tmp_path: Path,
) -> None:
    """A one-journey fold must not count as much as a two-journey fold.

    Candidate 1 has the lower *mean fold score* in the first two folds, but
    candidate 2 has lower macro error once every held-out journey is counted
    exactly once.  This catches the subtle GroupKFold ranking error that can
    occur when long drives occupy a validation fold by themselves.
    """

    journeys = np.asarray(("A", "B", "C", "D", "E", "F"))
    folds = [
        (np.asarray((1, 2, 3, 4, 5), dtype=np.int64), np.asarray((0,), dtype=np.int64)),
        (np.asarray((0, 3, 4, 5), dtype=np.int64), np.asarray((1, 2), dtype=np.int64)),
        (np.asarray((0, 1, 2, 4, 5), dtype=np.int64), np.asarray((3,), dtype=np.int64)),
        (np.asarray((0, 1, 2, 3, 5), dtype=np.int64), np.asarray((4,), dtype=np.int64)),
        (
            np.asarray((0, 1, 2, 3, 4), dtype=np.int64),
            np.asarray((5,), dtype=np.int64),
        ),
    ]

    def trainer(parameters, _train, validation, _limits, _checkpoint, _prefix):
        candidate_id = int(parameters["_candidate_id"])
        prediction = []
        for index in validation:
            # Candidate 1: excellent only on A, 2 m/s elsewhere. Candidate
            # 2: 2.1 m/s on A, exact elsewhere. Equal fold averaging favours
            # candidate 1 in the screen; journey-macro OOF correctly favours 2.
            error = (
                0.0 if index == 0 else 2.0
            ) if candidate_id == 1 else (
                2.1 if index == 0 else 0.0
            ) if candidate_id == 2 else 10.0
            prediction.append(
                {
                    "journey_id": journeys[index],
                    "anchor_timestamp_ns": int(index),
                    "end_timestamp_ns": int(index + 10),
                    "horizon_s": 5.0,
                    "actual_speed_mps": 10.0,
                    "prediction_speed_mps": 10.0 + error,
                }
            )
        frame = pd.DataFrame(prediction)
        return FoldOutcome(
            macro_journey_mae_mps=float(
                np.abs(frame.actual_speed_mps - frame.prediction_speed_mps).mean()
            ),
            best_epoch=1,
            elapsed_seconds=0.0,
            cpu_inference_p95_ms=float(candidate_id),
            predictions=frame,
        )

    outcome = run_successive_halving(
        family="ranking-test",
        candidates=[{"candidate": index} for index in range(1, 21)],
        folds=folds,
        artifact_directory=tmp_path,
        trainer=trainer,
        batch_size=1,
    )

    assert int(outcome.screening.iloc[0].candidate_id) == 2
    assert int(outcome.finalists.iloc[0].candidate_id) == 2
    assert outcome.finalists.iloc[0].cv_macro_journey_mae_mps == pytest.approx(0.35)
    assert FINAL_SEARCH_SEED > 0

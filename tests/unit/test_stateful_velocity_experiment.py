"""Fast structural checks for the efficient stateful-GRU experiment."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from sklearn.preprocessing import StandardScaler


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "notebooks"))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from stateful_velocity_experiment import (  # noqa: E402
    STATEFUL_FEATURE_NAMES,
    StatefulAnchorDeltaGru,
    StatefulBlackoutSequence,
    StatefulFoldResult,
    _chunk_outputs,
    collect_stateful_oof_predictions,
    run_stateful_successive_search,
)
from velocity_experiment import ExperimentConfig  # noqa: E402


def test_chunked_inference_matches_one_shot_inference() -> None:
    """Chunk boundaries must not reset or change the carried hidden state."""

    torch.manual_seed(5)
    model = StatefulAnchorDeltaGru(hidden_size=8, num_layers=1, dropout=0.0)
    model.eval()
    features = torch.from_numpy(
        np.random.default_rng(2)
        .normal(size=(3, 37, len(STATEFUL_FEATURE_NAMES)))
        .astype(np.float32)
    )

    with torch.inference_mode():
        encoded, _ = model.gru(features)
        one_shot = model.head(encoded).squeeze(-1)
        chunked = _chunk_outputs(model, features, chunk_steps=11)

    assert torch.allclose(one_shot, chunked, rtol=1e-6, atol=1e-6)


def test_stateful_gru_is_strictly_unidirectional() -> None:
    """The candidate must be capable of causal sample-by-sample deployment."""

    model = StatefulAnchorDeltaGru(hidden_size=8, num_layers=2, dropout=0.1)
    assert not model.gru.bidirectional


def test_successive_search_resumes_completed_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An interrupted search must reuse saved screen/fold results on restart."""

    import stateful_velocity_experiment as experiment

    calls: list[tuple[int, int]] = []

    def fake_train(*args: object, **kwargs: object) -> StatefulFoldResult:
        seed = int(kwargs["seed"])
        candidate_id = (seed - 42) // 100
        fold_id = seed - 42 - candidate_id * 100
        calls.append((candidate_id, fold_id))
        return StatefulFoldResult(
            model=None,  # type: ignore[arg-type]
            scaler=StandardScaler(),
            best_epoch=3,
            macro_journey_mae_mps=float(candidate_id),
            predictions=pd.DataFrame(),
            elapsed_seconds=0.01,
        )

    monkeypatch.setattr(experiment, "train_stateful_fold", fake_train)
    config = experiment.ExperimentConfig(seed=42)
    folds = (
        (np.asarray([0]), np.asarray([1])),
        (np.asarray([0]), np.asarray([1])),
    )

    first_screening, first_confirmation = run_stateful_successive_search(
        (),
        folds,
        experiment_config=config,
        device=torch.device("cpu"),
        artifact_directory=tmp_path,
        candidate_count=2,
        finalists=1,
    )
    first_call_count = len(calls)
    second_screening, second_confirmation = run_stateful_successive_search(
        (),
        folds,
        experiment_config=config,
        device=torch.device("cpu"),
        artifact_directory=tmp_path,
        candidate_count=2,
        finalists=1,
    )

    assert first_call_count == 4  # Two screen calls + two folds for finalist 1.
    assert len(calls) == first_call_count
    assert first_screening.equals(second_screening)
    assert first_confirmation.equals(second_confirmation)


def test_oof_predictions_reuse_saved_confirmation_checkpoint(tmp_path: Path) -> None:
    """OOF generation must infer from saved folds, not retrain the winner."""

    parameters: dict[str, object] = {
        "hidden_size": 8,
        "num_layers": 1,
        "dropout": 0.0,
        "learning_rate": 1e-3,
        "weight_decay": 1e-4,
    }
    features = np.zeros((3, len(STATEFUL_FEATURE_NAMES)), dtype=np.float32)
    common = {
        "anchor_speed_mps": 5.0,
        "features": features,
        "calibration_confidence": np.ones(3, dtype=np.float32),
        "target_delta_mps": np.zeros(3, dtype=np.float32),
        "training_mask": np.asarray([False, True, True]),
        "evaluation_mask": np.asarray([False, True, True]),
    }
    sequences = (
        StatefulBlackoutSequence(
            journey_id="train", anchor_timestamp_ns=1, **common
        ),
        StatefulBlackoutSequence(
            journey_id="validation", anchor_timestamp_ns=2, **common
        ),
    )
    model = StatefulAnchorDeltaGru(
        hidden_size=8,
        num_layers=1,
        dropout=0.0,
    )
    for tensor in model.state_dict().values():
        tensor.zero_()
    torch.save(
        {"state_dict": model.state_dict(), "parameters": parameters},
        tmp_path / "candidate_7_fold_1_best.pt",
    )

    predictions, metrics = collect_stateful_oof_predictions(
        sequences,
        ((np.asarray([0]), np.asarray([1])),),
        candidate_id=7,
        parameters=parameters,
        experiment_config=ExperimentConfig(
            blackout_horizons_s=(1, 2), sample_period_ns=1_000_000_000
        ),
        device=torch.device("cpu"),
        artifact_directory=tmp_path,
    )

    assert len(predictions) == 2
    assert set(predictions.journey_id) == {"validation"}
    assert metrics["macro_journey_mae_kmh"] == pytest.approx(0.0)
    assert (tmp_path / "stateful_oof_predictions.csv").exists()

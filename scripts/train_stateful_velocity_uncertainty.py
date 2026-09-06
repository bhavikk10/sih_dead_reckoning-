"""Train the initial calibrated variance model from stateful-GRU OOF residuals.

Only out-of-fold velocity predictions become residual labels here: a velocity
checkpoint never trains the uncertainty model on errors from journeys it saw
while fitting.  A second, journey-disjoint calibration split is reserved for
the global variance scale.  Frozen test journeys remain absent.

Usage:

    E:\\ANACONDA\\python.exe scripts\\train_stateful_velocity_uncertainty.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPOSITORY_ROOT / "src"), str(REPOSITORY_ROOT / "notebooks")]

import stateful_velocity_experiment as stateful  # noqa: E402
from idr_backend.uncertainty.calibration import (  # noqa: E402
    fit_variance_scale,
    gaussian_interval_coverage,
)
from idr_backend.uncertainty.features import UNCERTAINTY_FEATURE_NAMES  # noqa: E402
from idr_backend.uncertainty.model import HeteroscedasticVarianceNetwork  # noqa: E402
from idr_backend.uncertainty.training import (  # noqa: E402
    UncertaintyTrainingConfig,
    train_variance_network,
)
from velocity_experiment import ExperimentConfig  # noqa: E402


ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"
STATEFUL_DIRECTORY = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru"
OUTPUT_DIRECTORY = ARTIFACT_DIRECTORY / "stateful_velocity_uncertainty"
CALIBRATION_FRACTION = 0.20
SEED = 20_260_905
VARIANCE_FLOOR_M2PS2 = 0.04  # 0.2 m/s standard deviation.
VARIANCE_CEILING_M2PS2 = 400.0  # 20 m/s standard deviation safety ceiling.
HEURISTIC_SAFETY_CONFIG = {
    "variance_floor_m2ps2": 0.04,
    "variance_ceiling_m2ps2": 400.0,
    "reference_acceleration_rms_mps2": 2.0,
    "reference_angular_velocity_rms_radps": 0.5,
    "roughness_weight": 1.0,
    "turn_weight": 1.0,
    "calibration_weight": 1.0,
    "quality_weight": 1.0,
}


def _window_features(
    sequence: stateful.StatefulBlackoutSequence,
    *,
    step: int,
    sample_period_s: float,
    predicted_speed_mps: float,
) -> tuple[float, ...]:
    """Rebuild the runtime's causal uncertainty values at one OOF endpoint."""

    start = max(0, step - 49)
    imu = sequence.features[start : step + 1, :6]
    confidence = sequence.calibration_confidence[start : step + 1]
    acceleration = imu[:, :3]
    angular_velocity = imu[:, 3:]
    acceleration_magnitude = np.linalg.norm(acceleration, axis=1)
    angular_velocity_magnitude = np.linalg.norm(angular_velocity, axis=1)
    values = (
        float(np.sqrt(np.mean(np.square(acceleration.reshape(-1))))),
        float(np.std(acceleration_magnitude)),
        float(np.sqrt(np.mean(np.square(angular_velocity_magnitude)))),
        float(np.min(confidence)),
        # The replay cache stores accepted samples but not the quality monitor's
        # continuous score.  A value of one is truthful for the retained
        # acceptance label. Runtime still supplies the actual quality score,
        # which is protected by its deterministic heuristic safety lower bound.
        1.0,
        float((len(imu) - 1) * sample_period_s),
        float(step * sample_period_s),
        float(predicted_speed_mps),
    )
    if len(values) != len(UNCERTAINTY_FEATURE_NAMES):
        raise RuntimeError("Uncertainty feature contract changed without this script.")
    if not np.isfinite(values).all() or any(value < 0.0 for value in values):
        raise RuntimeError("Reconstructed uncertainty features are invalid.")
    return values


def _build_oof_training_frame(
    sequences: list[stateful.StatefulBlackoutSequence],
    oof: pd.DataFrame,
    *,
    sample_period_s: float,
) -> pd.DataFrame:
    """Attach only causal runtime features to each OOF velocity residual."""

    required = {
        "sequence_index",
        "journey_id",
        "horizon_s",
        "actual_speed_mps",
        "prediction_speed_mps",
    }
    if not required.issubset(oof.columns):
        raise RuntimeError("Stateful OOF CSV has an incompatible schema.")
    rows: list[dict[str, object]] = []
    for row in oof.itertuples(index=False):
        sequence_index = int(row.sequence_index)
        if not 0 <= sequence_index < len(sequences):
            raise RuntimeError("OOF sequence index does not resolve to replay data.")
        sequence = sequences[sequence_index]
        if sequence.journey_id != row.journey_id:
            raise RuntimeError("OOF journey ID does not match its replay sequence.")
        step = int(round(float(row.horizon_s) / sample_period_s))
        if not 0 <= step < len(sequence.features):
            raise RuntimeError("OOF horizon falls outside its replay sequence.")
        feature_values = _window_features(
            sequence,
            step=step,
            sample_period_s=sample_period_s,
            predicted_speed_mps=float(row.prediction_speed_mps),
        )
        rows.append(
            {
                "journey_id": sequence.journey_id,
                "sequence_index": sequence_index,
                "horizon_s": int(row.horizon_s),
                "residual_mps": float(row.actual_speed_mps - row.prediction_speed_mps),
                **dict(zip(UNCERTAINTY_FEATURE_NAMES, feature_values, strict=True)),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.duplicated(["sequence_index", "horizon_s"]).any():
        raise RuntimeError("Uncertainty training frame has duplicate OOF residuals.")
    return frame


def _network_variance(
    model: HeteroscedasticVarianceNetwork, features: np.ndarray
) -> np.ndarray:
    """Evaluate positive uncalibrated variance without changing train/eval state."""

    was_training = model.training
    model.eval()
    try:
        with torch.inference_mode():
            return model(torch.from_numpy(features.astype(np.float32))).numpy()
    finally:
        model.train(was_training)


def main() -> None:
    """Build OOF data, hold out journeys for calibration, and persist artifacts."""

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ARTIFACT_DIRECTORY / "manifest.json").read_text())
    config = ExperimentConfig(**manifest["config"])
    cached = joblib.load(ARTIFACT_DIRECTORY / "processed_journeys.joblib")
    journeys = cached.get("journeys") if isinstance(cached, dict) else None
    if not isinstance(journeys, list):
        raise RuntimeError("Processed-journey cache has an unsupported layout.")
    sequences = stateful.build_stateful_blackout_sequences(
        journeys,
        config=config,
        permitted_journeys=set(manifest["development_journeys"]),
    )
    oof = pd.read_csv(STATEFUL_DIRECTORY / "stateful_oof_predictions.csv")
    frame = _build_oof_training_frame(
        sequences,
        oof,
        sample_period_s=config.sample_period_s,
    )
    feature_matrix = frame.loc[:, UNCERTAINTY_FEATURE_NAMES].to_numpy(dtype=np.float32)
    residuals = frame.residual_mps.to_numpy(dtype=np.float32)
    groups = frame.journey_id.to_numpy()
    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=CALIBRATION_FRACTION,
        random_state=SEED,
    )
    train_indices, calibration_indices = next(splitter.split(feature_matrix, groups=groups))
    train_groups = set(groups[train_indices])
    calibration_groups = set(groups[calibration_indices])
    if train_groups & calibration_groups:
        raise RuntimeError("Uncertainty calibration split leaked a journey.")
    scaler = StandardScaler().fit(feature_matrix[train_indices])
    train_features = scaler.transform(feature_matrix[train_indices]).astype(np.float32)
    calibration_features = scaler.transform(feature_matrix[calibration_indices]).astype(
        np.float32
    )
    model = HeteroscedasticVarianceNetwork(
        feature_count=len(UNCERTAINTY_FEATURE_NAMES),
        hidden_size=16,
        variance_floor_m2ps2=VARIANCE_FLOOR_M2PS2,
        variance_ceiling_m2ps2=VARIANCE_CEILING_M2PS2,
    )
    losses = train_variance_network(
        model=model,
        features=torch.from_numpy(train_features),
        residuals_mps=torch.from_numpy(residuals[train_indices]),
        config=UncertaintyTrainingConfig(learning_rate=1e-3, epochs=100, batch_size=128),
    )
    calibration_variance = _network_variance(model, calibration_features)
    scale = fit_variance_scale(
        residuals_mps=residuals[calibration_indices].tolist(),
        predicted_variances_m2ps2=calibration_variance.tolist(),
    )
    calibrated_variance = np.clip(
        calibration_variance * scale.scale,
        VARIANCE_FLOOR_M2PS2,
        VARIANCE_CEILING_M2PS2,
    )
    diagnostics = {
        "rows": int(len(frame)),
        "train_rows": int(len(train_indices)),
        "calibration_rows": int(len(calibration_indices)),
        "train_journeys": sorted(train_groups),
        "calibration_journeys": sorted(calibration_groups),
        "calibration_rmse_mps": float(np.sqrt(np.mean(np.square(residuals[calibration_indices])))),
        "calibration_mean_predicted_std_mps": float(np.sqrt(np.mean(calibrated_variance))),
        "calibration_1sigma_coverage": gaussian_interval_coverage(
            residuals_mps=residuals[calibration_indices].tolist(),
            predicted_variances_m2ps2=calibrated_variance.tolist(),
            standard_deviations=1.0,
        ),
        "calibration_2sigma_coverage": gaussian_interval_coverage(
            residuals_mps=residuals[calibration_indices].tolist(),
            predicted_variances_m2ps2=calibrated_variance.tolist(),
            standard_deviations=2.0,
        ),
        "variance_scale": scale.scale,
        "final_training_nll": float(losses[-1]),
    }
    frame.to_csv(OUTPUT_DIRECTORY / "stateful_uncertainty_oof_training.csv", index=False)
    torch.save(
        {
            "schema_version": 1,
            "model_id": "stateful_anchor_delta_gru_onnx_v1",
            "feature_names": UNCERTAINTY_FEATURE_NAMES,
            "state_dict": model.state_dict(),
            "feature_scaler": scaler,
            "hidden_size": 16,
            "variance_floor_m2ps2": VARIANCE_FLOOR_M2PS2,
            "variance_ceiling_m2ps2": VARIANCE_CEILING_M2PS2,
            "variance_scale": scale.scale,
            "heuristic_safety_config": HEURISTIC_SAFETY_CONFIG,
            "training_scope": "stateful velocity OOF development journeys only",
            "quality_score_training_note": "accepted replay rows use score 1.0",
        },
        OUTPUT_DIRECTORY / "stateful_velocity_uncertainty.pt",
    )
    (OUTPUT_DIRECTORY / "stateful_velocity_uncertainty_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()

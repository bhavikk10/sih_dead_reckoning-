"""Render a qualitative stateful-vs-windowed GRU development trace.

The image is deliberately not a model-selection metric: both final models have
seen development data.  It helps inspect how the selected recurrent model
behaves over a complete GNSS blackout, while grouped CV and OOF metrics remain
the leakage-safe evidence for selection.

Usage:

    E:\\ANACONDA\\python.exe scripts\\plot_stateful_velocity_comparison.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPOSITORY_ROOT / "src"), str(REPOSITORY_ROOT / "notebooks")]

import stateful_velocity_experiment as stateful  # noqa: E402
from velocity_experiment import ExperimentConfig  # noqa: E402


ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"
STATEFUL_DIRECTORY = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru"


def main() -> None:
    """Reconstruct only development sequences and write the comparison image."""

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
    checkpoint = torch.load(
        STATEFUL_DIRECTORY / "stateful_anchor_delta_gru_candidate.pt",
        map_location="cpu",
        weights_only=False,
    )
    parameters = checkpoint["parameters"]
    model = stateful.StatefulAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        dropout=float(parameters["dropout"]),
    )
    model.load_state_dict(checkpoint["state_dict"])
    scaler = checkpoint["feature_scaler"]
    if max(oof.sequence_index) >= len(sequences):
        raise RuntimeError("OOF sequence IDs do not match reconstructed development data.")
    output_path = STATEFUL_DIRECTORY / "stateful_vs_windowed_gru_development_trace.png"
    figure = stateful.plot_stateful_vs_windowed_trace(
        sequences,
        oof,
        stateful_model=model,
        stateful_scaler=scaler,
        experiment_config=config,
        device=torch.device("cpu"),
        prior_windowed_artifact_directory=ARTIFACT_DIRECTORY,
        output_path=output_path,
    )
    figure.clear()
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()

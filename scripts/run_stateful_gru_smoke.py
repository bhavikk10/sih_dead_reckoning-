"""Run one visible three-epoch stateful-GRU fold on cached real data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(REPOSITORY_ROOT / "src"),
    str(REPOSITORY_ROOT / "notebooks"),
]

from stateful_velocity_experiment import (  # noqa: E402
    build_stateful_blackout_sequences,
    map_existing_grouped_folds,
    run_stateful_search,
)
from velocity_experiment import (  # noqa: E402
    ExperimentConfig,
    build_blackout_dataset,
    choose_grouped_holdout,
    make_grouped_cv_folds,
)


def main() -> None:
    artifact_directory = (
        REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"
    )
    cached = joblib.load(artifact_directory / "processed_journeys.joblib")
    journeys = cached["journeys"]
    manifest = json.loads(
        (artifact_directory / "manifest.json").read_text(encoding="utf-8")
    )
    config = ExperimentConfig(**manifest["config"])
    blackout_dataset = build_blackout_dataset(journeys, config)
    development, _ = choose_grouped_holdout(blackout_dataset, config)
    development_groups = set(blackout_dataset.journey_ids[development])
    folds = make_grouped_cv_folds(blackout_dataset, development, config)
    sequences = build_stateful_blackout_sequences(
        journeys,
        config=config,
        permitted_journeys=development_groups,
    )
    stateful_folds = map_existing_grouped_folds(
        sequences,
        blackout_dataset=blackout_dataset,
        blackout_folds=folds,
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(
        f"Real-data smoke: {len(sequences):,} development sequences on {device}",
        flush=True,
    )
    result = run_stateful_search(
        sequences,
        stateful_folds,
        experiment_config=config,
        device=device,
        artifact_directory=artifact_directory / "stateful_anchor_delta_gru",
        profile="smoke",
    )
    print(result.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()

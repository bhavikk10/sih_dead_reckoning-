"""Export the selected anchor-delta GRU checkpoint as ONNX plus strict metadata.

Usage from the repository root:

    E:\\ANACONDA\\python.exe scripts\\export_anchor_delta_gru_onnx.py

The script reads the selected checkpoint and CV table already produced by the
experiment. It does not train, select on test data, or mutate the checkpoint.
"""

from __future__ import annotations

import ast
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from idr_backend.adapters.anchor_delta_gru import (  # noqa: E402
    ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES,
)
from idr_backend.adapters.anchor_delta_gru_model import (  # noqa: E402
    AnchorDeltaGruNetwork,
)
from idr_backend.sensors.windowing import VELOCITY_MODEL_FEATURE_NAMES  # noqa: E402


ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"
CHECKPOINT_PATH = ARTIFACT_DIRECTORY / "anchor_delta_gru.pt"
SELECTION_PATH = ARTIFACT_DIRECTORY / "cv_selection.csv"
MANIFEST_PATH = ARTIFACT_DIRECTORY / "manifest.json"
ONNX_PATH = ARTIFACT_DIRECTORY / "anchor_delta_gru.onnx"
METADATA_PATH = ARTIFACT_DIRECTORY / "anchor_delta_gru.metadata.json"
PARITY_PATH = ARTIFACT_DIRECTORY / "anchor_delta_gru.onnx.parity.json"
VERIFIER_PATH = REPOSITORY_ROOT / "scripts" / "verify_anchor_delta_gru_onnx.py"


def _selected_gru_parameters() -> tuple[dict[str, object], list[int]]:
    """Read the best grouped-CV anchored GRU, never a frozen-test winner."""

    with SELECTION_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["model"] == "anchor_delta_gru"
        ]
    if not rows:
        raise RuntimeError("CV table contains no anchor_delta_gru candidate.")

    best = min(rows, key=lambda row: float(row["cv_macro_mae_mps"]))
    parameters = ast.literal_eval(best["parameters"])
    best_epochs = ast.literal_eval(best["fold_best_epochs"])
    if not isinstance(parameters, dict) or not isinstance(best_epochs, list):
        raise RuntimeError("Selected GRU CV row has malformed serialized values.")
    return parameters, [int(epoch) for epoch in best_epochs]


def _scaler_values(scaler: object, *, expected_length: int) -> dict[str, list[float]]:
    """Extract scaler numbers so runtime does not unpickle scikit-learn objects."""

    mean = getattr(scaler, "mean_", None)
    scale = getattr(scaler, "scale_", None)
    if mean is None or scale is None:
        raise RuntimeError("Checkpoint scaler lacks fitted mean_ or scale_.")

    mean_values = [float(value) for value in np.asarray(mean).reshape(-1)]
    scale_values = [float(value) for value in np.asarray(scale).reshape(-1)]
    if len(mean_values) != expected_length or len(scale_values) != expected_length:
        raise RuntimeError("Checkpoint scaler dimension differs from model contract.")
    if not np.isfinite(mean_values).all() or not np.isfinite(scale_values).all():
        raise RuntimeError("Checkpoint scaler values must be finite.")
    if any(value <= 0.0 for value in scale_values):
        raise RuntimeError("Checkpoint scaler values must be positive.")
    return {"mean": mean_values, "scale": scale_values}


def _fixed_experiment_cases(
    *,
    window_size: int,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, object]]]:
    """Recover three fixed held-out windows used by the original experiment.

    The CSV gives the archived target prediction and identifiers.  The
    processed-journey artifact supplies the exact cleaned 50-by-6 windows and
    calibration history.  This validates deployment against the experiment's
    real input path, not a fabricated zero tensor.
    """

    import joblib

    sys.path.insert(0, str(REPOSITORY_ROOT / "notebooks"))
    from velocity_experiment import ProcessedJourney

    del ProcessedJourney  # Needed by joblib's module lookup; never used directly.
    cached_preprocessing = joblib.load(
        ARTIFACT_DIRECTORY / "processed_journeys.joblib"
    )
    if not isinstance(cached_preprocessing, dict):
        raise RuntimeError("Processed-journey cache has an unsupported layout.")
    journeys = cached_preprocessing.get("journeys")
    if not isinstance(journeys, list):
        raise RuntimeError("Processed-journey cache does not contain journeys.")
    by_id = {journey.journey_id: journey for journey in journeys}
    with (ARTIFACT_DIRECTORY / "frozen_test_predictions.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    selected_rows: list[dict[str, str]] = []
    for horizon_s in (5, 60, 120):
        matching = next(
            (row for row in rows if int(row["horizon_s"]) == horizon_s),
            None,
        )
        if matching is None:
            raise RuntimeError(f"Frozen test lacks a {horizon_s}-second case.")
        selected_rows.append(matching)

    sequences: list[np.ndarray] = []
    contexts: list[np.ndarray] = []
    descriptors: list[dict[str, object]] = []
    for row in selected_rows:
        journey = by_id[row["journey_id"]]
        anchor_timestamp_ns = int(row["anchor_timestamp_ns"])
        end_timestamp_ns = int(row["end_timestamp_ns"])
        anchor_index = np.flatnonzero(
            journey.timestamps_ns == anchor_timestamp_ns
        )
        end_index = np.flatnonzero(journey.timestamps_ns == end_timestamp_ns)
        if len(anchor_index) != 1 or len(end_index) != 1:
            raise RuntimeError("Frozen-test identifiers no longer resolve uniquely.")
        start_index = int(end_index[0]) - window_size + 1
        if start_index < 0:
            raise RuntimeError("Frozen-test window starts before its journey data.")

        confidence = journey.calibration_confidence[
            int(anchor_index[0]) : int(end_index[0]) + 1
        ]
        sequences.append(
            np.asarray(
                journey.clean_imu[start_index : int(end_index[0]) + 1],
                dtype=np.float32,
            )
        )
        contexts.append(
            np.asarray(
                (
                    float(row["anchor_speed_mps"]),
                    float(row["integrated_speed_mps"]),
                    float(row["horizon_s"]),
                    float(confidence.mean()),
                    float(confidence.min()),
                ),
                dtype=np.float32,
            )
        )
        descriptors.append(
            {
                "journey_id": row["journey_id"],
                "anchor_timestamp_ns": anchor_timestamp_ns,
                "end_timestamp_ns": end_timestamp_ns,
                "horizon_s": int(row["horizon_s"]),
                "experiment_prediction_mps": float(
                    row["anchor_delta_gru_prediction_mps"]
                ),
            }
        )

    sequence_batch = np.stack(sequences)
    context_batch = np.stack(contexts)
    if sequence_batch.shape != (3, window_size, 6) or context_batch.shape != (3, 5):
        raise RuntimeError("Frozen-test parity cases do not match the GRU contract.")
    return sequence_batch, context_batch, descriptors


def main() -> None:
    """Export ONNX, validate it structurally, and record PyTorch/ORT parity."""

    if not CHECKPOINT_PATH.is_file() or not SELECTION_PATH.is_file():
        raise FileNotFoundError(
            "Expected selected GRU checkpoint and cv_selection.csv in "
            f"{ARTIFACT_DIRECTORY}."
        )

    checkpoint = torch.load(
        CHECKPOINT_PATH,
        map_location="cpu",
        weights_only=False,
    )
    parameters, fold_best_epochs = _selected_gru_parameters()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    config = manifest["config"]

    model = AnchorDeltaGruNetwork(
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        bidirectional=bool(parameters["bidirectional"]),
        dropout=float(parameters["dropout"]),
        context_dimension=len(ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES),
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    window_size = int(config["window_size"])
    sample_period_ns = int(config["sample_period_ns"])
    metadata = {
        "schema_version": 1,
        "model_id": "anchor_delta_gru_onnx_v1",
        "model_family": "anchor_delta_gru",
        "source_checkpoint": CHECKPOINT_PATH.name,
        "architecture": {
            "parameters": parameters,
            "context_dimension": len(ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES),
            "final_refit_epochs": int(np.median(fold_best_epochs)),
        },
        "input": {
            "window_size": window_size,
            "sample_period_ns": sample_period_ns,
            "sequence_feature_names": list(VELOCITY_MODEL_FEATURE_NAMES),
            "context_feature_names": list(
                ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES
            ),
        },
        "normalization": {
            "sequence": _scaler_values(
                checkpoint["sequence_scaler"],
                expected_length=len(VELOCITY_MODEL_FEATURE_NAMES),
            ),
            "context": _scaler_values(
                checkpoint["context_scaler"],
                expected_length=len(ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES),
            ),
        },
        "target": {
            "kind": "speed_delta_from_anchor",
            "unit": "m/s",
            "postprocess": "max(0, anchor_speed_mps + model_output)",
        },
    }

    example_window = torch.zeros(
        (1, window_size, len(VELOCITY_MODEL_FEATURE_NAMES)),
        dtype=torch.float32,
    )
    example_context = torch.zeros(
        (1, len(ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES)),
        dtype=torch.float32,
    )
    torch.onnx.export(
        model,
        (example_window, example_context),
        ONNX_PATH,
        input_names=["imu_window", "context"],
        output_names=["speed_delta_mps"],
        opset_version=17,
        do_constant_folding=True,
    )
    parity_window, parity_context, case_descriptors = _fixed_experiment_cases(
        window_size=window_size,
    )
    normalized_window = (
        parity_window
        - np.asarray(metadata["normalization"]["sequence"]["mean"], dtype=np.float32)
    ) / np.asarray(metadata["normalization"]["sequence"]["scale"], dtype=np.float32)
    normalized_context = (
        parity_context
        - np.asarray(metadata["normalization"]["context"]["mean"], dtype=np.float32)
    ) / np.asarray(metadata["normalization"]["context"]["scale"], dtype=np.float32)
    with torch.inference_mode():
        torch_delta = model(
            torch.from_numpy(normalized_window),
            torch.from_numpy(normalized_context),
        ).cpu().numpy()
    torch_speeds = np.maximum(0.0, parity_context[:, 0] + torch_delta)
    archived_speeds = np.asarray(
        [case["experiment_prediction_mps"] for case in case_descriptors],
        dtype=np.float32,
    )
    if not np.isclose(torch_speeds, archived_speeds, rtol=1e-5, atol=1e-5).all():
        raise RuntimeError("Checkpoint no longer matches archived experiment predictions.")
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory() as temporary_directory:
        case_path = Path(temporary_directory) / "fixed_experiment_cases.npz"
        np.savez(case_path, sequence=parity_window, context=parity_context)
        try:
            verification = subprocess.run(
                [
                    sys.executable,
                    str(VERIFIER_PATH),
                    "--onnx-path",
                    str(ONNX_PATH),
                    "--metadata-path",
                    str(METADATA_PATH),
                    "--case-path",
                    str(case_path),
                    "--torch-speed-mps",
                    *(repr(float(speed)) for speed in torch_speeds),
                    "--report-path",
                    str(PARITY_PATH),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "ONNX deployment parity process failed:\n"
                f"stdout:\n{error.stdout}\nstderr:\n{error.stderr}"
            ) from error
    parity_report = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
    parity_report["fixed_experiment_cases"] = case_descriptors
    PARITY_PATH.write_text(json.dumps(parity_report, indent=2), encoding="utf-8")
    print(f"Exported {ONNX_PATH.name}")
    print(f"Wrote {METADATA_PATH.name}")
    print(verification.stdout.strip())


if __name__ == "__main__":
    main()

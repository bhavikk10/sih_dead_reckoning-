"""Export the selected stateful anchor-delta GRU as recurrent ONNX.

The graph takes one or more normalized 11-feature IMU rows plus the hidden
state saved from the prior call.  The exporter does not train, reselect, or
inspect frozen-test data.  It verifies PyTorch/ONNX Runtime parity on fixed,
deterministic feature rows before publishing the artifact.

Usage:

    E:\\ANACONDA\\python.exe scripts\\export_stateful_anchor_delta_gru_onnx.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from idr_backend.adapters.stateful_anchor_delta_gru import (  # noqa: E402
    STATEFUL_FEATURE_NAMES,
)
from idr_backend.adapters.stateful_anchor_delta_gru_model import (  # noqa: E402
    StatefulAnchorDeltaGruNetwork,
)


ARTIFACT_DIRECTORY = (
    REPOSITORY_ROOT
    / "artifacts"
    / "anchored_velocity_comparison"
    / "stateful_anchor_delta_gru"
)
CHECKPOINT_PATH = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru_candidate.pt"
ONNX_PATH = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru.onnx"
METADATA_PATH = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru.metadata.json"
PARITY_PATH = ARTIFACT_DIRECTORY / "stateful_anchor_delta_gru.onnx.parity.json"
WARMUP_WINDOW_SIZE = 50
SAMPLE_PERIOD_NS = 100_000_000


def _scaler_values(scaler: object) -> dict[str, list[float]]:
    """Extract only finite scaler numbers; runtime never unpickles sklearn."""

    mean = getattr(scaler, "mean_", None)
    scale = getattr(scaler, "scale_", None)
    if mean is None or scale is None:
        raise RuntimeError("Stateful checkpoint scaler lacks mean_ or scale_.")
    mean_values = [float(value) for value in np.asarray(mean).reshape(-1)]
    scale_values = [float(value) for value in np.asarray(scale).reshape(-1)]
    expected = len(STATEFUL_FEATURE_NAMES)
    if len(mean_values) != expected or len(scale_values) != expected:
        raise RuntimeError("Stateful checkpoint scaler dimension is incompatible.")
    if not np.isfinite(mean_values).all() or not np.isfinite(scale_values).all():
        raise RuntimeError("Stateful checkpoint scaler must be finite.")
    if any(value <= 0.0 for value in scale_values):
        raise RuntimeError("Stateful checkpoint scaler scales must be positive.")
    return {"mean": mean_values, "scale": scale_values}


def main() -> None:
    """Export one selected checkpoint and reject any inference mismatch."""

    if not CHECKPOINT_PATH.is_file():
        raise FileNotFoundError(
            "Missing selected stateful checkpoint. Run the stateful notebook "
            "finalisation cell before ONNX export."
        )
    checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=False)
    parameters = checkpoint.get("parameters")
    if not isinstance(parameters, dict):
        raise RuntimeError("Stateful checkpoint does not contain hyperparameters.")
    feature_names = checkpoint.get("feature_names")
    if tuple(feature_names or ()) != STATEFUL_FEATURE_NAMES:
        raise RuntimeError("Stateful checkpoint feature order does not match runtime.")
    model = StatefulAnchorDeltaGruNetwork(
        feature_count=len(STATEFUL_FEATURE_NAMES),
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        dropout=float(parameters["dropout"]),
    )
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise RuntimeError("Stateful checkpoint does not contain a state_dict.")
    model.load_state_dict(state_dict)
    model.eval()

    hidden_shape = [int(parameters["num_layers"]), 1, int(parameters["hidden_size"])]
    metadata = {
        "schema_version": 1,
        "model_id": "stateful_anchor_delta_gru_onnx_v1",
        "model_family": "stateful_anchor_delta_gru",
        "source_checkpoint": CHECKPOINT_PATH.name,
        "architecture": {
            "hidden_size": hidden_shape[2],
            "num_layers": hidden_shape[0],
            "dropout": float(parameters["dropout"]),
            "parameters": parameters,
            "final_refit_epochs": int(checkpoint["final_refit_epochs"]),
        },
        "input": {
            "warmup_window_size": WARMUP_WINDOW_SIZE,
            "sample_period_ns": SAMPLE_PERIOD_NS,
            "feature_names": list(STATEFUL_FEATURE_NAMES),
        },
        "recurrent_state": {
            "input_name": "hidden_state",
            "output_name": "next_hidden_state",
            "shape": hidden_shape,
            "reset_events": [
                "trusted_gnss_anchor_change",
                "imu_stream_or_device_change",
                "fixed_rate_continuity_break",
            ],
        },
        "normalization": _scaler_values(checkpoint.get("feature_scaler")),
        "target": {
            "kind": "speed_delta_from_anchor",
            "unit": "m/s",
            "postprocess": "max(0, anchor_speed_mps + model_output)",
        },
        "deployment_status": "pre-EKF velocity observation; heuristic uncertainty only",
    }
    example_features = torch.zeros((1, 3, len(STATEFUL_FEATURE_NAMES)), dtype=torch.float32)
    example_hidden = torch.zeros(tuple(hidden_shape), dtype=torch.float32)
    torch.onnx.export(
        model,
        (example_features, example_hidden),
        ONNX_PATH,
        input_names=["features", "hidden_state"],
        output_names=["speed_delta_mps", "next_hidden_state"],
        dynamic_axes={
            "features": {1: "sequence_steps"},
            "speed_delta_mps": {1: "sequence_steps"},
        },
        opset_version=17,
        do_constant_folding=True,
    )

    # A fixed pseudo-random case provides repeatable export parity without
    # looking at the frozen test set. It includes a nonzero hidden state to
    # prove the recurrent hand-off, not merely one-shot inference.
    generator = np.random.default_rng(20_260_905)
    features = generator.normal(
        size=(1, 7, len(STATEFUL_FEATURE_NAMES))
    ).astype(np.float32)
    hidden_state = generator.normal(size=hidden_shape).astype(np.float32)
    with torch.inference_mode():
        torch_output, torch_next_hidden = model(
            torch.from_numpy(features), torch.from_numpy(hidden_state)
        )
    try:
        import onnxruntime as ort
    except (ImportError, OSError) as error:
        raise RuntimeError("A working ONNX Runtime is required for export parity.") from error
    session = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    onnx_output, onnx_next_hidden = session.run(
        ["speed_delta_mps", "next_hidden_state"],
        {"features": features, "hidden_state": hidden_state},
    )
    output_error = float(
        np.max(np.abs(torch_output.cpu().numpy() - np.asarray(onnx_output)))
    )
    hidden_error = float(
        np.max(
            np.abs(torch_next_hidden.cpu().numpy() - np.asarray(onnx_next_hidden))
        )
    )
    if output_error > 1e-5 or hidden_error > 1e-5:
        raise RuntimeError(
            "Stateful ONNX parity failed: "
            f"output={output_error:.3e}, hidden={hidden_error:.3e}."
        )
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    PARITY_PATH.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "case": "fixed_nonzero_recurrent_state",
                "maximum_output_absolute_error_mps": output_error,
                "maximum_hidden_state_absolute_error": hidden_error,
                "status": "passed",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Exported {ONNX_PATH}")
    print(f"PyTorch/ONNX output parity: {output_error:.3e}")
    print(f"PyTorch/ONNX hidden-state parity: {hidden_error:.3e}")


if __name__ == "__main__":
    main()

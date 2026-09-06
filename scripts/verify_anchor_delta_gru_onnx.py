"""Run deployment-path ONNX parity checks without importing PyTorch.

The script deliberately has no PyTorch import.  The exporter computes the
reference result using the experiment's PyTorch pathway, then this process
repeats the exported model's *whole* deployment path: metadata normalization,
ONNX inference, and anchor-plus-delta post-processing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from idr_backend.adapters.anchor_delta_gru import AnchorDeltaGruPredictor  # noqa: E402
from idr_backend.adapters.velocity_predictor import VelocityInferenceContext  # noqa: E402


def main() -> None:
    """Evaluate the fixed non-zero parity case and write a compact JSON report."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx-path", type=Path, required=True)
    parser.add_argument("--metadata-path", type=Path, required=True)
    parser.add_argument("--case-path", type=Path, required=True)
    parser.add_argument("--torch-speed-mps", type=float, nargs="+", required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    arguments = parser.parse_args()

    metadata = json.loads(arguments.metadata_path.read_text(encoding="utf-8"))
    input_contract = metadata["input"]
    window_size = int(input_contract["window_size"])
    feature_count = len(input_contract["sequence_feature_names"])
    context_count = len(input_contract["context_feature_names"])
    if feature_count != 6 or context_count != 5:
        raise ValueError("Parity verifier only supports the anchor-delta GRU contract.")

    with np.load(arguments.case_path) as case:
        window = np.asarray(case["sequence"], dtype=np.float32)
        context = np.asarray(case["context"], dtype=np.float32)
    if window.ndim != 3 or window.shape[1:] != (window_size, feature_count):
        raise ValueError("Parity sequence case does not match GRU metadata.")
    if context.shape != (len(window), context_count):
        raise ValueError("Parity context case does not match GRU metadata.")
    torch_speeds = np.asarray(arguments.torch_speed_mps, dtype=np.float32)
    if torch_speeds.shape != (len(window),):
        raise ValueError("One PyTorch speed must be supplied for each parity case.")

    predictor = AnchorDeltaGruPredictor(
        onnx_path=arguments.onnx_path,
        metadata_path=arguments.metadata_path,
    )
    # Live runtime predicts one completed IMU window at a time.  This calls
    # the actual adapter, including its metadata scaling and anchor-plus-delta
    # post-process, instead of duplicating that behavior in the verifier.
    onnx_speeds = np.asarray(
        [
            predictor.predict_speed_mps(
                tuple(tuple(float(value) for value in row) for row in window[index]),
                VelocityInferenceContext(
                    source_id="onnx-parity-case",
                    anchor_timestamp_ns=0,
                    anchor_speed_mps=float(context[index, 0]),
                    integrated_speed_mps=float(context[index, 1]),
                    seconds_since_anchor=float(context[index, 2]),
                    mean_calibration_confidence=float(context[index, 3]),
                    minimum_calibration_confidence=float(context[index, 4]),
                ),
            )
            for index in range(len(window))
        ],
        dtype=np.float32,
    )
    maximum_absolute_error = float(np.max(np.abs(torch_speeds - onnx_speeds)))
    if not np.isclose(
        torch_speeds,
        onnx_speeds,
        rtol=1e-5,
        atol=1e-6,
    ).all():
        raise RuntimeError("ONNX output does not match PyTorch within tolerance.")

    arguments.report_path.write_text(
        json.dumps(
            {
                "torch_speed_mps": [float(value) for value in torch_speeds],
                "onnx_speed_mps": [float(value) for value in onnx_speeds],
                "case_count": len(window),
                "maximum_absolute_error_mps": maximum_absolute_error,
                "rtol": 1e-5,
                "atol": 1e-6,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Verified PyTorch/ONNX parity: {maximum_absolute_error:.3g} m/s")


if __name__ == "__main__":
    main()

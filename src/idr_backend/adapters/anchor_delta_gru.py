"""ONNX Runtime adapter for the exported anchor-delta GRU speed model.

The GRU predicts speed change since the last trusted GNSS anchor.  This module
applies the exact exported scalers, supplies the five causal context values,
and converts that delta to a non-negative ground-speed estimate.  It has no
access to ground truth, future GNSS, or EKF state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from idr_backend.sensors.windowing import VELOCITY_MODEL_FEATURE_NAMES

from .velocity_predictor import (
    VelocityInferenceContext,
    VelocityPredictorAdapter,
    VelocityPredictorSpec,
)


ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES = (
    "anchor_speed_mps",
    "integrated_speed_mps",
    "seconds_since_anchor",
    "mean_calibration_confidence",
    "minimum_calibration_confidence",
)


@dataclass(frozen=True, slots=True)
class AnchorDeltaGruArtifact:
    """Validated artifact metadata independent from PyTorch or scikit-learn."""

    model_id: str
    window_size: int
    sample_period_ns: int
    sequence_mean: tuple[float, float, float, float, float, float]
    sequence_scale: tuple[float, float, float, float, float, float]
    context_mean: tuple[float, float, float, float, float]
    context_scale: tuple[float, float, float, float, float]

    @classmethod
    def from_json_file(cls, metadata_path: Path) -> AnchorDeltaGruArtifact:
        """Load and validate the deployment contract written by the exporter."""

        try:
            document = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Anchor-delta GRU metadata does not exist: {metadata_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Anchor-delta GRU metadata is not valid JSON: {metadata_path}"
            ) from error

        if document.get("schema_version") != 1:
            raise ValueError("Unsupported anchor-delta GRU metadata schema.")
        if document.get("model_family") != "anchor_delta_gru":
            raise ValueError("Metadata is not for an anchor-delta GRU.")

        input_contract = _mapping(document, "input")
        target_contract = _mapping(document, "target")
        normalization = _mapping(document, "normalization")
        sequence_normalization = _mapping(normalization, "sequence")
        context_normalization = _mapping(normalization, "context")

        if tuple(input_contract.get("sequence_feature_names", ())) != (
            VELOCITY_MODEL_FEATURE_NAMES
        ):
            raise ValueError("GRU sequence-feature order differs from IDR contract.")
        if tuple(input_contract.get("context_feature_names", ())) != (
            ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES
        ):
            raise ValueError("GRU context-feature order differs from IDR contract.")
        if target_contract != {
            "kind": "speed_delta_from_anchor",
            "unit": "m/s",
            "postprocess": "max(0, anchor_speed_mps + model_output)",
        }:
            raise ValueError("GRU target/postprocessing contract is unsupported.")

        return cls(
            model_id=_non_blank_string(document, "model_id"),
            window_size=_positive_int(input_contract, "window_size"),
            sample_period_ns=_positive_int(input_contract, "sample_period_ns"),
            sequence_mean=_finite_tuple(sequence_normalization, "mean", 6),
            sequence_scale=_positive_tuple(sequence_normalization, "scale", 6),
            context_mean=_finite_tuple(context_normalization, "mean", 5),
            context_scale=_positive_tuple(context_normalization, "scale", 5),
        )


class AnchorDeltaGruPredictor:
    """Run one exported GRU on a complete cleaned IMU window using ONNX."""

    def __init__(
        self,
        *,
        onnx_path: Path,
        metadata_path: Path,
    ) -> None:
        """Open a CPU-only ONNX Runtime session and its matching metadata."""

        if not onnx_path.is_file():
            raise FileNotFoundError(f"Anchor-delta GRU ONNX model missing: {onnx_path}")

        self._artifact = AnchorDeltaGruArtifact.from_json_file(metadata_path)
        try:
            import onnxruntime as ort
        except (ImportError, OSError) as error:
            raise RuntimeError(
                "ONNX Runtime is required to load the anchor-delta GRU. "
                "Install a working CPU ONNX Runtime before using this adapter."
            ) from error

        self._session = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        input_names = tuple(item.name for item in self._session.get_inputs())
        output_names = tuple(item.name for item in self._session.get_outputs())
        if input_names != ("imu_window", "context"):
            raise ValueError(f"Unexpected GRU ONNX inputs: {input_names!r}")
        if output_names != ("speed_delta_mps",):
            raise ValueError(f"Unexpected GRU ONNX outputs: {output_names!r}")

    @property
    def model_id(self) -> str:
        """Return the immutable deployed model identity."""

        return self._artifact.model_id

    @property
    def window_size(self) -> int:
        """Return the required number of fixed-rate cleaned IMU samples."""

        return self._artifact.window_size

    @property
    def sample_period_ns(self) -> int:
        """Return the required fixed sample period."""

        return self._artifact.sample_period_ns

    @classmethod
    def from_artifact_directory(
        cls,
        artifact_directory: Path,
    ) -> AnchorDeltaGruPredictor:
        """Load the standard ONNX+JSON pair from one experiment artifact folder."""

        return cls(
            onnx_path=artifact_directory / "anchor_delta_gru.onnx",
            metadata_path=artifact_directory / "anchor_delta_gru.metadata.json",
        )

    def predict_speed_mps(
        self,
        feature_rows: tuple[
            tuple[float, float, float, float, float, float], ...
        ],
        context: VelocityInferenceContext,
    ) -> float:
        """Scale one causal window, infer its delta-v, and recover ground speed."""

        if len(feature_rows) != self._artifact.window_size:
            raise ValueError(
                "GRU feature-window length does not match exported metadata."
            )

        sequence = np.asarray(feature_rows, dtype=np.float32)
        if sequence.shape != (self._artifact.window_size, 6):
            raise ValueError("GRU feature window must have shape (window_size, 6).")
        if not np.isfinite(sequence).all():
            raise ValueError("GRU sequence features must be finite.")

        context_values = np.asarray(
            (
                context.anchor_speed_mps,
                context.integrated_speed_mps,
                context.seconds_since_anchor,
                context.mean_calibration_confidence,
                context.minimum_calibration_confidence,
            ),
            dtype=np.float32,
        )
        if not np.isfinite(context_values).all():
            raise ValueError("GRU context features must be finite.")

        normalized_sequence = (
            sequence - np.asarray(self._artifact.sequence_mean, dtype=np.float32)
        ) / np.asarray(self._artifact.sequence_scale, dtype=np.float32)
        normalized_context = (
            context_values - np.asarray(self._artifact.context_mean, dtype=np.float32)
        ) / np.asarray(self._artifact.context_scale, dtype=np.float32)

        output = self._session.run(
            ["speed_delta_mps"],
            {
                "imu_window": normalized_sequence[np.newaxis, :, :],
                "context": normalized_context[np.newaxis, :],
            },
        )[0]
        predicted_delta_mps = float(np.asarray(output).reshape(-1)[0])
        if not isfinite(predicted_delta_mps):
            raise ValueError("GRU ONNX output must be finite.")
        return max(0.0, context.anchor_speed_mps + predicted_delta_mps)


def load_anchor_delta_gru_adapter(
    artifact_directory: Path,
) -> VelocityPredictorAdapter:
    """Load the exported GRU as the generic pre-EKF velocity-model boundary.

    The returned adapter is what ``DeterministicPreEkfPipeline`` consumes. It
    emits a ``VelocityObservation`` which the pipeline pairs with its current
    conservative uncertainty estimate; the function does not configure or
    update an EKF.
    """

    predictor = AnchorDeltaGruPredictor.from_artifact_directory(artifact_directory)
    return VelocityPredictorAdapter(
        spec=VelocityPredictorSpec(
            model_id=predictor.model_id,
            window_size=predictor.window_size,
            sample_period_ns=predictor.sample_period_ns,
        ),
        predictor=predictor,
    )


def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    """Read one JSON object field with a precise deployment-contract error."""

    field = value.get(key)
    if not isinstance(field, dict):
        raise ValueError(f"Artifact metadata field {key!r} must be an object.")
    return field


def _non_blank_string(value: dict[str, Any], key: str) -> str:
    """Read a required non-blank metadata string."""

    field = value.get(key)
    if not isinstance(field, str) or not field.strip():
        raise ValueError(f"Artifact metadata field {key!r} must be a non-blank string.")
    return field


def _positive_int(value: dict[str, Any], key: str) -> int:
    """Read one strictly positive integer metadata field."""

    field = value.get(key)
    if isinstance(field, bool) or not isinstance(field, int) or field <= 0:
        raise ValueError(f"Artifact metadata field {key!r} must be a positive integer.")
    return field


def _finite_tuple(
    value: dict[str, Any],
    key: str,
    length: int,
) -> tuple[float, ...]:
    """Read a fixed-length finite normalization vector."""

    field = value.get(key)
    if not isinstance(field, list) or len(field) != length:
        raise ValueError(
            f"Artifact metadata field {key!r} must have {length} numeric values."
        )
    converted = tuple(float(component) for component in field)
    if not all(isfinite(component) for component in converted):
        raise ValueError(f"Artifact metadata field {key!r} must be finite.")
    return converted


def _positive_tuple(
    value: dict[str, Any],
    key: str,
    length: int,
) -> tuple[float, ...]:
    """Read a fixed-length positive normalization-scale vector."""

    converted = _finite_tuple(value, key, length)
    if not all(component > 0.0 for component in converted):
        raise ValueError(f"Artifact metadata field {key!r} must be positive.")
    return converted

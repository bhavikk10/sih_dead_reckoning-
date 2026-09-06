"""Experimental state-carrying ONNX adapter for an anchor-to-blackout GRU.

Unlike the earlier five-second window model, this network sees every accepted
10 Hz sample after a trusted GNSS speed anchor.  Its ONNX hidden state is kept
only in this adapter and is reset on an anchor change, device change, or IMU
continuity break.  It produces a velocity observation; the uncertainty engine
remains a separate downstream owner of the corresponding variance.

The frozen test set found this experiment worse than the selected windowed
anchor-delta GRU. Keep it available for controlled research only; production
composition must use :mod:`idr_backend.adapters.anchor_delta_gru` instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

from idr_backend.sensors.types import VehicleImuSample, VelocityObservation
from idr_backend.sensors.windowing import (
    VELOCITY_MODEL_FEATURE_NAMES,
    VelocityModelInputWindow,
    vehicle_imu_feature_row,
)

from .velocity_predictor import VelocityInferenceContext


STATEFUL_CONTEXT_FEATURE_NAMES = (
    "anchor_speed_mps",
    "integrated_speed_mps",
    "seconds_since_anchor",
    "running_mean_calibration_confidence",
    "running_minimum_calibration_confidence",
)
STATEFUL_FEATURE_NAMES = VELOCITY_MODEL_FEATURE_NAMES + STATEFUL_CONTEXT_FEATURE_NAMES


@dataclass(frozen=True, slots=True)
class StatefulAnchorDeltaGruArtifact:
    """Validated, framework-independent contract for one stateful ONNX file."""

    model_id: str
    warmup_window_size: int
    sample_period_ns: int
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    hidden_size: int
    num_layers: int

    @classmethod
    def from_json_file(cls, metadata_path: Path) -> StatefulAnchorDeltaGruArtifact:
        """Load and strictly validate metadata emitted alongside the ONNX model."""

        try:
            document = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Stateful GRU metadata does not exist: {metadata_path}"
            ) from error
        except json.JSONDecodeError as error:
            raise ValueError("Stateful GRU metadata is not valid JSON.") from error

        if document.get("schema_version") != 1:
            raise ValueError("Unsupported stateful GRU metadata schema.")
        if document.get("model_family") != "stateful_anchor_delta_gru":
            raise ValueError("Metadata is not for the stateful anchor-delta GRU.")
        input_contract = _mapping(document, "input")
        recurrent_contract = _mapping(document, "recurrent_state")
        normalization = _mapping(document, "normalization")
        architecture = _mapping(document, "architecture")
        if tuple(input_contract.get("feature_names", ())) != STATEFUL_FEATURE_NAMES:
            raise ValueError("Stateful GRU feature order differs from IDR contract.")
        if recurrent_contract.get("input_name") != "hidden_state":
            raise ValueError("Stateful GRU hidden-state input name is unsupported.")
        if recurrent_contract.get("output_name") != "next_hidden_state":
            raise ValueError("Stateful GRU hidden-state output name is unsupported.")
        target = _mapping(document, "target")
        if target != {
            "kind": "speed_delta_from_anchor",
            "unit": "m/s",
            "postprocess": "max(0, anchor_speed_mps + model_output)",
        }:
            raise ValueError("Stateful GRU target/postprocessing is unsupported.")

        hidden_size = _positive_int(architecture, "hidden_size")
        num_layers = _positive_int(architecture, "num_layers")
        shape = recurrent_contract.get("shape")
        if shape != [num_layers, 1, hidden_size]:
            raise ValueError("Stateful GRU hidden-state shape does not match architecture.")
        return cls(
            model_id=_non_blank_string(document, "model_id"),
            warmup_window_size=_positive_int(input_contract, "warmup_window_size"),
            sample_period_ns=_positive_int(input_contract, "sample_period_ns"),
            feature_mean=_finite_tuple(
                normalization, "mean", len(STATEFUL_FEATURE_NAMES)
            ),
            feature_scale=_positive_tuple(
                normalization, "scale", len(STATEFUL_FEATURE_NAMES)
            ),
            hidden_size=hidden_size,
            num_layers=num_layers,
        )


class StatefulAnchorDeltaGruPredictor:
    """Run the causal ONNX graph and retain only per-stream recurrent state."""

    def __init__(self, *, onnx_path: Path, metadata_path: Path) -> None:
        if not onnx_path.is_file():
            raise FileNotFoundError(f"Stateful GRU ONNX model missing: {onnx_path}")
        self._artifact = StatefulAnchorDeltaGruArtifact.from_json_file(metadata_path)
        try:
            import onnxruntime as ort
        except (ImportError, OSError) as error:
            raise RuntimeError(
                "ONNX Runtime is required to load the stateful anchor-delta GRU."
            ) from error
        self._session = ort.InferenceSession(
            str(onnx_path), providers=["CPUExecutionProvider"]
        )
        if tuple(item.name for item in self._session.get_inputs()) != (
            "features",
            "hidden_state",
        ):
            raise ValueError("Unexpected stateful GRU ONNX input names.")
        if tuple(item.name for item in self._session.get_outputs()) != (
            "speed_delta_mps",
            "next_hidden_state",
        ):
            raise ValueError("Unexpected stateful GRU ONNX output names.")
        self.reset()

    @property
    def model_id(self) -> str:
        """Return the immutable selected-model identity."""

        return self._artifact.model_id

    @property
    def window_size(self) -> int:
        """Return the rolling preprocessor window required to start safely."""

        return self._artifact.warmup_window_size

    @property
    def sample_period_ns(self) -> int:
        """Return the exact fixed-rate period used during training."""

        return self._artifact.sample_period_ns

    def reset(self) -> None:
        """Forget history; the next call seeds state from its causal window."""

        self._source_id: str | None = None
        self._anchor_timestamp_ns: int | None = None
        self._last_timestamp_ns: int | None = None
        self._last_forward_acceleration_mps2: float | None = None
        self._integrated_speed_mps: float | None = None
        self._confidence_count = 0
        self._confidence_sum = 0.0
        self._minimum_confidence = 1.0
        self._hidden_state = np.zeros(
            (self._artifact.num_layers, 1, self._artifact.hidden_size),
            dtype=np.float32,
        )

    @classmethod
    def from_artifact_directory(cls, artifact_directory: Path) -> StatefulAnchorDeltaGruPredictor:
        """Load the standard stateful ONNX + metadata pair from one artifact folder."""

        return cls(
            onnx_path=artifact_directory / "stateful_anchor_delta_gru.onnx",
            metadata_path=artifact_directory / "stateful_anchor_delta_gru.metadata.json",
        )

    def predict_speed_mps(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> float:
        """Consume unseen samples and return the final causal speed estimate."""

        self._validate(window=window, context=context)
        must_reset = (
            self._source_id != window.source_id
            or self._anchor_timestamp_ns != context.anchor_timestamp_ns
            or self._last_timestamp_ns is None
        )
        if not must_reset and window.end_timestamp_ns <= self._last_timestamp_ns:
            raise ValueError("Stateful GRU windows must advance strictly in time.")
        if not must_reset and (
            window.samples[-1].timestamp_ns - self._last_timestamp_ns
            > self._artifact.sample_period_ns
        ):
            must_reset = True

        if must_reset:
            self.reset()
            self._source_id = window.source_id
            self._anchor_timestamp_ns = context.anchor_timestamp_ns
            # A newly received GNSS fix can fall inside a pre-existing rolling
            # window. Never feed samples predating that trusted anchor.
            samples = tuple(
                sample
                for sample in window.samples
                if sample.timestamp_ns >= context.anchor_timestamp_ns
            )
            if not samples:
                # This can only happen when an old rolling window completes
                # before the first resampled sample at a new anchor. Withhold
                # the prediction rather than fabricate pre-anchor history.
                raise ValueError("Stateful GRU has no post-anchor sample to seed from.")
        else:
            samples = tuple(
                sample
                for sample in window.samples
                if sample.timestamp_ns > self._last_timestamp_ns
            )
            if not samples:
                raise ValueError("Stateful GRU received a window with no new samples.")
            if (
                samples[0].timestamp_ns - self._last_timestamp_ns
                != self._artifact.sample_period_ns
            ):
                # The preprocessor should have cleared its own rolling window
                # on this condition; reset defensively if a caller bypasses it.
                self.reset()
                return self.predict_speed_mps(window=window, context=context)

        feature_rows = np.asarray(
            [self._feature_row(sample, context) for sample in samples],
            dtype=np.float32,
        )
        normalized = (
            feature_rows - np.asarray(self._artifact.feature_mean, dtype=np.float32)
        ) / np.asarray(self._artifact.feature_scale, dtype=np.float32)
        output, next_hidden = self._session.run(
            ["speed_delta_mps", "next_hidden_state"],
            {
                "features": normalized[np.newaxis, :, :],
                "hidden_state": self._hidden_state,
            },
        )
        self._hidden_state = np.asarray(next_hidden, dtype=np.float32)
        predicted_delta_mps = float(np.asarray(output)[0, -1])
        if not isfinite(predicted_delta_mps):
            raise ValueError("Stateful GRU ONNX output must be finite.")
        return max(0.0, context.anchor_speed_mps + predicted_delta_mps)

    def _feature_row(
        self,
        sample: VehicleImuSample,
        context: VelocityInferenceContext,
    ) -> tuple[float, ...]:
        """Build the exact causal eleven-feature row used by the experiment."""

        timestamp_ns = sample.timestamp_ns
        acceleration = sample.linear_acceleration_mps2[0]
        confidence = sample.calibration_confidence
        if not isfinite(acceleration) or not 0.0 <= confidence <= 1.0:
            raise ValueError("Stateful GRU sample values must be finite and valid.")

        if self._last_timestamp_ns is None:
            integrated_speed = context.anchor_speed_mps
        else:
            if timestamp_ns - self._last_timestamp_ns != self._artifact.sample_period_ns:
                raise ValueError("Stateful GRU samples must be fixed-rate and contiguous.")
            if self._last_forward_acceleration_mps2 is None or self._integrated_speed_mps is None:
                raise RuntimeError("Stateful GRU integration state is incomplete.")
            integrated_speed = max(
                0.0,
                self._integrated_speed_mps
                + 0.5
                * (self._last_forward_acceleration_mps2 + acceleration)
                * self._artifact.sample_period_ns
                * 1e-9,
            )
        self._last_timestamp_ns = timestamp_ns
        self._last_forward_acceleration_mps2 = acceleration
        self._integrated_speed_mps = integrated_speed
        self._confidence_count += 1
        self._confidence_sum += confidence
        self._minimum_confidence = min(self._minimum_confidence, confidence)
        return (
            *vehicle_imu_feature_row(sample),
            context.anchor_speed_mps,
            integrated_speed,
            max(0.0, (timestamp_ns - context.anchor_timestamp_ns) * 1e-9),
            self._confidence_sum / self._confidence_count,
            self._minimum_confidence,
        )

    def _validate(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> None:
        """Reject a window that cannot satisfy the exported recurrent contract."""

        if len(window.samples) != self._artifact.warmup_window_size:
            raise ValueError("Stateful GRU warmup-window length does not match metadata.")
        if window.sample_period_ns != self._artifact.sample_period_ns:
            raise ValueError("Stateful GRU sample period does not match metadata.")
        if context.source_id != window.source_id:
            raise ValueError("Stateful GRU context belongs to another IMU source.")
        if context.anchor_timestamp_ns > window.end_timestamp_ns:
            raise ValueError("Stateful GRU anchor cannot be newer than its window.")
        if not all(
            isfinite(value) and value >= 0.0
            for value in (
                context.anchor_speed_mps,
                context.integrated_speed_mps,
                context.seconds_since_anchor,
            )
        ):
            raise ValueError("Stateful GRU context values must be finite and non-negative.")


class StatefulAnchorDeltaGruAdapter:
    """Publish stateful ONNX estimates through the standard observation schema."""

    def __init__(self, predictor: StatefulAnchorDeltaGruPredictor) -> None:
        self._predictor = predictor

    @property
    def model_id(self) -> str:
        """Expose the immutable artifact identity required by composition checks."""

        return self._predictor.model_id

    def predict(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> VelocityObservation:
        """Infer one speed at the end of an accepted rolling IMU window."""

        speed_mps = self._predictor.predict_speed_mps(window=window, context=context)
        return VelocityObservation(
            timestamp_ns=window.end_timestamp_ns,
            source_id=window.source_id,
            window_start_timestamp_ns=window.samples[0].timestamp_ns,
            speed_mps=speed_mps,
            model_id=self._predictor.model_id,
        )


def load_stateful_anchor_delta_gru_adapter(
    artifact_directory: Path,
) -> StatefulAnchorDeltaGruAdapter:
    """Load the selected stateful model for ``DeterministicPreEkfPipeline``."""

    return StatefulAnchorDeltaGruAdapter(
        StatefulAnchorDeltaGruPredictor.from_artifact_directory(artifact_directory)
    )


def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    field = value.get(key)
    if not isinstance(field, dict):
        raise ValueError(f"Stateful GRU metadata field {key!r} must be an object.")
    return field


def _non_blank_string(value: dict[str, Any], key: str) -> str:
    field = value.get(key)
    if not isinstance(field, str) or not field.strip():
        raise ValueError(f"Stateful GRU metadata field {key!r} must be non-blank.")
    return field


def _positive_int(value: dict[str, Any], key: str) -> int:
    field = value.get(key)
    if isinstance(field, bool) or not isinstance(field, int) or field <= 0:
        raise ValueError(f"Stateful GRU metadata field {key!r} must be positive.")
    return field


def _finite_tuple(value: dict[str, Any], key: str, length: int) -> tuple[float, ...]:
    field = value.get(key)
    if not isinstance(field, list) or len(field) != length:
        raise ValueError(
            f"Stateful GRU metadata field {key!r} must have {length} values."
        )
    result = tuple(float(item) for item in field)
    if not all(isfinite(item) for item in result):
        raise ValueError(f"Stateful GRU metadata field {key!r} must be finite.")
    return result


def _positive_tuple(value: dict[str, Any], key: str, length: int) -> tuple[float, ...]:
    result = _finite_tuple(value, key, length)
    if not all(item > 0.0 for item in result):
        raise ValueError(f"Stateful GRU metadata field {key!r} must be positive.")
    return result

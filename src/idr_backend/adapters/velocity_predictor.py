"""Runtime boundary for the separately owned velocity-prediction model.

This adapter deliberately knows nothing about GRU/CNN/RF architecture, Torch
weights, scalers, or training.  A selected model is supplied as a small
callable with an explicit feature/context contract; the adapter validates the
causal window and publishes the core ``VelocityObservation`` consumed by the
uncertainty engine and later fusion.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from idr_backend.sensors.types import VelocityObservation
from idr_backend.sensors.windowing import (
    VelocityModelInputWindow,
    velocity_model_feature_rows,
)


@dataclass(frozen=True, slots=True)
class VelocityInferenceContext:
    """Causal state that a blackout-trained speed model may require.

    The anchor is the last trusted GNSS speed while GNSS was available.  Its
    value is held during a blackout; ``integrated_speed_mps`` is the separate
    deterministic IMU integration baseline, not a future ground-truth label.
    """

    source_id: str
    anchor_timestamp_ns: int
    anchor_speed_mps: float
    integrated_speed_mps: float
    seconds_since_anchor: float

    # These causal summaries are part of the selected anchored GRU's original
    # five-value context vector. They reveal mounting trust without changing
    # the clean six-channel IMU sequence itself.
    mean_calibration_confidence: float = 1.0
    minimum_calibration_confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class VelocityPredictorSpec:
    """Immutable input contract for one exported velocity-model artifact."""

    model_id: str
    window_size: int
    sample_period_ns: int


class VelocityPredictor(Protocol):
    """Architecture-neutral callable implemented by the chosen model package."""

    def predict_speed_mps(
        self,
        feature_rows: tuple[
            tuple[float, float, float, float, float, float], ...
        ],
        context: VelocityInferenceContext,
    ) -> float:
        """Return one non-negative scalar ground-speed estimate in m/s."""


class VelocityObservationProducer(Protocol):
    """Boundary shared by stateless-window and state-carrying model adapters."""

    def predict(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> VelocityObservation:
        """Publish an auditable speed observation for one causal IMU window."""


class VelocityPredictorAdapter:
    """Validate model input/output and publish a versioned speed observation."""

    def __init__(
        self,
        *,
        spec: VelocityPredictorSpec,
        predictor: VelocityPredictor,
    ) -> None:
        """Bind one selected model implementation to its immutable contract."""

        if not spec.model_id.strip():
            raise ValueError("model_id must not be blank.")
        if spec.window_size <= 0:
            raise ValueError("window_size must be positive.")
        if spec.sample_period_ns <= 0:
            raise ValueError("sample_period_ns must be positive.")

        self._spec = spec
        self._predictor = predictor

    @property
    def model_id(self) -> str:
        """Return the immutable identity of the bound model artifact."""

        return self._spec.model_id

    def predict(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> VelocityObservation:
        """Run the selected model on one complete causal sensor window."""

        self._validate_input(window=window, context=context)

        speed_mps = float(
            self._predictor.predict_speed_mps(
                velocity_model_feature_rows(window),
                context,
            )
        )
        if not isfinite(speed_mps) or speed_mps < 0.0:
            raise ValueError(
                "Velocity predictor must return a finite non-negative speed."
            )

        return VelocityObservation(
            timestamp_ns=window.end_timestamp_ns,
            source_id=window.source_id,
            window_start_timestamp_ns=window.samples[0].timestamp_ns,
            speed_mps=speed_mps,
            model_id=self.model_id,
        )

    def _validate_input(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> None:
        """Reject an input that does not match the artifact's causal contract."""

        if len(window.samples) != self._spec.window_size:
            raise ValueError(
                "Velocity window length does not match the selected model."
            )
        if window.sample_period_ns != self._spec.sample_period_ns:
            raise ValueError(
                "Velocity window period does not match the selected model."
            )
        if context.source_id != window.source_id:
            raise ValueError("Velocity context must belong to the window device.")
        if context.anchor_timestamp_ns > window.end_timestamp_ns:
            raise ValueError("Velocity anchor cannot be newer than its window.")
        if not all(
            isfinite(value) and value >= 0.0
            for value in (
                context.anchor_speed_mps,
                context.integrated_speed_mps,
                context.seconds_since_anchor,
            )
        ):
            raise ValueError(
                "Velocity context values must be finite and non-negative."
            )
        if not all(
            isfinite(value) and 0.0 <= value <= 1.0
            for value in (
                context.mean_calibration_confidence,
                context.minimum_calibration_confidence,
            )
        ):
            raise ValueError(
                "Calibration confidences must be finite and between 0.0 and 1.0."
            )
        if (
            context.minimum_calibration_confidence
            > context.mean_calibration_confidence
        ):
            raise ValueError(
                "Minimum calibration confidence cannot exceed its window mean."
            )

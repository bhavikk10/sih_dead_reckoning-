"""Build leakage-safe velocity-training examples from the runtime preprocessor.

This is deliberately an *offline* evaluation/training helper.  It replays raw
phone IMU and phone GNSS through ``DeterministicImuPreprocessor`` and the
pre-EKF anchoring/integration path used at runtime.  CAN speed remains an
offline target only.  Thus a velocity model trained from this dataset sees the
same six cleaned channels, fixed-rate windows, GNSS anchors, calibration
confidence, and GNSS-loss behaviour that it will see after export.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np
import pandas as pd

from idr_backend.adapters.velocity_predictor import VelocityInferenceContext
from idr_backend.pipeline.orchestrator import (
    DeterministicPipelineConfig,
    DeterministicPreEkfPipeline,
)
from idr_backend.sensors.preprocessing import DeterministicImuPreprocessor
from idr_backend.sensors.types import (
    CoordinateFrame,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
    VelocityObservation,
)
from idr_backend.sensors.windowing import (
    VelocityModelInputWindow,
    vehicle_imu_feature_row,
    velocity_model_feature_rows,
)
from idr_backend.uncertainty.heuristics import HeuristicUncertaintyConfig
from idr_backend.uncertainty.features import build_velocity_uncertainty_features
from idr_backend.uncertainty.protocol import HeuristicVelocityUncertaintyEstimator

from .replay import (
    RawReplayJourney,
    _NS_PER_SECOND,
    _phone_gnss_fix,
    _should_emit_gnss,
    default_preprocessor_config,
)


@dataclass(frozen=True, slots=True)
class ProductionVelocityDatasetConfig:
    """Explicit replay policy for production-compatible training examples.

    Every candidate anchor receives normal phone GNSS only through the anchor,
    then sees an uninterrupted IMU-only interval.  ``horizons_s`` therefore
    describe the same bounded GNSS loss that the deployed anchor-delta model
    is intended to correct.  Splits must still be grouped by ``journey_id``.
    """

    warmup_s: float = 30.0
    # Five-minute spacing keeps the notebook tractable while still sampling
    # many independent traffic states from long recordings. It changes only
    # offline example density; every emitted example is a real runtime replay.
    anchor_stride_s: float = 300.0
    horizons_s: tuple[float, ...] = (5.0, 10.0, 20.0, 30.0, 60.0, 90.0, 120.0)
    maximum_anchor_age_s: float = 120.0
    horizon_match_tolerance_s: float = 0.11

    def __post_init__(self) -> None:
        if not all(
            isfinite(value) and value > 0.0
            for value in (
                self.warmup_s,
                self.anchor_stride_s,
                self.maximum_anchor_age_s,
                self.horizon_match_tolerance_s,
            )
        ):
            raise ValueError("Production velocity replay timings must be positive.")
        if not self.horizons_s or any(
            not isfinite(value) or value <= 0.0 for value in self.horizons_s
        ):
            raise ValueError("Production velocity horizons must be non-empty and positive.")
        if any(right <= left for left, right in zip(self.horizons_s, self.horizons_s[1:])):
            raise ValueError("Production velocity horizons must increase strictly.")
        if self.horizons_s[-1] > self.maximum_anchor_age_s:
            raise ValueError("No requested horizon may exceed the runtime anchor limit.")


@dataclass(frozen=True, slots=True)
class ProductionVelocityDataset:
    """Arrays ready for grouped-CV training of an anchor-delta model.

    ``target_delta_mps`` is the only model target. ``target_speed_mps`` is
    retained for physical-unit evaluation after adding the GNSS anchor back.
    No CAN value occurs in ``sequence_windows`` or ``context_features``.
    """

    sequence_windows: np.ndarray
    context_features: np.ndarray
    target_delta_mps: np.ndarray
    target_speed_mps: np.ndarray
    anchor_speed_mps: np.ndarray
    journey_ids: np.ndarray
    anchor_timestamps_ns: np.ndarray
    end_timestamps_ns: np.ndarray
    horizons_s: np.ndarray
    # The first seven causal uncertainty facts. The eighth feature,
    # ``predicted_speed_mps``, is added only after an out-of-fold velocity
    # prediction exists, preventing the uncertainty learner from seeing an
    # in-sample speed prediction.
    uncertainty_base_features: np.ndarray

    def __post_init__(self) -> None:
        count = len(self.target_delta_mps)
        if self.sequence_windows.ndim != 3 or self.sequence_windows.shape[2] != 6:
            raise ValueError("Production windows must have shape (examples, time, 6).")
        if self.context_features.shape != (count, 5):
            raise ValueError("Production context must have five anchor-GRU values.")
        arrays = (
            self.sequence_windows,
            self.target_speed_mps,
            self.anchor_speed_mps,
            self.journey_ids,
            self.anchor_timestamps_ns,
            self.end_timestamps_ns,
            self.horizons_s,
            self.uncertainty_base_features,
        )
        if count == 0 or any(len(value) != count for value in arrays):
            raise ValueError("Production velocity dataset arrays must be non-empty and aligned.")
        numeric = (
            self.sequence_windows,
            self.context_features,
            self.target_delta_mps,
            self.target_speed_mps,
            self.anchor_speed_mps,
            self.horizons_s,
            self.uncertainty_base_features,
        )
        if not all(np.isfinite(value).all() for value in numeric):
            raise ValueError("Production velocity dataset numeric arrays must be finite.")
        if self.uncertainty_base_features.shape != (count, 7):
            raise ValueError("Production uncertainty base features must have seven columns.")


@dataclass(frozen=True, slots=True)
class ProductionStatefulSequence:
    """One exact production-preprocessor IMU stream after a GNSS anchor.

    The windowed dataset below is ideal for a five-second model.  A stateful
    model instead needs every new cleaned 10 Hz sample, its causal integration
    context, and its target speed change.  This development-only structure is
    produced from the same captured runtime windows rather than from a second,
    easier offline cleaning path.
    """

    journey_id: str
    anchor_timestamp_ns: int
    anchor_speed_mps: float
    timestamps_ns: np.ndarray
    features: np.ndarray  # shape (time, 11): six IMU + five causal context values
    target_delta_mps: np.ndarray
    training_mask: np.ndarray
    evaluation_mask: np.ndarray
    final_quality_score: np.ndarray

    def __post_init__(self) -> None:
        """Reject partial or non-finite streams before model training begins."""

        count = len(self.features)
        if self.features.ndim != 2 or self.features.shape[1] != 11:
            raise ValueError("Stateful production features must have shape (time, 11).")
        arrays = (
            self.timestamps_ns,
            self.target_delta_mps,
            self.training_mask,
            self.evaluation_mask,
            self.final_quality_score,
        )
        if count == 0 or any(len(values) != count for values in arrays):
            raise ValueError("Stateful production sequence arrays must be aligned.")
        if (
            not np.isfinite(self.features).all()
            or not np.isfinite(self.target_delta_mps).all()
            or not np.isfinite(self.final_quality_score).all()
        ):
            raise ValueError("Stateful production sequences must be finite.")
        if not np.all(np.diff(self.timestamps_ns) > 0):
            raise ValueError("Stateful production timestamps must increase strictly.")
        if not np.all((0.0 <= self.final_quality_score) & (self.final_quality_score <= 1.0)):
            raise ValueError("Stateful production quality scores must be in [0, 1].")
        if not self.evaluation_mask.any():
            raise ValueError("Stateful production sequence has no evaluation endpoint.")


@dataclass(frozen=True, slots=True)
class ProductionVelocityExperimentDataset:
    """One shared raw-replay capture for windowed and stateful experiments."""

    windowed: ProductionVelocityDataset
    stateful_sequences: tuple[ProductionStatefulSequence, ...]
    audits: tuple["ProductionVelocityDatasetAudit", ...]


_SPEED_BIN_EDGES_KMH = np.asarray((0.0, 20.0, 40.0, 60.0, 80.0, np.inf))
_DELTA_BIN_EDGES_KMH = np.asarray((0.0, 5.0, 10.0, 20.0, 40.0, np.inf))
_HORIZON_BIN_EDGES_S = np.asarray((0.0, 20.0, 60.0, np.inf))


def production_velocity_eda_frame(dataset: ProductionVelocityDataset) -> pd.DataFrame:
    """Return one row per real runtime-compatible window for notebook EDA.

    The table deliberately contains targets only for offline analysis and
    training.  It must never be passed to a live predictor or fusion path.
    """

    acceleration_rms = np.sqrt(np.mean(np.square(dataset.sequence_windows[:, :, 0]), axis=1))
    yaw_rate_rms = np.sqrt(np.mean(np.square(dataset.sequence_windows[:, :, 5]), axis=1))
    return pd.DataFrame(
        {
            "journey_id": dataset.journey_ids,
            "anchor_timestamp_ns": dataset.anchor_timestamps_ns,
            "end_timestamp_ns": dataset.end_timestamps_ns,
            "horizon_s": dataset.horizons_s,
            "anchor_speed_kmh": dataset.anchor_speed_mps * 3.6,
            "target_speed_kmh": dataset.target_speed_mps * 3.6,
            "speed_delta_kmh": dataset.target_delta_mps * 3.6,
            "absolute_speed_delta_kmh": np.abs(dataset.target_delta_mps) * 3.6,
            "forward_acceleration_rms_mps2": acceleration_rms,
            "yaw_rate_rms_radps": yaw_rate_rms,
            "minimum_calibration_confidence": dataset.context_features[:, 4],
        }
    )


def fold_balanced_sample_weights(
    dataset: ProductionVelocityDataset,
    train_indices: np.ndarray,
) -> np.ndarray:
    """Return bounded, training-only weights for journey and tail balancing.

    Selection remains macro-journey MAE, so every journey first receives equal
    total mass.  A square-root inverse count then increases exposure to sparse
    speed/change/horizon strata without allowing a handful of rare points to
    dominate every minibatch.  All counts are derived from ``train_indices``;
    validation journeys cannot affect training distribution or normalization.
    """

    train_indices = np.asarray(train_indices, dtype=np.int64)
    if train_indices.ndim != 1 or not len(train_indices):
        raise ValueError("train_indices must be a non-empty one-dimensional array.")
    if train_indices.min() < 0 or train_indices.max() >= len(dataset.target_delta_mps):
        raise IndexError("train_indices are outside the production dataset.")

    journey = dataset.journey_ids[train_indices]
    speed_kmh = dataset.target_speed_mps[train_indices] * 3.6
    delta_kmh = np.abs(dataset.target_delta_mps[train_indices]) * 3.6
    horizons = dataset.horizons_s[train_indices]
    speed_bin = np.digitize(speed_kmh, _SPEED_BIN_EDGES_KMH[1:-1], right=False)
    delta_bin = np.digitize(delta_kmh, _DELTA_BIN_EDGES_KMH[1:-1], right=False)
    horizon_bin = np.digitize(horizons, _HORIZON_BIN_EDGES_S[1:-1], right=False)

    _, journey_inverse, journey_counts = np.unique(
        journey, return_inverse=True, return_counts=True
    )
    strata = np.column_stack((speed_bin, delta_bin, horizon_bin))
    _, stratum_inverse, stratum_counts = np.unique(
        strata, axis=0, return_inverse=True, return_counts=True
    )
    journey_weight = len(train_indices) / (len(journey_counts) * journey_counts[journey_inverse])
    stratum_weight = np.sqrt(
        len(train_indices) / (len(stratum_counts) * stratum_counts[stratum_inverse])
    )
    raw = journey_weight * stratum_weight
    normalized = raw / np.mean(raw)
    return np.clip(normalized, 0.25, 4.0).astype(np.float64)


@dataclass(frozen=True, slots=True)
class ProductionVelocityDatasetAudit:
    """Per-journey replay retention, so failed calibration is never hidden."""

    journey_id: str
    attempted_anchors: int
    emitted_examples: int
    accepted_preprocessing_samples: int
    calibration_warming_up_samples: int
    calibration_untrusted_samples: int
    quality_rejected_samples: int


@dataclass(frozen=True, slots=True)
class _CapturedWindow:
    """Private causal facts emitted by the normal pre-EKF anchoring path."""

    window: VelocityModelInputWindow
    context: VelocityInferenceContext


class _ContextCapturingPredictor:
    """Record production model inputs without inserting a training model.

    The returned integrated-speed observation is only a harmless placeholder
    needed to let the pre-EKF pipeline build its usual uncertainty object. It
    is never used as a target or an input to the velocity model being trained.
    """

    model_id = "production_velocity_dataset_capture_v1"

    def __init__(self) -> None:
        self.captured: list[_CapturedWindow] = []

    def predict(
        self,
        *,
        window: VelocityModelInputWindow,
        context: VelocityInferenceContext,
    ) -> VelocityObservation:
        self.captured.append(_CapturedWindow(window=window, context=context))
        return VelocityObservation(
            timestamp_ns=window.end_timestamp_ns,
            source_id=window.source_id,
            window_start_timestamp_ns=window.samples[0].timestamp_ns,
            speed_mps=context.integrated_speed_mps,
            model_id=self.model_id,
        )


_CAPTURE_UNCERTAINTY = HeuristicVelocityUncertaintyEstimator(
    HeuristicUncertaintyConfig(
        variance_floor_m2ps2=1.0,
        variance_ceiling_m2ps2=4.0,
        reference_acceleration_rms_mps2=2.0,
        reference_angular_velocity_rms_radps=1.0,
        roughness_weight=0.0,
        turn_weight=0.0,
        calibration_weight=0.0,
        quality_weight=0.0,
    )
)


def build_production_velocity_dataset(
    journeys: Iterable[RawReplayJourney],
    *,
    config: ProductionVelocityDatasetConfig = ProductionVelocityDatasetConfig(),
) -> tuple[ProductionVelocityDataset, tuple[ProductionVelocityDatasetAudit, ...]]:
    """Replay supplied journeys and return examples grouped only by drive.

    Each replay begins from the raw recording's start, receives GNSS through
    one anchor, and then intentionally loses GNSS. This replays calibration,
    orientation, gravity removal, quality gating, resampling, windowing and
    anchor integration exactly once per candidate anchor. It is slower than
    an offline array transform by design: matching runtime semantics matters
    more than shortcutting the data path that caused the prior mismatch.
    """

    sequence_windows: list[np.ndarray] = []
    context_features: list[tuple[float, float, float, float, float]] = []
    target_delta_mps: list[float] = []
    target_speed_mps: list[float] = []
    anchor_speed_mps: list[float] = []
    journey_ids: list[str] = []
    anchor_timestamps_ns: list[int] = []
    end_timestamps_ns: list[int] = []
    horizons_s: list[float] = []
    uncertainty_base_features: list[tuple[float, float, float, float, float, float, float]] = []
    audits: list[ProductionVelocityDatasetAudit] = []

    for journey in journeys:
        anchors = _anchor_timestamps(journey, config)
        accepted = warming_up = untrusted = quality_rejected = emitted = 0
        for anchor_timestamp_ns in anchors:
            captured, counts = _capture_blackout_windows(
                journey=journey,
                anchor_timestamp_ns=anchor_timestamp_ns,
                config=config,
            )
            accepted += counts[0]
            warming_up += counts[1]
            untrusted += counts[2]
            quality_rejected += counts[3]
            for target_horizon_s, item in _choose_horizon_windows(captured, config):
                target_speed = float(
                    np.interp(
                        item.window.end_timestamp_ns,
                        journey.timestamps_ns,
                        journey.reference_speed_mps,
                    )
                )
                context = item.context
                sequence_windows.append(
                    np.asarray(velocity_model_feature_rows(item.window), dtype=np.float32)
                )
                context_features.append(
                    (
                        context.anchor_speed_mps,
                        context.integrated_speed_mps,
                        context.seconds_since_anchor,
                        context.mean_calibration_confidence,
                        context.minimum_calibration_confidence,
                    )
                )
                target_delta_mps.append(target_speed - context.anchor_speed_mps)
                target_speed_mps.append(target_speed)
                anchor_speed_mps.append(context.anchor_speed_mps)
                journey_ids.append(journey.journey_id)
                anchor_timestamps_ns.append(context.anchor_timestamp_ns)
                end_timestamps_ns.append(item.window.end_timestamp_ns)
                horizons_s.append(target_horizon_s)
                provisional_observation = VelocityObservation(
                    timestamp_ns=item.window.end_timestamp_ns,
                    source_id=item.window.source_id,
                    window_start_timestamp_ns=item.window.samples[0].timestamp_ns,
                    speed_mps=context.integrated_speed_mps,
                    model_id=_ContextCapturingPredictor.model_id,
                )
                uncertainty = build_velocity_uncertainty_features(
                    observation=provisional_observation,
                    window=item.window,
                    final_quality=item.window.final_quality,
                    seconds_since_anchor=context.seconds_since_anchor,
                )
                uncertainty_base_features.append(uncertainty.as_tuple()[:-1])
                emitted += 1
        audits.append(
            ProductionVelocityDatasetAudit(
                journey_id=journey.journey_id,
                attempted_anchors=len(anchors),
                emitted_examples=emitted,
                accepted_preprocessing_samples=accepted,
                calibration_warming_up_samples=warming_up,
                calibration_untrusted_samples=untrusted,
                quality_rejected_samples=quality_rejected,
            )
        )

    return (
        ProductionVelocityDataset(
            sequence_windows=np.asarray(sequence_windows, dtype=np.float32),
            context_features=np.asarray(context_features, dtype=np.float32),
            target_delta_mps=np.asarray(target_delta_mps, dtype=np.float32),
            target_speed_mps=np.asarray(target_speed_mps, dtype=np.float32),
            anchor_speed_mps=np.asarray(anchor_speed_mps, dtype=np.float32),
            journey_ids=np.asarray(journey_ids, dtype=str),
            anchor_timestamps_ns=np.asarray(anchor_timestamps_ns, dtype=np.int64),
            end_timestamps_ns=np.asarray(end_timestamps_ns, dtype=np.int64),
            horizons_s=np.asarray(horizons_s, dtype=np.float32),
            uncertainty_base_features=np.asarray(
                uncertainty_base_features, dtype=np.float32
            ),
        ),
        tuple(audits),
    )


def build_production_velocity_experiment_dataset(
    journeys: Iterable[RawReplayJourney],
    *,
    config: ProductionVelocityDatasetConfig = ProductionVelocityDatasetConfig(),
    stateful_label_period_s: float = 1.0,
) -> ProductionVelocityExperimentDataset:
    """Build dense windowed and stateful examples from one raw replay pass.

    Replaying every anchor is intentionally expensive, so the final model
    investigation must not build the stateful stream with a second pass over
    the same raw data.  This function records both views from each already
    captured runtime window.  ``horizons_s`` can be dense for training; callers
    select the canonical evaluation horizons when reporting scores.
    """

    if not isfinite(stateful_label_period_s) or stateful_label_period_s <= 0.0:
        raise ValueError("stateful_label_period_s must be finite and positive.")

    sequence_windows: list[np.ndarray] = []
    context_features: list[tuple[float, float, float, float, float]] = []
    target_delta_mps: list[float] = []
    target_speed_mps: list[float] = []
    anchor_speed_mps: list[float] = []
    journey_ids: list[str] = []
    anchor_timestamps_ns: list[int] = []
    end_timestamps_ns: list[int] = []
    horizons_s: list[float] = []
    uncertainty_base_features: list[tuple[float, float, float, float, float, float, float]] = []
    stateful_sequences: list[ProductionStatefulSequence] = []
    audits: list[ProductionVelocityDatasetAudit] = []

    for journey in journeys:
        anchors = _anchor_timestamps(journey, config)
        accepted = warming_up = untrusted = quality_rejected = emitted = 0
        for anchor_timestamp_ns in anchors:
            captured, counts = _capture_blackout_windows(
                journey=journey,
                anchor_timestamp_ns=anchor_timestamp_ns,
                config=config,
            )
            accepted += counts[0]
            warming_up += counts[1]
            untrusted += counts[2]
            quality_rejected += counts[3]

            for target_horizon_s, item in _choose_horizon_windows(captured, config):
                target_speed = float(
                    np.interp(
                        item.window.end_timestamp_ns,
                        journey.timestamps_ns,
                        journey.reference_speed_mps,
                    )
                )
                context = item.context
                sequence_windows.append(
                    np.asarray(velocity_model_feature_rows(item.window), dtype=np.float32)
                )
                context_features.append(
                    (
                        context.anchor_speed_mps,
                        context.integrated_speed_mps,
                        context.seconds_since_anchor,
                        context.mean_calibration_confidence,
                        context.minimum_calibration_confidence,
                    )
                )
                target_delta_mps.append(target_speed - context.anchor_speed_mps)
                target_speed_mps.append(target_speed)
                anchor_speed_mps.append(context.anchor_speed_mps)
                journey_ids.append(journey.journey_id)
                anchor_timestamps_ns.append(context.anchor_timestamp_ns)
                end_timestamps_ns.append(item.window.end_timestamp_ns)
                horizons_s.append(target_horizon_s)
                provisional_observation = VelocityObservation(
                    timestamp_ns=item.window.end_timestamp_ns,
                    source_id=item.window.source_id,
                    window_start_timestamp_ns=item.window.samples[0].timestamp_ns,
                    speed_mps=context.integrated_speed_mps,
                    model_id=_ContextCapturingPredictor.model_id,
                )
                uncertainty = build_velocity_uncertainty_features(
                    observation=provisional_observation,
                    window=item.window,
                    final_quality=item.window.final_quality,
                    seconds_since_anchor=context.seconds_since_anchor,
                )
                uncertainty_base_features.append(uncertainty.as_tuple()[:-1])
                emitted += 1

            sequence = _captured_windows_to_stateful_sequence(
                journey=journey,
                anchor_timestamp_ns=anchor_timestamp_ns,
                captured=captured,
                config=config,
                label_period_s=stateful_label_period_s,
            )
            if sequence is not None:
                stateful_sequences.append(sequence)

        audits.append(
            ProductionVelocityDatasetAudit(
                journey_id=journey.journey_id,
                attempted_anchors=len(anchors),
                emitted_examples=emitted,
                accepted_preprocessing_samples=accepted,
                calibration_warming_up_samples=warming_up,
                calibration_untrusted_samples=untrusted,
                quality_rejected_samples=quality_rejected,
            )
        )

    windowed = ProductionVelocityDataset(
        sequence_windows=np.asarray(sequence_windows, dtype=np.float32),
        context_features=np.asarray(context_features, dtype=np.float32),
        target_delta_mps=np.asarray(target_delta_mps, dtype=np.float32),
        target_speed_mps=np.asarray(target_speed_mps, dtype=np.float32),
        anchor_speed_mps=np.asarray(anchor_speed_mps, dtype=np.float32),
        journey_ids=np.asarray(journey_ids, dtype=str),
        anchor_timestamps_ns=np.asarray(anchor_timestamps_ns, dtype=np.int64),
        end_timestamps_ns=np.asarray(end_timestamps_ns, dtype=np.int64),
        horizons_s=np.asarray(horizons_s, dtype=np.float32),
        uncertainty_base_features=np.asarray(uncertainty_base_features, dtype=np.float32),
    )
    if not stateful_sequences:
        raise ValueError("Raw replay produced no stateful production sequences.")
    return ProductionVelocityExperimentDataset(
        windowed=windowed,
        stateful_sequences=tuple(stateful_sequences),
        audits=tuple(audits),
    )


def _captured_windows_to_stateful_sequence(
    *,
    journey: RawReplayJourney,
    anchor_timestamp_ns: int,
    captured: Iterable[_CapturedWindow],
    config: ProductionVelocityDatasetConfig,
    label_period_s: float,
) -> ProductionStatefulSequence | None:
    """Recover every new causal IMU sample from overlapping runtime windows."""

    captured_items = tuple(captured)
    if not captured_items:
        return None
    sample_period_ns = captured_items[0].window.sample_period_ns
    if any(item.window.sample_period_ns != sample_period_ns for item in captured_items):
        raise ValueError("Captured stateful windows changed their sample period.")

    # The first emitted 50-sample velocity window is also the stateful model's
    # warm-up boundary.  Before it, the deployed adapter cannot publish a
    # speed, even though it can accumulate hidden state internally.
    first_prediction_timestamp_ns = captured_items[0].window.end_timestamp_ns
    samples = []
    quality_by_timestamp: dict[int, float] = {}
    last_timestamp_ns: int | None = None
    for item in captured_items:
        quality_by_timestamp[item.window.end_timestamp_ns] = item.window.final_quality.score
        for sample in item.window.samples:
            if sample.timestamp_ns < anchor_timestamp_ns:
                continue
            if last_timestamp_ns is not None and sample.timestamp_ns <= last_timestamp_ns:
                continue
            if (
                last_timestamp_ns is not None
                and sample.timestamp_ns - last_timestamp_ns != sample_period_ns
            ):
                # The runtime window builder clears discontinuities. A single
                # stateful stream must not silently bridge one in offline data.
                return None
            samples.append(sample)
            last_timestamp_ns = sample.timestamp_ns
    if len(samples) < 2:
        return None

    period_s = sample_period_ns * 1e-9
    label_steps = max(1, round(label_period_s / period_s))
    anchor_speed = float(captured_items[0].context.anchor_speed_mps)
    integrated_speed = anchor_speed
    previous_acceleration: float | None = None
    confidence_sum = 0.0
    minimum_confidence = 1.0
    feature_rows: list[tuple[float, ...]] = []
    target_delta: list[float] = []
    training_mask: list[bool] = []
    evaluation_mask: list[bool] = []
    quality_scores: list[float] = []
    latest_quality_score = 1.0

    for index, sample in enumerate(samples):
        forward_acceleration = float(sample.linear_acceleration_mps2[0])
        if previous_acceleration is not None:
            integrated_speed = max(
                0.0,
                integrated_speed
                + 0.5 * (previous_acceleration + forward_acceleration) * period_s,
            )
        previous_acceleration = forward_acceleration
        confidence = float(sample.calibration_confidence)
        confidence_sum += confidence
        minimum_confidence = min(minimum_confidence, confidence)
        elapsed_s = max(0.0, (sample.timestamp_ns - anchor_timestamp_ns) * 1e-9)
        latest_quality_score = quality_by_timestamp.get(
            sample.timestamp_ns,
            latest_quality_score,
        )
        feature_rows.append(
            (
                *vehicle_imu_feature_row(sample),
                anchor_speed,
                integrated_speed,
                elapsed_s,
                confidence_sum / (index + 1),
                minimum_confidence,
            )
        )
        target_speed = float(
            np.interp(
                sample.timestamp_ns,
                journey.timestamps_ns,
                journey.reference_speed_mps,
            )
        )
        target_delta.append(target_speed - anchor_speed)
        elapsed_steps = int(round(elapsed_s / period_s))
        training_mask.append(
            sample.timestamp_ns >= first_prediction_timestamp_ns
            and elapsed_steps % label_steps == 0
        )
        evaluation_mask.append(
            any(
                abs(elapsed_s - horizon_s) <= config.horizon_match_tolerance_s
                for horizon_s in config.horizons_s
            )
        )
        quality_scores.append(latest_quality_score)

    if not any(evaluation_mask):
        return None
    return ProductionStatefulSequence(
        journey_id=journey.journey_id,
        anchor_timestamp_ns=anchor_timestamp_ns,
        anchor_speed_mps=anchor_speed,
        timestamps_ns=np.asarray([sample.timestamp_ns for sample in samples], dtype=np.int64),
        features=np.asarray(feature_rows, dtype=np.float32),
        target_delta_mps=np.asarray(target_delta, dtype=np.float32),
        training_mask=np.asarray(training_mask, dtype=bool),
        evaluation_mask=np.asarray(evaluation_mask, dtype=bool),
        final_quality_score=np.asarray(quality_scores, dtype=np.float32),
    )


def _anchor_timestamps(
    journey: RawReplayJourney,
    config: ProductionVelocityDatasetConfig,
) -> tuple[int, ...]:
    """Choose regularly spaced valid anchors without using target labels."""

    latest_anchor_s = journey.duration_s - config.horizons_s[-1]
    if latest_anchor_s < config.warmup_s:
        return ()
    candidates = np.arange(
        config.warmup_s,
        latest_anchor_s + 1e-9,
        config.anchor_stride_s,
    )
    timestamps = []
    for candidate_s in candidates:
        index = int(np.searchsorted(journey.timestamps_ns, candidate_s * _NS_PER_SECOND))
        if index < len(journey.timestamps_ns):
            timestamps.append(int(journey.timestamps_ns[index]))
    return tuple(dict.fromkeys(timestamps))


def _capture_blackout_windows(
    *,
    journey: RawReplayJourney,
    anchor_timestamp_ns: int,
    config: ProductionVelocityDatasetConfig,
) -> tuple[list[_CapturedWindow], tuple[int, int, int, int]]:
    """Run one causal GNSS-to-blackout replay and retain model-ready windows."""

    preprocessor = DeterministicImuPreprocessor(default_preprocessor_config())
    predictor = _ContextCapturingPredictor()
    pipeline = DeterministicPreEkfPipeline(
        config=DeterministicPipelineConfig(
            maximum_gnss_anchor_age_ns=int(config.maximum_anchor_age_s * _NS_PER_SECOND)
        ),
        preprocessor=preprocessor,
        velocity_predictor=predictor,
        uncertainty_estimator=_CAPTURE_UNCERTAINTY,
    )
    final_timestamp_ns = anchor_timestamp_ns + int(config.horizons_s[-1] * _NS_PER_SECOND)
    last_gnss_timestamp_ns: int | None = None
    accepted = warming_up = untrusted = quality_rejected = 0

    # A new runtime session gets a finite calibration/orientation warm-up; do
    # the same around each offline anchor rather than replaying thousands of
    # seconds of irrelevant history for every example. The code/configuration
    # remain exactly the runtime path, and the warm-up duration is recorded in
    # the dataset configuration.
    start_timestamp_ns = max(
        int(journey.timestamps_ns[0]),
        anchor_timestamp_ns - int(config.warmup_s * _NS_PER_SECOND),
    )
    start_index = int(np.searchsorted(journey.timestamps_ns, start_timestamp_ns))
    for index in range(start_index, len(journey.timestamps_ns)):
        timestamp_ns = int(journey.timestamps_ns[index])
        if timestamp_ns > final_timestamp_ns:
            break
        if timestamp_ns <= anchor_timestamp_ns and _should_emit_gnss(
            timestamp_ns, last_gnss_timestamp_ns
        ):
            pipeline.push_gnss_fix(_phone_gnss_fix(journey, index))
            last_gnss_timestamp_ns = timestamp_ns

        pipeline.push_raw_sample(_accelerometer_sample(journey, index))
        results = pipeline.push_raw_sample(_gyroscope_sample(journey, index))
        for result in results:
            disposition = result.preprocessing.disposition.value
            accepted += int(disposition == "accepted")
            warming_up += int(disposition == "calibration_warming_up")
            untrusted += int(disposition == "calibration_untrusted")
            quality_rejected += int(disposition == "quality_rejected")

    return predictor.captured, (accepted, warming_up, untrusted, quality_rejected)


def _choose_horizon_windows(
    captured: Iterable[_CapturedWindow],
    config: ProductionVelocityDatasetConfig,
) -> tuple[tuple[float, _CapturedWindow], ...]:
    """Choose at most one actual runtime window nearest each requested horizon."""

    selected: list[tuple[float, _CapturedWindow]] = []
    available = tuple(captured)
    for horizon_s in config.horizons_s:
        candidates = [
            item
            for item in available
            if abs(item.context.seconds_since_anchor - horizon_s)
            <= config.horizon_match_tolerance_s
        ]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda item: abs(item.context.seconds_since_anchor - horizon_s),
        )
        selected.append((horizon_s, best))
    return tuple(selected)


def _accelerometer_sample(journey: RawReplayJourney, index: int) -> RawSensorSample:
    """Create one raw phone acceleration callback in its declared sensor frame."""

    return RawSensorSample(
        timestamp_ns=int(journey.timestamps_ns[index]),
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=SensorKind.ACCELEROMETER,
        value=tuple(float(value) for value in journey.acceleration_sensor_mps2[index]),
        unit=MeasurementUnit.METERS_PER_SECOND_SQUARED,
        frame=CoordinateFrame.SENSOR,
    )


def _gyroscope_sample(journey: RawReplayJourney, index: int) -> RawSensorSample:
    """Create one raw phone gyroscope callback in its declared sensor frame."""

    return RawSensorSample(
        timestamp_ns=int(journey.timestamps_ns[index]),
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=SensorKind.GYROSCOPE,
        value=tuple(float(value) for value in journey.angular_velocity_sensor_radps[index]),
        unit=MeasurementUnit.RADIANS_PER_SECOND,
        frame=CoordinateFrame.SENSOR,
    )

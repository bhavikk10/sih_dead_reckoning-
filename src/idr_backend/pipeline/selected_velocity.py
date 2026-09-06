"""Composition helpers for the selected velocity model and its covariance.

This is the one place that selects runtime artifacts.  It keeps the selected
windowed anchor-delta GRU and its deterministic uncertainty profile paired by
their strict loader checks, leaving ``DeterministicPreEkfPipeline`` itself
independent from filesystem paths and model families.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from idr_backend.adapters.anchor_delta_gru import load_anchor_delta_gru_adapter
from idr_backend.adapters.stateful_anchor_delta_gru import (
    load_stateful_anchor_delta_gru_adapter,
)
from idr_backend.adapters.velocity_predictor import VelocityObservationProducer
from idr_backend.sensors.preprocessing import DeterministicImuPreprocessor
from idr_backend.uncertainty.artifacts import (
    load_deterministic_velocity_uncertainty_estimator,
)
from idr_backend.uncertainty.heuristics import HeuristicUncertaintyConfig
from idr_backend.uncertainty.protocol import (
    HeuristicVelocityUncertaintyEstimator,
    VelocityUncertaintyEstimator,
)

from .orchestrator import DeterministicPipelineConfig, DeterministicPreEkfPipeline


@dataclass(frozen=True, slots=True)
class SelectedVelocityRuntimeArtifacts:
    """Locations of the two artifacts that must describe one GRU contract."""

    velocity_artifact_directory: Path
    uncertainty_artifact_directory: Path
    uncertainty_profile_filename: str = "anchor_delta_gru_deterministic_uncertainty.json"
    # The default preserves the selected deployed five-second GRU. The
    # stateful family is available only when a separately evaluated ONNX graph
    # and deterministic OOF uncertainty profile have both passed promotion.
    model_family: Literal["anchor_delta_gru", "stateful_anchor_delta_gru"] = (
        "anchor_delta_gru"
    )
    # A fresh velocity artifact has no honest residual calibration yet. The
    # default is therefore strict: runtime refuses to start until its matching
    # profile exists. A caller may deliberately opt into this clearly marked,
    # high-variance bootstrap mode for an integration-only smoke test.
    allow_uncalibrated_heuristic_fallback: bool = False


@dataclass(frozen=True, slots=True)
class SelectedVelocityRuntimeComponents:
    """Validated, dependency-injection-ready selected-model components."""

    velocity_predictor: VelocityObservationProducer
    uncertainty_estimator: VelocityUncertaintyEstimator


def load_selected_velocity_runtime_components(
    artifacts: SelectedVelocityRuntimeArtifacts,
) -> SelectedVelocityRuntimeComponents:
    """Load the selected ONNX GRU and only its hash-matched covariance profile."""

    if artifacts.model_family == "anchor_delta_gru":
        velocity_predictor = load_anchor_delta_gru_adapter(
            artifacts.velocity_artifact_directory
        )
        onnx_filename = "anchor_delta_gru.onnx"
        metadata_filename = "anchor_delta_gru.metadata.json"
    else:
        velocity_predictor = load_stateful_anchor_delta_gru_adapter(
            artifacts.velocity_artifact_directory
        )
        onnx_filename = "stateful_anchor_delta_gru.onnx"
        metadata_filename = "stateful_anchor_delta_gru.metadata.json"
    try:
        uncertainty_estimator = load_deterministic_velocity_uncertainty_estimator(
            artifact_directory=artifacts.uncertainty_artifact_directory,
            velocity_artifact_directory=artifacts.velocity_artifact_directory,
            profile_filename=artifacts.uncertainty_profile_filename,
            velocity_onnx_filename=onnx_filename,
            velocity_metadata_filename=metadata_filename,
        )
    except FileNotFoundError:
        if not artifacts.allow_uncalibrated_heuristic_fallback:
            raise
        uncertainty_estimator = HeuristicVelocityUncertaintyEstimator(
            # This deliberately downweights an uncalibrated new speed model.
            # It is for wiring checks only, never a substitute for OOF
            # residual calibration before EKF performance evaluation.
            HeuristicUncertaintyConfig(
                variance_floor_m2ps2=25.0,
                variance_ceiling_m2ps2=100.0,
                reference_acceleration_rms_mps2=2.0,
                reference_angular_velocity_rms_radps=1.0,
                roughness_weight=1.0,
                turn_weight=1.0,
                calibration_weight=1.0,
                quality_weight=1.0,
            )
        )
    # Both loaders validate the same metadata. This explicit check also keeps
    # a clear error at the composition boundary if either implementation changes.
    if (
        not artifacts.allow_uncalibrated_heuristic_fallback
        and uncertainty_estimator.model_id != velocity_predictor.model_id
    ):
        raise ValueError("Selected velocity model and uncertainty profile differ.")
    return SelectedVelocityRuntimeComponents(
        velocity_predictor=velocity_predictor,
        uncertainty_estimator=uncertainty_estimator,
    )


def build_selected_velocity_pre_ekf_pipeline(
    *,
    config: DeterministicPipelineConfig,
    preprocessor: DeterministicImuPreprocessor,
    artifacts: SelectedVelocityRuntimeArtifacts,
) -> DeterministicPreEkfPipeline:
    """Build the pre-EKF stream using only the approved selected artifact pair."""

    components = load_selected_velocity_runtime_components(artifacts)
    return DeterministicPreEkfPipeline(
        config=config,
        preprocessor=preprocessor,
        velocity_predictor=components.velocity_predictor,
        uncertainty_estimator=components.uncertainty_estimator,
    )

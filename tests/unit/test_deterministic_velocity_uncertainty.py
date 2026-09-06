"""Tests for the selected GRU's deterministic uncertainty runtime contract."""

from pathlib import Path

import pytest

from idr_backend.pipeline.selected_velocity import (
    SelectedVelocityRuntimeArtifacts,
    load_selected_velocity_runtime_components,
)
from idr_backend.sensors.quality import VehicleImuQuality
from idr_backend.sensors.types import SensorSource, VehicleImuSample
from idr_backend.sensors.windowing import VelocityModelInputWindow
from idr_backend.adapters.velocity_predictor import VelocityInferenceContext
from idr_backend.uncertainty.deterministic import (
    DeterministicVelocityUncertaintyProfile,
)
from idr_backend.uncertainty.features import build_velocity_uncertainty_features


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"


def _profile() -> DeterministicVelocityUncertaintyProfile:
    """Use a small inspectable profile for monotonicity/safety tests."""

    return DeterministicVelocityUncertaintyProfile(
        model_id="selected-gru",
        horizon_seconds=(5.0, 120.0),
        base_standard_deviation_mps=(2.0, 5.0),
        variance_ceiling_m2ps2=100.0,
        reference_acceleration_std_mps2=1.0,
        reference_angular_velocity_rms_radps=0.2,
        reference_minimum_calibration_confidence=0.8,
        reference_final_quality_score=1.0,
        roughness_std_multiplier=0.5,
        turn_std_multiplier=0.25,
        calibration_std_multiplier=0.5,
        quality_std_multiplier=0.75,
    )


def _window() -> VelocityModelInputWindow:
    """Build one valid 50-sample, selected-GRU input window."""

    samples = tuple(
        VehicleImuSample(
            timestamp_ns=index * 100_000_000,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            linear_acceleration_mps2=(0.2, 0.0, 0.0),
            angular_velocity_radps=(0.0, 0.0, 0.05),
            vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
            calibration_confidence=0.8,
        )
        for index in range(50)
    )
    final_quality = VehicleImuQuality(
        timestamp_ns=samples[-1].timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        flags=frozenset(),
        sample_interval_ns=100_000_000,
        score=0.9,
        is_acceptable=True,
    )
    return VelocityModelInputWindow(
        end_timestamp_ns=samples[-1].timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        sample_period_ns=100_000_000,
        samples=samples,
        final_quality=final_quality,
    )


def test_profile_inflates_for_age_and_weaker_live_evidence() -> None:
    """No causal risk signal may reduce the baseline speed covariance."""

    profile = _profile()
    fresh_variance = profile.variance_m2ps2(
        seconds_since_anchor=5.0,
        linear_acceleration_magnitude_std_mps2=0.1,
        angular_velocity_rms_radps=0.02,
        minimum_calibration_confidence=0.9,
        final_quality_score=1.0,
    )
    degraded_variance = profile.variance_m2ps2(
        seconds_since_anchor=120.0,
        linear_acceleration_magnitude_std_mps2=3.0,
        angular_velocity_rms_radps=1.0,
        minimum_calibration_confidence=0.2,
        final_quality_score=0.2,
    )

    assert fresh_variance == pytest.approx(4.0)
    assert degraded_variance > fresh_variance


def test_selected_onnx_gru_and_profile_publish_one_aligned_pair() -> None:
    """The actual selected artifacts load and agree on the velocity model ID."""

    components = load_selected_velocity_runtime_components(
        SelectedVelocityRuntimeArtifacts(
            velocity_artifact_directory=ARTIFACT_DIRECTORY,
            uncertainty_artifact_directory=ARTIFACT_DIRECTORY,
        )
    )
    window = _window()
    context = VelocityInferenceContext(
        source_id=window.source_id,
        anchor_timestamp_ns=0,
        anchor_speed_mps=10.0,
        integrated_speed_mps=10.5,
        seconds_since_anchor=4.9,
        mean_calibration_confidence=0.8,
        minimum_calibration_confidence=0.8,
    )
    observation = components.velocity_predictor.predict(window=window, context=context)
    features = build_velocity_uncertainty_features(
        observation=observation,
        window=window,
        final_quality=window.final_quality,
        seconds_since_anchor=context.seconds_since_anchor,
    )
    estimate = components.uncertainty_estimator.estimate(
        observation=observation,
        features=features,
    )

    assert observation.model_id == "anchor_delta_gru_onnx_v1"
    assert estimate.model_id == observation.model_id
    assert estimate.velocity_observation_timestamp_ns == observation.timestamp_ns
    assert estimate.is_calibrated
    assert 0.0 < estimate.speed_variance_m2ps2 <= 400.0

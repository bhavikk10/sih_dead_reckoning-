"""Runtime checks for the exported state-carrying ONNX velocity adapter."""

from __future__ import annotations

from math import isfinite
from pathlib import Path

from idr_backend.adapters.stateful_anchor_delta_gru import (
    StatefulAnchorDeltaGruAdapter,
    StatefulAnchorDeltaGruPredictor,
)
from idr_backend.adapters.velocity_predictor import VelocityInferenceContext
from idr_backend.sensors.quality import VehicleImuQuality
from idr_backend.sensors.types import SensorSource, VehicleImuSample, VelocityObservation
from idr_backend.sensors.windowing import VelocityModelInputWindow
from idr_backend.uncertainty.artifacts import (
    load_stateful_velocity_uncertainty_estimator,
)
from idr_backend.uncertainty.features import (
    VelocityUncertaintyFeatures,
    build_velocity_uncertainty_features,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIRECTORY = (
    REPOSITORY_ROOT
    / "artifacts"
    / "anchored_velocity_comparison"
    / "stateful_anchor_delta_gru"
)


def _window(start_step: int) -> VelocityModelInputWindow:
    """Create one accepted 50-sample stream window at the exported 10 Hz rate."""

    samples = tuple(
        VehicleImuSample(
            timestamp_ns=(start_step + step) * 100_000_000,
            source=SensorSource.PHONE,
            source_id="stateful-test-phone",
            linear_acceleration_mps2=(0.1, 0.0, 0.0),
            angular_velocity_radps=(0.0, 0.0, 0.01),
            vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
            calibration_confidence=0.9,
        )
        for step in range(50)
    )
    return VelocityModelInputWindow(
        end_timestamp_ns=samples[-1].timestamp_ns,
        source=SensorSource.PHONE,
        source_id="stateful-test-phone",
        sample_period_ns=100_000_000,
        samples=samples,
        final_quality=VehicleImuQuality(
            timestamp_ns=samples[-1].timestamp_ns,
            source=SensorSource.PHONE,
            source_id="stateful-test-phone",
            flags=frozenset(),
            sample_interval_ns=100_000_000,
            score=1.0,
            is_acceptable=True,
        ),
    )


def _context() -> VelocityInferenceContext:
    return VelocityInferenceContext(
        source_id="stateful-test-phone",
        anchor_timestamp_ns=0,
        anchor_speed_mps=8.0,
        integrated_speed_mps=8.5,
        seconds_since_anchor=4.9,
        mean_calibration_confidence=0.9,
        minimum_calibration_confidence=0.9,
    )


def test_exported_stateful_adapter_carries_hidden_state_across_windows() -> None:
    """The actual ONNX artifact must accept an initial window then one new row."""

    adapter = StatefulAnchorDeltaGruAdapter(
        StatefulAnchorDeltaGruPredictor.from_artifact_directory(ARTIFACT_DIRECTORY)
    )
    assert adapter.model_id == "stateful_anchor_delta_gru_onnx_v1"
    first = adapter.predict(window=_window(0), context=_context())
    second = adapter.predict(window=_window(1), context=_context())

    assert first.model_id == "stateful_anchor_delta_gru_onnx_v1"
    assert first.timestamp_ns == 4_900_000_000
    assert second.timestamp_ns == 5_000_000_000
    assert isfinite(first.speed_mps) and first.speed_mps >= 0.0
    assert isfinite(second.speed_mps) and second.speed_mps >= 0.0


def test_oof_trained_uncertainty_artifact_scales_runtime_features() -> None:
    """The learned branch must consume the same eight-feature artifact contract."""

    estimator = load_stateful_velocity_uncertainty_estimator(
        REPOSITORY_ROOT
        / "artifacts"
        / "anchored_velocity_comparison"
        / "stateful_velocity_uncertainty"
    )
    observation = VelocityObservation(
        timestamp_ns=1,
        source_id="stateful-test-phone",
        window_start_timestamp_ns=0,
        speed_mps=8.0,
        model_id="stateful_anchor_delta_gru_onnx_v1",
    )
    estimate = estimator.estimate(
        observation=observation,
        features=VelocityUncertaintyFeatures(
            timestamp_ns=1,
            source_id="stateful-test-phone",
            model_id="stateful_anchor_delta_gru_onnx_v1",
            linear_acceleration_rms_mps2=0.1,
            linear_acceleration_magnitude_std_mps2=0.01,
            angular_velocity_rms_radps=0.01,
            minimum_calibration_confidence=0.9,
            final_quality_score=1.0,
            window_duration_s=4.9,
            seconds_since_anchor=5.0,
            predicted_speed_mps=8.0,
        ),
    )

    assert estimate.is_calibrated
    assert not estimate.used_heuristic_bound
    assert isfinite(estimate.speed_variance_m2ps2)
    assert estimate.speed_variance_m2ps2 > 0.0


def test_selected_velocity_and_uncertainty_artifacts_publish_one_aligned_pair() -> None:
    """The two selected artifacts must meet at the standard pre-EKF boundary."""

    window = _window(0)
    observation = StatefulAnchorDeltaGruAdapter(
        StatefulAnchorDeltaGruPredictor.from_artifact_directory(ARTIFACT_DIRECTORY)
    ).predict(window=window, context=_context())
    features = build_velocity_uncertainty_features(
        observation=observation,
        window=window,
        final_quality=window.final_quality,
        seconds_since_anchor=4.9,
    )
    estimate = load_stateful_velocity_uncertainty_estimator(
        REPOSITORY_ROOT
        / "artifacts"
        / "anchored_velocity_comparison"
        / "stateful_velocity_uncertainty"
    ).estimate(observation=observation, features=features)

    assert estimate.timestamp_ns == observation.timestamp_ns
    assert estimate.velocity_observation_timestamp_ns == observation.timestamp_ns
    assert estimate.model_id == observation.model_id

"""Tests for the pre-fusion velocity observation and uncertainty boundary."""

from dataclasses import replace

import pytest
import torch

from idr_backend.adapters.velocity_predictor import (
    VelocityInferenceContext,
    VelocityPredictorAdapter,
    VelocityPredictorSpec,
)
from idr_backend.sensors.quality import VehicleImuQuality
from idr_backend.sensors.types import SensorSource, VehicleImuSample
from idr_backend.sensors.windowing import VelocityModelInputWindow
from idr_backend.uncertainty.calibration import fit_variance_scale
from idr_backend.uncertainty.features import (
    UNCERTAINTY_FEATURE_NAMES,
    build_velocity_uncertainty_features,
)
from idr_backend.uncertainty.heuristics import (
    HeuristicUncertaintyConfig,
    heuristic_uncertainty,
)
from idr_backend.uncertainty.inference import LearnedVelocityUncertaintyEstimator
from idr_backend.uncertainty.losses import gaussian_negative_log_likelihood
from idr_backend.uncertainty.model import HeteroscedasticVarianceNetwork


class _FixedPredictor:
    def predict_speed_mps(self, feature_rows: tuple[tuple[float, ...], ...], context: VelocityInferenceContext) -> float:
        assert len(feature_rows) == 3
        return context.integrated_speed_mps + 0.5


def _window() -> VelocityModelInputWindow:
    samples = tuple(
        VehicleImuSample(
            timestamp_ns=index * 100_000_000,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            linear_acceleration_mps2=(1.0 + index, 0.0, 0.0),
            angular_velocity_radps=(0.0, 0.0, 0.1 * index),
            vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
            calibration_confidence=0.8,
        )
        for index in range(3)
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


def _quality(window: VelocityModelInputWindow) -> VehicleImuQuality:
    return VehicleImuQuality(
        timestamp_ns=window.end_timestamp_ns,
        source=window.source,
        source_id=window.source_id,
        flags=frozenset(),
        sample_interval_ns=100_000_000,
        score=0.9,
        is_acceptable=True,
    )


def test_velocity_adapter_and_heuristic_uncertainty_publish_aligned_outputs() -> None:
    """One causal window becomes a speed observation plus a bounded variance."""

    window = _window()
    context = VelocityInferenceContext(
        source_id="phone-primary",
        anchor_timestamp_ns=0,
        anchor_speed_mps=8.0,
        integrated_speed_mps=9.0,
        seconds_since_anchor=0.2,
    )
    observation = VelocityPredictorAdapter(
        spec=VelocityPredictorSpec(
            model_id="selected-model",
            window_size=3,
            sample_period_ns=100_000_000,
        ),
        predictor=_FixedPredictor(),
    ).predict(window=window, context=context)

    features = build_velocity_uncertainty_features(
        observation=observation,
        window=window,
        final_quality=_quality(window),
        seconds_since_anchor=context.seconds_since_anchor,
    )
    estimate = heuristic_uncertainty(
        observation=observation,
        features=features,
        config=HeuristicUncertaintyConfig(
            variance_floor_m2ps2=0.25,
            variance_ceiling_m2ps2=4.0,
            reference_acceleration_rms_mps2=2.0,
            reference_angular_velocity_rms_radps=0.2,
            roughness_weight=1.0,
            turn_weight=1.0,
            calibration_weight=1.0,
            quality_weight=1.0,
        ),
    )

    assert observation.speed_mps == 9.5
    assert estimate.velocity_observation_timestamp_ns == observation.timestamp_ns
    assert 0.25 <= estimate.speed_variance_m2ps2 <= 4.0
    assert not estimate.is_calibrated
    assert estimate.used_heuristic_bound


def test_variance_loss_network_and_held_out_scale_are_positive() -> None:
    """The learned branch never emits invalid covariance values."""

    model = HeteroscedasticVarianceNetwork(
        feature_count=8,
        hidden_size=4,
        variance_floor_m2ps2=0.1,
        variance_ceiling_m2ps2=2.0,
    )
    variance = model(torch.zeros(5, 8))
    loss = gaussian_negative_log_likelihood(torch.ones(5), variance)
    calibration = fit_variance_scale(
        residuals_mps=(1.0, -1.0),
        predicted_variances_m2ps2=(0.5, 0.5),
    )

    assert torch.all(variance >= 0.1)
    assert torch.all(variance <= 2.0)
    assert torch.isfinite(loss)
    assert calibration.scale == pytest.approx(2.0)


def test_learned_uncertainty_clamps_calibrated_variance_positive() -> None:
    """A held-out scale cannot turn a learned output into invalid covariance."""

    window = _window()
    observation = VelocityPredictorAdapter(
        spec=VelocityPredictorSpec(
            model_id="selected-model",
            window_size=3,
            sample_period_ns=100_000_000,
        ),
        predictor=_FixedPredictor(),
    ).predict(
        window=window,
        context=VelocityInferenceContext(
            source_id="phone-primary",
            anchor_timestamp_ns=0,
            anchor_speed_mps=8.0,
            integrated_speed_mps=9.0,
            seconds_since_anchor=0.2,
        ),
    )
    features = build_velocity_uncertainty_features(
        observation=observation,
        window=window,
        final_quality=_quality(window),
        seconds_since_anchor=0.2,
    )
    network = HeteroscedasticVarianceNetwork(
        feature_count=8,
        hidden_size=4,
        variance_floor_m2ps2=0.1,
        variance_ceiling_m2ps2=1.0,
    )
    estimator = LearnedVelocityUncertaintyEstimator(
        network=network,
        calibration=fit_variance_scale(
            residuals_mps=(0.0,),
            predicted_variances_m2ps2=(0.5,),
        ),
        variance_floor_m2ps2=0.1,
        variance_ceiling_m2ps2=2.0,
    )

    estimate = estimator.estimate(observation=observation, features=features)

    assert estimate.is_calibrated
    assert not estimate.used_heuristic_bound
    assert 0.1 <= estimate.speed_variance_m2ps2 <= 2.0


def test_learned_uncertainty_can_exclude_an_untrained_runtime_feature() -> None:
    """Live quality may remain heuristic-only when replay preserved no score."""

    window = _window()
    observation = VelocityPredictorAdapter(
        spec=VelocityPredictorSpec(
            model_id="selected-model",
            window_size=3,
            sample_period_ns=100_000_000,
        ),
        predictor=_FixedPredictor(),
    ).predict(
        window=window,
        context=VelocityInferenceContext(
            source_id="phone-primary",
            anchor_timestamp_ns=0,
            anchor_speed_mps=8.0,
            integrated_speed_mps=9.0,
            seconds_since_anchor=0.2,
        ),
    )
    features = build_velocity_uncertainty_features(
        observation=observation,
        window=window,
        final_quality=_quality(window),
        seconds_since_anchor=0.2,
    )
    learned_names = tuple(
        name for name in UNCERTAINTY_FEATURE_NAMES if name != "final_quality_score"
    )
    estimator = LearnedVelocityUncertaintyEstimator(
        network=HeteroscedasticVarianceNetwork(
            feature_count=len(learned_names),
            hidden_size=4,
            variance_floor_m2ps2=0.1,
            variance_ceiling_m2ps2=2.0,
        ),
        calibration=fit_variance_scale(
            residuals_mps=(0.0,),
            predicted_variances_m2ps2=(0.5,),
        ),
        variance_floor_m2ps2=0.1,
        variance_ceiling_m2ps2=2.0,
        feature_mean=(0.0,) * len(learned_names),
        feature_scale=(1.0,) * len(learned_names),
        feature_names=learned_names,
    )

    original = estimator.estimate(observation=observation, features=features)
    different_live_quality = estimator.estimate(
        observation=observation,
        features=replace(features, final_quality_score=0.1),
    )

    assert original.speed_variance_m2ps2 == pytest.approx(
        different_live_quality.speed_variance_m2ps2
    )

"""End-to-end tests for the deterministic pipeline before EKF fusion begins."""

import pytest

from idr_backend.adapters.velocity_predictor import (
    VelocityInferenceContext,
    VelocityPredictorAdapter,
    VelocityPredictorSpec,
)
from idr_backend.pipeline.orchestrator import (
    DeterministicPipelineConfig,
    DeterministicPreEkfPipeline,
)
from idr_backend.sensors.calibration_evidence import CalibrationEvidenceLimits
from idr_backend.sensors.gnss import GnssQualityLimits
from idr_backend.sensors.preprocessing import (
    DeterministicImuPreprocessor,
    DeterministicPreprocessorConfig,
    PreprocessingDisposition,
)
from idr_backend.sensors.quality import VehicleImuQualityLimits
from idr_backend.sensors.types import (
    CoordinateFrame,
    GnssFix,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
)
from idr_backend.uncertainty.inference import HeuristicVelocityUncertaintyEstimator
from idr_backend.uncertainty.heuristics import HeuristicUncertaintyConfig


class _BaselinePlusQuarterPredictor:
    """Small deterministic stand-in for an externally supplied model artifact."""

    def __init__(self) -> None:
        self.contexts: list[VelocityInferenceContext] = []

    def predict_speed_mps(
        self,
        feature_rows: tuple[tuple[float, float, float, float, float, float], ...],
        context: VelocityInferenceContext,
    ) -> float:
        assert len(feature_rows) == 2
        self.contexts.append(context)
        return context.integrated_speed_mps + 0.25


def _pipeline(*, maximum_anchor_age_ns: int) -> tuple[
    DeterministicPreEkfPipeline, _BaselinePlusQuarterPredictor
]:
    """Create a two-sample test pipeline with an identity mounting event."""

    preprocessor = DeterministicImuPreprocessor(
        DeterministicPreprocessorConfig(
            max_imu_skew_ns=1_000_000,
            max_pending_imu_samples=8,
            accelerometer_correction_gain_per_s=0.0,
            acceleration_trust_tolerance_mps2=0.2,
            minimum_calibration_evidence_count=1,
            minimum_calibration_evidence_confidence=0.1,
            maximum_calibration_disagreement_rad=0.5,
            remount_evidence_count=2,
            minimum_calibration_confidence_for_output=0.1,
            velocity_model_sample_period_ns=100_000_000,
            velocity_model_window_size=2,
            gnss_quality_limits=GnssQualityLimits(
                max_gap_ns=2_000_000_000,
                max_horizontal_accuracy_m=10.0,
                max_speed_accuracy_mps=1.0,
                min_course_speed_mps=3.0,
                max_course_accuracy_rad=0.5,
            ),
            calibration_evidence_limits=CalibrationEvidenceLimits(
                max_imu_gnss_skew_ns=1_000_000,
                min_gnss_interval_ns=500_000_000,
                max_gnss_interval_ns=2_000_000_000,
                min_gnss_longitudinal_acceleration_mps2=0.5,
                min_sensor_linear_acceleration_mps2=0.5,
                max_course_rate_radps=0.2,
            ),
            vehicle_imu_quality_limits=VehicleImuQualityLimits(
                max_gap_ns=1_000_000_000,
                max_linear_acceleration_mps2=20.0,
                max_angular_velocity_radps=10.0,
                minimum_calibration_confidence=0.1,
            ),
        )
    )
    predictor = _BaselinePlusQuarterPredictor()
    pipeline = DeterministicPreEkfPipeline(
        config=DeterministicPipelineConfig(
            maximum_gnss_anchor_age_ns=maximum_anchor_age_ns,
        ),
        preprocessor=preprocessor,
        velocity_predictor=VelocityPredictorAdapter(
            spec=VelocityPredictorSpec(
                model_id="test-selected-model",
                window_size=2,
                sample_period_ns=100_000_000,
            ),
            predictor=predictor,
        ),
        uncertainty_estimator=HeuristicVelocityUncertaintyEstimator(
            HeuristicUncertaintyConfig(
                variance_floor_m2ps2=0.1,
                variance_ceiling_m2ps2=4.0,
                reference_acceleration_rms_mps2=2.0,
                reference_angular_velocity_rms_radps=1.0,
                roughness_weight=1.0,
                turn_weight=1.0,
                calibration_weight=1.0,
                quality_weight=1.0,
            )
        ),
    )
    return pipeline, predictor


def _fix(timestamp_ns: int, speed_mps: float) -> GnssFix:
    """Create a GNSS observation accurate enough to become an anchor."""

    return GnssFix(
        timestamp_ns=timestamp_ns,
        receiver_id="phone-primary",
        latitude_deg=12.0,
        longitude_deg=77.0,
        altitude_m=None,
        horizontal_accuracy_m=3.0,
        vertical_accuracy_m=None,
        speed_mps=speed_mps,
        speed_accuracy_mps=0.2,
        course_over_ground_rad=0.0,
        course_accuracy_rad=0.05,
    )


def _raw(
    timestamp_ns: int,
    kind: SensorKind,
    value: tuple[float, float, float],
) -> RawSensorSample:
    """Create one SI sensor callback in the level-phone test orientation."""

    return RawSensorSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        kind=kind,
        value=value,
        unit=(
            MeasurementUnit.METERS_PER_SECOND_SQUARED
            if kind is SensorKind.ACCELEROMETER
            else MeasurementUnit.RADIANS_PER_SECOND
        ),
        frame=CoordinateFrame.SENSOR,
    )


def _push_pair(
    pipeline: DeterministicPreEkfPipeline,
    *,
    timestamp_ns: int,
    forward_acceleration_mps2: float,
) -> tuple:
    """Push one synchronized acceleration/gyro pair and return its result."""

    assert pipeline.push_raw_sample(
        _raw(
            timestamp_ns,
            SensorKind.ACCELEROMETER,
            (forward_acceleration_mps2, 0.0, 9.80665),
        )
    ) == ()
    return pipeline.push_raw_sample(
        _raw(timestamp_ns, SensorKind.GYROSCOPE, (0.0, 0.0, 0.0))
    )


def _warm_and_calibrate(pipeline: DeterministicPreEkfPipeline) -> None:
    """Create gravity-only attitude state then one straight GNSS calibration event."""

    pipeline.push_gnss_fix(_fix(1_000_000_000, 10.0))
    warmup = _push_pair(
        pipeline,
        timestamp_ns=1_900_000_000,
        forward_acceleration_mps2=0.0,
    )
    assert warmup[0].preprocessing.disposition is PreprocessingDisposition.CALIBRATION_WARMING_UP
    pipeline.push_gnss_fix(_fix(2_000_000_000, 12.0))


def test_pipeline_emits_aligned_velocity_and_heuristic_uncertainty() -> None:
    """The complete deterministic path reaches pre-EKF measurements causally."""

    pipeline, predictor = _pipeline(maximum_anchor_age_ns=1_000_000_000)
    _warm_and_calibrate(pipeline)

    first = _push_pair(
        pipeline,
        timestamp_ns=2_000_000_000,
        forward_acceleration_mps2=1.0,
    )
    assert first[0].preprocessing.disposition is PreprocessingDisposition.ACCEPTED
    assert first[0].velocity_observations == ()

    second = _push_pair(
        pipeline,
        timestamp_ns=2_100_000_000,
        forward_acceleration_mps2=1.0,
    )
    result = second[0]

    assert len(result.velocity_observations) == 1
    assert len(result.uncertainty_estimates) == 1
    observation = result.velocity_observations[0]
    uncertainty = result.uncertainty_estimates[0]
    assert observation.speed_mps == pytest.approx(12.35)
    assert predictor.contexts[0].integrated_speed_mps == pytest.approx(12.1)
    assert predictor.contexts[0].mean_calibration_confidence == pytest.approx(1.0)
    assert predictor.contexts[0].minimum_calibration_confidence == pytest.approx(1.0)
    assert uncertainty.timestamp_ns == observation.timestamp_ns
    assert uncertainty.velocity_observation_timestamp_ns == observation.timestamp_ns
    assert uncertainty.speed_variance_m2ps2 > 0.0


def test_pipeline_withholds_model_output_after_supported_blackout_age() -> None:
    """An old GNSS anchor suppresses model output instead of guessing context."""

    pipeline, predictor = _pipeline(maximum_anchor_age_ns=50_000_000)
    _warm_and_calibrate(pipeline)
    _push_pair(
        pipeline,
        timestamp_ns=2_000_000_000,
        forward_acceleration_mps2=1.0,
    )
    result = _push_pair(
        pipeline,
        timestamp_ns=2_100_000_000,
        forward_acceleration_mps2=1.0,
    )[0]

    assert result.velocity_observations == ()
    assert result.uncertainty_estimates == ()
    assert predictor.contexts == []

"""Integration tests for the EKF consumer of completed pre-EKF outputs."""

from dataclasses import dataclass, replace
from math import sqrt

import pytest

from idr_backend.fusion.constraints import NonHolonomicConstraintConfig
from idr_backend.fusion.covariance import ImuNoiseDensity
from idr_backend.fusion.modes import NavigationModeConfig
from idr_backend.fusion.measurements import MeasurementDisposition, MeasurementKind
from idr_backend.fusion.observations import FusionMeasurementConfig
from idr_backend.fusion.propagation import (
    PropagationConfig,
    PropagationDisposition,
    PropagationResult,
)
from idr_backend.fusion.state import ErrorStateEkfState
import idr_backend.pipeline.fusion as fusion_pipeline_module
from idr_backend.pipeline.fusion import FusionPipelineConfig, NavigationFusionPipeline
from idr_backend.pipeline.runtime import NavigationRuntimeConfig
from idr_backend.sensors.gnss import GnssFixQuality
from idr_backend.sensors.quality import VehicleImuQuality
from idr_backend.sensors.types import (
    GnssFix,
    SensorSource,
    UncertaintyEstimate,
    VehicleImuSample,
    VelocityObservation,
)


@dataclass(frozen=True, slots=True)
class _PreprocessingResult:
    """Only the attributes consumed by the fusion boundary are represented."""

    vehicle_imu_sample: VehicleImuSample
    quality: VehicleImuQuality


@dataclass(frozen=True, slots=True)
class _PreEkfResult:
    """A completed deterministic result supplied by the upstream pipeline."""

    preprocessing: _PreprocessingResult
    velocity_observations: tuple[VelocityObservation, ...]
    uncertainty_estimates: tuple[UncertaintyEstimate, ...]


class _CompletedPreEkfPipeline:
    """Test double: fusion sees only the established pre-EKF public boundary."""

    def __init__(self, results: tuple[_PreEkfResult, ...]) -> None:
        self._results = list(results)

    def push_gnss_fix(self, fix: GnssFix) -> GnssFixQuality:
        return GnssFixQuality(
            timestamp_ns=fix.timestamp_ns,
            receiver_id=fix.receiver_id,
            flags=frozenset(),
            sample_interval_ns=None,
            position_is_acceptable=True,
            speed_is_acceptable=True,
            course_is_acceptable=True,
        )

    def push_raw_sample(self, _raw_sample: object) -> tuple[_PreEkfResult, ...]:
        return (self._results.pop(0),)


def _vehicle_sample(timestamp_ns: int) -> VehicleImuSample:
    """Point vehicle forward toward ENU north, aligned with the GNSS course."""

    return VehicleImuSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id="phone-primary",
        linear_acceleration_mps2=(0.0, 0.0, 0.0),
        angular_velocity_radps=(0.0, 0.0, 0.0),
        vehicle_to_navigation_wxyz=(sqrt(0.5), 0.0, 0.0, sqrt(0.5)),
        calibration_confidence=1.0,
    )


def _pre_ekf_result(
    timestamp_ns: int,
    *,
    velocity_speed_mps: float | None = None,
) -> _PreEkfResult:
    """Create an accepted vehicle sample with an optional paired model output."""

    sample = _vehicle_sample(timestamp_ns)
    quality = VehicleImuQuality(
        timestamp_ns=timestamp_ns,
        source=sample.source,
        source_id=sample.source_id,
        flags=frozenset(),
        sample_interval_ns=100_000_000,
        score=1.0,
        is_acceptable=True,
    )
    observations: tuple[VelocityObservation, ...] = ()
    uncertainties: tuple[UncertaintyEstimate, ...] = ()
    if velocity_speed_mps is not None:
        observation = VelocityObservation(
            timestamp_ns=timestamp_ns,
            source_id=sample.source_id,
            window_start_timestamp_ns=timestamp_ns - 100_000_000,
            speed_mps=velocity_speed_mps,
            model_id="selected-gru",
        )
        observations = (observation,)
        uncertainties = (
            UncertaintyEstimate(
                timestamp_ns=timestamp_ns,
                velocity_observation_timestamp_ns=timestamp_ns,
                model_id="selected-gru",
                speed_variance_m2ps2=0.25,
                is_calibrated=True,
                used_heuristic_bound=False,
            ),
        )
    return _PreEkfResult(
        preprocessing=_PreprocessingResult(sample, quality),
        velocity_observations=observations,
        uncertainty_estimates=uncertainties,
    )


def _fix(timestamp_ns: int, latitude_deg: float = 12.0) -> GnssFix:
    """Create a fully usable 4 m/s northbound receiver observation."""

    return GnssFix(
        timestamp_ns=timestamp_ns,
        receiver_id="phone-primary",
        latitude_deg=latitude_deg,
        longitude_deg=77.0,
        altitude_m=None,
        horizontal_accuracy_m=3.0,
        vertical_accuracy_m=None,
        speed_mps=4.0,
        speed_accuracy_mps=0.2,
        course_over_ground_rad=0.0,
        course_accuracy_rad=0.05,
    )


def _config() -> FusionPipelineConfig:
    """Use deliberately permissive gates so the wiring, not tuning, is tested."""

    return FusionPipelineConfig(
        propagation=PropagationConfig(
            noise=ImuNoiseDensity(
                accelerometer_mps2_per_sqrt_hz=0.05,
                gyroscope_radps_per_sqrt_hz=0.01,
                accelerometer_bias_rw_mps2_per_sqrt_s=0.001,
                gyroscope_bias_rw_radps_per_sqrt_s=0.0001,
            ),
            maximum_delta_time_s=0.5,
        ),
        measurements=FusionMeasurementConfig(
            maximum_gnss_association_age_ns=250_000_000,
            gnss_position_nis_gate=100.0,
            gnss_velocity_nis_gate=100.0,
            velocity_model_nis_gate=100.0,
        ),
        non_holonomic_constraint=NonHolonomicConstraintConfig(
            minimum_calibration_confidence=0.8,
            soft_yaw_rate_radps=0.2,
            maximum_yaw_rate_radps=1.0,
            lateral_velocity_std_mps=0.2,
            vertical_velocity_std_mps=0.2,
            nis_gate=100.0,
        ),
        navigation_mode=NavigationModeConfig(
            maximum_accepted_gnss_silence_s=5.0,
            accepted_gnss_updates_for_recovery=2,
        ),
        runtime=NavigationRuntimeConfig(
            maximum_pending_events=16,
            cycle_latency_budget_ms=1_000.0,
            late_cycles_before_degraded=3,
            trace_history_capacity=16,
        ),
        initial_error_std=(10.0,) * 6 + (0.5,) * 3 + (0.1,) * 6,
    )


def test_fusion_initializes_then_uses_speed_nhc_and_gnss_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The completed velocity variance reaches a frame-correct EKF update."""

    def _propagate_without_native_matrix_exponential(
        prior: ErrorStateEkfState,
        sample: VehicleImuSample,
        _config: PropagationConfig,
    ) -> PropagationResult:
        """Isolate pipeline wiring from this host's crashing SciPy expm binary.

        Covariance's Van-Loan implementation is exercised in its own numerical
        tests.  On this host SciPy aborts the entire separate pytest process
        inside ``expm`` before Python can report an assertion, so this test
        advances a timestamp-preserving identity state only to test the public
        cross-folder orchestration contract.
        """

        return PropagationResult(
            disposition=PropagationDisposition.PROPAGATED,
            state=ErrorStateEkfState(
                nominal=replace(prior.nominal, timestamp_ns=sample.timestamp_ns),
                covariance=prior.covariance,
            ),
            diagnostics=None,
        )

    monkeypatch.setattr(
        fusion_pipeline_module,
        "propagate_ekf",
        _propagate_without_native_matrix_exponential,
    )

    upstream = _CompletedPreEkfPipeline(
        (
            _pre_ekf_result(1_000_000_000),
            _pre_ekf_result(1_100_000_000, velocity_speed_mps=5.0),
            _pre_ekf_result(1_200_000_000),
        )
    )
    pipeline = NavigationFusionPipeline(pre_ekf_pipeline=upstream, config=_config())

    pipeline.push_gnss_fix(_fix(1_000_000_000))
    initialized = pipeline.push_raw_sample(object())[0]
    assert initialized.propagation_disposition is PropagationDisposition.INITIALISED
    assert initialized.navigation_estimate is not None
    assert initialized.navigation_estimate.velocity_enu_mps[1] == pytest.approx(4.0)

    speed_fused = pipeline.push_raw_sample(object())[0]
    assert speed_fused.propagation_disposition is PropagationDisposition.PROPAGATED
    assert {trace.kind.value for trace in speed_fused.measurement_traces} == {
        "velocity_model",
        "non_holonomic_constraint",
    }
    assert speed_fused.navigation_estimate is not None
    assert speed_fused.navigation_estimate.velocity_enu_mps[1] > 4.0

    pipeline.push_gnss_fix(_fix(1_200_000_000, latitude_deg=12.00001))
    gnss_fused = pipeline.push_raw_sample(object())[0]
    assert {trace.kind.value for trace in gnss_fused.measurement_traces} == {
        "gnss_position",
        "gnss_velocity",
        "non_holonomic_constraint",
    }
    assert gnss_fused.navigation_estimate is not None
    assert gnss_fused.navigation_estimate.mode.value == "gnss_aided"


def test_fusion_reinitializes_only_after_consistent_gnss_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long outage needs two plausible rejected fixes before recentering.

    This models the difficult recovery case: the filter has drifted so far
    that returning GNSS is rejected by its ordinary NIS gate.  One fix may be
    multipath, so it must not reset the filter.  Two nearby quality-accepted
    fixes deliberately rebuild the state; a further normal update is needed
    before the UI leaves ``RECOVERY`` for ``GNSS_AIDED``.
    """

    def _propagate_without_native_matrix_exponential(
        prior: ErrorStateEkfState,
        sample: VehicleImuSample,
        _config: PropagationConfig,
    ) -> PropagationResult:
        return PropagationResult(
            disposition=PropagationDisposition.PROPAGATED,
            state=ErrorStateEkfState(
                nominal=replace(prior.nominal, timestamp_ns=sample.timestamp_ns),
                covariance=prior.covariance,
            ),
            diagnostics=None,
        )

    monkeypatch.setattr(
        fusion_pipeline_module,
        "propagate_ekf",
        _propagate_without_native_matrix_exponential,
    )

    base_config = _config()
    recovery_config = replace(
        base_config,
        measurements=replace(
            base_config.measurements,
            # Reject the roughly 111 m position jump through the ordinary
            # update, allowing the separate guarded recovery policy to act.
            gnss_position_nis_gate=0.01,
            recovery_reinitialization_silence_ns=200_000_000,
            recovery_required_consecutive_fixes=2,
            recovery_maximum_interfix_distance_m=80.0,
        ),
        navigation_mode=NavigationModeConfig(
            maximum_accepted_gnss_silence_s=0.2,
            accepted_gnss_updates_for_recovery=2,
        ),
    )
    upstream = _CompletedPreEkfPipeline(
        tuple(_pre_ekf_result(timestamp_ns) for timestamp_ns in (
            1_000_000_000,
            1_100_000_000,
            1_300_000_000,
            1_400_000_000,
            1_500_000_000,
            1_600_000_000,
        ))
    )
    pipeline = NavigationFusionPipeline(
        pre_ekf_pipeline=upstream,
        config=recovery_config,
    )

    pipeline.push_gnss_fix(_fix(1_000_000_000))
    assert (
        pipeline.push_raw_sample(object())[0].propagation_disposition
        is PropagationDisposition.INITIALISED
    )
    pipeline.push_raw_sample(object())  # 0.1 s: normal GNSS-aided operation.
    dead_reckoning = pipeline.push_raw_sample(object())[0]  # 0.3 s outage.
    assert dead_reckoning.navigation_estimate is not None
    assert dead_reckoning.navigation_estimate.mode.value == "dead_reckoning"

    returned_fix = _fix(1_400_000_000, latitude_deg=12.001)
    pipeline.push_gnss_fix(returned_fix)
    first_return = pipeline.push_raw_sample(object())[0]
    assert first_return.propagation_disposition is PropagationDisposition.PROPAGATED
    assert first_return.navigation_estimate is not None
    assert first_return.navigation_estimate.mode.value == "dead_reckoning"
    assert first_return.measurement_traces[0].kind is MeasurementKind.GNSS_POSITION
    assert (
        first_return.measurement_traces[0].disposition
        is MeasurementDisposition.INNOVATION_REJECTED
    )

    # The matching second receiver fix is the deliberate, guarded reset.
    pipeline.push_gnss_fix(_fix(1_500_000_000, latitude_deg=12.001))
    recovery = pipeline.push_raw_sample(object())[0]
    assert recovery.propagation_disposition is PropagationDisposition.INITIALISED
    assert recovery.navigation_estimate is not None
    assert recovery.navigation_estimate.mode.value == "recovery"
    assert [trace.disposition for trace in recovery.measurement_traces[:2]] == [
        MeasurementDisposition.INNOVATION_REJECTED,
        MeasurementDisposition.ACCEPTED,
    ]

    # A normal, zero-residual GNSS update provides the second accepted fix
    # required to display full GNSS-aided navigation again.
    pipeline.push_gnss_fix(_fix(1_600_000_000, latitude_deg=12.001))
    reacquired = pipeline.push_raw_sample(object())[0]
    assert reacquired.navigation_estimate is not None
    assert reacquired.navigation_estimate.mode.value == "gnss_aided"

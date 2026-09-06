"""Causal deterministic orchestration up to, but not including, EKF fusion.

This module connects the sensor pipeline to the separately supplied velocity
predictor and uncertainty engine. It deliberately stops at aligned velocity and
variance observations; later EKF code owns measurement acceptance and fusion.
"""

import logging
from dataclasses import dataclass
from math import isfinite

from idr_backend.adapters.velocity_predictor import (
    VelocityInferenceContext,
    VelocityObservationProducer,
)
from idr_backend.sensors.gnss import GnssFixQuality
from idr_backend.sensors.preprocessing import (
    DeterministicImuPreprocessor,
    PreprocessedImuResult,
)
from idr_backend.sensors.types import (
    GnssFix,
    RawSensorSample,
    UncertaintyEstimate,
    VelocityObservation,
)
from idr_backend.sensors.windowing import VelocityModelInputWindow
from idr_backend.uncertainty.features import build_velocity_uncertainty_features
from idr_backend.uncertainty.protocol import VelocityUncertaintyEstimator


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeterministicPipelineConfig:
    """Explicit policy for GNSS-anchored, pre-EKF velocity inference."""

    # The selected velocity artifact is trained for bounded GNSS blackouts.
    # Beyond this age, omit a model output instead of advertising unsupported
    # extrapolation as a prediction fit for later fusion.
    maximum_gnss_anchor_age_ns: int


@dataclass(frozen=True, slots=True)
class PreEkfPipelineResult:
    """One preprocessing decision and any aligned pre-EKF model outputs."""

    preprocessing: PreprocessedImuResult
    velocity_observations: tuple[VelocityObservation, ...]
    uncertainty_estimates: tuple[UncertaintyEstimate, ...]

    def __post_init__(self) -> None:
        """Enforce a one-to-one uncertainty attachment for every prediction."""

        if len(self.velocity_observations) != len(self.uncertainty_estimates):
            raise ValueError(
                "Every velocity observation must have exactly one uncertainty estimate."
            )
        for observation, estimate in zip(
            self.velocity_observations,
            self.uncertainty_estimates,
            strict=True,
        ):
            if (
                estimate.timestamp_ns != observation.timestamp_ns
                or estimate.velocity_observation_timestamp_ns
                != observation.timestamp_ns
                or estimate.model_id != observation.model_id
            ):
                raise ValueError(
                    "Uncertainty estimate must describe its paired velocity observation."
                )


@dataclass(frozen=True, slots=True)
class _GnssSpeedAnchor:
    """Last trusted observed speed; private because it is causal runtime state."""

    timestamp_ns: int
    speed_mps: float


class _ForwardAccelerationIntegrator:
    """Integrate forward acceleration between velocity-model windows safely."""

    def __init__(self) -> None:
        self._last_timestamp_ns: int | None = None
        self._last_forward_acceleration_mps2: float | None = None
        self._speed_mps: float | None = None

    def reset(self) -> None:
        """Forget integration history when an anchor or IMU sequence changes."""

        self._last_timestamp_ns = None
        self._last_forward_acceleration_mps2 = None
        self._speed_mps = None

    def speed_at_window_end(
        self,
        *,
        window: VelocityModelInputWindow,
        anchor: _GnssSpeedAnchor,
    ) -> float:
        """Return the causal trapezoidal baseline at a window's end timestamp."""

        if anchor.timestamp_ns > window.end_timestamp_ns:
            raise ValueError("GNSS anchor cannot be newer than a model window.")

        if self._last_timestamp_ns is None:
            self._seed_from_window(window=window, anchor=anchor)
        else:
            self._advance_from_new_window_samples(window=window, anchor=anchor)

        if self._speed_mps is None:
            raise RuntimeError("Velocity integrator did not produce a speed.")
        return self._speed_mps

    def _seed_from_window(
        self,
        *,
        window: VelocityModelInputWindow,
        anchor: _GnssSpeedAnchor,
    ) -> None:
        """Start at the earliest clean data available after a GNSS anchor."""

        speed_mps = anchor.speed_mps
        previous = window.samples[0]
        for current in window.samples[1:]:
            speed_mps = _trapezoidal_speed_step(
                speed_mps=speed_mps,
                previous_timestamp_ns=previous.timestamp_ns,
                previous_acceleration_mps2=previous.linear_acceleration_mps2[0],
                current_timestamp_ns=current.timestamp_ns,
                current_acceleration_mps2=current.linear_acceleration_mps2[0],
                expected_period_ns=window.sample_period_ns,
            )
            previous = current

        self._last_timestamp_ns = previous.timestamp_ns
        self._last_forward_acceleration_mps2 = previous.linear_acceleration_mps2[0]
        self._speed_mps = speed_mps

    def _advance_from_new_window_samples(
        self,
        *,
        window: VelocityModelInputWindow,
        anchor: _GnssSpeedAnchor,
    ) -> None:
        """Advance only across unseen contiguous samples in a sliding window."""

        if (
            self._last_timestamp_ns is None
            or self._last_forward_acceleration_mps2 is None
            or self._speed_mps is None
        ):
            raise RuntimeError("Velocity integrator state is incomplete.")

        new_samples = tuple(
            sample
            for sample in window.samples
            if sample.timestamp_ns > self._last_timestamp_ns
        )
        if not new_samples:
            raise ValueError("Velocity windows must advance strictly in time.")

        if new_samples[0].timestamp_ns - self._last_timestamp_ns != window.sample_period_ns:
            # Preprocessing intentionally cleared this discontinuity. Restart
            # from the last trusted GNSS anchor rather than bridging the gap.
            self.reset()
            self._seed_from_window(window=window, anchor=anchor)
            return

        speed_mps = self._speed_mps
        previous_timestamp_ns = self._last_timestamp_ns
        previous_acceleration_mps2 = self._last_forward_acceleration_mps2
        for current in new_samples:
            speed_mps = _trapezoidal_speed_step(
                speed_mps=speed_mps,
                previous_timestamp_ns=previous_timestamp_ns,
                previous_acceleration_mps2=previous_acceleration_mps2,
                current_timestamp_ns=current.timestamp_ns,
                current_acceleration_mps2=current.linear_acceleration_mps2[0],
                expected_period_ns=window.sample_period_ns,
            )
            previous_timestamp_ns = current.timestamp_ns
            previous_acceleration_mps2 = current.linear_acceleration_mps2[0]

        self._last_timestamp_ns = previous_timestamp_ns
        self._last_forward_acceleration_mps2 = previous_acceleration_mps2
        self._speed_mps = speed_mps


def _trapezoidal_speed_step(
    *,
    speed_mps: float,
    previous_timestamp_ns: int,
    previous_acceleration_mps2: float,
    current_timestamp_ns: int,
    current_acceleration_mps2: float,
    expected_period_ns: int,
) -> float:
    """Integrate one contiguous forward-acceleration interval safely."""

    if current_timestamp_ns - previous_timestamp_ns != expected_period_ns:
        raise ValueError("Velocity integration requires contiguous model samples.")
    if not all(
        isfinite(value)
        for value in (
            speed_mps,
            previous_acceleration_mps2,
            current_acceleration_mps2,
        )
    ):
        raise ValueError("Velocity integration values must be finite.")

    delta_time_s = expected_period_ns * 1e-9
    return max(
        0.0,
        speed_mps
        + 0.5
        * (previous_acceleration_mps2 + current_acceleration_mps2)
        * delta_time_s,
    )


class DeterministicPreEkfPipeline:
    """Run raw IMU through deterministic stages, velocity, and uncertainty.

    Callers submit chronological GNSS fixes through :meth:`push_gnss_fix` and
    raw accelerometer/gyroscope callbacks through :meth:`push_raw_sample`.
    There is no asynchronous queue or EKF state in this class.
    """

    def __init__(
        self,
        *,
        config: DeterministicPipelineConfig,
        preprocessor: DeterministicImuPreprocessor,
        velocity_predictor: VelocityObservationProducer,
        uncertainty_estimator: VelocityUncertaintyEstimator,
    ) -> None:
        """Bind one chronological preprocessing stream to selected artifacts."""

        if config.maximum_gnss_anchor_age_ns <= 0:
            raise ValueError("maximum_gnss_anchor_age_ns must be positive.")

        self._config = config
        self._preprocessor = preprocessor
        self._velocity_predictor = velocity_predictor
        self._uncertainty_estimator = uncertainty_estimator
        self._gnss_speed_anchor: _GnssSpeedAnchor | None = None
        self._integrator = _ForwardAccelerationIntegrator()

    def push_gnss_fix(self, fix: GnssFix) -> GnssFixQuality:
        """Forward GNSS to calibration and refresh a trusted speed anchor."""

        quality = self._preprocessor.push_gnss_fix(fix)
        if quality.speed_is_acceptable:
            if fix.speed_mps is None:
                raise RuntimeError("Accepted GNSS speed unexpectedly missing.")
            self._gnss_speed_anchor = _GnssSpeedAnchor(
                timestamp_ns=fix.timestamp_ns,
                speed_mps=fix.speed_mps,
            )
            self._integrator.reset()
        return quality

    def push_raw_sample(
        self,
        raw_sample: RawSensorSample,
    ) -> tuple[PreEkfPipelineResult, ...]:
        """Process one raw IMU callback and emit its causal model outputs."""

        preprocessing_results = self._preprocessor.push_raw_sample(raw_sample)
        return tuple(
            self._outputs_for_preprocessing_result(result)
            for result in preprocessing_results
        )

    def _outputs_for_preprocessing_result(
        self,
        result: PreprocessedImuResult,
    ) -> PreEkfPipelineResult:
        """Run each completed, quality-gated window through both model boundaries."""

        observations: list[VelocityObservation] = []
        estimates: list[UncertaintyEstimate] = []
        for window in result.velocity_windows:
            output = self._predict_window(window)
            if output is None:
                continue
            observation, estimate = output
            observations.append(observation)
            estimates.append(estimate)

        return PreEkfPipelineResult(
            preprocessing=result,
            velocity_observations=tuple(observations),
            uncertainty_estimates=tuple(estimates),
        )

    def _predict_window(
        self,
        window: VelocityModelInputWindow,
    ) -> tuple[VelocityObservation, UncertaintyEstimate] | None:
        """Predict only when recent trusted GNSS context makes it valid."""

        anchor = self._gnss_speed_anchor
        if anchor is None or anchor.timestamp_ns > window.end_timestamp_ns:
            return None

        anchor_age_ns = window.end_timestamp_ns - anchor.timestamp_ns
        if anchor_age_ns > self._config.maximum_gnss_anchor_age_ns:
            self._integrator.reset()
            return None

        integrated_speed_mps = self._integrator.speed_at_window_end(
            window=window,
            anchor=anchor,
        )
        context = VelocityInferenceContext(
            source_id=window.source_id,
            anchor_timestamp_ns=anchor.timestamp_ns,
            anchor_speed_mps=anchor.speed_mps,
            integrated_speed_mps=integrated_speed_mps,
            seconds_since_anchor=anchor_age_ns * 1e-9,
            mean_calibration_confidence=(
                sum(
                    sample.calibration_confidence
                    for sample in window.samples
                )
                / len(window.samples)
            ),
            minimum_calibration_confidence=min(
                sample.calibration_confidence
                for sample in window.samples
            ),
        )
        observation = self._velocity_predictor.predict(
            window=window,
            context=context,
        )
        features = build_velocity_uncertainty_features(
            observation=observation,
            window=window,
            final_quality=window.final_quality,
            seconds_since_anchor=context.seconds_since_anchor,
        )
        estimate = self._uncertainty_estimator.estimate(
            observation=observation,
            features=features,
        )
        # Deliberately an observability boundary, not an EKF measurement call.
        # It records only output diagnostics; raw IMU values and location stay
        # out of standard application logs.
        LOGGER.info(
            "pre_ekf_velocity_observation model_id=%s timestamp_ns=%s "
            "speed_mps=%.6f variance_m2ps2=%.6f heuristic_uncertainty=%s",
            observation.model_id,
            observation.timestamp_ns,
            observation.speed_mps,
            estimate.speed_variance_m2ps2,
            estimate.used_heuristic_bound,
        )
        return observation, estimate

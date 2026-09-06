"""Causal assembly of deterministic preprocessing and the error-state EKF.

This is deliberately a serial, first-pass integration boundary.  GNSS is
applied to the first later IMU state only when it is recent enough; arbitrary
out-of-sequence replay is a separate future capability, not something silently
approximated in the EKF core.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite, sin, cos

import numpy as np

from ..fusion.constraints import (
    NonHolonomicConstraintConfig,
    build_non_holonomic_measurement,
)
from ..fusion.measurements import (
    MeasurementDisposition,
    MeasurementKind,
    MeasurementUpdateTrace,
    apply_linearised_measurement,
)
from ..fusion.modes import (
    NavigationModeConfig,
    NavigationModeState,
    advance_navigation_mode,
)
from ..fusion.observations import (
    FusionMeasurementConfig,
    LocalEnuReference,
    build_gnss_position_measurement,
    build_gnss_velocity_measurement,
    build_velocity_model_measurement,
)
from ..fusion.propagation import (
    PropagationConfig,
    PropagationDisposition,
    propagate_ekf,
)
from ..fusion.state import ERROR_STATE_DIM, ErrorStateEkfState, initialise_filter_state
from ..sensors.gnss import GnssFixQuality
from ..sensors.types import GnssFix, NavigationEstimate, NavigationMode, RawSensorSample
from .orchestrator import DeterministicPreEkfPipeline, PreEkfPipelineResult
from .runtime import (
    CycleOutcome,
    NavigationRuntime,
    NavigationRuntimeConfig,
    RuntimeSnapshot,
)


@dataclass(frozen=True, slots=True)
class FusionPipelineConfig:
    """All explicit policies needed after deterministic preprocessing."""

    propagation: PropagationConfig
    measurements: FusionMeasurementConfig
    non_holonomic_constraint: NonHolonomicConstraintConfig
    navigation_mode: NavigationModeConfig
    runtime: NavigationRuntimeConfig

    # Standard deviations use the state ordering declared in fusion/state.py.
    initial_error_std: tuple[float, ...]

    # Standalone sessions default to the first good GNSS position as their
    # local ENU origin. A map-matched session instead supplies the exact ENU
    # origin used when its offline OSM graph was prepared. This keeps EKF
    # positions, covariance ellipses, and road geometry in one metric frame.
    local_enu_reference: LocalEnuReference | None = None

    def __post_init__(self) -> None:
        """Validate the one shape not owned by a subordinate configuration."""

        std = np.asarray(self.initial_error_std, dtype=float)
        if (
            std.shape != (ERROR_STATE_DIM,)
            or not np.all(np.isfinite(std))
            or np.any(std <= 0.0)
        ):
            raise ValueError("initial_error_std must be a positive finite 15-vector.")


@dataclass(frozen=True, slots=True)
class FusionPipelineResult:
    """One pre-EKF result plus the latest atomically published fusion state."""

    pre_ekf: PreEkfPipelineResult
    runtime_snapshot: RuntimeSnapshot
    propagation_disposition: PropagationDisposition | None
    measurement_traces: tuple[MeasurementUpdateTrace, ...]

    @property
    def filter_state(self) -> ErrorStateEkfState | None:
        """Expose the committed EKF state without a mutable pipeline reference."""

        return self.runtime_snapshot.filter_state

    @property
    def navigation_estimate(self) -> NavigationEstimate | None:
        """Expose the committed UI/API estimate, if fusion has initialized."""

        return self.runtime_snapshot.navigation_estimate


@dataclass(frozen=True, slots=True)
class _PendingGnssFix:
    """A quality-assessed receiver fix awaiting the next later IMU cycle."""

    fix: GnssFix
    quality: GnssFixQuality


class NavigationFusionPipeline:
    """Run the completed velocity pipeline and fuse its outputs safely.

    The supplied :class:`DeterministicPreEkfPipeline` remains the single owner
    of raw IMU preprocessing, calibration, velocity inference, and uncertainty
    inference.  This class only consumes those completed outputs and owns the
    EKF/runtime state, so it never touches training notebooks or model kernels.
    """

    def __init__(
        self,
        *,
        pre_ekf_pipeline: DeterministicPreEkfPipeline,
        config: FusionPipelineConfig,
    ) -> None:
        self._pre_ekf_pipeline = pre_ekf_pipeline
        self._config = config
        self._runtime = NavigationRuntime(config.runtime)
        self._runtime.start()

        self._pending_gnss: deque[_PendingGnssFix] = deque()
        self._last_queued_gnss_timestamp_ns: int | None = None
        self._local_enu_reference = config.local_enu_reference
        self._mode_state: NavigationModeState | None = None
        self._recovery_gnss_candidate: _PendingGnssFix | None = None
        self._recovery_gnss_candidate_count = 0

    @property
    def runtime_snapshot(self) -> RuntimeSnapshot:
        """Return the current committed state for callers that need no new input."""

        return self._runtime.snapshot

    @property
    def local_enu_reference(self) -> LocalEnuReference | None:
        """Return the immutable ENU origin used by this navigation session.

        The value is ``None`` only before a standalone session receives its
        first usable GNSS fix. Map-matching composition rejects that ambiguous
        state and requires an explicit map-origin reference at construction.
        """

        return self._local_enu_reference

    def push_gnss_fix(self, fix: GnssFix) -> GnssFixQuality:
        """Send GNSS to calibration and queue it for one future EKF cycle."""

        quality = self._pre_ekf_pipeline.push_gnss_fix(fix)

        # The preprocessor has already marked timestamp regressions as unsafe.
        # Do not let one poison the queue order used by the causal EKF boundary.
        if (
            self._last_queued_gnss_timestamp_ns is None
            or fix.timestamp_ns >= self._last_queued_gnss_timestamp_ns
        ):
            self._pending_gnss.append(_PendingGnssFix(fix=fix, quality=quality))
            self._last_queued_gnss_timestamp_ns = fix.timestamp_ns
        return quality

    def push_raw_sample(
        self,
        raw_sample: RawSensorSample,
    ) -> tuple[FusionPipelineResult, ...]:
        """Process raw IMU input and return one result per synchronized sample."""

        return tuple(
            self._fuse_pre_ekf_result(pre_ekf)
            for pre_ekf in self._pre_ekf_pipeline.push_raw_sample(raw_sample)
        )

    def stop(self) -> RuntimeSnapshot:
        """Stop the owned runtime after the caller has finished the session."""

        return self._runtime.stop()

    def _fuse_pre_ekf_result(
        self,
        pre_ekf: PreEkfPipelineResult,
    ) -> FusionPipelineResult:
        """Fuse exactly one accepted vehicle-IMU state, never a raw callback."""

        preprocessing = pre_ekf.preprocessing
        sample = preprocessing.vehicle_imu_sample
        if (
            sample is None
            or preprocessing.quality is None
            or not preprocessing.quality.is_acceptable
        ):
            return self._result(pre_ekf=pre_ekf, disposition=None, traces=())

        pending_gnss = self._take_due_gnss(sample.timestamp_ns)
        fresh_gnss = self._fresh_acceptable_position_fix(
            pending_gnss,
            sample.timestamp_ns,
        )
        snapshot = self._runtime.snapshot
        if snapshot.filter_state is None:
            if fresh_gnss is None:
                return self._result(pre_ekf=pre_ekf, disposition=None, traces=())
            return self._initialise_from_gnss(
                pre_ekf=pre_ekf,
                pending_gnss=fresh_gnss,
            )

        token = self._runtime.begin_cycle(sample.timestamp_ns)
        propagation = propagate_ekf(
            snapshot.filter_state,
            sample,
            self._config.propagation,
        )
        if (
            propagation.disposition
            is PropagationDisposition.TIMING_GAP_REQUIRES_RECOVERY
        ):
            if fresh_gnss is not None:
                return self._initialise_from_gnss(
                    pre_ekf=pre_ekf,
                    pending_gnss=fresh_gnss,
                    active_token=token,
                )
            self._runtime.abort_cycle(token, "IMU timing gap without fresh GNSS recovery.")
            return self._result(
                pre_ekf=pre_ekf,
                disposition=propagation.disposition,
                traces=(),
            )

        state = propagation.state
        traces: list[MeasurementUpdateTrace] = []
        gnss_position_trace: MeasurementUpdateTrace | None = None
        if fresh_gnss is not None:
            gnss_position = apply_linearised_measurement(
                state,
                build_gnss_position_measurement(
                    state=state,
                    fix=fresh_gnss.fix,
                    local_enu_reference=self._require_local_enu_reference(),
                    nis_gate=self._config.measurements.gnss_position_nis_gate,
                ),
            )
            state = gnss_position.state
            gnss_position_trace = gnss_position.trace
            traces.append(gnss_position.trace)

            if gnss_position.trace.disposition is MeasurementDisposition.ACCEPTED:
                self._clear_recovery_gnss_candidates()
            elif self._recovery_reinitialization_is_ready(
                pending_gnss=fresh_gnss,
                timestamp_ns=sample.timestamp_ns,
            ):
                # Preserve the rejected ordinary update beside the explicit
                # reset. Offline replay can therefore distinguish a normal
                # NIS rejection from a deliberate two-fix recovery action.
                return self._initialise_from_gnss(
                    pre_ekf=pre_ekf,
                    pending_gnss=fresh_gnss,
                    active_token=token,
                    prior_traces=tuple(traces),
                )

            # Course is stricter than position quality; only then may GNSS
            # provide horizontal velocity in addition to its position update.
            if fresh_gnss.quality.course_is_acceptable:
                gnss_velocity = apply_linearised_measurement(
                    state,
                    build_gnss_velocity_measurement(
                        state=state,
                        fix=fresh_gnss.fix,
                        nis_gate=self._config.measurements.gnss_velocity_nis_gate,
                    ),
                )
                state = gnss_velocity.state
                traces.append(gnss_velocity.trace)

        for observation, uncertainty in zip(
            pre_ekf.velocity_observations,
            pre_ekf.uncertainty_estimates,
            strict=True,
        ):
            association_age_ns = sample.timestamp_ns - observation.timestamp_ns
            if (
                association_age_ns < 0
                or association_age_ns
                > self._config.measurements.maximum_velocity_model_association_age_ns
            ):
                continue
            velocity_update = apply_linearised_measurement(
                state,
                build_velocity_model_measurement(
                    state=state,
                    observation=observation,
                    uncertainty=uncertainty,
                    nis_gate=self._config.measurements.velocity_model_nis_gate,
                    maximum_association_age_ns=(
                        self._config.measurements
                        .maximum_velocity_model_association_age_ns
                    ),
                ),
            )
            state = velocity_update.state
            traces.append(velocity_update.trace)

        nhc_decision = build_non_holonomic_measurement(
            state,
            sample,
            self._config.non_holonomic_constraint,
        )
        if nhc_decision.measurement is not None:
            nhc_update = apply_linearised_measurement(state, nhc_decision.measurement)
            state = nhc_update.state
            traces.append(nhc_update.trace)

        if self._mode_state is None:
            raise RuntimeError("An initialized EKF must have a navigation mode state.")
        mode_update = advance_navigation_mode(
            prior=self._mode_state,
            timestamp_ns=sample.timestamp_ns,
            gnss_quality=None if pending_gnss is None else pending_gnss.quality,
            gnss_position_trace=gnss_position_trace,
            config=self._config.navigation_mode,
        )
        self._mode_state = mode_update.state
        estimate = _navigation_estimate(state, mode_update.state)
        self._runtime.commit_cycle(
            token,
            CycleOutcome(
                filter_state=state,
                mode_state=mode_update.state,
                navigation_estimate=estimate,
                propagation_disposition=propagation.disposition,
                measurement_traces=tuple(traces),
            ),
        )
        return self._result(
            pre_ekf=pre_ekf,
            disposition=propagation.disposition,
            traces=tuple(traces),
        )

    def _initialise_from_gnss(
        self,
        *,
        pre_ekf: PreEkfPipelineResult,
        pending_gnss: _PendingGnssFix,
        active_token: object | None = None,
        prior_traces: tuple[MeasurementUpdateTrace, ...] = (),
    ) -> FusionPipelineResult:
        """Create or safely recover the EKF from one fresh accepted GNSS fix."""

        sample = pre_ekf.preprocessing.vehicle_imu_sample
        if sample is None:
            raise RuntimeError("Cannot initialize fusion without a vehicle IMU sample.")
        token = (
            self._runtime.begin_cycle(sample.timestamp_ns)
            if active_token is None
            else active_token
        )
        if self._local_enu_reference is None:
            self._local_enu_reference = LocalEnuReference.from_gnss_fix(pending_gnss.fix)

        position = self._local_enu_reference.project(pending_gnss.fix)
        state = initialise_filter_state(
            timestamp_ns=sample.timestamp_ns,
            position_enu_m=tuple(float(value) for value in position),
            velocity_enu_mps=_initial_velocity_enu(pending_gnss),
            vehicle_to_navigation_wxyz=sample.vehicle_to_navigation_wxyz,
            initial_error_std=np.asarray(self._config.initial_error_std, dtype=float),
        )
        initial_gnss_trace = MeasurementUpdateTrace(
            kind=MeasurementKind.GNSS_POSITION,
            timestamp_ns=sample.timestamp_ns,
            disposition=MeasurementDisposition.ACCEPTED,
            nis=0.0,
            nis_gate=self._config.measurements.gnss_position_nis_gate,
            correction=np.zeros(ERROR_STATE_DIM),
        )
        self._clear_recovery_gnss_candidates()
        if self._mode_state is None:
            self._mode_state = NavigationModeState(
                mode=NavigationMode.GNSS_AIDED,
                last_accepted_gnss_position_timestamp_ns=sample.timestamp_ns,
                blackout_started_timestamp_ns=None,
            )
        else:
            self._mode_state = advance_navigation_mode(
                prior=self._mode_state,
                timestamp_ns=sample.timestamp_ns,
                gnss_quality=pending_gnss.quality,
                gnss_position_trace=initial_gnss_trace,
                config=self._config.navigation_mode,
            ).state

        estimate = _navigation_estimate(state, self._mode_state)
        self._runtime.commit_cycle(
            token,
            CycleOutcome(
                filter_state=state,
                mode_state=self._mode_state,
                navigation_estimate=estimate,
                propagation_disposition=PropagationDisposition.INITIALISED,
                measurement_traces=(*prior_traces, initial_gnss_trace),
            ),
        )
        return self._result(
            pre_ekf=pre_ekf,
            disposition=PropagationDisposition.INITIALISED,
            traces=(*prior_traces, initial_gnss_trace),
        )

    def _recovery_reinitialization_is_ready(
        self,
        *,
        pending_gnss: _PendingGnssFix,
        timestamp_ns: int,
    ) -> bool:
        """Require two nearby quality-accepted fixes before resetting EKF state."""

        mode_state = self._mode_state
        if (
            mode_state is None
            or mode_state.last_accepted_gnss_position_timestamp_ns is None
            or timestamp_ns - mode_state.last_accepted_gnss_position_timestamp_ns
            < self._config.measurements.recovery_reinitialization_silence_ns
            or not pending_gnss.quality.position_is_acceptable
        ):
            self._clear_recovery_gnss_candidates()
            return False

        prior = self._recovery_gnss_candidate
        if prior is None:
            self._recovery_gnss_candidate = pending_gnss
            self._recovery_gnss_candidate_count = 1
            return False
        if not self._recovery_fixes_are_consistent(prior.fix, pending_gnss.fix):
            self._recovery_gnss_candidate = pending_gnss
            self._recovery_gnss_candidate_count = 1
            return False
        self._recovery_gnss_candidate = pending_gnss
        self._recovery_gnss_candidate_count += 1
        return (
            self._recovery_gnss_candidate_count
            >= self._config.measurements.recovery_required_consecutive_fixes
        )

    def _recovery_fixes_are_consistent(self, before: GnssFix, after: GnssFix) -> bool:
        """Reject an implausible recovery jump before it can reset navigation."""

        if self._local_enu_reference is None:
            return False
        before_enu = self._local_enu_reference.project(before)
        after_enu = self._local_enu_reference.project(after)
        return float(np.linalg.norm((after_enu - before_enu)[:2])) <= (
            self._config.measurements.recovery_maximum_interfix_distance_m
        )

    def _clear_recovery_gnss_candidates(self) -> None:
        """Forget a candidate sequence after an accepted update or bad input."""

        self._recovery_gnss_candidate = None
        self._recovery_gnss_candidate_count = 0

    def _take_due_gnss(self, timestamp_ns: int) -> _PendingGnssFix | None:
        """Use only the newest queued fix whose observation time has arrived."""

        newest: _PendingGnssFix | None = None
        while self._pending_gnss and self._pending_gnss[0].fix.timestamp_ns <= timestamp_ns:
            newest = self._pending_gnss.popleft()
        return newest

    def _fresh_acceptable_position_fix(
        self,
        pending_gnss: _PendingGnssFix | None,
        imu_timestamp_ns: int,
    ) -> _PendingGnssFix | None:
        """Reject stale or receiver-rejected GNSS before the EKF sees it."""

        if pending_gnss is None or not pending_gnss.quality.position_is_acceptable:
            return None
        if (
            imu_timestamp_ns - pending_gnss.fix.timestamp_ns
            > self._config.measurements.maximum_gnss_association_age_ns
        ):
            return None
        return pending_gnss

    def _require_local_enu_reference(self) -> LocalEnuReference:
        """Return the session origin after EKF initialization has established it."""

        if self._local_enu_reference is None:
            raise RuntimeError("GNSS position update requires an initialized ENU origin.")
        return self._local_enu_reference

    def _result(
        self,
        *,
        pre_ekf: PreEkfPipelineResult,
        disposition: PropagationDisposition | None,
        traces: tuple[MeasurementUpdateTrace, ...],
    ) -> FusionPipelineResult:
        """Build a result only from the last atomic runtime publication."""

        return FusionPipelineResult(
            pre_ekf=pre_ekf,
            runtime_snapshot=self._runtime.snapshot,
            propagation_disposition=disposition,
            measurement_traces=traces,
        )


def _initial_velocity_enu(pending_gnss: _PendingGnssFix) -> tuple[float, float, float]:
    """Use GNSS course only when its stricter quality decision permits it."""

    fix = pending_gnss.fix
    if (
        not pending_gnss.quality.course_is_acceptable
        or fix.speed_mps is None
        or fix.course_over_ground_rad is None
    ):
        return (0.0, 0.0, 0.0)
    return (
        fix.speed_mps * sin(fix.course_over_ground_rad),
        fix.speed_mps * cos(fix.course_over_ground_rad),
        0.0,
    )


def _navigation_estimate(
    state: ErrorStateEkfState,
    mode_state: NavigationModeState,
) -> NavigationEstimate:
    """Publish typed physical summaries while retaining full covariance internally."""

    covariance = state.covariance
    nominal = state.nominal
    return NavigationEstimate(
        timestamp_ns=nominal.timestamp_ns,
        mode=mode_state.mode,
        position_enu_m=tuple(float(value) for value in nominal.position_enu_m),
        velocity_enu_mps=tuple(float(value) for value in nominal.velocity_enu_mps),
        vehicle_to_navigation_wxyz=nominal.vehicle_to_navigation_wxyz,
        position_covariance_enu_m2=tuple(
            tuple(float(value) for value in row)
            for row in covariance[0:3, 0:3]
        ),
        velocity_covariance_enu_m2ps2=tuple(
            tuple(float(value) for value in row)
            for row in covariance[3:6, 3:6]
        ),
        # The state uses vehicle-frame attitude error.  With the selected FLU
        # convention, the z-axis is the local yaw/heading perturbation.
        heading_variance_rad2=float(max(0.0, covariance[8, 8])),
        matched_road_edge_id=None,
        map_match_confidence=None,
    )

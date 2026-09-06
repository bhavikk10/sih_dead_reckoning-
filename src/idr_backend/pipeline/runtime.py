from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter_ns

from ..fusion.measurements import MeasurementUpdateTrace
from ..fusion.modes import NavigationModeState
from ..fusion.propagation import PropagationDisposition
from ..fusion.state import ErrorStateEkfState
from ..sensors.types import NavigationEstimate


class RuntimePhase(StrEnum):
    """Backend execution lifecycle, separate from GNSS navigation mode."""

    COLD = "cold"
    WARMING_UP = "warming_up"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class NavigationRuntimeConfig:
    """Operational limits, not sensor-fusion tuning parameters."""

    maximum_pending_events: int
    cycle_latency_budget_ms: float
    late_cycles_before_degraded: int
    trace_history_capacity: int


@dataclass(frozen=True, slots=True)
class CycleToken:
    """Uniquely identifies one serial fusion cycle being processed."""

    sequence_number: int
    timestamp_ns: int
    started_performance_ns: int


@dataclass(frozen=True, slots=True)
class CycleOutcome:
    """Everything produced by one successfully processed cycle."""

    filter_state: ErrorStateEkfState
    mode_state: NavigationModeState
    navigation_estimate: NavigationEstimate

    propagation_disposition: PropagationDisposition
    measurement_traces: tuple[MeasurementUpdateTrace, ...]


@dataclass(frozen=True, slots=True)
class RuntimeTrace:
    """Privacy-safe, bounded diagnostic record without raw sensor values."""

    sequence_number: int
    timestamp_ns: int
    processing_latency_ms: float
    runtime_phase: RuntimePhase
    propagation_disposition: PropagationDisposition
    accepted_measurements: int
    rejected_measurements: int


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Last atomically committed runtime state."""

    phase: RuntimePhase
    last_cycle_timestamp_ns: int | None
    cycle_count: int
    late_cycle_streak: int

    filter_state: ErrorStateEkfState | None
    mode_state: NavigationModeState | None
    navigation_estimate: NavigationEstimate | None


def has_queue_capacity(
    pending_event_count: int,
    config: NavigationRuntimeConfig,
) -> bool:
    """Return whether the orchestrator may accept one more source event."""

    if pending_event_count < 0:
        raise ValueError("pending_event_count must not be negative.")
    if config.maximum_pending_events < 1:
        raise ValueError("maximum_pending_events must be at least one.")

    return pending_event_count < config.maximum_pending_events


class NavigationRuntime:
    """Single-owner lifecycle and atomic publication boundary."""

    def __init__(self, config: NavigationRuntimeConfig) -> None:
        if config.cycle_latency_budget_ms <= 0.0:
            raise ValueError("cycle_latency_budget_ms must be positive.")
        if config.late_cycles_before_degraded < 1:
            raise ValueError("late_cycles_before_degraded must be at least one.")
        if config.trace_history_capacity < 1:
            raise ValueError("trace_history_capacity must be at least one.")

        self._config = config
        self._phase = RuntimePhase.COLD
        self._snapshot = RuntimeSnapshot(
            phase=RuntimePhase.COLD,
            last_cycle_timestamp_ns=None,
            cycle_count=0,
            late_cycle_streak=0,
            filter_state=None,
            mode_state=None,
            navigation_estimate=None,
        )
        self._active_cycle: CycleToken | None = None
        self._traces: deque[RuntimeTrace] = deque(
            maxlen=config.trace_history_capacity
        )

    @property
    def snapshot(self) -> RuntimeSnapshot:
        """Return the most recent atomically committed state without mutation."""

        return self._snapshot

    @property
    def traces(self) -> tuple[RuntimeTrace, ...]:
        """Return bounded, privacy-safe diagnostics in commit order."""

        return tuple(self._traces)


    def start(self) -> RuntimeSnapshot:
        """Enter warm-up while preprocessing gathers calibration/GNSS evidence."""

        if self._phase is not RuntimePhase.COLD:
            raise RuntimeError("Runtime can only start from COLD.")

        self._phase = RuntimePhase.WARMING_UP
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=None,
            cycle_count=0,
            late_cycle_streak=0,
            filter_state=None,
            mode_state=None,
            navigation_estimate=None,
        )
        return self._snapshot


    def begin_cycle(self, timestamp_ns: int) -> CycleToken:
        """Reserve exactly one monotonic IMU-driven fusion cycle."""

        if self._phase in {
            RuntimePhase.COLD,
            RuntimePhase.STOPPED,
            RuntimePhase.FAILED,
        }:
            raise RuntimeError(f"Cannot process events while {self._phase}.")
        if self._active_cycle is not None:
            raise RuntimeError("Previous cycle has not been committed or aborted.")

        previous_timestamp = self._snapshot.last_cycle_timestamp_ns
        if (
            previous_timestamp is not None
            and timestamp_ns <= previous_timestamp
        ):
            raise ValueError("Pipeline cycle timestamps must be strictly increasing.")

        token = CycleToken(
            sequence_number=self._snapshot.cycle_count + 1,
            timestamp_ns=timestamp_ns,
            started_performance_ns=perf_counter_ns(),
        )
        self._active_cycle = token
        return token


    def commit_cycle(
        self,
        token: CycleToken,
        outcome: CycleOutcome,
    ) -> RuntimeSnapshot:
        """Atomically publish a complete fusion result and bounded diagnostics."""

        if token != self._active_cycle:
            raise RuntimeError("Only the active cycle token may be committed.")
        if outcome.filter_state.nominal.timestamp_ns != token.timestamp_ns:
            raise ValueError("Filter state timestamp does not match cycle token.")
        if outcome.navigation_estimate.timestamp_ns != token.timestamp_ns:
            raise ValueError("Published estimate timestamp does not match cycle token.")
        if outcome.navigation_estimate.mode != outcome.mode_state.mode:
            raise ValueError("Published estimate and mode state disagree.")

        latency_ms = (
            perf_counter_ns() - token.started_performance_ns
        ) / 1_000_000.0

        late_streak = (
            self._snapshot.late_cycle_streak + 1
            if latency_ms > self._config.cycle_latency_budget_ms
            else 0
        )
        next_phase = (
            RuntimePhase.DEGRADED
            if late_streak >= self._config.late_cycles_before_degraded
            else RuntimePhase.RUNNING
        )

        accepted = sum(
            trace.disposition.value == "accepted"
            for trace in outcome.measurement_traces
        )
        rejected = sum(
            trace.disposition.value != "accepted"
            for trace in outcome.measurement_traces
        )

        self._snapshot = RuntimeSnapshot(
            phase=next_phase,
            last_cycle_timestamp_ns=token.timestamp_ns,
            cycle_count=token.sequence_number,
            late_cycle_streak=late_streak,
            filter_state=outcome.filter_state,
            mode_state=outcome.mode_state,
            navigation_estimate=outcome.navigation_estimate,
        )
        self._phase = next_phase
        self._traces.append(
            RuntimeTrace(
                sequence_number=token.sequence_number,
                timestamp_ns=token.timestamp_ns,
                processing_latency_ms=latency_ms,
                runtime_phase=next_phase,
                propagation_disposition=outcome.propagation_disposition,
                accepted_measurements=accepted,
                rejected_measurements=rejected,
            )
        )
        self._active_cycle = None
        return self._snapshot

    def abort_cycle(self, token: CycleToken, reason: str) -> RuntimeSnapshot:
        """Discard incomplete work while preserving the last complete estimate."""

        if token != self._active_cycle:
            raise RuntimeError("Only the active cycle token may be aborted.")
        if not reason.strip():
            raise ValueError("A non-empty abort reason is required.")

        self._active_cycle = None
        self._phase = RuntimePhase.DEGRADED
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=self._snapshot.last_cycle_timestamp_ns,
            cycle_count=self._snapshot.cycle_count,
            late_cycle_streak=self._snapshot.late_cycle_streak,
            filter_state=self._snapshot.filter_state,
            mode_state=self._snapshot.mode_state,
            navigation_estimate=self._snapshot.navigation_estimate,
        )
        return self._snapshot


    def stop(self) -> RuntimeSnapshot:
        """End the session after all active work has completed or been aborted."""

        if self._active_cycle is not None:
            raise RuntimeError("Abort or commit the active cycle before stopping.")

        self._phase = RuntimePhase.STOPPED
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=self._snapshot.last_cycle_timestamp_ns,
            cycle_count=self._snapshot.cycle_count,
            late_cycle_streak=self._snapshot.late_cycle_streak,
            filter_state=self._snapshot.filter_state,
            mode_state=self._snapshot.mode_state,
            navigation_estimate=self._snapshot.navigation_estimate,
        )
        return self._snapshot


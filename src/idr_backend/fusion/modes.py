from dataclasses import dataclass
from enum import StrEnum

from ..sensors.gnss import GnssFixQuality
from ..sensors.types import NavigationMode
from .measurements import (
    MeasurementDisposition,
    MeasurementKind,
    MeasurementUpdateTrace,
)


@dataclass(frozen=True, slots=True)
class NavigationModeConfig:
    """Explicit timing policy for GNSS loss and return."""

    # A few missing/rejected fixes should not instantly declare a blackout.
    maximum_accepted_gnss_silence_s: float

    # One plausible GNSS update after a tunnel may still be multipath or stale.
    # Require several consecutive accepted position updates before displaying
    # normal GNSS-aided mode again.
    accepted_gnss_updates_for_recovery: int


class ModeTransitionReason(StrEnum):
    """Why the published navigation mode changed or remained meaningful."""

    GNSS_POSITION_ACCEPTED = "gnss_position_accepted"
    GNSS_ACCEPTED_SILENCE_EXCEEDED = "gnss_accepted_silence_exceeded"
    GNSS_QUALITY_UNACCEPTABLE = "gnss_quality_unacceptable"
    GNSS_INNOVATION_REJECTED = "gnss_innovation_rejected"
    GNSS_UNAVAILABLE = "gnss_unavailable"


@dataclass(frozen=True, slots=True)
class NavigationModeState:
    """Persistent state of GNSS handoff across fusion cycles."""

    mode: NavigationMode

    # Most recent GNSS position update that passed both receiver-quality checks
    # and the EKF innovation gate.
    last_accepted_gnss_position_timestamp_ns: int | None

    # Set when accepted GNSS support has been absent long enough to declare
    # dead reckoning. It is useful for uncertainty growth and UI messaging.
    blackout_started_timestamp_ns: int | None

    # Counts only consecutive accepted GNSS-position updates during RECOVERY.
    recovery_accepted_position_updates: int = 0


@dataclass(frozen=True, slots=True)
class ModeTransition:
    """One mode decision retained for replay, diagnostics, and UI state."""

    previous_mode: NavigationMode
    current_mode: NavigationMode
    reason: ModeTransitionReason
    blackout_elapsed_s: float | None


@dataclass(frozen=True, slots=True)
class ModeUpdateResult:
    """Updated persistent mode state plus an explainable transition record."""

    state: NavigationModeState
    transition: ModeTransition


def gnss_position_was_accepted(trace: MeasurementUpdateTrace | None,) -> bool:
    """Return true only for a GNSS-position EKF update accepted this cycle."""

    return (
        trace is not None
        and trace.kind is MeasurementKind.GNSS_POSITION
        and trace.disposition is MeasurementDisposition.ACCEPTED
    )


def current_gnss_reason(
    quality: GnssFixQuality | None,
    trace: MeasurementUpdateTrace | None,
) -> ModeTransitionReason:
    """Describe the best available explanation for missing GNSS assistance."""

    if (
        trace is not None
        and trace.kind is MeasurementKind.GNSS_POSITION
        and trace.disposition is MeasurementDisposition.INNOVATION_REJECTED
    ):
        return ModeTransitionReason.GNSS_INNOVATION_REJECTED

    if quality is None:
        return ModeTransitionReason.GNSS_UNAVAILABLE

    if not quality.position_is_acceptable:
        return ModeTransitionReason.GNSS_QUALITY_UNACCEPTABLE

    # A usable receiver fix may simply not have reached the update boundary yet.
    return ModeTransitionReason.GNSS_UNAVAILABLE


def blackout_elapsed_seconds(
    mode_state: NavigationModeState,
    timestamp_ns: int,
) -> float | None:
    """Return dead-reckoning duration when a declared blackout is active."""

    if mode_state.blackout_started_timestamp_ns is None:
        return None

    return max(
        0.0,
        (timestamp_ns - mode_state.blackout_started_timestamp_ns) * 1e-9,
    )


def advance_navigation_mode(
    *,
    prior: NavigationModeState,
    timestamp_ns: int,
    gnss_quality: GnssFixQuality | None,
    gnss_position_trace: MeasurementUpdateTrace | None,
    config: NavigationModeConfig,
) -> ModeUpdateResult:
    """Advance GNSS-aided, dead-reckoning, and recovery mode safely."""

    if timestamp_ns < 0:
        raise ValueError("timestamp_ns must be non-negative.")
    if config.maximum_accepted_gnss_silence_s <= 0.0:
        raise ValueError("maximum_accepted_gnss_silence_s must be positive.")
    if config.accepted_gnss_updates_for_recovery < 1:
        raise ValueError("accepted_gnss_updates_for_recovery must be at least one.")

    if gnss_position_was_accepted(gnss_position_trace):
        if prior.mode is NavigationMode.DEAD_RECKONING:
            next_mode = NavigationMode.RECOVERY
            recovery_count = 1
            blackout_started = prior.blackout_started_timestamp_ns

        elif prior.mode is NavigationMode.RECOVERY:
            recovery_count = prior.recovery_accepted_position_updates + 1
            next_mode = (
                NavigationMode.GNSS_AIDED
                if recovery_count >= config.accepted_gnss_updates_for_recovery
                else NavigationMode.RECOVERY
            )
            blackout_started = (
                None
                if next_mode is NavigationMode.GNSS_AIDED
                else prior.blackout_started_timestamp_ns
            )

        else:
            next_mode = NavigationMode.GNSS_AIDED
            recovery_count = 0
            blackout_started = None

        next_state = NavigationModeState(
            mode=next_mode,
            last_accepted_gnss_position_timestamp_ns=timestamp_ns,
            blackout_started_timestamp_ns=blackout_started,
            recovery_accepted_position_updates=recovery_count,
        )
        return ModeUpdateResult(
            state=next_state,
            transition=ModeTransition(
                previous_mode=prior.mode,
                current_mode=next_mode,
                reason=ModeTransitionReason.GNSS_POSITION_ACCEPTED,
                blackout_elapsed_s=blackout_elapsed_seconds(
                    next_state,
                    timestamp_ns,
                ),
            ),
        )

    last_accepted = prior.last_accepted_gnss_position_timestamp_ns
    silence_s = (
        None
        if last_accepted is None
        else (timestamp_ns - last_accepted) * 1e-9
    )

    if (
        silence_s is not None
        and silence_s > config.maximum_accepted_gnss_silence_s
    ):
        blackout_started = (
            prior.blackout_started_timestamp_ns
            if prior.blackout_started_timestamp_ns is not None
            else timestamp_ns
        )
        next_state = NavigationModeState(
            mode=NavigationMode.DEAD_RECKONING,
            last_accepted_gnss_position_timestamp_ns=last_accepted,
            blackout_started_timestamp_ns=blackout_started,
            recovery_accepted_position_updates=0,
        )
        return ModeUpdateResult(
            state=next_state,
            transition=ModeTransition(
                previous_mode=prior.mode,
                current_mode=NavigationMode.DEAD_RECKONING,
                reason=ModeTransitionReason.GNSS_ACCEPTED_SILENCE_EXCEEDED,
                blackout_elapsed_s=blackout_elapsed_seconds(
                    next_state,
                    timestamp_ns,
                ),
            ),
        )

    return ModeUpdateResult(
        state=prior,
        transition=ModeTransition(
            previous_mode=prior.mode,
            current_mode=prior.mode,
            reason=current_gnss_reason(
                gnss_quality,
                gnss_position_trace,
            ),
            blackout_elapsed_s=blackout_elapsed_seconds(
                prior,
                timestamp_ns,
            ),
        ),
    )

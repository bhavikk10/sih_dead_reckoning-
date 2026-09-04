"""Deterministic GNSS quality assessment.

This module judges what a receiver actually observed. It does not fill GNSS
gaps, estimate dead-reckoned position, project WGS-84 coordinates into ENU,
or create EKF measurement covariance yet.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, pi

from .types import GnssFix


class GnssQualityFlag(StrEnum):
    """Observable reasons why parts of one GNSS fix are unsafe to use."""

    TIMESTAMP_INVALID = "timestamp_invalid"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    GNSS_GAP = "gnss_gap"

    POSITION_NONFINITE = "position_nonfinite"
    LATITUDE_OUT_OF_RANGE = "latitude_out_of_range"
    LONGITUDE_OUT_OF_RANGE = "longitude_out_of_range"
    HORIZONTAL_ACCURACY_UNAVAILABLE = "horizontal_accuracy_unavailable"
    HORIZONTAL_ACCURACY_INVALID = "horizontal_accuracy_invalid"
    HORIZONTAL_ACCURACY_TOO_LARGE = "horizontal_accuracy_too_large"

    SPEED_UNAVAILABLE = "speed_unavailable"
    SPEED_INVALID = "speed_invalid"
    SPEED_ACCURACY_UNAVAILABLE = "speed_accuracy_unavailable"
    SPEED_ACCURACY_INVALID = "speed_accuracy_invalid"
    SPEED_ACCURACY_TOO_LARGE = "speed_accuracy_too_large"

    COURSE_UNAVAILABLE = "course_unavailable"
    COURSE_INVALID = "course_invalid"
    COURSE_ACCURACY_UNAVAILABLE = "course_accuracy_unavailable"
    COURSE_ACCURACY_INVALID = "course_accuracy_invalid"
    COURSE_ACCURACY_TOO_LARGE = "course_accuracy_too_large"
    COURSE_SPEED_TOO_LOW = "course_speed_too_low"


@dataclass(frozen=True, slots=True)
class GnssQualityLimits:
    """Configured bounds for one chronological GNSS receiver stream."""

    # A long time between fixes is important to report to fusion, but does not
    # mean the newly arrived fix is automatically inaccurate.
    max_gap_ns: int

    # Position is accepted only if the receiver supplies a sufficiently small
    # horizontal uncertainty.
    max_horizontal_accuracy_m: float

    # Speed/course quality bounds used for velocity updates and calibration.
    max_speed_accuracy_mps: float
    min_course_speed_mps: float
    max_course_accuracy_rad: float


@dataclass(frozen=True, slots=True)
class GnssFixQuality:
    """Usability facts for one GNSS fix.

    Separate booleans prevent us from making the wrong all-or-nothing decision.
    A position can assist the EKF even when course cannot assist calibration.
    """

    timestamp_ns: int
    receiver_id: str
    flags: frozenset[GnssQualityFlag]
    sample_interval_ns: int | None

    # For later GNSS position measurements in the EKF.
    position_is_acceptable: bool

    # For later GNSS speed measurements and velocity-model evaluation.
    speed_is_acceptable: bool

    # For phone-to-vehicle calibration. This is deliberately the strictest:
    # it needs reliable speed and reliable direction of actual movement.
    course_is_acceptable: bool


class GnssQualityMonitor:
    """Assess chronological GNSS fixes from exactly one receiver."""

    def __init__(self, limits: GnssQualityLimits) -> None:
        """Store validated receiver-quality thresholds."""

        if limits.max_gap_ns <= 0:
            raise ValueError("max_gap_ns must be positive.")

        if (
            not isfinite(limits.max_horizontal_accuracy_m)
            or limits.max_horizontal_accuracy_m <= 0.0
        ):
            raise ValueError(
                "max_horizontal_accuracy_m must be finite and positive."
            )

        if (
            not isfinite(limits.max_speed_accuracy_mps)
            or limits.max_speed_accuracy_mps <= 0.0
        ):
            raise ValueError(
                "max_speed_accuracy_mps must be finite and positive."
            )

        if (
            not isfinite(limits.min_course_speed_mps)
            or limits.min_course_speed_mps < 0.0
        ):
            raise ValueError(
                "min_course_speed_mps must be finite and non-negative."
            )

        if (
            not isfinite(limits.max_course_accuracy_rad)
            or not 0.0 < limits.max_course_accuracy_rad <= pi
        ):
            raise ValueError(
                "max_course_accuracy_rad must be in the range (0, pi]."
            )

        self._limits = limits
        self._receiver_id: str | None = None
        self._last_timestamp_ns: int | None = None


    def assess(self, fix: GnssFix) -> GnssFixQuality:
        """Assess one GNSS fix without changing its values."""

        self._register_or_validate_receiver(fix)

        flags: set[GnssQualityFlag] = set()
        sample_interval_ns: int | None = None

        self._assess_timestamp(fix, flags)
        sample_interval_ns = self._assess_timing_gap(fix, flags)

        self._assess_position(fix, flags)
        self._assess_speed(fix, flags)
        self._assess_course(fix, flags)

        frozen_flags = frozenset(flags)

        return GnssFixQuality(
            timestamp_ns=fix.timestamp_ns,
            receiver_id=fix.receiver_id,
            flags=frozen_flags,
            sample_interval_ns=sample_interval_ns,
            position_is_acceptable=not (
                frozen_flags
                & {
                    GnssQualityFlag.TIMESTAMP_INVALID,
                    GnssQualityFlag.TIMESTAMP_REGRESSION,
                    GnssQualityFlag.POSITION_NONFINITE,
                    GnssQualityFlag.LATITUDE_OUT_OF_RANGE,
                    GnssQualityFlag.LONGITUDE_OUT_OF_RANGE,
                    GnssQualityFlag.HORIZONTAL_ACCURACY_UNAVAILABLE,
                    GnssQualityFlag.HORIZONTAL_ACCURACY_INVALID,
                    GnssQualityFlag.HORIZONTAL_ACCURACY_TOO_LARGE,
                }
            ),
            speed_is_acceptable=not (
                frozen_flags
                & {
                    GnssQualityFlag.TIMESTAMP_INVALID,
                    GnssQualityFlag.TIMESTAMP_REGRESSION,
                    GnssQualityFlag.SPEED_UNAVAILABLE,
                    GnssQualityFlag.SPEED_INVALID,
                    GnssQualityFlag.SPEED_ACCURACY_UNAVAILABLE,
                    GnssQualityFlag.SPEED_ACCURACY_INVALID,
                    GnssQualityFlag.SPEED_ACCURACY_TOO_LARGE,
                }
            ),
            course_is_acceptable=not (
                frozen_flags
                & {
                    GnssQualityFlag.TIMESTAMP_INVALID,
                    GnssQualityFlag.TIMESTAMP_REGRESSION,
                    GnssQualityFlag.SPEED_UNAVAILABLE,
                    GnssQualityFlag.SPEED_INVALID,
                    GnssQualityFlag.SPEED_ACCURACY_UNAVAILABLE,
                    GnssQualityFlag.SPEED_ACCURACY_INVALID,
                    GnssQualityFlag.SPEED_ACCURACY_TOO_LARGE,
                    GnssQualityFlag.COURSE_UNAVAILABLE,
                    GnssQualityFlag.COURSE_INVALID,
                    GnssQualityFlag.COURSE_ACCURACY_UNAVAILABLE,
                    GnssQualityFlag.COURSE_ACCURACY_INVALID,
                    GnssQualityFlag.COURSE_ACCURACY_TOO_LARGE,
                    GnssQualityFlag.COURSE_SPEED_TOO_LOW,
                }
            ),
        )


    def _register_or_validate_receiver(self, fix: GnssFix) -> None:
        """Bind the monitor to one receiver and prevent accidental mixing."""

        if not fix.receiver_id.strip():
            raise ValueError("receiver_id must not be blank.")

        if self._receiver_id is None:
            self._receiver_id = fix.receiver_id
        elif fix.receiver_id != self._receiver_id:
            raise ValueError(
                "Cannot mix multiple GNSS receivers in one GnssQualityMonitor."
            )


    def _assess_timestamp(
        self,
        fix: GnssFix,
        flags: set[GnssQualityFlag],
    ) -> None:
        """Record invalid or backward session timestamps."""

        if fix.timestamp_ns < 0:
            flags.add(GnssQualityFlag.TIMESTAMP_INVALID)
            return

        if (
            self._last_timestamp_ns is not None
            and fix.timestamp_ns <= self._last_timestamp_ns
        ):
            flags.add(GnssQualityFlag.TIMESTAMP_REGRESSION)


    def _assess_timing_gap(
        self,
        fix: GnssFix,
        flags: set[GnssQualityFlag],
    ) -> int | None:
        """Measure time since the previous usable timestamp."""

        if fix.timestamp_ns < 0:
            return None

        if self._last_timestamp_ns is None:
            self._last_timestamp_ns = fix.timestamp_ns
            return None

        if fix.timestamp_ns <= self._last_timestamp_ns:
            return None

        interval_ns = fix.timestamp_ns - self._last_timestamp_ns
        self._last_timestamp_ns = fix.timestamp_ns

        if interval_ns > self._limits.max_gap_ns:
            flags.add(GnssQualityFlag.GNSS_GAP)

        return interval_ns


    def _assess_position(
        self,
        fix: GnssFix,
        flags: set[GnssQualityFlag],
    ) -> None:
        """Check raw WGS-84 position and horizontal receiver accuracy."""

        if not isfinite(fix.latitude_deg) or not isfinite(fix.longitude_deg):
            flags.add(GnssQualityFlag.POSITION_NONFINITE)
        else:
            if not -90.0 <= fix.latitude_deg <= 90.0:
                flags.add(GnssQualityFlag.LATITUDE_OUT_OF_RANGE)

            if not -180.0 <= fix.longitude_deg <= 180.0:
                flags.add(GnssQualityFlag.LONGITUDE_OUT_OF_RANGE)

        if fix.horizontal_accuracy_m is None:
            flags.add(GnssQualityFlag.HORIZONTAL_ACCURACY_UNAVAILABLE)
        elif (
            not isfinite(fix.horizontal_accuracy_m)
            or fix.horizontal_accuracy_m < 0.0
        ):
            flags.add(GnssQualityFlag.HORIZONTAL_ACCURACY_INVALID)
        elif (
            fix.horizontal_accuracy_m
            > self._limits.max_horizontal_accuracy_m
        ):
            flags.add(GnssQualityFlag.HORIZONTAL_ACCURACY_TOO_LARGE)


    def _assess_speed(
        self,
        fix: GnssFix,
        flags: set[GnssQualityFlag],
    ) -> None:
        """Check receiver-reported speed and its uncertainty."""

        if fix.speed_mps is None:
            flags.add(GnssQualityFlag.SPEED_UNAVAILABLE)
        elif not isfinite(fix.speed_mps) or fix.speed_mps < 0.0:
            flags.add(GnssQualityFlag.SPEED_INVALID)

        if fix.speed_accuracy_mps is None:
            flags.add(GnssQualityFlag.SPEED_ACCURACY_UNAVAILABLE)
        elif (
            not isfinite(fix.speed_accuracy_mps)
            or fix.speed_accuracy_mps < 0.0
        ):
            flags.add(GnssQualityFlag.SPEED_ACCURACY_INVALID)
        elif (
            fix.speed_accuracy_mps
            > self._limits.max_speed_accuracy_mps
        ):
            flags.add(GnssQualityFlag.SPEED_ACCURACY_TOO_LARGE)


    def _assess_course(
        self,
        fix: GnssFix,
        flags: set[GnssQualityFlag],
    ) -> None:
        """Check whether course-over-ground can aid mounting calibration."""

        if fix.course_over_ground_rad is None:
            flags.add(GnssQualityFlag.COURSE_UNAVAILABLE)
        elif (
            not isfinite(fix.course_over_ground_rad)
            or not 0.0 <= fix.course_over_ground_rad < 2.0 * pi
        ):
            flags.add(GnssQualityFlag.COURSE_INVALID)

        if fix.course_accuracy_rad is None:
            flags.add(GnssQualityFlag.COURSE_ACCURACY_UNAVAILABLE)
        elif (
            not isfinite(fix.course_accuracy_rad)
            or fix.course_accuracy_rad < 0.0
        ):
            flags.add(GnssQualityFlag.COURSE_ACCURACY_INVALID)
        elif (
            fix.course_accuracy_rad
            > self._limits.max_course_accuracy_rad
        ):
            flags.add(GnssQualityFlag.COURSE_ACCURACY_TOO_LARGE)

        if (
            fix.speed_mps is not None
            and isfinite(fix.speed_mps)
            and fix.speed_mps < self._limits.min_course_speed_mps
        ):
            flags.add(GnssQualityFlag.COURSE_SPEED_TOO_LOW)


    def reset(self) -> None:
        """Forget receiver state after a confirmed session restart."""

        self._receiver_id = None
        self._last_timestamp_ns = None
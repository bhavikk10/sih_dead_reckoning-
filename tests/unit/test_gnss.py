from idr_backend.sensors.gnss import (
    GnssQualityFlag,
    GnssQualityLimits,
    GnssQualityMonitor,
)
from idr_backend.sensors.types import GnssFix


def _limits() -> GnssQualityLimits:
    """Return ordinary phone-GNSS acceptance limits for unit tests."""

    return GnssQualityLimits(
        max_gap_ns=2_000_000_000,
        max_horizontal_accuracy_m=15.0,
        max_speed_accuracy_mps=1.0,
        min_course_speed_mps=3.0,
        max_course_accuracy_rad=0.35,
    )


def _fix(
    *,
    timestamp_ns: int,
    speed_mps: float | None = 12.0,
    speed_accuracy_mps: float | None = 0.5,
    course_over_ground_rad: float | None = 0.4,
    course_accuracy_rad: float | None = 0.1,
    horizontal_accuracy_m: float | None = 5.0,
) -> GnssFix:
    """Build one otherwise-valid GNSS fix, overriding only what a test needs."""

    return GnssFix(
        timestamp_ns=timestamp_ns,
        receiver_id="phone-primary",
        latitude_deg=12.9716,
        longitude_deg=77.5946,
        altitude_m=900.0,
        horizontal_accuracy_m=horizontal_accuracy_m,
        vertical_accuracy_m=12.0,
        speed_mps=speed_mps,
        speed_accuracy_mps=speed_accuracy_mps,
        course_over_ground_rad=course_over_ground_rad,
        course_accuracy_rad=course_accuracy_rad,
    )


def test_valid_fix_is_acceptable_for_position_speed_and_course() -> None:
    """A good moving fix may serve all three downstream consumers."""

    monitor = GnssQualityMonitor(_limits())

    quality = monitor.assess(
        _fix(timestamp_ns=1_000_000_000)
    )

    assert quality.flags == frozenset()
    assert quality.sample_interval_ns is None
    assert quality.position_is_acceptable
    assert quality.speed_is_acceptable
    assert quality.course_is_acceptable


def test_slow_fix_keeps_speed_but_rejects_course() -> None:
    """Course-over-ground must not aid calibration when the vehicle is slow."""

    monitor = GnssQualityMonitor(_limits())

    quality = monitor.assess(
        _fix(
            timestamp_ns=1_000_000_000,
            speed_mps=1.5,
        )
    )

    assert quality.position_is_acceptable
    assert quality.speed_is_acceptable
    assert not quality.course_is_acceptable
    assert GnssQualityFlag.COURSE_SPEED_TOO_LOW in quality.flags


def test_gnss_gap_is_reported_without_rejecting_a_good_returning_fix() -> None:
    """A valid returning fix remains usable after temporary GNSS loss."""

    monitor = GnssQualityMonitor(_limits())

    monitor.assess(
        _fix(timestamp_ns=1_000_000_000)
    )

    quality = monitor.assess(
        _fix(timestamp_ns=5_000_000_000)
    )

    assert quality.sample_interval_ns == 4_000_000_000
    assert GnssQualityFlag.GNSS_GAP in quality.flags
    assert quality.position_is_acceptable
    assert quality.speed_is_acceptable
    assert quality.course_is_acceptable


def test_timestamp_regression_is_rejected_without_moving_time_backward() -> None:
    """A bad old fix cannot alter the monitor's valid timestamp reference."""

    monitor = GnssQualityMonitor(_limits())

    monitor.assess(
        _fix(timestamp_ns=10_000_000_000)
    )

    regressed_quality = monitor.assess(
        _fix(timestamp_ns=9_000_000_000)
    )

    recovered_quality = monitor.assess(
        _fix(timestamp_ns=11_000_000_000)
    )

    assert GnssQualityFlag.TIMESTAMP_REGRESSION in regressed_quality.flags
    assert not regressed_quality.position_is_acceptable
    assert regressed_quality.sample_interval_ns is None

    # The interval is measured from 10 s, not the invalid 9 s event.
    assert recovered_quality.sample_interval_ns == 1_000_000_000


def test_missing_horizontal_accuracy_rejects_position() -> None:
    """The EKF must not trust position when the receiver supplies no accuracy."""

    monitor = GnssQualityMonitor(_limits())

    quality = monitor.assess(
        _fix(
            timestamp_ns=1_000_000_000,
            horizontal_accuracy_m=None,
        )
    )

    assert GnssQualityFlag.HORIZONTAL_ACCURACY_UNAVAILABLE in quality.flags
    assert not quality.position_is_acceptable

    # Speed/course are independent reported observations in this contract.
    assert quality.speed_is_acceptable
    assert quality.course_is_acceptable



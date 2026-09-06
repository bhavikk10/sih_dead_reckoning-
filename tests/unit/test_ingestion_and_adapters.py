"""Tests for lossless record boundaries before deterministic processing."""

import math

import pytest

from idr_backend.adapters.gnss import parse_gnss_record
from idr_backend.sensors.ingestion import (
    parse_raw_sensor_record,
    parse_raw_sensor_records,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    MeasurementUnit,
    SensorKind,
    SensorSource,
)


def _imu_record() -> dict[str, object]:
    return {
        "timestamp_ns": 123,
        "source": "phone",
        "source_id": "phone-primary",
        "kind": "accelerometer",
        "x": 1,
        "y": 2.5,
        "z": -3,
        "unit": "m/s^2",
        "frame": "sensor",
        "vendor_accuracy": 2,
    }


def test_raw_record_parser_preserves_declared_metadata() -> None:
    """Ingestion parses shape but does not normalize units or rotate axes."""

    sample = parse_raw_sensor_record(_imu_record())

    assert sample.timestamp_ns == 123
    assert sample.source is SensorSource.PHONE
    assert sample.kind is SensorKind.ACCELEROMETER
    assert sample.value == (1.0, 2.5, -3.0)
    assert sample.unit is MeasurementUnit.METERS_PER_SECOND_SQUARED
    assert sample.frame is CoordinateFrame.SENSOR


def test_raw_batch_parser_reports_the_bad_record_index() -> None:
    """A malformed later record must not be silently discarded."""

    malformed = _imu_record()
    del malformed["x"]

    with pytest.raises(ValueError, match="index 1.*x"):
        parse_raw_sensor_records((_imu_record(), malformed))


def test_gnss_adapter_converts_explicit_degree_course_to_radians() -> None:
    """The source boundary is the sole degree-to-radian conversion point."""

    fix = parse_gnss_record(
        {
            "timestamp_ns": 1_000_000_000,
            "receiver_id": "phone-primary",
            "latitude_deg": 12.9716,
            "longitude_deg": 77.5946,
            "speed_mps": 10.0,
            "speed_accuracy_mps": 0.4,
            "course_over_ground_deg": 90.0,
            "course_accuracy_deg": 10.0,
        }
    )

    assert fix.course_over_ground_rad == pytest.approx(math.pi / 2.0)
    assert fix.course_accuracy_rad == pytest.approx(math.pi / 18.0)

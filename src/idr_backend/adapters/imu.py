"""Transport-free boundary for phone and external-IMU callback records.

Native/mobile code is responsible for producing the canonical mapping used
here.  This adapter intentionally does not smooth, reorder, filter, convert
units, or infer a coordinate frame; those decisions remain auditable in the
deterministic sensor modules.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from idr_backend.sensors.ingestion import (
    parse_raw_sensor_record,
    parse_raw_sensor_records,
)
from idr_backend.sensors.types import RawSensorSample


def parse_imu_record(record: Mapping[str, Any]) -> RawSensorSample:
    """Parse one canonical phone/external-IMU record without altering it."""

    return parse_raw_sensor_record(record)


def parse_imu_records(
    records: Iterable[Mapping[str, Any]],
) -> tuple[RawSensorSample, ...]:
    """Parse an ordered IMU batch while preserving its incoming order."""

    return parse_raw_sensor_records(records)

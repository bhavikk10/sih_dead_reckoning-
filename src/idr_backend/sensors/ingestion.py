"""Lossless parsing at the raw inertial-sensor boundary.

Platform adapters turn a source-specific callback, CSV row, or transport
payload into the canonical mapping described below.  This module constructs
``RawSensorSample`` values without converting units, changing time order, or
guessing coordinate frames.  Those decisions remain visible to later stages.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from .types import (
    CoordinateFrame,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
)


_REQUIRED_RECORD_FIELDS = frozenset(
    {
        "timestamp_ns",
        "source",
        "source_id",
        "kind",
        "x",
        "y",
        "z",
        "unit",
        "frame",
    }
)


def parse_raw_sensor_record(record: Mapping[str, Any]) -> RawSensorSample:
    """Parse one adapter record without changing its physical meaning.

    The supported canonical fields are ``timestamp_ns``, ``source``,
    ``source_id``, ``kind``, ``x``, ``y``, ``z``, ``unit``, and ``frame``;
    ``vendor_accuracy`` is optional opaque platform metadata.  Values are
    deliberately only shape-parsed here.  SI conversion and physical validity
    are the responsibility of :func:`normalize_raw_sample`.
    """

    missing_fields = _REQUIRED_RECORD_FIELDS.difference(record)
    if missing_fields:
        missing_text = ", ".join(sorted(missing_fields))
        raise ValueError(
            f"Raw sensor record is missing required fields: {missing_text}."
        )

    try:
        vendor_accuracy = record.get("vendor_accuracy")
        return RawSensorSample(
            timestamp_ns=int(record["timestamp_ns"]),
            source=SensorSource(str(record["source"])),
            source_id=str(record["source_id"]),
            kind=SensorKind(str(record["kind"])),
            value=(
                float(record["x"]),
                float(record["y"]),
                float(record["z"]),
            ),
            unit=MeasurementUnit(str(record["unit"])),
            frame=CoordinateFrame(str(record["frame"])),
            vendor_accuracy=(
                None if vendor_accuracy is None else int(vendor_accuracy)
            ),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Malformed raw sensor record: {error}") from error


def parse_raw_sensor_records(
    records: Iterable[Mapping[str, Any]],
) -> tuple[RawSensorSample, ...]:
    """Parse an ordered source batch and identify any bad record by index.

    The function does not sort, deduplicate, interpolate, or discard records:
    stream-order policy belongs to synchronization and quality monitoring.
    """

    parsed_samples: list[RawSensorSample] = []
    for index, record in enumerate(records):
        try:
            parsed_samples.append(parse_raw_sensor_record(record))
        except ValueError as error:
            raise ValueError(
                f"Invalid raw sensor record at index {index}: {error}"
            ) from error

    return tuple(parsed_samples)

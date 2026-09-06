"""Canonical GNSS-record adapter.

This module is intentionally transport-free: it turns a source adapter's
already-decoded mapping into the core ``GnssFix`` contract.  It never contacts
GPS hardware, starts a live service, or carries stale observations forward.
"""

from collections.abc import Mapping
from math import isfinite, radians
from typing import Any

from idr_backend.sensors.types import GnssFix


_REQUIRED_RECORD_FIELDS = frozenset(
    {"timestamp_ns", "receiver_id", "latitude_deg", "longitude_deg"}
)


def parse_gnss_record(record: Mapping[str, Any]) -> GnssFix:
    """Parse one receiver record with an explicit degree-to-radian boundary.

    Required coordinates are WGS-84 degrees.  Optional course fields must be
    named ``course_over_ground_deg`` and ``course_accuracy_deg`` so a caller
    cannot silently confuse degree-valued platform data with the core's radian
    contract.  Other optional numeric fields already use metres or m/s.
    """

    missing_fields = _REQUIRED_RECORD_FIELDS.difference(record)
    if missing_fields:
        missing_text = ", ".join(sorted(missing_fields))
        raise ValueError(f"GNSS record is missing required fields: {missing_text}.")

    try:
        latitude_deg = float(record["latitude_deg"])
        longitude_deg = float(record["longitude_deg"])
        if not isfinite(latitude_deg) or not -90.0 <= latitude_deg <= 90.0:
            raise ValueError("latitude_deg must be finite and in [-90, 90].")
        if not isfinite(longitude_deg) or not -180.0 <= longitude_deg <= 180.0:
            raise ValueError("longitude_deg must be finite and in [-180, 180].")

        course_deg = record.get("course_over_ground_deg")
        course_accuracy_deg = record.get("course_accuracy_deg")

        return GnssFix(
            timestamp_ns=int(record["timestamp_ns"]),
            receiver_id=str(record["receiver_id"]),
            latitude_deg=latitude_deg,
            longitude_deg=longitude_deg,
            altitude_m=_optional_finite_float(record.get("altitude_m")),
            horizontal_accuracy_m=_optional_finite_float(
                record.get("horizontal_accuracy_m")
            ),
            vertical_accuracy_m=_optional_finite_float(
                record.get("vertical_accuracy_m")
            ),
            speed_mps=_optional_finite_float(record.get("speed_mps")),
            speed_accuracy_mps=_optional_finite_float(
                record.get("speed_accuracy_mps")
            ),
            course_over_ground_rad=(
                None if course_deg is None else radians(float(course_deg))
            ),
            course_accuracy_rad=(
                None
                if course_accuracy_deg is None
                else radians(float(course_accuracy_deg))
            ),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Malformed GNSS record: {error}") from error


def _optional_finite_float(value: Any) -> float | None:
    """Convert an optional numeric source field while preserving absence."""

    if value is None:
        return None

    converted = float(value)
    if not isfinite(converted):
        raise ValueError("Optional GNSS numeric fields must be finite.")
    return converted

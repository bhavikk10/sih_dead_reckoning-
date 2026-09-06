"""Build sparse, provenance-preserving road-context source rows offline.

This module is deliberately outside the live navigation path.  It consumes
already aligned :class:`RawReplayJourney` recordings and produces a sparse
GPS/CAN table ready for a later *offline* trajectory map-matching step.  It
does not import fusion, map matching, IMU preprocessing, or velocity-model
code, and CAN speed remains an offline target only.

Road attributes and matched-edge features are intentionally not joined here:
that requires a versioned OSM graph and a trajectory-level matcher.  Keeping
the raw-source stage separate makes its quality decisions auditable and avoids
quietly treating a nearest-edge snap as a trustworthy training label.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from idr_backend.evaluation.replay import RawReplayJourney


RoadContextPositionSource = Literal["phone_gnss", "reference"]

_EARTH_RADIUS_M = 6_371_008.8
_SOURCE_COLUMNS = (
    "journey_id",
    "timestamp_ns",
    "elapsed_s",
    "target_speed_mps",
    "target_source",
    "match_latitude_deg",
    "match_longitude_deg",
    "match_position_source",
    "phone_latitude_deg",
    "phone_longitude_deg",
    "phone_altitude_m",
    "phone_speed_mps",
    "phone_horizontal_accuracy_m",
    "phone_course_rad",
    "has_usable_phone_course",
    "reference_latitude_deg",
    "reference_longitude_deg",
    "phone_reference_distance_m",
)


@dataclass(frozen=True, slots=True)
class RoadContextSourceDatasetConfig:
    """Quality and cadence policy for one offline source-table build.

    The default two-second cadence is an upper bound on density, not a claim
    that successive points are independent. Journey- and edge-balanced
    weighting is applied later within each training fold after map matching.

    ``match_position_source`` is intentionally explicit. The raw recordings
    retain both phone GNSS and a paired reference coordinate, but the latter
    has no recorded accuracy field in the current data. The first build
    defaults to quality-gated phone GNSS and preserves both coordinate streams
    for a later documented comparison.
    """

    sample_period_s: float = 2.0
    maximum_phone_horizontal_accuracy_m: float = 20.0
    maximum_target_speed_mps: float = 75.0
    maximum_phone_speed_mps: float = 75.0
    minimum_course_speed_mps: float = 2.0
    match_position_source: RoadContextPositionSource = "phone_gnss"

    def __post_init__(self) -> None:
        positive = (
            self.sample_period_s,
            self.maximum_phone_horizontal_accuracy_m,
            self.maximum_target_speed_mps,
            self.maximum_phone_speed_mps,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("Road-context cadence and maximum limits must be positive.")
        if not isfinite(self.minimum_course_speed_mps) or self.minimum_course_speed_mps < 0.0:
            raise ValueError("minimum_course_speed_mps must be finite and non-negative.")
        if self.match_position_source not in ("phone_gnss", "reference"):
            raise ValueError("match_position_source must be 'phone_gnss' or 'reference'.")


@dataclass(frozen=True, slots=True)
class RoadContextJourneyAudit:
    """Counts showing exactly why raw rows did or did not reach the source table."""

    journey_id: str
    total_rows: int
    emitted_rows: int
    skipped_by_cadence: int
    rejected_invalid_timestamp: int
    rejected_invalid_target_speed: int
    rejected_invalid_phone_position: int
    rejected_invalid_phone_accuracy: int
    rejected_invalid_phone_speed: int
    rejected_invalid_reference_position: int

    def __post_init__(self) -> None:
        if not self.journey_id.strip():
            raise ValueError("Road-context audit journey_id must not be blank.")
        counts = (
            self.total_rows,
            self.emitted_rows,
            self.skipped_by_cadence,
            self.rejected_invalid_timestamp,
            self.rejected_invalid_target_speed,
            self.rejected_invalid_phone_position,
            self.rejected_invalid_phone_accuracy,
            self.rejected_invalid_phone_speed,
            self.rejected_invalid_reference_position,
        )
        if any(count < 0 for count in counts):
            raise ValueError("Road-context audit counts must be non-negative.")
        if self.emitted_rows > self.total_rows:
            raise ValueError("Road-context audit cannot emit more rows than it receives.")


@dataclass(frozen=True, slots=True)
class RoadContextSourceDataset:
    """Sparse, validated source observations before OSM/map-match joining.

    Each row uses CAN indicated speed only as the offline ``target_speed_mps``.
    No target field belongs in future runtime feature construction.
    """

    frame: pd.DataFrame
    audits: tuple[RoadContextJourneyAudit, ...]
    config: RoadContextSourceDatasetConfig

    def __post_init__(self) -> None:
        if tuple(self.frame.columns) != _SOURCE_COLUMNS:
            raise ValueError("Road-context source frame has an unexpected schema.")
        if self.frame.empty:
            raise ValueError("Road-context source frame must contain at least one row.")
        if not self.audits:
            raise ValueError("Road-context source dataset requires at least one audit.")

        numeric_columns = (
            "elapsed_s",
            "target_speed_mps",
            "match_latitude_deg",
            "match_longitude_deg",
            "phone_latitude_deg",
            "phone_longitude_deg",
            "phone_altitude_m",
            "phone_speed_mps",
            "phone_horizontal_accuracy_m",
            "reference_latitude_deg",
            "reference_longitude_deg",
            "phone_reference_distance_m",
        )
        numeric = self.frame.loc[:, numeric_columns].to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError("Road-context source frame numeric fields must be finite.")
        if (self.frame["target_speed_mps"].to_numpy(dtype=float) < 0.0).any():
            raise ValueError("Road-context target speeds must be non-negative.")
        if (self.frame["phone_horizontal_accuracy_m"].to_numpy(dtype=float) < 0.0).any():
            raise ValueError("Road-context phone accuracies must be non-negative.")
        if (self.frame["phone_reference_distance_m"].to_numpy(dtype=float) < 0.0).any():
            raise ValueError("Road-context phone/reference distances must be non-negative.")
        if not self.frame["target_source"].eq("can_indicated_speed").all():
            raise ValueError("Road-context source targets must be CAN indicated speed.")
        if not self.frame["match_position_source"].isin(("phone_gnss", "reference")).all():
            raise ValueError("Road-context source position provenance is invalid.")

        audit_ids = {audit.journey_id for audit in self.audits}
        frame_ids = set(self.frame["journey_id"])
        if not frame_ids.issubset(audit_ids):
            raise ValueError("Every emitted road-context journey requires an audit.")

        for journey_id, group in self.frame.groupby("journey_id", sort=False):
            timestamps_ns = group["timestamp_ns"].to_numpy(dtype=np.int64)
            if not str(journey_id).strip() or not np.all(np.diff(timestamps_ns) > 0):
                raise ValueError(
                    "Road-context source timestamps must increase within each journey."
                )


def build_road_context_source_dataset(
    journeys: Iterable[RawReplayJourney],
    *,
    config: RoadContextSourceDatasetConfig = RoadContextSourceDatasetConfig(),
) -> RoadContextSourceDataset:
    """Create sparse, map-ready source rows from aligned raw replay journeys.

    This is a deterministic offline transformation. It neither replays the
    navigation pipeline nor changes any live runtime state. Quality rejection
    is intentionally sequential and recorded in ``RoadContextJourneyAudit`` so
    every discarded raw row has one primary, reproducible reason.
    """

    journey_items = tuple(journeys)
    if not journey_items:
        raise ValueError("At least one raw replay journey is required.")

    journey_ids = tuple(journey.journey_id for journey in journey_items)
    if len(set(journey_ids)) != len(journey_ids):
        raise ValueError("Road-context source journeys must have unique journey IDs.")

    frames: list[pd.DataFrame] = []
    audits: list[RoadContextJourneyAudit] = []
    for journey in journey_items:
        frame, audit = _build_journey_source_frame(journey, config=config)
        audits.append(audit)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise ValueError("No raw rows passed the road-context source quality policy.")

    result = pd.concat(frames, ignore_index=True)
    return RoadContextSourceDataset(
        frame=result.loc[:, _SOURCE_COLUMNS],
        audits=tuple(audits),
        config=config,
    )


def _build_journey_source_frame(
    journey: RawReplayJourney,
    *,
    config: RoadContextSourceDatasetConfig,
) -> tuple[pd.DataFrame, RoadContextJourneyAudit]:
    """Validate and cadence-sample one journey without map matching it."""

    timestamps_ns = np.asarray(journey.timestamps_ns, dtype=float)
    target_speed_mps = np.asarray(journey.reference_speed_mps, dtype=float)
    phone_latitude_deg = np.asarray(journey.phone_latitude_deg, dtype=float)
    phone_longitude_deg = np.asarray(journey.phone_longitude_deg, dtype=float)
    phone_altitude_m = np.asarray(journey.phone_altitude_m, dtype=float)
    phone_speed_mps = np.asarray(journey.phone_speed_mps, dtype=float)
    phone_accuracy_m = np.asarray(journey.phone_horizontal_accuracy_m, dtype=float)
    phone_course_rad = np.asarray(journey.phone_course_rad, dtype=float)
    reference_latitude_deg = np.asarray(journey.reference_latitude_deg, dtype=float)
    reference_longitude_deg = np.asarray(journey.reference_longitude_deg, dtype=float)

    count = len(timestamps_ns)
    valid_timestamp = np.isfinite(timestamps_ns)
    valid_target_speed = (
        np.isfinite(target_speed_mps)
        & (target_speed_mps >= 0.0)
        & (target_speed_mps <= config.maximum_target_speed_mps)
    )
    valid_phone_position = _valid_latitude_longitude(phone_latitude_deg, phone_longitude_deg)
    valid_phone_accuracy = (
        np.isfinite(phone_accuracy_m)
        & (phone_accuracy_m >= 0.0)
        & (phone_accuracy_m <= config.maximum_phone_horizontal_accuracy_m)
    )
    valid_phone_speed = (
        np.isfinite(phone_speed_mps)
        & (phone_speed_mps >= 0.0)
        & (phone_speed_mps <= config.maximum_phone_speed_mps)
    )
    valid_reference_position = _valid_latitude_longitude(
        reference_latitude_deg,
        reference_longitude_deg,
    )

    primary_rejection = np.full(count, "", dtype=object)
    _set_primary_rejection(primary_rejection, ~valid_timestamp, "invalid_timestamp")
    _set_primary_rejection(primary_rejection, ~valid_target_speed, "invalid_target_speed")
    _set_primary_rejection(primary_rejection, ~valid_phone_position, "invalid_phone_position")
    _set_primary_rejection(primary_rejection, ~valid_phone_accuracy, "invalid_phone_accuracy")
    _set_primary_rejection(primary_rejection, ~valid_phone_speed, "invalid_phone_speed")
    _set_primary_rejection(
        primary_rejection,
        ~valid_reference_position,
        "invalid_reference_position",
    )

    eligible = primary_rejection == ""
    selected = np.zeros(count, dtype=bool)
    sample_period_ns = int(round(config.sample_period_s * 1e9))
    previous_selected_timestamp_ns: int | None = None
    for index in np.flatnonzero(eligible):
        timestamp_ns = int(timestamps_ns[index])
        if (
            previous_selected_timestamp_ns is None
            or timestamp_ns - previous_selected_timestamp_ns >= sample_period_ns
        ):
            selected[index] = True
            previous_selected_timestamp_ns = timestamp_ns

    usable_course = (
        np.isfinite(phone_course_rad)
        & (phone_speed_mps >= config.minimum_course_speed_mps)
    )
    normalised_course_rad = np.mod(phone_course_rad, 2.0 * pi)
    phone_reference_distance_m = _haversine_distance_m(
        phone_latitude_deg,
        phone_longitude_deg,
        reference_latitude_deg,
        reference_longitude_deg,
    )
    elapsed_s = (timestamps_ns - timestamps_ns[0]) * 1e-9

    if config.match_position_source == "phone_gnss":
        match_latitude_deg = phone_latitude_deg
        match_longitude_deg = phone_longitude_deg
    else:
        match_latitude_deg = reference_latitude_deg
        match_longitude_deg = reference_longitude_deg

    frame = pd.DataFrame(
        {
            "journey_id": journey.journey_id,
            "timestamp_ns": timestamps_ns[selected].astype(np.int64),
            "elapsed_s": elapsed_s[selected],
            "target_speed_mps": target_speed_mps[selected],
            "target_source": "can_indicated_speed",
            "match_latitude_deg": match_latitude_deg[selected],
            "match_longitude_deg": match_longitude_deg[selected],
            "match_position_source": config.match_position_source,
            "phone_latitude_deg": phone_latitude_deg[selected],
            "phone_longitude_deg": phone_longitude_deg[selected],
            "phone_altitude_m": phone_altitude_m[selected],
            "phone_speed_mps": phone_speed_mps[selected],
            "phone_horizontal_accuracy_m": phone_accuracy_m[selected],
            "phone_course_rad": normalised_course_rad[selected],
            "has_usable_phone_course": usable_course[selected],
            "reference_latitude_deg": reference_latitude_deg[selected],
            "reference_longitude_deg": reference_longitude_deg[selected],
            "phone_reference_distance_m": phone_reference_distance_m[selected],
        }
    )

    audit = RoadContextJourneyAudit(
        journey_id=journey.journey_id,
        total_rows=count,
        emitted_rows=int(selected.sum()),
        skipped_by_cadence=int((eligible & ~selected).sum()),
        rejected_invalid_timestamp=int((primary_rejection == "invalid_timestamp").sum()),
        rejected_invalid_target_speed=int((primary_rejection == "invalid_target_speed").sum()),
        rejected_invalid_phone_position=int((primary_rejection == "invalid_phone_position").sum()),
        rejected_invalid_phone_accuracy=int((primary_rejection == "invalid_phone_accuracy").sum()),
        rejected_invalid_phone_speed=int((primary_rejection == "invalid_phone_speed").sum()),
        rejected_invalid_reference_position=int(
            (primary_rejection == "invalid_reference_position").sum()
        ),
    )
    return frame.loc[:, _SOURCE_COLUMNS], audit


def _set_primary_rejection(
    primary_rejection: np.ndarray,
    rejected: np.ndarray,
    reason: str,
) -> None:
    """Assign the earliest applicable rejection reason without double-counting."""

    primary_rejection[(primary_rejection == "") & rejected] = reason


def _valid_latitude_longitude(
    latitude_deg: np.ndarray,
    longitude_deg: np.ndarray,
) -> np.ndarray:
    """Return the finite WGS-84 coordinate validity mask."""

    return (
        np.isfinite(latitude_deg)
        & np.isfinite(longitude_deg)
        & (latitude_deg >= -90.0)
        & (latitude_deg <= 90.0)
        & (longitude_deg >= -180.0)
        & (longitude_deg <= 180.0)
    )


def _haversine_distance_m(
    first_latitude_deg: np.ndarray,
    first_longitude_deg: np.ndarray,
    second_latitude_deg: np.ndarray,
    second_longitude_deg: np.ndarray,
) -> np.ndarray:
    """Return horizontal separation between paired phone/reference coordinates."""

    first_latitude_rad = np.deg2rad(first_latitude_deg)
    first_longitude_rad = np.deg2rad(first_longitude_deg)
    second_latitude_rad = np.deg2rad(second_latitude_deg)
    second_longitude_rad = np.deg2rad(second_longitude_deg)
    latitude_delta = second_latitude_rad - first_latitude_rad
    longitude_delta = second_longitude_rad - first_longitude_rad
    haversine = (
        np.square(np.sin(latitude_delta / 2.0))
        + np.cos(first_latitude_rad)
        * np.cos(second_latitude_rad)
        * np.square(np.sin(longitude_delta / 2.0))
    )
    return 2.0 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))

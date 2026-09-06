"""Tests for offline raw-to-road-context source-table preparation."""

from __future__ import annotations

import numpy as np
import pytest

from idr_backend.evaluation.replay import RawReplayJourney
from idr_backend.road_context.datasets import (
    RoadContextSourceDatasetConfig,
    build_road_context_source_dataset,
)


def _journey(
    *,
    journey_id: str = "journey-a",
    timestamps_ns: np.ndarray | None = None,
    target_speed_mps: np.ndarray | None = None,
    phone_latitude_deg: np.ndarray | None = None,
    phone_longitude_deg: np.ndarray | None = None,
    phone_speed_mps: np.ndarray | None = None,
    phone_accuracy_m: np.ndarray | None = None,
    phone_course_rad: np.ndarray | None = None,
    reference_latitude_deg: np.ndarray | None = None,
    reference_longitude_deg: np.ndarray | None = None,
) -> RawReplayJourney:
    """Build a small aligned raw fixture without replaying the live pipeline."""

    timestamps_ns = (
        np.asarray((0, 500_000_000, 1_000_000_000, 2_000_000_000, 4_000_000_000))
        if timestamps_ns is None
        else timestamps_ns
    )
    count = len(timestamps_ns)
    phone_latitude_deg = (
        np.linspace(12.9716, 12.9718, count)
        if phone_latitude_deg is None
        else phone_latitude_deg
    )
    phone_longitude_deg = (
        np.linspace(77.5946, 77.5948, count)
        if phone_longitude_deg is None
        else phone_longitude_deg
    )
    reference_latitude_deg = (
        phone_latitude_deg + 0.00001
        if reference_latitude_deg is None
        else reference_latitude_deg
    )
    reference_longitude_deg = (
        phone_longitude_deg + 0.00001
        if reference_longitude_deg is None
        else reference_longitude_deg
    )
    return RawReplayJourney(
        journey_id=journey_id,
        timestamps_ns=np.asarray(timestamps_ns, dtype=np.int64),
        acceleration_sensor_mps2=np.zeros((count, 3), dtype=float),
        angular_velocity_sensor_radps=np.zeros((count, 3), dtype=float),
        phone_latitude_deg=np.asarray(phone_latitude_deg, dtype=float),
        phone_longitude_deg=np.asarray(phone_longitude_deg, dtype=float),
        phone_altitude_m=np.full(count, 900.0),
        phone_speed_mps=np.full(count, 10.0)
        if phone_speed_mps is None
        else np.asarray(phone_speed_mps, dtype=float),
        phone_horizontal_accuracy_m=np.full(count, 5.0)
        if phone_accuracy_m is None
        else np.asarray(phone_accuracy_m, dtype=float),
        phone_course_rad=np.full(count, np.pi / 2.0)
        if phone_course_rad is None
        else np.asarray(phone_course_rad, dtype=float),
        reference_latitude_deg=np.asarray(reference_latitude_deg, dtype=float),
        reference_longitude_deg=np.asarray(reference_longitude_deg, dtype=float),
        reference_speed_mps=np.full(count, 12.0)
        if target_speed_mps is None
        else np.asarray(target_speed_mps, dtype=float),
    )


def test_source_dataset_preserves_provenance_and_samples_at_configured_cadence() -> None:
    """CAN remains an offline label while both coordinate streams are retained."""

    dataset = build_road_context_source_dataset((_journey(),))

    assert dataset.frame["timestamp_ns"].tolist() == [0, 2_000_000_000, 4_000_000_000]
    assert dataset.frame["target_speed_mps"].tolist() == [12.0, 12.0, 12.0]
    assert dataset.frame["target_source"].unique().tolist() == ["can_indicated_speed"]
    assert dataset.frame["match_position_source"].unique().tolist() == ["phone_gnss"]
    assert np.allclose(
        dataset.frame["match_latitude_deg"],
        dataset.frame["phone_latitude_deg"],
    )
    assert dataset.frame["has_usable_phone_course"].all()
    assert (dataset.frame["phone_reference_distance_m"] > 0.0).all()

    audit = dataset.audits[0]
    assert audit.total_rows == 5
    assert audit.emitted_rows == 3
    assert audit.skipped_by_cadence == 2


def test_source_dataset_uses_explicit_reference_position_when_requested() -> None:
    """The selected matching coordinate has visible provenance rather than inference."""

    dataset = build_road_context_source_dataset(
        (_journey(),),
        config=RoadContextSourceDatasetConfig(match_position_source="reference"),
    )

    assert dataset.frame["match_position_source"].unique().tolist() == ["reference"]
    assert np.allclose(
        dataset.frame["match_latitude_deg"],
        dataset.frame["reference_latitude_deg"],
    )
    assert np.allclose(
        dataset.frame["match_longitude_deg"],
        dataset.frame["reference_longitude_deg"],
    )


def test_source_dataset_records_one_primary_quality_rejection_per_raw_row() -> None:
    """Rejected rows are auditable and do not silently reach training data."""

    dataset = build_road_context_source_dataset(
        (
            _journey(
                timestamps_ns=np.asarray(
                    (0, 2_000_000_000, 4_000_000_000, 6_000_000_000, 8_000_000_000)
                ),
                target_speed_mps=np.asarray((12.0, -1.0, 12.0, 12.0, 12.0)),
                phone_latitude_deg=np.asarray((12.9716, 12.9717, 95.0, 12.9719, 12.9720)),
                phone_accuracy_m=np.asarray((5.0, 25.0, 5.0, 5.0, 5.0)),
                phone_speed_mps=np.asarray((10.0, 10.0, 10.0, -0.1, 10.0)),
                reference_latitude_deg=np.asarray((12.97161, 12.97171, 12.97181, 12.97191, 95.0)),
            ),
        )
    )

    assert dataset.frame["timestamp_ns"].tolist() == [0]
    audit = dataset.audits[0]
    assert audit.emitted_rows == 1
    assert audit.rejected_invalid_target_speed == 1
    assert audit.rejected_invalid_phone_position == 1
    assert audit.rejected_invalid_phone_speed == 1
    assert audit.rejected_invalid_reference_position == 1
    # At index one, target failure is intentionally recorded before the bad
    # phone-accuracy condition: quality reasons are disjoint and reproducible.
    assert audit.rejected_invalid_phone_accuracy == 0


def test_source_dataset_rejects_duplicate_journey_ids() -> None:
    """A journey cannot be split invisibly across folds or source batches."""

    with pytest.raises(ValueError, match="unique journey IDs"):
        build_road_context_source_dataset((_journey(), _journey()))

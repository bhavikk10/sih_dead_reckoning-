"""Offline trajectory-map-match contracts for road-context training data.

This module is offline-only. It validates candidates produced by a future
trajectory-level matcher; it does not call the live HMM or mutate navigation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from .datasets import RoadContextSourceDataset

_MATCH_COLUMNS = (
    "graph_id",
    "matched_edge_id",
    "matched_travel_direction",
    "matched_osm_way_id",
    "matched_candidate_rank",
    "matched_posterior",
    "matched_top_two_margin",
    "matched_lateral_error_m",
    "matched_heading_error_deg",
    "matched_heading_checked",
)

RoadTravelDirection = Literal["forward", "reverse"]


@dataclass(frozen=True, slots=True)
class OfflineRoadMatchConfig:
    """Frozen acceptance policy for offline training labels."""

    graph_id: str
    minimum_top_posterior: float = 0.70
    minimum_top_two_margin: float = 0.15
    maximum_lateral_error_m: float = 30.0
    maximum_heading_error_deg: float = 60.0

    def __post_init__(self) -> None:
        if not self.graph_id.strip():
            raise ValueError("graph_id must not be blank.")
        probabilities = (
            self.minimum_top_posterior,
            self.minimum_top_two_margin,
        )
        if not all(isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities):
            raise ValueError("Match probability thresholds must lie in [0, 1].")
        if not isfinite(self.maximum_lateral_error_m) or self.maximum_lateral_error_m <= 0.0:
            raise ValueError("maximum_lateral_error_m must be positive.")
        if (
            not isfinite(self.maximum_heading_error_deg)
            or not 0.0 <= self.maximum_heading_error_deg <= 180.0
        ):
            raise ValueError("maximum_heading_error_deg must lie in [0, 180].")


@dataclass(frozen=True, slots=True)
class OfflineRoadMatchCandidate:
    """One candidate emitted by an offline trajectory-level map matcher."""

    journey_id: str
    timestamp_ns: int
    graph_id: str
    edge_id: str
    travel_direction: RoadTravelDirection
    osm_way_id: str
    candidate_rank: int
    posterior: float
    lateral_error_m: float
    heading_error_deg: float | None = None

    def __post_init__(self) -> None:
        if not self.journey_id.strip() or not self.graph_id.strip():
            raise ValueError("Journey and graph IDs must not be blank.")
        if not self.edge_id.strip() or not self.osm_way_id.strip():
            raise ValueError("Edge and OSM way IDs must not be blank.")
        if self.travel_direction not in ("forward", "reverse"):
            raise ValueError("travel_direction must be 'forward' or 'reverse'.")
        if self.timestamp_ns <= 0 or self.candidate_rank < 0:
            raise ValueError("Timestamp must be positive and candidate rank non-negative.")
        if not isfinite(self.posterior) or not 0.0 <= self.posterior <= 1.0:
            raise ValueError("Candidate posterior must lie in [0, 1].")
        if not isfinite(self.lateral_error_m) or self.lateral_error_m < 0.0:
            raise ValueError("Candidate lateral error must be finite and non-negative.")
        if self.heading_error_deg is not None and (
            not isfinite(self.heading_error_deg)
            or not 0.0 <= self.heading_error_deg <= 180.0
        ):
            raise ValueError("Candidate heading error must lie in [0, 180].")


@dataclass(frozen=True, slots=True)
class RoadContextMatchAudit:
    """One primary, reproducible disposition per source row."""

    journey_id: str
    source_rows: int
    accepted_rows: int
    missing_candidates: int
    low_posterior: int
    low_margin: int
    excessive_lateral_error: int
    excessive_heading_error: int

    def __post_init__(self) -> None:
        counts = (
            self.source_rows,
            self.accepted_rows,
            self.missing_candidates,
            self.low_posterior,
            self.low_margin,
            self.excessive_lateral_error,
            self.excessive_heading_error,
        )
        if not self.journey_id.strip() or any(value < 0 for value in counts):
            raise ValueError("Match-audit identifiers and counts are invalid.")
        if self.accepted_rows > self.source_rows:
            raise ValueError("Match audit cannot accept more rows than it received.")
        if (
            self.accepted_rows
            + self.missing_candidates
            + self.low_posterior
            + self.low_margin
            + self.excessive_lateral_error
            + self.excessive_heading_error
            != self.source_rows
        ):
            raise ValueError(
                "Each source row must have exactly one match-audit disposition."
            )


@dataclass(frozen=True, slots=True)
class RoadContextMatchedDataset:
    """High-confidence source rows bound to one versioned map graph."""

    frame: pd.DataFrame
    audits: tuple[RoadContextMatchAudit, ...]
    config: OfflineRoadMatchConfig

    def __post_init__(self) -> None:
        if self.frame.empty or not self.audits:
            raise ValueError("Matched road-context data requires rows and audits.")
        if not set(_MATCH_COLUMNS).issubset(self.frame.columns):
            raise ValueError("Matched road-context frame lacks required match columns.")
        if self.frame.duplicated(["journey_id", "timestamp_ns"]).any():
            raise ValueError("A source timestamp may have only one accepted road match.")
        if not self.frame["graph_id"].eq(self.config.graph_id).all():
            raise ValueError("Matched rows belong to a different graph version.")
        if not self.frame["matched_candidate_rank"].eq(0).all():
            raise ValueError("Accepted rows must retain only the top-ranked candidate.")
        if not self.frame["matched_travel_direction"].isin(("forward", "reverse")).all():
            raise ValueError("Matched rows have an invalid travel direction.")


def build_matched_road_context_dataset(
    source: RoadContextSourceDataset,
    candidates: Iterable[OfflineRoadMatchCandidate],
    *,
    config: OfflineRoadMatchConfig,
) -> RoadContextMatchedDataset:
    """Join high-confidence offline matches to sparse source rows.

    Candidate rows must come from a trajectory-level matcher and include all
    retained probability mass for each source timestamp.
    """

    source_keys = {
        (str(row.journey_id), int(row.timestamp_ns))
        for row in source.frame.itertuples(index=False)
    }
    candidates_by_key: dict[
        tuple[str, int], list[OfflineRoadMatchCandidate]
    ] = {}

    for candidate in candidates:
        if candidate.graph_id != config.graph_id:
            raise ValueError("Offline candidate graph_id differs from configured graph.")
        key = (candidate.journey_id, candidate.timestamp_ns)
        if key not in source_keys:
            raise ValueError(f"Matcher emitted a candidate for unknown source row: {key}.")
        candidates_by_key.setdefault(key, []).append(candidate)

    accepted_records: list[dict[str, object]] = []
    audits: list[RoadContextMatchAudit] = []

    for journey_id, journey_rows in source.frame.groupby("journey_id", sort=False):
        counts = {
            "source_rows": 0,
            "accepted_rows": 0,
            "missing_candidates": 0,
            "low_posterior": 0,
            "low_margin": 0,
            "excessive_lateral_error": 0,
            "excessive_heading_error": 0,
        }

        for source_row in journey_rows.itertuples(index=False):
            counts["source_rows"] += 1
            key = (str(source_row.journey_id), int(source_row.timestamp_ns))
            row_candidates = candidates_by_key.get(key, [])

            if not row_candidates:
                counts["missing_candidates"] += 1
                continue

            row_candidates = sorted(row_candidates, key=lambda item: item.candidate_rank)
            ranks = [item.candidate_rank for item in row_candidates]

            if ranks[0] != 0 or len(set(ranks)) != len(ranks):
                raise ValueError(f"Invalid candidate ranks for source row {key}.")

            probability_mass = sum(item.posterior for item in row_candidates)
            if not np.isclose(probability_mass, 1.0, atol=1e-6):
                raise ValueError(
                    f"Candidate probabilities for {key} sum to {probability_mass:.6f}, not 1."
                )

            best = row_candidates[0]
            runner_up_posterior = (
                row_candidates[1].posterior if len(row_candidates) > 1 else 0.0
            )
            top_two_margin = best.posterior - runner_up_posterior

            if best.posterior < config.minimum_top_posterior:
                counts["low_posterior"] += 1
                continue
            if top_two_margin < config.minimum_top_two_margin:
                counts["low_margin"] += 1
                continue
            if best.lateral_error_m > config.maximum_lateral_error_m:
                counts["excessive_lateral_error"] += 1
                continue

            heading_checked = bool(source_row.has_usable_phone_course)
            if heading_checked and (
                best.heading_error_deg is None
                or best.heading_error_deg > config.maximum_heading_error_deg
            ):
                counts["excessive_heading_error"] += 1
                continue

            record = source_row._asdict()
            record.update(
                {
                    "graph_id": config.graph_id,
                    "matched_travel_direction": best.travel_direction,
                    "matched_edge_id": best.edge_id,
                    "matched_osm_way_id": best.osm_way_id,
                    "matched_candidate_rank": best.candidate_rank,
                    "matched_posterior": best.posterior,
                    "matched_top_two_margin": top_two_margin,
                    "matched_lateral_error_m": best.lateral_error_m,
                    "matched_heading_error_deg": best.heading_error_deg,
                    "matched_heading_checked": heading_checked,
                }
            )
            accepted_records.append(record)
            counts["accepted_rows"] += 1

        audits.append(RoadContextMatchAudit(journey_id=str(journey_id), **counts))

    if not accepted_records:
        raise ValueError("No source rows passed the offline map-match policy.")

    column_order = [*source.frame.columns, *_MATCH_COLUMNS]
    frame = pd.DataFrame.from_records(accepted_records).loc[:, column_order]

    return RoadContextMatchedDataset(
        frame=frame,
        audits=tuple(audits),
        config=config,
    )

"""Leak-free static road-context feature construction.

This module is offline-only. It accepts high-confidence matched rows plus
versioned static edge facts. It does not consume IMU, GRU, EKF speed, GNSS
speed, HMM confidence, or monotonic elapsed time as a proxy for clock time.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np
import pandas as pd

from .offline_matching import (
    RoadContextMatchedDataset,
    RoadTravelDirection,
)

ROAD_CONTEXT_FEATURE_NAMES = (
    "road_class",
    "road_class_known",
    "speed_limit_mps",
    "speed_limit_known",
    "lane_count",
    "lane_count_known",
    "is_oneway",
    "is_link",
    "is_tunnel",
    "is_bridge",
    "is_roundabout",
    "edge_length_m",
    "mean_abs_curvature_rad_per_m",
    "p95_abs_curvature_rad_per_m",
    "from_node_degree",
    "to_node_degree",
)

_TARGET_COLUMN = "target_speed_mps"


@dataclass(frozen=True, slots=True)
class RoadContextEdgeFeatures:
    """Static, versioned facts for one directed OSM-derived edge.

    Missing OSM tags remain ``None``. They become NaN plus an explicit
    missingness flag in the training feature table; we never invent a limit,
    lane count. Distance-to-junction and distance-to-signal require a matched
    position along an edge, so they are deliberately deferred until the
    matching contract retains that offset.
    """

    graph_id: str
    edge_id: str
    travel_direction: RoadTravelDirection
    osm_way_id: str
    road_class: str | None
    speed_limit_mps: float | None
    lane_count: int | None
    is_oneway: bool
    is_link: bool
    is_tunnel: bool
    is_bridge: bool
    is_roundabout: bool
    edge_length_m: float
    mean_abs_curvature_rad_per_m: float
    p95_abs_curvature_rad_per_m: float
    from_node_degree: int
    to_node_degree: int

    def __post_init__(self) -> None:
        if (
            not self.graph_id.strip()
            or not self.edge_id.strip()
            or not self.osm_way_id.strip()
        ):
            raise ValueError("Edge graph_id, edge_id, and OSM way ID must not be blank.")

        if self.travel_direction not in ("forward", "reverse"):
            raise ValueError("travel_direction must be 'forward' or 'reverse'.")

        required_nonnegative = (
            self.edge_length_m,
            self.mean_abs_curvature_rad_per_m,
            self.p95_abs_curvature_rad_per_m,
        )
        if not all(isfinite(value) and value >= 0.0 for value in required_nonnegative):
            raise ValueError("Required edge geometry values must be finite and non-negative.")

        if self.speed_limit_mps is not None and (
            not isfinite(self.speed_limit_mps) or self.speed_limit_mps < 0.0
        ):
            raise ValueError("Optional edge speed limits must be non-negative.")

        if self.lane_count is not None and self.lane_count <= 0:
            raise ValueError("lane_count must be positive when available.")
        if self.from_node_degree < 0 or self.to_node_degree < 0:
            raise ValueError("Topology degrees must be non-negative.")


@dataclass(frozen=True, slots=True)
class RoadContextFeatureDataset:
    """Offline training rows with a strict target/feature boundary."""

    frame: pd.DataFrame
    graph_id: str

    def __post_init__(self) -> None:
        if self.frame.empty:
            raise ValueError("Road-context feature dataset must not be empty.")
        if not self.graph_id.strip():
            raise ValueError("Feature dataset graph_id must not be blank.")
        if not set(ROAD_CONTEXT_FEATURE_NAMES).issubset(self.frame.columns):
            raise ValueError("Feature frame lacks the declared feature schema.")
        if _TARGET_COLUMN not in self.frame.columns:
            raise ValueError("Feature frame lacks the offline CAN-speed target.")
        if not self.frame["graph_id"].eq(self.graph_id).all():
            raise ValueError("Feature rows span more than one graph version.")
        targets = self.frame[_TARGET_COLUMN].to_numpy(dtype=float)
        if not np.isfinite(targets).all() or (targets < 0.0).any():
            raise ValueError("Offline CAN-speed targets must be finite and non-negative.")

    @property
    def model_features(self) -> pd.DataFrame:
        """Return only runtime-permitted learned-model inputs."""

        return self.frame.loc[:, ROAD_CONTEXT_FEATURE_NAMES].copy()

    @property
    def targets_mps(self) -> pd.Series:
        """Return CAN speed for offline training only."""

        return self.frame[_TARGET_COLUMN].copy()


def build_road_context_feature_dataset(
    matched: RoadContextMatchedDataset,
    edge_features: Iterable[RoadContextEdgeFeatures],
) -> RoadContextFeatureDataset:
    """Attach static edge facts to accepted matched source rows."""

    edge_by_traversal: dict[
        tuple[str, RoadTravelDirection], RoadContextEdgeFeatures
    ] = {}

    for edge in edge_features:
        if edge.graph_id != matched.config.graph_id:
            raise ValueError(
                "Edge feature graph_id differs from matched-data graph_id."
            )
        edge_key = (edge.edge_id, edge.travel_direction)
        if edge_key in edge_by_traversal:
            raise ValueError(
                f"Duplicate static features for directed edge {edge_key!r}."
            )
        edge_by_traversal[edge_key] = edge

    matched_edge_ids = {
        (row.matched_edge_id, row.matched_travel_direction)
        for row in matched.frame.itertuples(index=False)
    }
    missing_edges = matched_edge_ids.difference(edge_by_traversal)

    if missing_edges:
        raise ValueError(
            f"{len(missing_edges)} accepted matched edges lack static graph features."
        )

    records: list[dict[str, object]] = []

    for row in matched.frame.itertuples(index=False):
        edge = edge_by_traversal[
            (row.matched_edge_id, row.matched_travel_direction)
        ]
        if row.matched_osm_way_id != edge.osm_way_id:
            raise ValueError(
                "Matched OSM way ID differs from the graph edge's source way ID."
            )
        record = row._asdict()

        record.update(
            {
                "road_class": edge.road_class or "<unknown>",
                "road_class_known": edge.road_class is not None,
                "speed_limit_mps": (
                    np.nan if edge.speed_limit_mps is None else edge.speed_limit_mps
                ),
                "speed_limit_known": edge.speed_limit_mps is not None,
                "lane_count": np.nan if edge.lane_count is None else edge.lane_count,
                "lane_count_known": edge.lane_count is not None,
                "is_oneway": edge.is_oneway,
                "is_link": edge.is_link,
                "is_tunnel": edge.is_tunnel,
                "is_bridge": edge.is_bridge,
                "is_roundabout": edge.is_roundabout,
                "edge_length_m": edge.edge_length_m,
                "mean_abs_curvature_rad_per_m": edge.mean_abs_curvature_rad_per_m,
                "p95_abs_curvature_rad_per_m": edge.p95_abs_curvature_rad_per_m,
                "from_node_degree": edge.from_node_degree,
                "to_node_degree": edge.to_node_degree,
            }
        )
        records.append(record)

    frame = pd.DataFrame.from_records(records)

    # CAN speed is present for offline supervision but cannot enter model_features.
    assert _TARGET_COLUMN not in ROAD_CONTEXT_FEATURE_NAMES

    return RoadContextFeatureDataset(
        frame=frame,
        graph_id=matched.config.graph_id,
    )

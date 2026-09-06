"""Offline road-match and static-feature contract tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from idr_backend.road_context.datasets import (
    RoadContextJourneyAudit,
    RoadContextSourceDataset,
    RoadContextSourceDatasetConfig,
    _SOURCE_COLUMNS,
)
from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextEdgeFeatures,
    build_road_context_feature_dataset,
)
from idr_backend.road_context.offline_matching import (
    OfflineRoadMatchCandidate,
    OfflineRoadMatchConfig,
    build_matched_road_context_dataset,
)


def _source_dataset() -> RoadContextSourceDataset:
    """Return one source row with a valid CAN target and GNSS provenance."""

    frame = pd.DataFrame(
        [
            {
                "journey_id": "journey-1",
                "timestamp_ns": 1_000_000_000,
                "elapsed_s": 0.0,
                "target_speed_mps": 12.0,
                "target_source": "can_indicated_speed",
                "match_latitude_deg": 12.0,
                "match_longitude_deg": 77.0,
                "match_position_source": "phone_gnss",
                "phone_latitude_deg": 12.0,
                "phone_longitude_deg": 77.0,
                "phone_altitude_m": 900.0,
                "phone_speed_mps": 12.0,
                "phone_horizontal_accuracy_m": 5.0,
                "phone_course_rad": 0.0,
                "has_usable_phone_course": True,
                "reference_latitude_deg": 12.0,
                "reference_longitude_deg": 77.0,
                "phone_reference_distance_m": 0.0,
            }
        ],
        columns=_SOURCE_COLUMNS,
    )
    return RoadContextSourceDataset(
        frame=frame,
        audits=(
            RoadContextJourneyAudit(
                journey_id="journey-1",
                total_rows=1,
                emitted_rows=1,
                skipped_by_cadence=0,
                rejected_invalid_timestamp=0,
                rejected_invalid_target_speed=0,
                rejected_invalid_phone_position=0,
                rejected_invalid_phone_accuracy=0,
                rejected_invalid_phone_speed=0,
                rejected_invalid_reference_position=0,
            ),
        ),
        config=RoadContextSourceDatasetConfig(),
    )


def test_directed_match_joins_only_matching_directed_edge_features() -> None:
    """A reverse match must not accidentally receive forward-edge facts."""

    config = OfflineRoadMatchConfig(graph_id="graph-v1")
    matched = build_matched_road_context_dataset(
        _source_dataset(),
        [
            OfflineRoadMatchCandidate(
                journey_id="journey-1",
                timestamp_ns=1_000_000_000,
                graph_id="graph-v1",
                edge_id="edge-1",
                travel_direction="reverse",
                osm_way_id="way-1",
                candidate_rank=0,
                posterior=1.0,
                lateral_error_m=2.0,
                heading_error_deg=3.0,
            )
        ],
        config=config,
    )
    feature_dataset = build_road_context_feature_dataset(
        matched,
        [
            RoadContextEdgeFeatures(
                graph_id="graph-v1",
                edge_id="edge-1",
                travel_direction="reverse",
                osm_way_id="way-1",
                road_class="residential",
                speed_limit_mps=None,
                lane_count=None,
                is_oneway=False,
                is_link=False,
                is_tunnel=False,
                is_bridge=False,
                is_roundabout=False,
                edge_length_m=100.0,
                mean_abs_curvature_rad_per_m=0.01,
                p95_abs_curvature_rad_per_m=0.02,
                from_node_degree=2,
                to_node_degree=3,
            )
        ],
    )

    assert tuple(feature_dataset.model_features.columns) == ROAD_CONTEXT_FEATURE_NAMES
    assert feature_dataset.targets_mps.tolist() == [12.0]
    assert np.isnan(feature_dataset.model_features.loc[0, "speed_limit_mps"])
    assert feature_dataset.model_features.loc[0, "road_class"] == "residential"

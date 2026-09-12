"""Tests for the decision-only road-context runtime adapter."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from idr_backend.map_matching.graph import (
    MapEnuReference,
    RoadGraph,
    RoadGraphMetadata,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from idr_backend.pipeline.feedback import (
    CandidateBelief,
    FeedbackDisposition,
    FeedbackLookup,
    MapMatchFeedback,
)
from idr_backend.pipeline.road_context import RoadContextCandidatePipeline
from idr_backend.road_context.features import ROAD_CONTEXT_FEATURE_NAMES
from idr_backend.road_context.priors import RoadContextMixtureDisposition
from idr_backend.road_context.quantile_model import RoadContextQuantileModelMetadata
from idr_backend.road_context.rules import RoadContextQuantilePrediction
from idr_backend.sensors.types import CoordinateFrame, RoadCandidate, TravelDirection


_GRAPH_ID = "road-context-pipeline-test-v1"


def _graph() -> RoadGraph:
    attributes = RoadSegmentAttributes(
        road_class="residential",
        source_way_id="fixture-way",
        speed_limit_mps=20.0,
        lane_count=1,
    )
    return RoadGraph(
        metadata=RoadGraphMetadata(
            graph_id=_GRAPH_ID,
            region_id="fixture-region",
            source_dataset="openstreetmap",
            source_version="2026-09-07",
            enu_reference=MapEnuReference(latitude_deg=12.9716, longitude_deg=77.5946),
            coordinate_frame=CoordinateFrame.NAVIGATION_ENU,
        ),
        nodes=(
            RoadNode("a", (0.0, 0.0)),
            RoadNode("b", (0.0, 100.0)),
            RoadNode("c", (10.0, 0.0)),
            RoadNode("d", (10.0, 100.0)),
        ),
        segments=(
            RoadSegment(
                edge_id="main-road",
                start_node_id="a",
                end_node_id="b",
                centerline_enu_m=((0.0, 0.0), (0.0, 100.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=True,
            ),
            RoadSegment(
                edge_id="parallel-road",
                start_node_id="c",
                end_node_id="d",
                centerline_enu_m=((10.0, 0.0), (10.0, 100.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=False,
            ),
        ),
    )


def _candidate(candidate_id: str, edge_id: str) -> RoadCandidate:
    return RoadCandidate(
        timestamp_ns=100,
        candidate_id=candidate_id,
        graph_id=_GRAPH_ID,
        edge_id=edge_id,
        travel_direction=TravelDirection.FORWARD,
        snap_position_enu_m=(0.0, 20.0),
        lateral_distance_m=1.0,
        road_heading_enu_rad=0.0,
    )


@dataclass(frozen=True, slots=True)
class _StaticPredictor:
    metadata: RoadContextQuantileModelMetadata

    def predict(
        self,
        features: pd.DataFrame,
    ) -> tuple[RoadContextQuantilePrediction, ...]:
        assert tuple(features.columns) == ROAD_CONTEXT_FEATURE_NAMES
        assert "target_speed_mps" not in features.columns
        return tuple(
            RoadContextQuantilePrediction(
                model_id=self.metadata.model_id,
                speed_p10_mps=8.0,
                speed_p50_mps=10.0,
                speed_p90_mps=12.0,
            )
            for _ in range(len(features))
        )


def _predictor() -> _StaticPredictor:
    return _StaticPredictor(
        metadata=RoadContextQuantileModelMetadata(
            model_id="static-test-model",
            graph_id=_GRAPH_ID,
            feature_names=ROAD_CONTEXT_FEATURE_NAMES,
            training_kind="test",
        )
    )


def test_adapter_uses_prior_feedback_and_stops_before_ekf_fusion() -> None:
    main_candidate = _candidate("main", "main-road")
    parallel_candidate = _candidate("parallel", "parallel-road")
    lookup = FeedbackLookup(
        disposition=FeedbackDisposition.AVAILABLE,
        feedback=MapMatchFeedback(
            timestamp_ns=100,
            graph_id=_GRAPH_ID,
            candidate_beliefs=(
                CandidateBelief(candidate=main_candidate, probability=0.75),
                CandidateBelief(candidate=parallel_candidate, probability=0.25),
            ),
            selected_candidate_id=main_candidate.candidate_id,
            map_match_confidence=0.75,
        ),
        age_s=0.1,
    )

    decision = RoadContextCandidatePipeline(
        graph=_graph(),
        predictor=_predictor(),
    ).decision_for_cycle(cycle_timestamp_ns=200, feedback_lookup=lookup)

    assert decision.disposition is RoadContextMixtureDisposition.AVAILABLE
    assert decision.source_belief_timestamp_ns == 100
    assert decision.speed_mean_mps == 10.0
    assert decision.speed_variance_m2ps2 is not None
    assert decision.speed_variance_m2ps2 > 0.0
    assert len(decision.contributions) == 2


def test_adapter_omits_feedback_from_another_graph() -> None:
    foreign_candidate = RoadCandidate(
        timestamp_ns=100,
        candidate_id="foreign",
        graph_id="other-graph",
        edge_id="main-road",
        travel_direction=TravelDirection.FORWARD,
        snap_position_enu_m=(0.0, 20.0),
        lateral_distance_m=1.0,
        road_heading_enu_rad=0.0,
    )
    lookup = FeedbackLookup(
        disposition=FeedbackDisposition.AVAILABLE,
        feedback=MapMatchFeedback(
            timestamp_ns=100,
            graph_id="other-graph",
            candidate_beliefs=(
                CandidateBelief(candidate=foreign_candidate, probability=1.0),
            ),
            selected_candidate_id=foreign_candidate.candidate_id,
            map_match_confidence=1.0,
        ),
        age_s=0.1,
    )

    decision = RoadContextCandidatePipeline(
        graph=_graph(),
        predictor=_predictor(),
    ).decision_for_cycle(cycle_timestamp_ns=200, feedback_lookup=lookup)

    assert decision.disposition is RoadContextMixtureDisposition.GRAPH_MISMATCH
    assert decision.speed_mean_mps is None

"""Tests for independent bounded HMM map-matching composition."""

from idr_backend.map_matching.candidates import CandidateGenerationConfig
from idr_backend.map_matching.graph import (
    MapEnuReference,
    RoadGraph,
    RoadGraphMetadata,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from idr_backend.map_matching.pipeline import IncrementalMapMatchingPipeline
from idr_backend.map_matching.scoring import MapMatchingScoringConfig
from idr_backend.map_matching.viterbi import (
    IncrementalViterbiConfig,
    ViterbiDisposition,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    NavigationEstimate,
    NavigationMode,
)


def _graph() -> RoadGraph:
    """Build one northbound route plus a plausible parallel-road ambiguity."""

    attributes = RoadSegmentAttributes(
        road_class="residential",
        source_way_id="fixture-way",
        speed_limit_mps=12.0,
        lane_count=1,
    )
    return RoadGraph(
        metadata=RoadGraphMetadata(
            graph_id="matching-pipeline-v1",
            region_id="fixture-region",
            source_dataset="openstreetmap",
            source_version="fixture",
            enu_reference=MapEnuReference(12.0, 77.0),
            coordinate_frame=CoordinateFrame.NAVIGATION_ENU,
        ),
        nodes=(
            RoadNode("main-start", (0.0, 0.0)),
            RoadNode("main-end", (0.0, 100.0)),
            RoadNode("parallel-start", (6.0, 0.0)),
            RoadNode("parallel-end", (6.0, 100.0)),
        ),
        segments=(
            RoadSegment(
                edge_id="main-road",
                start_node_id="main-start",
                end_node_id="main-end",
                centerline_enu_m=((0.0, 0.0), (0.0, 100.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=True,
            ),
            RoadSegment(
                edge_id="parallel-road",
                start_node_id="parallel-start",
                end_node_id="parallel-end",
                centerline_enu_m=((6.0, 0.0), (6.0, 100.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=False,
            ),
        ),
    )


def _estimate(timestamp_ns: int, north_m: float, east_m: float = 0.25) -> NavigationEstimate:
    """Create a northbound EKF publication in the graph's exact ENU frame."""

    return NavigationEstimate(
        timestamp_ns=timestamp_ns,
        mode=NavigationMode.DEAD_RECKONING,
        position_enu_m=(east_m, north_m, 0.0),
        velocity_enu_mps=(0.0, 5.0, 0.0),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        position_covariance_enu_m2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 2.0)),
        velocity_covariance_enu_m2ps2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        heading_variance_rad2=0.05,
        matched_road_edge_id=None,
        map_match_confidence=None,
    )


def _pipeline() -> IncrementalMapMatchingPipeline:
    """Use compact deterministic bounds that retain both fixture roads."""

    return IncrementalMapMatchingPipeline(
        graph=_graph(),
        candidate_config=CandidateGenerationConfig(
            minimum_search_radius_m=8.0,
            maximum_search_radius_m=8.0,
            position_sigma_multiplier=2.0,
            maximum_candidate_count=4,
            minimum_heading_speed_mps=0.5,
            heading_rank_weight=0.5,
            maximum_prior_belief_age_ns=2_000_000_000,
            prior_belief_rank_bonus=0.2,
        ),
        scoring_config=MapMatchingScoringConfig(
            position_std_floor_m=1.0,
            minimum_heading_speed_mps=0.5,
            heading_std_floor_rad=0.2,
            speed_limit_tolerance_mps=2.0,
            speed_limit_std_mps=3.0,
            speed_limit_penalty_weight=0.1,
            transition_distance_std_floor_m=1.0,
            transition_position_uncertainty_multiplier=1.0,
            transition_route_slack_m=5.0,
            maximum_route_distance_m=80.0,
        ),
        viterbi_config=IncrementalViterbiConfig(
            backtracking_window_steps=2,
            maximum_cycle_gap_ns=500_000_000,
            minimum_publish_confidence=0.0,
        ),
    )


def test_pipeline_commits_the_delayed_estimate_with_a_stable_road() -> None:
    """A commit decorates the original estimate, not the newest EKF timestamp."""

    pipeline = _pipeline()
    results = tuple(
        pipeline.update(_estimate(timestamp_ns, north_m))
        for timestamp_ns, north_m in (
            (1_000_000_000, 0.0),
            (1_100_000_000, 0.5),
            (1_200_000_000, 1.0),
            (1_300_000_000, 1.5),
        )
    )

    assert results[0].viterbi.disposition is ViterbiDisposition.INITIALIZED
    committed = results[-1].committed_navigation_estimate
    assert committed is not None
    assert committed.timestamp_ns == 1_000_000_000
    assert committed.matched_road_edge_id == "main-road"
    assert committed.map_match_confidence is not None
    assert committed.map_match_confidence > 0.0


def test_pipeline_resets_route_history_when_current_estimate_leaves_graph() -> None:
    """No map coverage must clear continuity rather than retain a stale route."""

    pipeline = _pipeline()
    pipeline.update(_estimate(1_000_000_000, 0.0))
    no_coverage = pipeline.update(_estimate(1_100_000_000, 0.5, east_m=500.0))

    assert no_coverage.viterbi.disposition is ViterbiDisposition.RESET_NO_CANDIDATES
    assert no_coverage.viterbi.current_belief is None
    assert no_coverage.committed_navigation_estimate is None

"""Tests for bounded, causal road-candidate generation."""

from math import pi

import pytest

from idr_backend.map_matching.candidates import (
    CandidateGenerationConfig,
    CandidateGenerationDisposition,
    PreviousTraversalBelief,
    RoadCandidateGenerator,
    project_point_to_polyline,
)
from idr_backend.map_matching.graph import (
    DirectedRoadTraversal,
    MapEnuReference,
    RoadGraph,
    RoadGraphMetadata,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    NavigationEstimate,
    NavigationMode,
    TravelDirection,
)


def _config() -> CandidateGenerationConfig:
    """Use small explicit bounds, making each fixture expectation exact."""

    return CandidateGenerationConfig(
        minimum_search_radius_m=2.0,
        maximum_search_radius_m=8.0,
        position_sigma_multiplier=2.0,
        maximum_candidate_count=4,
        minimum_heading_speed_mps=0.5,
        heading_rank_weight=0.5,
        maximum_prior_belief_age_ns=100,
        prior_belief_rank_bonus=1.0,
    )


def _fixture_graph() -> RoadGraph:
    """Build two nearby northbound roads.

    main-road is bidirectional at east=0.
    parallel-road is northbound-only at east=4.

          north
            ^
      x=0   │ main-road
      x=4   │ parallel-road
    """

    metadata = RoadGraphMetadata(
        graph_id="candidate-fixture-v1",
        region_id="candidate-fixture-region",
        source_dataset="openstreetmap",
        source_version="2026-09-05",
        enu_reference=MapEnuReference(
            latitude_deg=12.9716,
            longitude_deg=77.5946,
        ),
        coordinate_frame=CoordinateFrame.NAVIGATION_ENU,
    )

    attributes = RoadSegmentAttributes(
        road_class="residential",
        source_way_id="fixture-way",
        speed_limit_mps=8.33,
        lane_count=1,
    )

    return RoadGraph(
        metadata=metadata,
        nodes=(
            RoadNode("main-start", (0.0, 0.0)),
            RoadNode("main-end", (0.0, 20.0)),
            RoadNode("parallel-start", (4.0, 0.0)),
            RoadNode("parallel-end", (4.0, 20.0)),
        ),
        segments=(
            RoadSegment(
                edge_id="main-road",
                start_node_id="main-start",
                end_node_id="main-end",
                centerline_enu_m=((0.0, 0.0), (0.0, 20.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=True,
            ),
            RoadSegment(
                edge_id="parallel-road",
                start_node_id="parallel-start",
                end_node_id="parallel-end",
                centerline_enu_m=((4.0, 0.0), (4.0, 20.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=False,
            ),
        ),
    )


def _estimate(
    *,
    timestamp_ns: int = 1_000,
    east_m: float = 0.5,
    north_m: float = 10.0,
    east_velocity_mps: float = 0.0,
    north_velocity_mps: float = 2.0,
    position_standard_deviation_m: float = 1.0,
) -> NavigationEstimate:
    """Create a minimal valid EKF output in the graph's shared ENU frame."""

    position_variance_m2 = position_standard_deviation_m**2

    return NavigationEstimate(
        timestamp_ns=timestamp_ns,
        mode=NavigationMode.DEAD_RECKONING,
        position_enu_m=(east_m, north_m, 0.0),
        velocity_enu_mps=(
            east_velocity_mps,
            north_velocity_mps,
            0.0,
        ),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        position_covariance_enu_m2=(
            (position_variance_m2, 0.0, 0.0),
            (0.0, position_variance_m2, 0.0),
            (0.0, 0.0, 1.0),
        ),
        velocity_covariance_enu_m2ps2=(
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        ),
        heading_variance_rad2=0.1,
        matched_road_edge_id=None,
        map_match_confidence=None,
    )


def test_polyline_projection_returns_snap_distance_and_progress() -> None:
    """Projection preserves both lateral evidence and traversal progress."""

    projection = project_point_to_polyline(
        point_enu_m=(3.0, 8.0),
        geometry_enu_m=((0.0, 0.0), (0.0, 10.0)),
    )

    assert projection.snap_position_enu_m == pytest.approx((0.0, 8.0))
    assert projection.lateral_distance_m == pytest.approx(3.0)
    assert projection.along_traversal_m == pytest.approx(8.0)
    assert projection.traversal_length_m == pytest.approx(10.0)
    assert projection.traversal_fraction == pytest.approx(0.8)


def test_generator_uses_bounded_covariance_search_and_heading_ranking() -> None:
    """Low EKF uncertainty selects nearby roads and prefers travel direction."""

    generator = RoadCandidateGenerator(
        graph=_fixture_graph(),
        config=_config(),
    )

    result = generator.generate(estimate=_estimate())

    # One-sigma = 1 m and multiplier = 2, so the configured minimum is exactly
    # the resulting radius. The parallel road is 3.5 m away and excluded.
    assert result.search_radius_m == pytest.approx(2.0)
    assert result.disposition is (
        CandidateGenerationDisposition.CANDIDATES_GENERATED
    )
    assert result.queried_traversal_count == 2

    # EKF velocity is northbound. Both directions are geometrically possible,
    # but heading ranking publishes main-road forward before reverse.
    assert tuple(
        candidate.candidate_id for candidate in result.candidates
    ) == (
        "main-road:forward",
        "main-road:reverse",
    )

    first_candidate = result.candidates[0]
    assert first_candidate.snap_position_enu_m == pytest.approx((0.0, 10.0))
    assert first_candidate.lateral_distance_m == pytest.approx(0.5)
    assert first_candidate.road_heading_enu_rad == pytest.approx(0.0)


def test_larger_position_covariance_widens_search_without_becoming_unbounded() -> None:
    """Uncertainty admits parallel hypotheses but remains below the hard cap."""

    generator = RoadCandidateGenerator(
        graph=_fixture_graph(),
        config=_config(),
    )

    result = generator.generate(
        estimate=_estimate(position_standard_deviation_m=3.0)
    )

    # 3 sigma metres × multiplier 2 = 6 m. This includes the road at east=4.
    assert result.search_radius_m == pytest.approx(6.0)
    assert {
        candidate.candidate_id for candidate in result.candidates
    } == {
        "main-road:forward",
        "main-road:reverse",
        "parallel-road:forward",
    }


def test_recent_prior_belief_can_rank_a_nearby_reverse_traversal_first() -> None:
    """Prior Viterbi belief influences rank only after geometry admits a road."""

    graph = _fixture_graph()
    generator = RoadCandidateGenerator(graph=graph, config=_config())

    reverse_main_road = DirectedRoadTraversal(
        edge_id="main-road",
        travel_direction=TravelDirection.REVERSE,
    )
    result = generator.generate(
        estimate=_estimate(),
        prior_beliefs=(
            PreviousTraversalBelief(
                source_belief_timestamp_ns=999,
                traversal=reverse_main_road,
                probability=1.0,
            ),
        ),
    )

    assert result.usable_prior_belief_count == 1

    # A strong, causal prior offsets the northbound heading preference. It does
    # not invent a road candidate: reverse main-road was already near the EKF.
    assert result.candidates[0].candidate_id == "main-road:reverse"
    assert result.candidates[0].road_heading_enu_rad == pytest.approx(pi)


def test_stale_prior_belief_is_ignored() -> None:
    """Old Viterbi state cannot bias the current navigation estimate forever."""

    graph = _fixture_graph()
    generator = RoadCandidateGenerator(graph=graph, config=_config())

    reverse_main_road = DirectedRoadTraversal(
        edge_id="main-road",
        travel_direction=TravelDirection.REVERSE,
    )
    result = generator.generate(
        estimate=_estimate(),
        prior_beliefs=(
            PreviousTraversalBelief(
                # Age 101 ns exceeds the configuration's 100 ns limit.
                source_belief_timestamp_ns=899,
                traversal=reverse_main_road,
                probability=1.0,
            ),
        ),
    )

    assert result.usable_prior_belief_count == 0
    assert result.candidates[0].candidate_id == "main-road:forward"


def test_future_prior_belief_is_rejected_to_preserve_causality() -> None:
    """Candidate generation must never consume same-or-future cycle belief."""

    graph = _fixture_graph()
    generator = RoadCandidateGenerator(graph=graph, config=_config())

    with pytest.raises(ValueError, match="predate"):
        generator.generate(
            estimate=_estimate(timestamp_ns=1_000),
            prior_beliefs=(
                PreviousTraversalBelief(
                    source_belief_timestamp_ns=1_000,
                    traversal=DirectedRoadTraversal(
                        edge_id="main-road",
                        travel_direction=TravelDirection.FORWARD,
                    ),
                    probability=0.8,
                ),
            ),
        )


def test_generator_reports_no_graph_coverage_for_far_away_estimate() -> None:
    """No plausible local road is an explicit result, never a fabricated match."""

    generator = RoadCandidateGenerator(
        graph=_fixture_graph(),
        config=_config(),
    )

    result = generator.generate(
        estimate=_estimate(east_m=100.0, north_m=100.0)
    )

    assert result.disposition is (
        CandidateGenerationDisposition.NO_GRAPH_COVERAGE
    )
    assert result.candidates == ()



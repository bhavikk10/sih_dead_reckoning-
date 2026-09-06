"""Tests for immutable directed road-graph topology and geometry."""

from math import pi

import pytest

from idr_backend.map_matching.graph import (
    DirectedRoadTraversal,
    MapEnuReference,
    RoadGraph,
    RoadGraphCoordinateError,
    RoadGraphMetadata,
    RoadGraphTopologyError,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    TravelDirection,
)


def _metadata() -> RoadGraphMetadata:
    """Create stable ENU provenance for each small in-memory fixture graph."""

    return RoadGraphMetadata(
        graph_id="fixture-graph-v1",
        region_id="fixture-region",
        source_dataset="openstreetmap",
        source_version="2026-09-05",
        enu_reference=MapEnuReference(
            latitude_deg=12.9716,
            longitude_deg=77.5946,
        ),
        coordinate_frame=CoordinateFrame.NAVIGATION_ENU,
    )


def _attributes(
    *,
    road_class: str = "residential",
) -> RoadSegmentAttributes:
    """Create minimal valid static OSM facts for a fixture road."""

    return RoadSegmentAttributes(
        road_class=road_class,
        source_way_id=f"way-{road_class}",
        speed_limit_mps=8.33,
        lane_count=1,
    )


def _fixture_graph() -> RoadGraph:
    """Build a two-way north road followed by a one-way east road.

        n0 ── north-road ── n1 ── east-road ──> n2
    """

    nodes = (
        RoadNode(
            node_id="n0",
            position_enu_m=(0.0, 0.0),
        ),
        RoadNode(
            node_id="n1",
            position_enu_m=(0.0, 10.0),
            is_intersection=True,
            has_traffic_signal=True,
        ),
        RoadNode(
            node_id="n2",
            position_enu_m=(10.0, 10.0),
        ),
    )

    segments = (
        RoadSegment(
            edge_id="north-road",
            start_node_id="n0",
            end_node_id="n1",
            centerline_enu_m=(
                (0.0, 0.0),
                (0.0, 10.0),
            ),
            attributes=_attributes(),
            allows_forward=True,
            allows_reverse=True,
        ),
        RoadSegment(
            edge_id="east-road",
            start_node_id="n1",
            end_node_id="n2",
            centerline_enu_m=(
                (0.0, 10.0),
                (10.0, 10.0),
            ),
            attributes=_attributes(road_class="primary"),
            allows_forward=True,
            allows_reverse=False,
        ),
    )

    return RoadGraph(
        metadata=_metadata(),
        nodes=nodes,
        segments=segments,
    )


def test_graph_exposes_legal_directed_traversals() -> None:
    """Two-way roads create two traversals; one-way roads create only one."""

    graph = _fixture_graph()

    northbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.FORWARD,
    )
    southbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.REVERSE,
    )
    eastbound = DirectedRoadTraversal(
        edge_id="east-road",
        travel_direction=TravelDirection.FORWARD,
    )

    assert graph.traversal_count == 3
    assert graph.traversals_from("n0") == (northbound,)
    assert set(graph.traversals_from("n1")) == {
        southbound,
        eastbound,
    }

    assert graph.traversal_start_node_id(northbound) == "n0"
    assert graph.traversal_end_node_id(northbound) == "n1"

    assert graph.traversal_start_node_id(southbound) == "n1"
    assert graph.traversal_end_node_id(southbound) == "n0"


def test_graph_uses_gnss_compatible_heading_convention() -> None:
    """Heading is clockwise from north, matching GNSS course-over-ground."""

    graph = _fixture_graph()

    northbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.FORWARD,
    )
    southbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.REVERSE,
    )
    eastbound = DirectedRoadTraversal(
        edge_id="east-road",
        travel_direction=TravelDirection.FORWARD,
    )

    assert graph.traversal_heading_enu_rad(northbound) == pytest.approx(
        0.0
    )
    assert graph.traversal_heading_enu_rad(southbound) == pytest.approx(
        pi
    )
    assert graph.traversal_heading_enu_rad(eastbound) == pytest.approx(
        pi / 2.0
    )


def test_graph_finds_bounded_legal_route_distance() -> None:
    """Dijkstra follows legal directions and respects the search bound."""

    graph = _fixture_graph()

    assert graph.shortest_node_path_distance_m(
        start_node_id="n0",
        end_node_id="n2",
        maximum_distance_m=25.0,
    ) == pytest.approx(20.0)

    # east-road is one-way, so the reverse trip has no legal route.
    assert graph.shortest_node_path_distance_m(
        start_node_id="n2",
        end_node_id="n0",
        maximum_distance_m=25.0,
    ) is None

    # Even a valid route is rejected when it exceeds the caller's local bound.
    assert graph.shortest_node_path_distance_m(
        start_node_id="n0",
        end_node_id="n2",
        maximum_distance_m=15.0,
    ) is None


def test_graph_rejects_segment_referencing_unknown_node() -> None:
    """A graph cannot contain a road endpoint absent from its node table."""

    valid_node = RoadNode(
        node_id="n0",
        position_enu_m=(0.0, 0.0),
    )
    invalid_segment = RoadSegment(
        edge_id="invalid-road",
        start_node_id="n0",
        end_node_id="missing-node",
        centerline_enu_m=(
            (0.0, 0.0),
            (0.0, 10.0),
        ),
        attributes=_attributes(),
        allows_forward=True,
        allows_reverse=False,
    )

    with pytest.raises(
        RoadGraphTopologyError,
        match="unknown node",
    ):
        RoadGraph(
            metadata=_metadata(),
            nodes=(valid_node,),
            segments=(invalid_segment,),
        )


def test_graph_rejects_geometry_disconnected_from_declared_endpoint() -> None:
    """A topology edge and its centreline must describe the same physical road."""

    start_node = RoadNode(
        node_id="n0",
        position_enu_m=(0.0, 0.0),
    )
    end_node = RoadNode(
        node_id="n1",
        position_enu_m=(0.0, 10.0),
    )
    offset_geometry = RoadSegment(
        edge_id="offset-road",
        start_node_id="n0",
        end_node_id="n1",
        centerline_enu_m=(
            (5.0, 0.0),
            (5.0, 10.0),
        ),
        attributes=_attributes(),
        allows_forward=True,
        allows_reverse=True,
    )

    with pytest.raises(
        RoadGraphCoordinateError,
        match="start geometry",
    ):
        RoadGraph(
            metadata=_metadata(),
            nodes=(start_node, end_node),
            segments=(offset_geometry,),
            endpoint_tolerance_m=0.5,
        )


def test_graph_rejects_duplicate_node_ids() -> None:
    """Stable node identity is required for deterministic routing."""

    duplicate_node = RoadNode(
        node_id="duplicate",
        position_enu_m=(0.0, 0.0),
    )

    with pytest.raises(
        RoadGraphTopologyError,
        match="Duplicate road node ID",
    ):
        RoadGraph(
            metadata=_metadata(),
            nodes=(duplicate_node, duplicate_node),
            segments=(),
        )


def test_graph_mappings_are_immutable() -> None:
    """Runtime map matching cannot mutate validated road topology."""

    graph = _fixture_graph()

    with pytest.raises(TypeError):
        graph.nodes["unexpected"] = RoadNode(
            node_id="unexpected",
            position_enu_m=(1.0, 1.0),
        )



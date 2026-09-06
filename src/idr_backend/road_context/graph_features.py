"""Derive static, directed road-context facts from one immutable RoadGraph."""

from __future__ import annotations

from math import atan2, hypot, pi

import numpy as np

from idr_backend.map_matching.graph import DirectedRoadTraversal, RoadGraph
from idr_backend.sensors.types import TravelDirection

from .features import RoadContextEdgeFeatures


def _direction_name(direction: TravelDirection) -> str:
    if direction is TravelDirection.FORWARD:
        return "forward"
    if direction is TravelDirection.REVERSE:
        return "reverse"
    raise ValueError(f"Unsupported travel direction: {direction!r}")


def _wrapped_angle_difference_rad(first: float, second: float) -> float:
    """Return the signed smallest angle from first heading to second heading."""

    return (second - first + pi) % (2.0 * pi) - pi


def _curvature_summary(
    geometry: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    """Return length-weighted mean and p95 absolute curvature in rad/m."""

    directed_parts: list[tuple[float, float]] = []

    for start, end in zip(geometry, geometry[1:]):
        east_delta = end[0] - start[0]
        north_delta = end[1] - start[1]
        length_m = hypot(east_delta, north_delta)

        if length_m > 1e-9:
            heading_rad = atan2(east_delta, north_delta)
            directed_parts.append((length_m, heading_rad))

    if len(directed_parts) < 2:
        return 0.0, 0.0

    curvatures: list[float] = []
    supports_m: list[float] = []

    for (previous_length, previous_heading), (next_length, next_heading) in zip(
        directed_parts,
        directed_parts[1:],
    ):
        support_m = 0.5 * (previous_length + next_length)
        heading_change_rad = abs(
            _wrapped_angle_difference_rad(previous_heading, next_heading)
        )
        curvatures.append(heading_change_rad / support_m)
        supports_m.append(support_m)

    return (
        float(np.average(curvatures, weights=supports_m)),
        float(np.quantile(curvatures, 0.95)),
    )


def build_road_context_edge_features(
    graph: RoadGraph,
) -> tuple[RoadContextEdgeFeatures, ...]:
    """Derive one static feature record for every legal directed traversal."""

    results: list[RoadContextEdgeFeatures] = []

    for edge_id in sorted(graph.segments):
        segment = graph.segment(edge_id)
        attributes = segment.attributes

        legal_directions = (
            (TravelDirection.FORWARD, segment.allows_forward),
            (TravelDirection.REVERSE, segment.allows_reverse),
        )

        for direction, is_legal in legal_directions:
            if not is_legal:
                continue

            traversal = DirectedRoadTraversal(
                edge_id=segment.edge_id,
                travel_direction=direction,
            )
            geometry = graph.traversal_geometry(traversal)
            mean_curvature, p95_curvature = _curvature_summary(geometry)

            start_node_id = graph.traversal_start_node_id(traversal)
            end_node_id = graph.traversal_end_node_id(traversal)

            # "unknown" is an explicit graph fallback, not a verified OSM class.
            road_class = (
                None
                if attributes.road_class.strip().lower() == "unknown"
                else attributes.road_class
            )

            results.append(
                RoadContextEdgeFeatures(
                    graph_id=graph.metadata.graph_id,
                    edge_id=segment.edge_id,
                    travel_direction=_direction_name(direction),
                    osm_way_id=attributes.source_way_id,
                    road_class=road_class,
                    speed_limit_mps=attributes.speed_limit_mps,
                    lane_count=attributes.lane_count,
                    is_oneway=segment.allows_forward != segment.allows_reverse,
                    is_link=attributes.is_link,
                    is_tunnel=attributes.is_tunnel,
                    is_bridge=attributes.is_bridge,
                    is_roundabout=attributes.is_roundabout,
                    edge_length_m=segment.length_m,
                    mean_abs_curvature_rad_per_m=mean_curvature,
                    p95_abs_curvature_rad_per_m=p95_curvature,
                    from_node_degree=len(graph.traversals_from(start_node_id)),
                    to_node_degree=len(graph.traversals_from(end_node_id)),
                )
            )

    if not results:
        raise ValueError("Road graph has no legal directed traversals.")

    return tuple(results)



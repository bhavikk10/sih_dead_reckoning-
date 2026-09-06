"""Validated offline road-graph contracts for causal map matching.

This module contains only deterministic, in-memory graph data structures and
topology access. It does not download OSM data, call routing APIs, render maps,
or run HMM/Viterbi logic. Those belong to the OSM adapter and later
map-matching modules respectively.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from heapq import heappop, heappush
from math import atan2, hypot, isfinite, pi
from types import MappingProxyType

from ..sensors.types import (
    CoordinateFrame,
    TravelDirection,
    Vector2,
)

class RoadGraphError(ValueError):
    """Base error for invalid or inconsistent offline road-graph data."""


class RoadGraphCoordinateError(RoadGraphError):
    """Raised when map geometry is not expressed in the navigation ENU frame."""


@dataclass(frozen=True, slots=True)
class MapEnuReference:
    """The WGS-84 origin used when a regional road graph was projected to ENU.

    Every road-node coordinate and polyline point in this graph is measured in
    metres relative to this exact geographic origin:

        x = east
        y = north
        z is intentionally absent because road matching is horizontal.

    The EKF session must use the same ENU reference before its position can be
    compared directly with this graph. Keeping the origin in graph metadata
    prevents a silent, metre-scale coordinate mismatch between navigation and
    map data.
    """

    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0

    def __post_init__(self) -> None:
        """Reject impossible geographic metadata before graph loading begins."""

        if not (
            isfinite(self.latitude_deg)
            and -90.0 <= self.latitude_deg <= 90.0
        ):
            raise RoadGraphCoordinateError(
                "Map ENU reference latitude must be finite and in [-90, 90]."
            )

        if not (
            isfinite(self.longitude_deg)
            and -180.0 <= self.longitude_deg <= 180.0
        ):
            raise RoadGraphCoordinateError(
                "Map ENU reference longitude must be finite and in [-180, 180]."
            )

        if not isfinite(self.altitude_m):
            raise RoadGraphCoordinateError(
                "Map ENU reference altitude must be finite."
            )


@dataclass(frozen=True, slots=True)
class RoadGraphMetadata:
    """Version and coordinate provenance for one immutable offline graph.

    ``graph_id`` should identify the exact prepared graph artifact, normally a
    content hash or versioned build ID. ``source_dataset`` and
    ``source_version`` make map-matching and road-context results reproducible:
    the same GPS/IMU replay can be rerun against the exact same OSM extract.
    """

    graph_id: str
    region_id: str

    source_dataset: str
    source_version: str

    enu_reference: MapEnuReference
    coordinate_frame: CoordinateFrame = CoordinateFrame.NAVIGATION_ENU

    def __post_init__(self) -> None:
        """Require explicit, reproducible, metre-based graph provenance."""

        text_fields = (
            self.graph_id,
            self.region_id,
            self.source_dataset,
            self.source_version,
        )
        if not all(value.strip() for value in text_fields):
            raise RoadGraphError(
                "Graph ID, region ID, source dataset, and source version are required."
            )

        # Candidate distance, EKF position covariance, and road geometry can
        # only be compared directly when both use the same local ENU convention.
        if self.coordinate_frame is not CoordinateFrame.NAVIGATION_ENU:
            raise RoadGraphCoordinateError(
                "Road graph geometry must use the navigation ENU frame."
            )

def _validate_enu_point(
    point: Vector2,
    *,
    field_name: str,
) -> None:
    """Require one finite horizontal [east, north] point in metres."""

    if len(point) != 2 or not all(isfinite(value) for value in point):
        raise RoadGraphCoordinateError(
            f"{field_name} must be a finite (east, north) ENU point."
        )


def planar_distance_m(
    first: Vector2,
    second: Vector2,
) -> float:
    """Return horizontal Euclidean distance between two ENU points in metres."""

    _validate_enu_point(first, field_name="first point")
    _validate_enu_point(second, field_name="second point")

    east_delta_m = second[0] - first[0]
    north_delta_m = second[1] - first[1]
    return hypot(east_delta_m, north_delta_m)


def polyline_length_m(
    centerline_enu_m: tuple[Vector2, ...],
) -> float:
    """Return the total horizontal length of a road centreline in metres."""

    if len(centerline_enu_m) < 2:
        raise RoadGraphCoordinateError(
            "A road centreline must contain at least two ENU points."
        )

    return sum(
        planar_distance_m(start, end)
        for start, end in zip(
            centerline_enu_m,
            centerline_enu_m[1:],
        )
    )


def polyline_heading_enu_rad(
    centerline_enu_m: tuple[Vector2, ...],
) -> float:
    """Return the first valid travel heading, clockwise from ENU north.

    This uses the same convention as GNSS course-over-ground:

        0          = north
        pi / 2     = east
        pi         = south
        3 * pi / 2 = west

    Consecutive duplicate geometry points are skipped because they carry no
    direction information and can occur in imperfect OSM extracts.
    """

    if len(centerline_enu_m) < 2:
        raise RoadGraphCoordinateError(
            "A road centreline must contain at least two ENU points."
        )

    for start, end in zip(
        centerline_enu_m,
        centerline_enu_m[1:],
    ):
        east_delta_m = end[0] - start[0]
        north_delta_m = end[1] - start[1]

        if hypot(east_delta_m, north_delta_m) > 0.0:
            return atan2(east_delta_m, north_delta_m) % (2.0 * pi)

    raise RoadGraphCoordinateError(
        "A road centreline cannot consist entirely of duplicate points."
    )


@dataclass(frozen=True, slots=True)
class RoadNode:
    """One routable road-topology node in the graph's shared ENU frame."""

    node_id: str
    position_enu_m: Vector2

    # OSM-derived facts that will later help road-context rules distinguish
    # ordinary road vertices from intersections and controlled junctions.
    is_intersection: bool = False
    has_traffic_signal: bool = False

    def __post_init__(self) -> None:
        """Validate stable identity and coordinate-frame compatibility."""

        if not self.node_id.strip():
            raise RoadGraphError("Road node ID must not be blank.")

        _validate_enu_point(
            self.position_enu_m,
            field_name=f"Road node {self.node_id!r} position",
        )


@dataclass(frozen=True, slots=True)
class RoadSegmentAttributes:
    """Static OSM-derived facts retained for scoring and road-context priors."""

    # OSM ``highway`` classification, such as residential, primary, trunk,
    # service, motorway, or an explicit project fallback such as unknown.
    road_class: str

    # Stable source provenance. Many directed graph segments can originate from
    # one OSM way after intersections split its geometry.
    source_way_id: str

    # Optional because OSM coverage is incomplete and tags must not be invented.
    speed_limit_mps: float | None = None
    lane_count: int | None = None

    # These facts later influence candidate plausibility and speed-rule trust.
    is_link: bool = False
    is_tunnel: bool = False
    is_bridge: bool = False
    is_roundabout: bool = False

    def __post_init__(self) -> None:
        """Reject malformed optional metadata without fabricating missing facts."""

        if not self.road_class.strip():
            raise RoadGraphError("Road class must not be blank.")
        if not self.source_way_id.strip():
            raise RoadGraphError("Source OSM way ID must not be blank.")

        if self.speed_limit_mps is not None and (
            not isfinite(self.speed_limit_mps)
            or self.speed_limit_mps <= 0.0
        ):
            raise RoadGraphError(
                "Road speed limit must be finite and positive when supplied."
            )

        if self.lane_count is not None and self.lane_count < 1:
            raise RoadGraphError(
                "Road lane count must be at least one when supplied."
            )


@dataclass(frozen=True, slots=True)
class RoadSegment:
    """One physical road segment with canonical start-to-end geometry.

    Geometry is stored once in the direction from ``start_node_id`` to
    ``end_node_id``. A segment can allow forward travel, reverse travel, or
    both. Candidate generation and Viterbi represent a particular legal
    direction using ``DirectedRoadTraversal`` below.
    """

    edge_id: str
    start_node_id: str
    end_node_id: str
    centerline_enu_m: tuple[Vector2, ...]
    attributes: RoadSegmentAttributes

    allows_forward: bool
    allows_reverse: bool

    def __post_init__(self) -> None:
        """Validate a segment before it becomes part of graph topology."""

        text_fields = (
            self.edge_id,
            self.start_node_id,
            self.end_node_id,
        )
        if not all(value.strip() for value in text_fields):
            raise RoadGraphError(
                "Road edge ID and both endpoint node IDs are required."
            )

        if not (self.allows_forward or self.allows_reverse):
            raise RoadGraphError(
                f"Road segment {self.edge_id!r} permits no travel direction."
            )

        for index, point in enumerate(self.centerline_enu_m):
            _validate_enu_point(
                point,
                field_name=(
                    f"Road segment {self.edge_id!r} "
                    f"centreline point {index}"
                ),
            )

        if polyline_length_m(self.centerline_enu_m) <= 0.0:
            raise RoadGraphCoordinateError(
                f"Road segment {self.edge_id!r} has zero geometric length."
            )

    @property
    def length_m(self) -> float:
        """Return the immutable segment's centreline length in metres."""

        return polyline_length_m(self.centerline_enu_m)

    def geometry_for(
        self,
        travel_direction: TravelDirection,
    ) -> tuple[Vector2, ...]:
        """Return the centreline in the requested legal travel direction."""

        if travel_direction is TravelDirection.FORWARD:
            if not self.allows_forward:
                raise RoadGraphTopologyError(
                    f"Segment {self.edge_id!r} does not allow forward travel."
                )
            return self.centerline_enu_m

        if travel_direction is TravelDirection.REVERSE:
            if not self.allows_reverse:
                raise RoadGraphTopologyError(
                    f"Segment {self.edge_id!r} does not allow reverse travel."
                )
            return tuple(reversed(self.centerline_enu_m))

        raise RoadGraphTopologyError(
            f"Unsupported travel direction: {travel_direction!r}."
        )

    def heading_for(
        self,
        travel_direction: TravelDirection,
    ) -> float:
        """Return legal travel heading in the GNSS-compatible ENU convention."""

        return polyline_heading_enu_rad(
            self.geometry_for(travel_direction)
        )


@dataclass(frozen=True, slots=True)
class DirectedRoadTraversal:
    """One legal directed traversal used as an HMM state or routing step."""

    edge_id: str
    travel_direction: TravelDirection

    def __post_init__(self) -> None:
        """Require an edge identity before graph lookup."""

        if not self.edge_id.strip():
            raise RoadGraphError(
                "Directed road traversal edge ID must not be blank."
            )


class RoadGraphTopologyError(RoadGraphError):
    """Raised when edges, nodes, or traversals violate road connectivity."""


class RoadGraph:
    """Validated immutable road topology with directed traversal access.

    The graph owns no live spatial index, network connection, or mutable OSM
    object. It can therefore be shared safely by candidate generation, HMM
    scoring, route-distance evaluation, and road-context feature extraction.
    """

    def __init__(
        self,
        *,
        metadata: RoadGraphMetadata,
        nodes: Iterable[RoadNode],
        segments: Iterable[RoadSegment],
        endpoint_tolerance_m: float = 0.5,
    ) -> None:
        """Build and validate one reproducible directed road graph.

        ``endpoint_tolerance_m`` allows minor OSM/projection rounding between a
        node and the first/last centreline point. It is not a snapping radius:
        a large mismatch is a corrupt graph and must fail at load time.
        """

        if (
            not isfinite(endpoint_tolerance_m)
            or endpoint_tolerance_m < 0.0
        ):
            raise RoadGraphCoordinateError(
                "Endpoint tolerance must be finite and non-negative."
            )

        node_by_id: dict[str, RoadNode] = {}
        for node in nodes:
            if node.node_id in node_by_id:
                raise RoadGraphTopologyError(
                    f"Duplicate road node ID: {node.node_id!r}."
                )
            node_by_id[node.node_id] = node

        segment_by_id: dict[str, RoadSegment] = {}
        for segment in segments:
            if segment.edge_id in segment_by_id:
                raise RoadGraphTopologyError(
                    f"Duplicate road edge ID: {segment.edge_id!r}."
                )
            self._validate_segment_endpoints(
                segment=segment,
                nodes=node_by_id,
                endpoint_tolerance_m=endpoint_tolerance_m,
            )
            segment_by_id[segment.edge_id] = segment

        outgoing: dict[str, list[DirectedRoadTraversal]] = {
            node_id: []
            for node_id in node_by_id
        }

        for segment in segment_by_id.values():
            if segment.allows_forward:
                outgoing[segment.start_node_id].append(
                    DirectedRoadTraversal(
                        edge_id=segment.edge_id,
                        travel_direction=TravelDirection.FORWARD,
                    )
                )

            if segment.allows_reverse:
                outgoing[segment.end_node_id].append(
                    DirectedRoadTraversal(
                        edge_id=segment.edge_id,
                        travel_direction=TravelDirection.REVERSE,
                    )
                )

        # Mapping proxies and tuples prevent a caller from accidentally
        # rewriting graph topology during a live navigation session.
        self._metadata = metadata
        self._nodes: Mapping[str, RoadNode] = MappingProxyType(node_by_id)
        self._segments: Mapping[str, RoadSegment] = MappingProxyType(
            segment_by_id
        )
        self._outgoing: Mapping[
            str,
            tuple[DirectedRoadTraversal, ...],
        ] = MappingProxyType(
            {
                node_id: tuple(
                    sorted(
                        traversals,
                        key=lambda traversal: (
                            traversal.edge_id,
                            traversal.travel_direction.value,
                        ),
                    )
                )
                for node_id, traversals in outgoing.items()
            }
        )

    @property
    def metadata(self) -> RoadGraphMetadata:
        """Return immutable graph provenance and ENU-reference metadata."""

        return self._metadata

    @property
    def nodes(self) -> Mapping[str, RoadNode]:
        """Expose immutable node lookup by stable graph-local ID."""

        return self._nodes

    @property
    def segments(self) -> Mapping[str, RoadSegment]:
        """Expose immutable physical road-segment lookup by edge ID."""

        return self._segments

    @property
    def traversal_count(self) -> int:
        """Return the number of legal directed HMM/routing states."""

        return sum(
            len(traversals)
            for traversals in self._outgoing.values()
        )

    def segment(
        self,
        edge_id: str,
    ) -> RoadSegment:
        """Return one segment or raise a clear graph-topology error."""

        try:
            return self._segments[edge_id]
        except KeyError as error:
            raise RoadGraphTopologyError(
                f"Unknown road edge ID: {edge_id!r}."
            ) from error

    def node(
        self,
        node_id: str,
    ) -> RoadNode:
        """Return one node or raise a clear graph-topology error."""

        try:
            return self._nodes[node_id]
        except KeyError as error:
            raise RoadGraphTopologyError(
                f"Unknown road node ID: {node_id!r}."
            ) from error

    def traversals_from(
        self,
        node_id: str,
    ) -> tuple[DirectedRoadTraversal, ...]:
        """Return every legal traversal that departs from one topology node."""

        self.node(node_id)
        return self._outgoing[node_id]

    def traversal_start_node_id(
        self,
        traversal: DirectedRoadTraversal,
    ) -> str:
        """Return the topology node from which this directed traversal departs."""

        segment = self._require_legal_traversal(traversal)

        if traversal.travel_direction is TravelDirection.FORWARD:
            return segment.start_node_id
        return segment.end_node_id

    def traversal_end_node_id(
        self,
        traversal: DirectedRoadTraversal,
    ) -> str:
        """Return the topology node reached after this directed traversal."""

        segment = self._require_legal_traversal(traversal)

        if traversal.travel_direction is TravelDirection.FORWARD:
            return segment.end_node_id
        return segment.start_node_id

    def traversal_geometry(
        self,
        traversal: DirectedRoadTraversal,
    ) -> tuple[Vector2, ...]:
        """Return the centreline ordered in the legal direction of travel."""

        segment = self._require_legal_traversal(traversal)
        return segment.geometry_for(traversal.travel_direction)

    def traversal_heading_enu_rad(
        self,
        traversal: DirectedRoadTraversal,
    ) -> float:
        """Return GNSS-compatible heading for one legal directed traversal."""

        segment = self._require_legal_traversal(traversal)
        return segment.heading_for(traversal.travel_direction)

    def shortest_node_path_distance_m(
        self,
        *,
        start_node_id: str,
        end_node_id: str,
        maximum_distance_m: float,
    ) -> float | None:
        """Return bounded directed route distance, or ``None`` if unreachable.

        This is Dijkstra over legal directed traversals. It is deliberately
        bounded because transition scoring needs only plausible local routes;
        searching across an entire city graph for every HMM candidate pair would
        be too slow and would make impossible transitions look plausible.
        """

        if (
            not isfinite(maximum_distance_m)
            or maximum_distance_m <= 0.0
        ):
            raise ValueError(
                "maximum_distance_m must be finite and positive."
            )

        self.node(start_node_id)
        self.node(end_node_id)

        if start_node_id == end_node_id:
            return 0.0

        best_distance_m: dict[str, float] = {
            start_node_id: 0.0,
        }
        pending_nodes: list[tuple[float, str]] = [
            (0.0, start_node_id),
        ]

        while pending_nodes:
            current_distance_m, current_node_id = heappop(
                pending_nodes
            )

            if current_distance_m != best_distance_m[current_node_id]:
                continue

            if current_node_id == end_node_id:
                return current_distance_m

            for traversal in self.traversals_from(current_node_id):
                segment = self.segment(traversal.edge_id)
                next_node_id = self.traversal_end_node_id(traversal)
                next_distance_m = (
                    current_distance_m + segment.length_m
                )

                if next_distance_m > maximum_distance_m:
                    continue

                previous_best_m = best_distance_m.get(next_node_id)
                if (
                    previous_best_m is None
                    or next_distance_m < previous_best_m
                ):
                    best_distance_m[next_node_id] = next_distance_m
                    heappush(
                        pending_nodes,
                        (next_distance_m, next_node_id),
                    )

        return None

    def _require_legal_traversal(
        self,
        traversal: DirectedRoadTraversal,
    ) -> RoadSegment:
        """Resolve a traversal and reject prohibited one-way movement."""

        segment = self.segment(traversal.edge_id)

        if (
            traversal.travel_direction is TravelDirection.FORWARD
            and not segment.allows_forward
        ):
            raise RoadGraphTopologyError(
                f"Forward traversal is prohibited on {segment.edge_id!r}."
            )

        if (
            traversal.travel_direction is TravelDirection.REVERSE
            and not segment.allows_reverse
        ):
            raise RoadGraphTopologyError(
                f"Reverse traversal is prohibited on {segment.edge_id!r}."
            )

        return segment

    @staticmethod
    def _validate_segment_endpoints(
        *,
        segment: RoadSegment,
        nodes: Mapping[str, RoadNode],
        endpoint_tolerance_m: float,
    ) -> None:
        """Ensure geometry and graph topology describe the same physical road."""

        try:
            start_node = nodes[segment.start_node_id]
            end_node = nodes[segment.end_node_id]
        except KeyError as error:
            raise RoadGraphTopologyError(
                f"Segment {segment.edge_id!r} references unknown node "
                f"{error.args[0]!r}."
            ) from error

        start_offset_m = planar_distance_m(
            start_node.position_enu_m,
            segment.centerline_enu_m[0],
        )
        end_offset_m = planar_distance_m(
            end_node.position_enu_m,
            segment.centerline_enu_m[-1],
        )

        if start_offset_m > endpoint_tolerance_m:
            raise RoadGraphCoordinateError(
                f"Segment {segment.edge_id!r} start geometry is "
                f"{start_offset_m:.3f} m from its start node."
            )

        if end_offset_m > endpoint_tolerance_m:
            raise RoadGraphCoordinateError(
                f"Segment {segment.edge_id!r} end geometry is "
                f"{end_offset_m:.3f} m from its end node."
            )


    def all_traversals(self) -> tuple[DirectedRoadTraversal, ...]:
        """Return every legal directed traversal in deterministic order.

        Candidate generation normally uses a spatial query first, then resolves
        only nearby segments. This method is intentionally available for graph
        validation, small fixture graphs, and offline diagnostics—not as a
        substitute for the later bounded spatial candidate search.
        """

        return tuple(
            traversal
            for node_id in sorted(self._outgoing)
            for traversal in self._outgoing[node_id]
        )



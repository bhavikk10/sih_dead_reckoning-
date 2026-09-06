"""Bounded, causal road-candidate generation from an EKF navigation estimate.

Candidate generation proposes plausible directed road traversals near the current
EKF position. It does not choose the final road: emission/transition scoring and
bounded Viterbi own that later decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import atan2, hypot, isfinite, pi, sqrt
from typing import Protocol

from ..sensors.types import (
    NavigationEstimate,
    RoadCandidate,
    TravelDirection,
    Vector2,
)
from .graph import (
    DirectedRoadTraversal,
    RoadGraph,
    RoadGraphCoordinateError,
)


class CandidateGenerationDisposition(StrEnum):
    """Whether a bounded candidate search found usable road hypotheses."""

    CANDIDATES_GENERATED = "candidates_generated"
    NO_GRAPH_COVERAGE = "no_graph_coverage"


@dataclass(frozen=True, slots=True)
class CandidateGenerationConfig:
    """Explicit search, ranking, and causal-belief limits.

    Position covariance widens the spatial search radius, but all searches stay
    bounded. A dead-reckoning estimate may become uncertain; it must not cause
    an unbounded scan across an entire city graph.
    """

    minimum_search_radius_m: float
    maximum_search_radius_m: float
    position_sigma_multiplier: float

    maximum_candidate_count: int

    # Heading is unreliable while stationary, so it only affects ranking above
    # this horizontal velocity magnitude.
    minimum_heading_speed_mps: float
    heading_rank_weight: float

    # A previous Viterbi belief is useful for continuity, but must be from an
    # older cycle and recent enough to remain meaningful.
    maximum_prior_belief_age_ns: int
    prior_belief_rank_bonus: float

    def __post_init__(self) -> None:
        """Validate bounds before a live navigation session starts."""

        positive_values = (
            self.minimum_search_radius_m,
            self.maximum_search_radius_m,
            self.position_sigma_multiplier,
            self.minimum_heading_speed_mps,
        )
        if not all(
            isfinite(value) and value > 0.0
            for value in positive_values
        ):
            raise ValueError(
                "Candidate search distances, multiplier, and heading speed "
                "must be finite and positive."
            )

        if (
            self.minimum_search_radius_m
            > self.maximum_search_radius_m
        ):
            raise ValueError(
                "minimum_search_radius_m must not exceed "
                "maximum_search_radius_m."
            )

        if self.maximum_candidate_count < 1:
            raise ValueError(
                "maximum_candidate_count must be at least one."
            )

        if self.maximum_prior_belief_age_ns <= 0:
            raise ValueError(
                "maximum_prior_belief_age_ns must be positive."
            )

        if (
            not isfinite(self.heading_rank_weight)
            or self.heading_rank_weight < 0.0
        ):
            raise ValueError(
                "heading_rank_weight must be finite and non-negative."
            )

        if (
            not isfinite(self.prior_belief_rank_bonus)
            or self.prior_belief_rank_bonus < 0.0
        ):
            raise ValueError(
                "prior_belief_rank_bonus must be finite and non-negative."
            )


@dataclass(frozen=True, slots=True)
class PreviousTraversalBelief:
    """One candidate probability published by an earlier HMM/Viterbi cycle.

    This is intentionally a small, transport-neutral bridge. `viterbi.py` will
    later convert its own belief state into these records without creating a
    circular import between candidate generation and Viterbi.
    """

    source_belief_timestamp_ns: int
    traversal: DirectedRoadTraversal
    probability: float

    def __post_init__(self) -> None:
        """Keep temporal causality and probability meaning explicit."""

        if self.source_belief_timestamp_ns < 0:
            raise ValueError(
                "source_belief_timestamp_ns must be non-negative."
            )

        if (
            not isfinite(self.probability)
            or not 0.0 <= self.probability <= 1.0
        ):
            raise ValueError(
                "Previous traversal probability must be in [0, 1]."
            )


@dataclass(frozen=True, slots=True)
class CandidateGenerationResult:
    """Bounded candidate output plus diagnostics safe for later logging."""

    timestamp_ns: int
    disposition: CandidateGenerationDisposition

    search_radius_m: float
    queried_traversal_count: int
    usable_prior_belief_count: int

    candidates: tuple[RoadCandidate, ...]

    def __post_init__(self) -> None:
        """Protect downstream HMM code from malformed candidate batches."""

        if self.timestamp_ns < 0:
            raise ValueError("Candidate result timestamp must be non-negative.")

        if (
            not isfinite(self.search_radius_m)
            or self.search_radius_m <= 0.0
        ):
            raise ValueError(
                "Candidate search radius must be finite and positive."
            )

        if (
            self.queried_traversal_count < 0
            or self.usable_prior_belief_count < 0
        ):
            raise ValueError(
                "Candidate diagnostic counts must be non-negative."
            )

        candidate_ids = tuple(
            candidate.candidate_id
            for candidate in self.candidates
        )
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError(
                "Candidate IDs must be unique within one generation result."
            )

        if any(
            candidate.timestamp_ns != self.timestamp_ns
            for candidate in self.candidates
        ):
            raise ValueError(
                "Every road candidate must use the result timestamp."
            )

        if (
            self.disposition
            is CandidateGenerationDisposition.NO_GRAPH_COVERAGE
            and self.candidates
        ):
            raise ValueError(
                "NO_GRAPH_COVERAGE must not contain road candidates."
            )


class RoadSpatialIndex(Protocol):
    """Return a bounded superset of traversals near a horizontal ENU point."""

    def query_radius(
        self,
        *,
        position_enu_m: Vector2,
        radius_m: float,
    ) -> tuple[DirectedRoadTraversal, ...]:
        """Return traversals whose geometry bounding box intersects the radius."""


@dataclass(frozen=True, slots=True)
class _TraversalBounds:
    """Axis-aligned ENU bounding box for one legal directed traversal."""

    minimum_east_m: float
    maximum_east_m: float
    minimum_north_m: float
    maximum_north_m: float

    def intersects_radius(
        self,
        *,
        position_enu_m: Vector2,
        radius_m: float,
    ) -> bool:
        """Return whether a circle intersects this bounding box."""

        east_m, north_m = position_enu_m

        nearest_east_m = min(
            max(east_m, self.minimum_east_m),
            self.maximum_east_m,
        )
        nearest_north_m = min(
            max(north_m, self.minimum_north_m),
            self.maximum_north_m,
        )

        return hypot(
            east_m - nearest_east_m,
            north_m - nearest_north_m,
        ) <= radius_m


class BruteForceRoadSpatialIndex:
    """Correct deterministic baseline index for fixtures and small map regions.

    It prefilters traversal geometry by bounding box. A production regional map
    can later replace this with an R-tree/grid index while preserving the same
    `RoadSpatialIndex` interface and candidate-generation behaviour.
    """

    def __init__(
        self,
        graph: RoadGraph,
    ) -> None:
        self._traversals = graph.all_traversals()
        self._bounds_by_traversal = {
            traversal: _bounds_for_geometry(
                graph.traversal_geometry(traversal)
            )
            for traversal in self._traversals
        }

    def query_radius(
        self,
        *,
        position_enu_m: Vector2,
        radius_m: float,
    ) -> tuple[DirectedRoadTraversal, ...]:
        """Return geometry whose bounding box can plausibly touch the search."""

        _require_enu_point(
            position_enu_m,
            description="Candidate query position",
        )
        if not isfinite(radius_m) or radius_m <= 0.0:
            raise ValueError(
                "Candidate query radius must be finite and positive."
            )

        return tuple(
            traversal
            for traversal in self._traversals
            if self._bounds_by_traversal[
                traversal
            ].intersects_radius(
                position_enu_m=position_enu_m,
                radius_m=radius_m,
            )
        )


def _require_enu_point(
    point: Vector2,
    *,
    description: str,
) -> None:
    """Require a finite horizontal EKF/map coordinate."""

    if len(point) != 2 or not all(
        isfinite(value)
        for value in point
    ):
        raise RoadGraphCoordinateError(
            f"{description} must be a finite (east, north) point."
        )


def _bounds_for_geometry(
    geometry_enu_m: tuple[Vector2, ...],
) -> _TraversalBounds:
    """Build the conservative ENU rectangle around a road centreline."""

    if not geometry_enu_m:
        raise RoadGraphCoordinateError(
            "Road traversal geometry must not be empty."
        )

    for point in geometry_enu_m:
        _require_enu_point(
            point,
            description="Road traversal geometry point",
        )

    east_values = tuple(point[0] for point in geometry_enu_m)
    north_values = tuple(point[1] for point in geometry_enu_m)

    return _TraversalBounds(
        minimum_east_m=min(east_values),
        maximum_east_m=max(east_values),
        minimum_north_m=min(north_values),
        maximum_north_m=max(north_values),
    )


@dataclass(frozen=True, slots=True)
class PolylineProjection:
    """Nearest point on a directed road centreline to one EKF position."""

    snap_position_enu_m: Vector2
    lateral_distance_m: float

    # Distance measured from the first geometry point in travel direction.
    along_traversal_m: float
    traversal_length_m: float

    def __post_init__(self) -> None:
        """Keep projection geometry physically meaningful."""

        _require_enu_point(
            self.snap_position_enu_m,
            description="Projected road position",
        )

        values = (
            self.lateral_distance_m,
            self.along_traversal_m,
            self.traversal_length_m,
        )
        if not all(isfinite(value) and value >= 0.0 for value in values):
            raise ValueError(
                "Projection distance values must be finite and non-negative."
            )

        if self.along_traversal_m > self.traversal_length_m + 1e-9:
            raise ValueError(
                "Projection distance cannot exceed traversal length."
            )

    @property
    def traversal_fraction(self) -> float:
        """Return position on traversal in [0, 1], including its endpoints."""

        if self.traversal_length_m == 0.0:
            return 0.0

        return min(
            1.0,
            self.along_traversal_m / self.traversal_length_m,
        )


def project_point_to_polyline(
    *,
    point_enu_m: Vector2,
    geometry_enu_m: tuple[Vector2, ...],
) -> PolylineProjection:
    """Project one ENU point onto a polyline and retain travel-relative progress.

    Duplicate neighbouring geometry points are skipped. They occur in some map
    extracts but contain no usable direction or distance information.

    The final PolylineProjection is created only after the full traversal length
    is known. During the loop, a lightweight tuple stores the best local snap:
    (snap position, lateral distance, along-traversal distance).
    """

    _require_enu_point(
        point_enu_m,
        description="Point being projected",
    )

    if len(geometry_enu_m) < 2:
        raise RoadGraphCoordinateError(
            "Polyline projection requires at least two geometry points."
        )

    # Do not construct PolylineProjection yet: its invariant requires the final
    # complete polyline length, which is not available until this loop finishes.
    best_projection: tuple[Vector2, float, float] | None = None
    accumulated_length_m = 0.0

    for start, end in zip(
        geometry_enu_m,
        geometry_enu_m[1:],
    ):
        _require_enu_point(
            start,
            description="Polyline start point",
        )
        _require_enu_point(
            end,
            description="Polyline end point",
        )

        segment_east_m = end[0] - start[0]
        segment_north_m = end[1] - start[1]
        segment_length_m = hypot(
            segment_east_m,
            segment_north_m,
        )

        # Repeated OSM geometry vertices add neither distance nor direction.
        if segment_length_m == 0.0:
            continue

        relative_east_m = point_enu_m[0] - start[0]
        relative_north_m = point_enu_m[1] - start[1]

        unbounded_fraction = (
            relative_east_m * segment_east_m
            + relative_north_m * segment_north_m
        ) / (segment_length_m**2)

        # Clamp to the physical segment, so a point beyond an endpoint snaps
        # to that endpoint rather than an imaginary extension of the road.
        segment_fraction = min(
            1.0,
            max(0.0, unbounded_fraction),
        )

        snap_position_enu_m = (
            start[0] + segment_fraction * segment_east_m,
            start[1] + segment_fraction * segment_north_m,
        )
        lateral_distance_m = hypot(
            point_enu_m[0] - snap_position_enu_m[0],
            point_enu_m[1] - snap_position_enu_m[1],
        )
        along_traversal_m = (
            accumulated_length_m
            + segment_fraction * segment_length_m
        )

        candidate_projection = (
            snap_position_enu_m,
            lateral_distance_m,
            along_traversal_m,
        )

        # Strict comparison keeps the first equally-close segment, preserving
        # deterministic behaviour at polyline corners.
        if (
            best_projection is None
            or candidate_projection[1] < best_projection[1]
        ):
            best_projection = candidate_projection

        accumulated_length_m += segment_length_m

    if best_projection is None or accumulated_length_m <= 0.0:
        raise RoadGraphCoordinateError(
            "Polyline cannot consist entirely of duplicate points."
        )

    return PolylineProjection(
        snap_position_enu_m=best_projection[0],
        lateral_distance_m=best_projection[1],
        along_traversal_m=best_projection[2],
        traversal_length_m=accumulated_length_m,
    )


def _horizontal_position_enu_m(
    estimate: NavigationEstimate,
) -> Vector2:
    """Extract and validate the EKF horizontal position."""

    position_enu_m = (
        estimate.position_enu_m[0],
        estimate.position_enu_m[1],
    )
    _require_enu_point(
        position_enu_m,
        description="Navigation estimate horizontal position",
    )
    return position_enu_m


def _horizontal_position_std_upper_bound_m(
    estimate: NavigationEstimate,
) -> float:
    """Return the largest horizontal one-sigma uncertainty axis in metres.

    The 2x2 East/North covariance ellipse may be rotated. Its largest eigenvalue
    gives the conservative direction in which candidate search must widen.
    """

    covariance = estimate.position_covariance_enu_m2

    east_variance_m2 = covariance[0][0]
    east_north_covariance_m2 = 0.5 * (
        covariance[0][1] + covariance[1][0]
    )
    north_variance_m2 = covariance[1][1]

    values = (
        east_variance_m2,
        east_north_covariance_m2,
        north_variance_m2,
    )
    if not all(isfinite(value) for value in values):
        raise ValueError(
            "Navigation position covariance must contain finite values."
        )

    trace_m2 = east_variance_m2 + north_variance_m2
    discriminant_m2 = sqrt(
        (east_variance_m2 - north_variance_m2) ** 2
        + 4.0 * east_north_covariance_m2**2
    )

    largest_eigenvalue_m2 = 0.5 * (
        trace_m2 + discriminant_m2
    )
    smallest_eigenvalue_m2 = 0.5 * (
        trace_m2 - discriminant_m2
    )

    if smallest_eigenvalue_m2 < -1e-9:
        raise ValueError(
            "Navigation horizontal covariance must be positive semidefinite."
        )

    return sqrt(max(0.0, largest_eigenvalue_m2))


def _search_radius_m(
    *,
    estimate: NavigationEstimate,
    config: CandidateGenerationConfig,
) -> float:
    """Turn EKF covariance into a bounded graph-search radius."""

    position_std_m = _horizontal_position_std_upper_bound_m(
        estimate
    )
    uncertainty_radius_m = (
        config.position_sigma_multiplier * position_std_m
    )

    return min(
        config.maximum_search_radius_m,
        max(
            config.minimum_search_radius_m,
            uncertainty_radius_m,
        ),
    )


def _motion_heading_enu_rad(
    *,
    estimate: NavigationEstimate,
    minimum_speed_mps: float,
) -> float | None:
    """Return velocity heading only when EKF horizontal motion is meaningful."""

    east_velocity_mps = estimate.velocity_enu_mps[0]
    north_velocity_mps = estimate.velocity_enu_mps[1]

    if not (
        isfinite(east_velocity_mps)
        and isfinite(north_velocity_mps)
    ):
        raise ValueError(
            "Navigation horizontal velocity must be finite."
        )

    horizontal_speed_mps = hypot(
        east_velocity_mps,
        north_velocity_mps,
    )
    if horizontal_speed_mps < minimum_speed_mps:
        return None

    # Same heading convention used by GNSS course and graph geometry.
    return atan2(
        east_velocity_mps,
        north_velocity_mps,
    ) % (2.0 * pi)


def _wrapped_heading_difference_rad(
    first_heading_rad: float,
    second_heading_rad: float,
) -> float:
    """Return the smallest unsigned circular separation in [0, pi]."""

    return abs(
        (first_heading_rad - second_heading_rad + pi)
        % (2.0 * pi)
        - pi
    )


def _prior_probabilities(
    *,
    graph: RoadGraph,
    estimate_timestamp_ns: int,
    prior_beliefs: tuple[PreviousTraversalBelief, ...],
    config: CandidateGenerationConfig,
) -> dict[DirectedRoadTraversal, float]:
    """Return recent causal traversal beliefs, retaining the highest duplicate."""

    probabilities: dict[DirectedRoadTraversal, float] = {}

    for belief in prior_beliefs:
        if (
            belief.source_belief_timestamp_ns
            >= estimate_timestamp_ns
        ):
            raise ValueError(
                "Previous traversal belief must predate the current estimate."
            )

        belief_age_ns = (
            estimate_timestamp_ns
            - belief.source_belief_timestamp_ns
        )
        if belief_age_ns > config.maximum_prior_belief_age_ns:
            continue

        # Resolving geometry here also rejects an obsolete graph edge or an
        # illegal direction before it can affect candidate continuity ranking.
        graph.traversal_geometry(belief.traversal)

        existing_probability = probabilities.get(
            belief.traversal,
            0.0,
        )
        probabilities[belief.traversal] = max(
            existing_probability,
            belief.probability,
        )

    return probabilities


def _candidate_id(
    traversal: DirectedRoadTraversal,
) -> str:
    """Create a deterministic ID unique within one graph-candidate batch."""

    return (
        f"{traversal.edge_id}:"
        f"{traversal.travel_direction.value}"
    )


class RoadCandidateGenerator:
    """Generate bounded, deterministic directed-road hypotheses per EKF cycle."""

    def __init__(
        self,
        *,
        graph: RoadGraph,
        config: CandidateGenerationConfig,
        spatial_index: RoadSpatialIndex | None = None,
    ) -> None:
        """Bind one immutable graph to explicit candidate-generation policy."""

        self._graph = graph
        self._config = config
        self._spatial_index = (
            BruteForceRoadSpatialIndex(graph)
            if spatial_index is None
            else spatial_index
        )

    def generate(
        self,
        *,
        estimate: NavigationEstimate,
        prior_beliefs: tuple[PreviousTraversalBelief, ...] = (),
    ) -> CandidateGenerationResult:
        """Produce ranked nearby directed road hypotheses for one EKF timestamp.

        Candidate membership is determined by exact geometry distance. Heading
        and prior belief only rank already-near hypotheses; they do not hard
        reject parallel roads or junction exits that Viterbi needs to consider.
        """

        if estimate.timestamp_ns < 0:
            raise ValueError(
                "Navigation estimate timestamp must be non-negative."
            )

        position_enu_m = _horizontal_position_enu_m(estimate)
        search_radius_m = _search_radius_m(
            estimate=estimate,
            config=self._config,
        )
        motion_heading_rad = _motion_heading_enu_rad(
            estimate=estimate,
            minimum_speed_mps=self._config.minimum_heading_speed_mps,
        )
        prior_probability_by_traversal = _prior_probabilities(
            graph=self._graph,
            estimate_timestamp_ns=estimate.timestamp_ns,
            prior_beliefs=prior_beliefs,
            config=self._config,
        )

        queried_traversals = self._spatial_index.query_radius(
            position_enu_m=position_enu_m,
            radius_m=search_radius_m,
        )

        # A previous high-belief traversal may fall outside a coarse external
        # spatial-index result but still lie within exact search geometry.
        traversals_to_evaluate = {
            *queried_traversals,
            *prior_probability_by_traversal,
        }

        ranked_candidates: list[
            tuple[
                float,
                float,
                str,
                str,
                RoadCandidate,
            ]
        ] = []

        for traversal in sorted(
            traversals_to_evaluate,
            key=lambda value: (
                value.edge_id,
                value.travel_direction.value,
            ),
        ):
            geometry_enu_m = self._graph.traversal_geometry(
                traversal
            )
            projection = project_point_to_polyline(
                point_enu_m=position_enu_m,
                geometry_enu_m=geometry_enu_m,
            )

            # Bounding boxes only prefilter. This exact distance check makes the
            # radius meaningful around curves, diagonals, and parallel roads.
            if projection.lateral_distance_m > search_radius_m:
                continue

            road_heading_rad = self._graph.traversal_heading_enu_rad(
                traversal
            )
            heading_penalty = (
                0.0
                if motion_heading_rad is None
                else (
                    _wrapped_heading_difference_rad(
                        motion_heading_rad,
                        road_heading_rad,
                    )
                    / pi
                )
            )

            prior_probability = prior_probability_by_traversal.get(
                traversal,
                0.0,
            )
            rank = (
                projection.lateral_distance_m / search_radius_m
                + self._config.heading_rank_weight * heading_penalty
                - self._config.prior_belief_rank_bonus
                * prior_probability
            )

            candidate = RoadCandidate(
                timestamp_ns=estimate.timestamp_ns,
                candidate_id=_candidate_id(traversal),
                graph_id=self._graph.metadata.graph_id,
                edge_id=traversal.edge_id,
                travel_direction=traversal.travel_direction,
                snap_position_enu_m=projection.snap_position_enu_m,
                lateral_distance_m=projection.lateral_distance_m,
                road_heading_enu_rad=road_heading_rad,
            )

            ranked_candidates.append(
                (
                    rank,
                    projection.lateral_distance_m,
                    traversal.edge_id,
                    traversal.travel_direction.value,
                    candidate,
                )
            )

        ranked_candidates.sort()

        candidates = tuple(
            item[-1]
            for item in ranked_candidates[
                : self._config.maximum_candidate_count
            ]
        )

        return CandidateGenerationResult(
            timestamp_ns=estimate.timestamp_ns,
            disposition=(
                CandidateGenerationDisposition.CANDIDATES_GENERATED
                if candidates
                else CandidateGenerationDisposition.NO_GRAPH_COVERAGE
            ),
            search_radius_m=search_radius_m,
            queried_traversal_count=len(queried_traversals),
            usable_prior_belief_count=len(
                prior_probability_by_traversal
            ),
            candidates=candidates,
        )

    

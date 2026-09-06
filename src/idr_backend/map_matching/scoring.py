"""HMM emission and transition scoring for causal road map matching.

This module scores already-generated road candidates. It does not generate
candidates, mutate EKF state, choose a final Viterbi path, or consume learned
road-context priors. Keeping those responsibilities separate prevents hidden
same-cycle feedback and double-counted map evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import atan2, hypot, inf, isfinite, log, pi, sqrt

from ..sensors.types import (
    NavigationEstimate,
    RoadCandidate,
    Vector2,
)
from .candidates import project_point_to_polyline
from .graph import (
    DirectedRoadTraversal,
    RoadGraph,
)


class TransitionDisposition(StrEnum):
    """Whether a directed road transition can be scored as reachable."""

    SCORED = "scored"
    UNREACHABLE = "unreachable"
    TIMESTAMP_INVALID = "timestamp_invalid"


@dataclass(frozen=True, slots=True)
class MapMatchingScoringConfig:
    """Explicit likelihood policy for candidate emission and transition scoring."""

    # Position likelihood uses the EKF horizontal covariance plus this minimum
    # uncertainty, preventing one overconfident estimate from rejecting every
    # nearby road because of tiny numerical covariance values.
    position_std_floor_m: float

    # Heading from velocity is meaningless near standstill, stop lights, or
    # very slow manoeuvres, so it is omitted below this speed.
    minimum_heading_speed_mps: float
    heading_std_floor_rad: float

    # OSM maxspeed values are incomplete and sometimes stale. They supply only
    # a weak soft penalty for implausibly high observed speed, never rejection.
    speed_limit_tolerance_mps: float
    speed_limit_std_mps: float
    speed_limit_penalty_weight: float

    # Transition scoring compares road-network distance with EKF displacement.
    # Uncertainty and slack prevent legitimate curves/junction geometry from
    # becoming impossible merely because straight-line displacement is shorter.
    transition_distance_std_floor_m: float
    transition_position_uncertainty_multiplier: float
    transition_route_slack_m: float
    maximum_route_distance_m: float

    def __post_init__(self) -> None:
        """Reject unsafe scoring policy before any HMM cycle begins."""

        positive_values = (
            self.position_std_floor_m,
            self.minimum_heading_speed_mps,
            self.heading_std_floor_rad,
            self.speed_limit_tolerance_mps,
            self.speed_limit_std_mps,
            self.transition_distance_std_floor_m,
            self.transition_position_uncertainty_multiplier,
            self.transition_route_slack_m,
            self.maximum_route_distance_m,
        )
        if not all(
            isfinite(value) and value > 0.0
            for value in positive_values
        ):
            raise ValueError(
                "Scoring distances, standard deviations, and bounds must be "
                "finite and positive."
            )

        if (
            not isfinite(self.speed_limit_penalty_weight)
            or self.speed_limit_penalty_weight < 0.0
        ):
            raise ValueError(
                "speed_limit_penalty_weight must be finite and non-negative."
            )


@dataclass(frozen=True, slots=True)
class CandidateEmissionScore:
    """Log-likelihood terms explaining one current candidate score."""

    candidate_id: str
    log_likelihood: float

    position_log_likelihood: float
    heading_log_likelihood: float
    speed_limit_log_likelihood: float


@dataclass(frozen=True, slots=True)
class CandidateTransitionScore:
    """Log-likelihood and route evidence between two time-ordered candidates."""

    previous_candidate_id: str
    current_candidate_id: str

    disposition: TransitionDisposition
    log_likelihood: float

    observed_displacement_m: float | None
    road_route_distance_m: float | None


def _require_candidate_alignment(
    *,
    graph: RoadGraph,
    candidate: RoadCandidate,
    estimate: NavigationEstimate,
) -> None:
    """Ensure a score never mixes candidates from another graph or timestamp."""

    if candidate.graph_id != graph.metadata.graph_id:
        raise ValueError(
            "Road candidate graph ID does not match the active road graph."
        )

    if candidate.timestamp_ns != estimate.timestamp_ns:
        raise ValueError(
            "Road candidate timestamp must match its navigation estimate."
        )


def _candidate_traversal(
    candidate: RoadCandidate,
) -> DirectedRoadTraversal:
    """Convert the shared candidate contract into graph traversal lookup."""

    return DirectedRoadTraversal(
        edge_id=candidate.edge_id,
        travel_direction=candidate.travel_direction,
    )


def _horizontal_position_enu_m(
    estimate: NavigationEstimate,
) -> Vector2:
    """Extract one finite horizontal EKF position."""

    east_m = estimate.position_enu_m[0]
    north_m = estimate.position_enu_m[1]

    if not (isfinite(east_m) and isfinite(north_m)):
        raise ValueError(
            "Navigation horizontal position must be finite."
        )

    return (east_m, north_m)


def _horizontal_speed_mps(
    estimate: NavigationEstimate,
) -> float:
    """Return finite EKF horizontal speed magnitude."""

    east_velocity_mps = estimate.velocity_enu_mps[0]
    north_velocity_mps = estimate.velocity_enu_mps[1]

    if not (
        isfinite(east_velocity_mps)
        and isfinite(north_velocity_mps)
    ):
        raise ValueError(
            "Navigation horizontal velocity must be finite."
        )

    return hypot(east_velocity_mps, north_velocity_mps)


def _motion_heading_enu_rad(
    *,
    estimate: NavigationEstimate,
    minimum_speed_mps: float,
) -> float | None:
    """Return GNSS-style motion heading only when speed makes it meaningful."""

    east_velocity_mps = estimate.velocity_enu_mps[0]
    north_velocity_mps = estimate.velocity_enu_mps[1]

    if _horizontal_speed_mps(estimate) < minimum_speed_mps:
        return None

    return atan2(
        east_velocity_mps,
        north_velocity_mps,
    ) % (2.0 * pi)


def _wrapped_heading_difference_rad(
    first_heading_rad: float,
    second_heading_rad: float,
) -> float:
    """Return the smallest angular separation in the interval [0, pi]."""

    if not (
        isfinite(first_heading_rad)
        and isfinite(second_heading_rad)
    ):
        raise ValueError("Heading values must be finite.")

    return abs(
        (first_heading_rad - second_heading_rad + pi)
        % (2.0 * pi)
        - pi
    )


def _gaussian_log_likelihood(
    *,
    residual: float,
    standard_deviation: float,
) -> float:
    """Return a normalized one-dimensional Gaussian log-likelihood."""

    if not (
        isfinite(residual)
        and isfinite(standard_deviation)
        and standard_deviation > 0.0
    ):
        raise ValueError(
            "Gaussian residual must be finite and standard deviation positive."
        )

    normalized_residual = residual / standard_deviation

    return (
        -0.5 * normalized_residual**2
        - log(standard_deviation)
        - 0.5 * log(2.0 * pi)
    )


def _horizontal_covariance_terms(
    estimate: NavigationEstimate,
    *,
    position_std_floor_m: float,
) -> tuple[float, float, float, float]:
    """Return a positive-definite horizontal covariance and its determinant.

    The returned values are:

        east_variance_m2,
        east_north_covariance_m2,
        north_variance_m2,
        determinant_m4
    """

    covariance = estimate.position_covariance_enu_m2

    east_variance_m2 = covariance[0][0]
    east_north_covariance_m2 = 0.5 * (
        covariance[0][1] + covariance[1][0]
    )
    north_variance_m2 = covariance[1][1]

    if not all(
        isfinite(value)
        for value in (
            east_variance_m2,
            east_north_covariance_m2,
            north_variance_m2,
        )
    ):
        raise ValueError(
            "Navigation horizontal covariance must be finite."
        )

    trace_m2 = east_variance_m2 + north_variance_m2
    discriminant_m2 = sqrt(
        (east_variance_m2 - north_variance_m2) ** 2
        + 4.0 * east_north_covariance_m2**2
    )
    smallest_eigenvalue_m2 = 0.5 * (
        trace_m2 - discriminant_m2
    )

    if smallest_eigenvalue_m2 < -1e-9:
        raise ValueError(
            "Navigation horizontal covariance must be positive semidefinite."
        )

    variance_floor_m2 = position_std_floor_m**2
    east_variance_m2 += variance_floor_m2
    north_variance_m2 += variance_floor_m2

    determinant_m4 = (
        east_variance_m2 * north_variance_m2
        - east_north_covariance_m2**2
    )
    if determinant_m4 <= 0.0:
        raise ValueError(
            "Position covariance must become positive definite after flooring."
        )

    return (
        east_variance_m2,
        east_north_covariance_m2,
        north_variance_m2,
        determinant_m4,
    )


def _position_log_likelihood(
    *,
    estimate: NavigationEstimate,
    candidate: RoadCandidate,
    config: MapMatchingScoringConfig,
) -> float:
    """Score candidate snap position under the EKF horizontal covariance ellipse."""

    position_enu_m = _horizontal_position_enu_m(estimate)

    east_residual_m = (
        candidate.snap_position_enu_m[0] - position_enu_m[0]
    )
    north_residual_m = (
        candidate.snap_position_enu_m[1] - position_enu_m[1]
    )

    (
        east_variance_m2,
        east_north_covariance_m2,
        north_variance_m2,
        determinant_m4,
    ) = _horizontal_covariance_terms(
        estimate,
        position_std_floor_m=config.position_std_floor_m,
    )

    mahalanobis_distance_squared = (
        north_variance_m2 * east_residual_m**2
        - 2.0
        * east_north_covariance_m2
        * east_residual_m
        * north_residual_m
        + east_variance_m2 * north_residual_m**2
    ) / determinant_m4

    return (
        -0.5 * mahalanobis_distance_squared
        - log(2.0 * pi)
        - 0.5 * log(determinant_m4)
    )


def _heading_log_likelihood(
    *,
    estimate: NavigationEstimate,
    candidate: RoadCandidate,
    config: MapMatchingScoringConfig,
) -> float:
    """Score road heading only while vehicle motion provides usable heading."""

    motion_heading_rad = _motion_heading_enu_rad(
        estimate=estimate,
        minimum_speed_mps=config.minimum_heading_speed_mps,
    )
    if motion_heading_rad is None:
        return 0.0

    if not isfinite(estimate.heading_variance_rad2):
        raise ValueError("Navigation heading variance must be finite.")

    heading_std_rad = max(
        config.heading_std_floor_rad,
        sqrt(max(0.0, estimate.heading_variance_rad2)),
    )
    heading_residual_rad = _wrapped_heading_difference_rad(
        motion_heading_rad,
        candidate.road_heading_enu_rad,
    )

    return _gaussian_log_likelihood(
        residual=heading_residual_rad,
        standard_deviation=heading_std_rad,
    )


def _speed_limit_log_likelihood(
    *,
    graph: RoadGraph,
    candidate: RoadCandidate,
    estimate: NavigationEstimate,
    config: MapMatchingScoringConfig,
) -> float:
    """Apply only a weak penalty when current speed exceeds tagged OSM maxspeed."""

    segment = graph.segment(candidate.edge_id)
    speed_limit_mps = segment.attributes.speed_limit_mps

    if speed_limit_mps is None:
        return 0.0

    speed_excess_mps = max(
        0.0,
        _horizontal_speed_mps(estimate)
        - speed_limit_mps
        - config.speed_limit_tolerance_mps,
    )

    if speed_excess_mps == 0.0:
        return 0.0

    normalized_excess = (
        speed_excess_mps / config.speed_limit_std_mps
    )

    return (
        -0.5
        * config.speed_limit_penalty_weight
        * normalized_excess**2
    )


def score_candidate_emission(
    *,
    graph: RoadGraph,
    candidate: RoadCandidate,
    estimate: NavigationEstimate,
    config: MapMatchingScoringConfig,
) -> CandidateEmissionScore:
    """Return explainable HMM emission score for one current road candidate."""

    _require_candidate_alignment(
        graph=graph,
        candidate=candidate,
        estimate=estimate,
    )

    position_score = _position_log_likelihood(
        estimate=estimate,
        candidate=candidate,
        config=config,
    )
    heading_score = _heading_log_likelihood(
        estimate=estimate,
        candidate=candidate,
        config=config,
    )
    speed_limit_score = _speed_limit_log_likelihood(
        graph=graph,
        candidate=candidate,
        estimate=estimate,
        config=config,
    )

    return CandidateEmissionScore(
        candidate_id=candidate.candidate_id,
        log_likelihood=(
            position_score
            + heading_score
            + speed_limit_score
        ),
        position_log_likelihood=position_score,
        heading_log_likelihood=heading_score,
        speed_limit_log_likelihood=speed_limit_score,
    )


def score_candidate_emissions(
    *,
    graph: RoadGraph,
    candidates: tuple[RoadCandidate, ...],
    estimate: NavigationEstimate,
    config: MapMatchingScoringConfig,
) -> tuple[CandidateEmissionScore, ...]:
    """Score a complete same-timestamp candidate batch in deterministic order."""

    return tuple(
        score_candidate_emission(
            graph=graph,
            candidate=candidate,
            estimate=estimate,
            config=config,
        )
        for candidate in candidates
    )


def _candidate_projection(
    *,
    graph: RoadGraph,
    candidate: RoadCandidate,
):
    """Reconstruct along-road progress from the candidate snap point."""

    traversal = _candidate_traversal(candidate)

    return project_point_to_polyline(
        point_enu_m=candidate.snap_position_enu_m,
        geometry_enu_m=graph.traversal_geometry(traversal),
    )


def _road_route_distance_m(
    *,
    graph: RoadGraph,
    previous_candidate: RoadCandidate,
    current_candidate: RoadCandidate,
    maximum_route_distance_m: float,
) -> float | None:
    """Return legal directed road distance between two snapped candidate points.

    A direct forward movement on the same traversal is handled exactly. Other
    transitions travel from the previous snap to its legal end node, across the
    graph, then from the current traversal's start node to its current snap.
    """

    previous_traversal = _candidate_traversal(previous_candidate)
    current_traversal = _candidate_traversal(current_candidate)

    previous_projection = _candidate_projection(
        graph=graph,
        candidate=previous_candidate,
    )
    current_projection = _candidate_projection(
        graph=graph,
        candidate=current_candidate,
    )

    if (
        previous_traversal == current_traversal
        and current_projection.along_traversal_m
        >= previous_projection.along_traversal_m
    ):
        direct_progress_m = (
            current_projection.along_traversal_m
            - previous_projection.along_traversal_m
        )
        return (
            direct_progress_m
            if direct_progress_m <= maximum_route_distance_m
            else None
        )

    fixed_distance_m = (
        previous_projection.traversal_length_m
        - previous_projection.along_traversal_m
        + current_projection.along_traversal_m
    )

    if fixed_distance_m > maximum_route_distance_m:
        return None

    previous_end_node_id = graph.traversal_end_node_id(
        previous_traversal
    )
    current_start_node_id = graph.traversal_start_node_id(
        current_traversal
    )

    if previous_end_node_id == current_start_node_id:
        connecting_distance_m = 0.0
    else:
        connecting_distance_m = graph.shortest_node_path_distance_m(
            start_node_id=previous_end_node_id,
            end_node_id=current_start_node_id,
            maximum_distance_m=(
                maximum_route_distance_m - fixed_distance_m
            ),
        )

        if connecting_distance_m is None:
            return None

    route_distance_m = fixed_distance_m + connecting_distance_m

    return (
        route_distance_m
        if route_distance_m <= maximum_route_distance_m
        else None
    )


def _relative_position_std_m(
    *,
    previous_estimate: NavigationEstimate,
    current_estimate: NavigationEstimate,
    config: MapMatchingScoringConfig,
) -> float:
    """Return conservative one-dimensional uncertainty for EKF displacement."""

    previous_covariance = previous_estimate.position_covariance_enu_m2
    current_covariance = current_estimate.position_covariance_enu_m2

    horizontal_variance_trace_m2 = (
        previous_covariance[0][0]
        + previous_covariance[1][1]
        + current_covariance[0][0]
        + current_covariance[1][1]
    )

    if (
        not isfinite(horizontal_variance_trace_m2)
        or horizontal_variance_trace_m2 < -1e-9
    ):
        raise ValueError(
            "Transition position covariance trace must be non-negative and finite."
        )

    return max(
        config.transition_distance_std_floor_m,
        config.transition_position_uncertainty_multiplier
        * sqrt(max(0.0, horizontal_variance_trace_m2)),
    )


def _observed_displacement_m(
    *,
    previous_estimate: NavigationEstimate,
    current_estimate: NavigationEstimate,
) -> float:
    """Return horizontal EKF displacement between consecutive map-match cycles."""

    previous_position_enu_m = _horizontal_position_enu_m(
        previous_estimate
    )
    current_position_enu_m = _horizontal_position_enu_m(
        current_estimate
    )

    return hypot(
        current_position_enu_m[0] - previous_position_enu_m[0],
        current_position_enu_m[1] - previous_position_enu_m[1],
    )


def score_candidate_transition(
    *,
    graph: RoadGraph,
    previous_candidate: RoadCandidate,
    current_candidate: RoadCandidate,
    previous_estimate: NavigationEstimate,
    current_estimate: NavigationEstimate,
    config: MapMatchingScoringConfig,
) -> CandidateTransitionScore:
    """Score one time-ordered directed transition for bounded Viterbi.

    An unreachable transition is represented by negative infinity rather than
    an exception. Viterbi can then discard that path normally while retaining
    diagnostic evidence about why the transition was impossible.
    """

    _require_candidate_alignment(
        graph=graph,
        candidate=previous_candidate,
        estimate=previous_estimate,
    )
    _require_candidate_alignment(
        graph=graph,
        candidate=current_candidate,
        estimate=current_estimate,
    )

    if (
        current_estimate.timestamp_ns
        <= previous_estimate.timestamp_ns
    ):
        return CandidateTransitionScore(
            previous_candidate_id=previous_candidate.candidate_id,
            current_candidate_id=current_candidate.candidate_id,
            disposition=TransitionDisposition.TIMESTAMP_INVALID,
            log_likelihood=-inf,
            observed_displacement_m=None,
            road_route_distance_m=None,
        )

    observed_displacement_m = _observed_displacement_m(
        previous_estimate=previous_estimate,
        current_estimate=current_estimate,
    )
    displacement_std_m = _relative_position_std_m(
        previous_estimate=previous_estimate,
        current_estimate=current_estimate,
        config=config,
    )

    route_search_bound_m = min(
        config.maximum_route_distance_m,
        observed_displacement_m
        + config.transition_route_slack_m
        + 3.0 * displacement_std_m,
    )

    road_route_distance_m = _road_route_distance_m(
        graph=graph,
        previous_candidate=previous_candidate,
        current_candidate=current_candidate,
        maximum_route_distance_m=route_search_bound_m,
    )

    if road_route_distance_m is None:
        return CandidateTransitionScore(
            previous_candidate_id=previous_candidate.candidate_id,
            current_candidate_id=current_candidate.candidate_id,
            disposition=TransitionDisposition.UNREACHABLE,
            log_likelihood=-inf,
            observed_displacement_m=observed_displacement_m,
            road_route_distance_m=None,
        )

    distance_residual_m = (
        road_route_distance_m - observed_displacement_m
    )
    transition_log_likelihood = _gaussian_log_likelihood(
        residual=distance_residual_m,
        standard_deviation=displacement_std_m,
    )

    return CandidateTransitionScore(
        previous_candidate_id=previous_candidate.candidate_id,
        current_candidate_id=current_candidate.candidate_id,
        disposition=TransitionDisposition.SCORED,
        log_likelihood=transition_log_likelihood,
        observed_displacement_m=observed_displacement_m,
        road_route_distance_m=road_route_distance_m,
    )



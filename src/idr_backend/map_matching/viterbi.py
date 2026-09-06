"""Bounded-latency incremental Viterbi map matching.

This module combines current candidate emission scores with legal transitions
from the prior candidate layer. It retains only a small history window, so it
can stabilize route choices without growing memory for an entire drive.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from math import exp, inf, isfinite
from types import MappingProxyType

from ..sensors.types import (
    NavigationEstimate,
    RoadCandidate,
)
from .candidates import PreviousTraversalBelief
from .graph import (
    DirectedRoadTraversal,
    RoadGraph,
)
from .scoring import (
    MapMatchingScoringConfig,
    score_candidate_emissions,
    score_candidate_transition,
)


class ViterbiDisposition(StrEnum):
    """Meaningful outcome of one bounded HMM update."""

    INITIALIZED = "initialized"
    UPDATED = "updated"
    REINITIALIZED_AFTER_DISCONNECTION = (
        "reinitialized_after_disconnection"
    )
    RESET_AFTER_TIMING_GAP = "reset_after_timing_gap"
    RESET_NO_CANDIDATES = "reset_no_candidates"


@dataclass(frozen=True, slots=True)
class IncrementalViterbiConfig:
    """Operational policy for bounded history and safe road publication."""

    # A committed decision waits for this many later candidate layers. Small
    # values reduce latency; larger values reduce rapid flips on parallel roads.
    backtracking_window_steps: int

    # A gap means route continuity cannot honestly be scored. The current layer
    # becomes a fresh HMM start instead of bridging an unsupported interval.
    maximum_cycle_gap_ns: int

    # The best relative Viterbi-path weight must exceed this before a delayed
    # match is published to UI or later road-context feedback.
    minimum_publish_confidence: float

    def __post_init__(self) -> None:
        """Validate runtime policy before HMM state begins accumulating."""

        if self.backtracking_window_steps < 1:
            raise ValueError(
                "backtracking_window_steps must be at least one."
            )

        if self.maximum_cycle_gap_ns <= 0:
            raise ValueError(
                "maximum_cycle_gap_ns must be positive."
            )

        if (
            not isfinite(self.minimum_publish_confidence)
            or not 0.0 <= self.minimum_publish_confidence <= 1.0
        ):
            raise ValueError(
                "minimum_publish_confidence must be in [0, 1]."
            )


@dataclass(frozen=True, slots=True)
class ViterbiBeliefEntry:
    """One current candidate weighted relative to other Viterbi paths."""

    candidate: RoadCandidate
    relative_path_probability: float
    best_path_log_likelihood: float

    def __post_init__(self) -> None:
        """Keep belief output safe for future road-context consumption."""

        if (
            not isfinite(self.relative_path_probability)
            or not 0.0 <= self.relative_path_probability <= 1.0
        ):
            raise ValueError(
                "Relative Viterbi probability must be in [0, 1]."
            )

        if not isfinite(self.best_path_log_likelihood):
            raise ValueError(
                "Published Viterbi path likelihood must be finite."
            )


@dataclass(frozen=True, slots=True)
class MapMatchBelief:
    """Current ranked path belief, suitable only for a future pipeline cycle.

    These weights normalize maximum-path scores. They are useful for confidence
    and bounded prior-candidate retention, but they are not full forward-backward
    Bayesian marginals.
    """

    timestamp_ns: int
    entries: tuple[ViterbiBeliefEntry, ...]

    def __post_init__(self) -> None:
        """Require one non-empty, timestamp-aligned ranked candidate belief."""

        if self.timestamp_ns < 0:
            raise ValueError("Map-match belief timestamp must be non-negative.")

        if not self.entries:
            raise ValueError("Map-match belief must contain at least one entry.")

        if any(
            entry.candidate.timestamp_ns != self.timestamp_ns
            for entry in self.entries
        ):
            raise ValueError(
                "Belief entry timestamps must match the belief timestamp."
            )

        if len(
            {
                entry.candidate.candidate_id
                for entry in self.entries
            }
        ) != len(self.entries):
            raise ValueError(
                "Map-match belief candidate IDs must be unique."
            )

    @property
    def best_entry(self) -> ViterbiBeliefEntry:
        """Return the highest-ranked current Viterbi path state."""

        return self.entries[0]

    def as_previous_traversal_beliefs(
        self,
    ) -> tuple[PreviousTraversalBelief, ...]:
        """Expose this completed cycle as causal input to the next one."""

        return tuple(
            PreviousTraversalBelief(
                source_belief_timestamp_ns=self.timestamp_ns,
                traversal=DirectedRoadTraversal(
                    edge_id=entry.candidate.edge_id,
                    travel_direction=entry.candidate.travel_direction,
                ),
                probability=entry.relative_path_probability,
            )
            for entry in self.entries
        )


@dataclass(frozen=True, slots=True)
class CommittedRoadMatch:
    """A delayed, stabilized road decision safe for UI publication."""

    timestamp_ns: int
    candidate: RoadCandidate
    confidence: float


@dataclass(frozen=True, slots=True)
class ViterbiUpdateResult:
    """Everything published after one causal candidate-batch update."""

    disposition: ViterbiDisposition
    current_belief: MapMatchBelief | None

    # This is older than current_belief by the configured backtracking window.
    # It is None during warm-up, reset, or insufficient confidence.
    committed_match: CommittedRoadMatch | None


@dataclass(frozen=True, slots=True)
class _ViterbiPathState:
    """Best path reaching one candidate in one HMM layer."""

    best_path_log_likelihood: float
    predecessor_candidate_id: str | None


@dataclass(frozen=True, slots=True)
class _ViterbiLayer:
    """One timestamped candidate lattice layer retained in bounded history."""

    estimate: NavigationEstimate
    candidates_by_id: Mapping[str, RoadCandidate]
    states_by_candidate_id: Mapping[str, _ViterbiPathState]


def _candidate_mapping(
    *,
    candidates: tuple[RoadCandidate, ...],
    estimate: NavigationEstimate,
) -> Mapping[str, RoadCandidate]:
    """Validate one same-time candidate batch and freeze lookup by ID."""

    candidate_by_id: dict[str, RoadCandidate] = {}

    for candidate in candidates:
        if candidate.timestamp_ns != estimate.timestamp_ns:
            raise ValueError(
                "Every candidate must share the navigation estimate timestamp."
            )

        if candidate.candidate_id in candidate_by_id:
            raise ValueError(
                "Candidate IDs must be unique inside one Viterbi layer."
            )

        candidate_by_id[candidate.candidate_id] = candidate

    if not candidate_by_id:
        raise ValueError(
            "A Viterbi layer requires at least one candidate."
        )

    return MappingProxyType(candidate_by_id)


def _initial_layer(
    *,
    graph: RoadGraph,
    candidates: tuple[RoadCandidate, ...],
    estimate: NavigationEstimate,
    scoring_config: MapMatchingScoringConfig,
) -> _ViterbiLayer:
    """Create a fresh HMM layer using only current emission likelihoods."""

    candidate_by_id = _candidate_mapping(
        candidates=candidates,
        estimate=estimate,
    )
    emission_scores = score_candidate_emissions(
        graph=graph,
        candidates=candidates,
        estimate=estimate,
        config=scoring_config,
    )

    state_by_candidate_id = {
        score.candidate_id: _ViterbiPathState(
            best_path_log_likelihood=score.log_likelihood,
            predecessor_candidate_id=None,
        )
        for score in emission_scores
    }

    return _ViterbiLayer(
        estimate=estimate,
        candidates_by_id=candidate_by_id,
        states_by_candidate_id=MappingProxyType(
            state_by_candidate_id
        ),
    )


def _best_candidate_id(
    layer: _ViterbiLayer,
) -> str:
    """Return the best path with stable ID tie-breaking."""

    return max(
        layer.states_by_candidate_id,
        key=lambda candidate_id: (
            layer.states_by_candidate_id[
                candidate_id
            ].best_path_log_likelihood,
            candidate_id,
        ),
    )


def _belief_from_layer(
    layer: _ViterbiLayer,
) -> MapMatchBelief:
    """Normalize current maximum-path scores into stable relative weights."""

    best_score = max(
        state.best_path_log_likelihood
        for state in layer.states_by_candidate_id.values()
    )

    unnormalized_weights = {
        candidate_id: exp(
            state.best_path_log_likelihood - best_score
        )
        for candidate_id, state in layer.states_by_candidate_id.items()
    }
    total_weight = sum(unnormalized_weights.values())

    if not isfinite(total_weight) or total_weight <= 0.0:
        raise RuntimeError(
            "Viterbi belief normalization produced no positive weight."
        )

    ordered_candidate_ids = sorted(
        layer.states_by_candidate_id,
        key=lambda candidate_id: (
            -layer.states_by_candidate_id[
                candidate_id
            ].best_path_log_likelihood,
            candidate_id,
        ),
    )

    return MapMatchBelief(
        timestamp_ns=layer.estimate.timestamp_ns,
        entries=tuple(
            ViterbiBeliefEntry(
                candidate=layer.candidates_by_id[candidate_id],
                relative_path_probability=(
                    unnormalized_weights[candidate_id] / total_weight
                ),
                best_path_log_likelihood=(
                    layer.states_by_candidate_id[
                        candidate_id
                    ].best_path_log_likelihood
                ),
            )
            for candidate_id in ordered_candidate_ids
        ),
    )


class IncrementalViterbiMatcher:
    """Single-owner bounded Viterbi matcher for one road graph and drive."""

    def __init__(
        self,
        *,
        graph: RoadGraph,
        scoring_config: MapMatchingScoringConfig,
        config: IncrementalViterbiConfig,
    ) -> None:
        """Bind immutable graph/scoring policy and begin with empty history."""

        self._graph = graph
        self._scoring_config = scoring_config
        self._config = config
        self._history: deque[_ViterbiLayer] = deque()

    @property
    def current_belief(self) -> MapMatchBelief | None:
        """Return the latest live belief without advancing matcher state."""

        if not self._history:
            return None

        return _belief_from_layer(self._history[-1])

    def reset(self) -> None:
        """Forget path continuity after a confirmed session or graph reset."""

        self._history.clear()


    def update(
        self,
        *,
        estimate: NavigationEstimate,
        candidates: tuple[RoadCandidate, ...],
    ) -> ViterbiUpdateResult:
        """Advance one causal candidate layer and optionally commit old output."""

        if not candidates:
            self._history.clear()
            return ViterbiUpdateResult(
                disposition=ViterbiDisposition.RESET_NO_CANDIDATES,
                current_belief=None,
                committed_match=None,
            )

        if not self._history:
            initial_layer = _initial_layer(
                graph=self._graph,
                candidates=candidates,
                estimate=estimate,
                scoring_config=self._scoring_config,
            )
            self._history.append(initial_layer)

            return ViterbiUpdateResult(
                disposition=ViterbiDisposition.INITIALIZED,
                current_belief=_belief_from_layer(initial_layer),
                committed_match=None,
            )

        previous_layer = self._history[-1]
        timestamp_gap_ns = (
            estimate.timestamp_ns
            - previous_layer.estimate.timestamp_ns
        )

        if (
            timestamp_gap_ns <= 0
            or timestamp_gap_ns > self._config.maximum_cycle_gap_ns
        ):
            reset_layer = _initial_layer(
                graph=self._graph,
                candidates=candidates,
                estimate=estimate,
                scoring_config=self._scoring_config,
            )
            self._history.clear()
            self._history.append(reset_layer)

            return ViterbiUpdateResult(
                disposition=ViterbiDisposition.RESET_AFTER_TIMING_GAP,
                current_belief=_belief_from_layer(reset_layer),
                committed_match=None,
            )

        next_layer = self._transition_layer(
            previous_layer=previous_layer,
            estimate=estimate,
            candidates=candidates,
        )

        if next_layer is None:
            # Current candidates are spatially plausible but no legal graph path
            # could connect them to the previous layer. Restart rather than
            # preserving a false route history through a divider or map gap.
            reset_layer = _initial_layer(
                graph=self._graph,
                candidates=candidates,
                estimate=estimate,
                scoring_config=self._scoring_config,
            )
            self._history.clear()
            self._history.append(reset_layer)

            return ViterbiUpdateResult(
                disposition=(
                    ViterbiDisposition.REINITIALIZED_AFTER_DISCONNECTION
                ),
                current_belief=_belief_from_layer(reset_layer),
                committed_match=None,
            )

        self._history.append(next_layer)
        current_belief = _belief_from_layer(next_layer)

        committed_match = self._commit_if_ready(
            confidence=current_belief.best_entry.relative_path_probability
        )

        return ViterbiUpdateResult(
            disposition=ViterbiDisposition.UPDATED,
            current_belief=current_belief,
            committed_match=committed_match,
        )

    
    def _transition_layer(
        self,
        *,
        previous_layer: _ViterbiLayer,
        estimate: NavigationEstimate,
        candidates: tuple[RoadCandidate, ...],
    ) -> _ViterbiLayer | None:
        """Build one dynamic-programming layer from prior best-path states."""

        candidate_by_id = _candidate_mapping(
            candidates=candidates,
            estimate=estimate,
        )
        emission_scores = score_candidate_emissions(
            graph=self._graph,
            candidates=candidates,
            estimate=estimate,
            config=self._scoring_config,
        )
        emission_by_candidate_id = {
            score.candidate_id: score.log_likelihood
            for score in emission_scores
        }

        next_states: dict[str, _ViterbiPathState] = {}

        for current_candidate_id, current_candidate in (
            candidate_by_id.items()
        ):
            best_total_score = -inf
            best_predecessor_id: str | None = None

            for (
                previous_candidate_id,
                previous_state,
            ) in previous_layer.states_by_candidate_id.items():
                transition_score = score_candidate_transition(
                    graph=self._graph,
                    previous_candidate=(
                        previous_layer.candidates_by_id[
                            previous_candidate_id
                        ]
                    ),
                    current_candidate=current_candidate,
                    previous_estimate=previous_layer.estimate,
                    current_estimate=estimate,
                    config=self._scoring_config,
                )

                if not isfinite(transition_score.log_likelihood):
                    continue

                total_score = (
                    previous_state.best_path_log_likelihood
                    + transition_score.log_likelihood
                    + emission_by_candidate_id[current_candidate_id]
                )

                if (
                    total_score > best_total_score
                    or (
                        total_score == best_total_score
                        and (
                            best_predecessor_id is None
                            or previous_candidate_id
                            < best_predecessor_id
                        )
                    )
                ):
                    best_total_score = total_score
                    best_predecessor_id = previous_candidate_id

            if best_predecessor_id is not None:
                next_states[current_candidate_id] = _ViterbiPathState(
                    best_path_log_likelihood=best_total_score,
                    predecessor_candidate_id=best_predecessor_id,
                )

        if not next_states:
            return None

        return _ViterbiLayer(
            estimate=estimate,
            candidates_by_id=candidate_by_id,
            states_by_candidate_id=MappingProxyType(next_states),
        )

    def _commit_if_ready(
        self,
        *,
        confidence: float,
    ) -> CommittedRoadMatch | None:
        """Trace the best current path and commit its oldest stable candidate."""

        required_layer_count = (
            self._config.backtracking_window_steps + 1
        )
        if len(self._history) <= required_layer_count:
            return None

        latest_candidate_id = _best_candidate_id(self._history[-1])
        candidate_id = latest_candidate_id

        # Follow the selected current path backwards to the oldest retained
        # layer. Each predecessor is a candidate ID in the immediately earlier
        # layer, so no full route history is stored.
        for layer_index in range(
            len(self._history) - 1,
            0,
            -1,
        ):
            predecessor_candidate_id = (
                self._history[layer_index]
                .states_by_candidate_id[candidate_id]
                .predecessor_candidate_id
            )
            if predecessor_candidate_id is None:
                raise RuntimeError(
                    "Connected Viterbi layer is missing a predecessor."
                )

            candidate_id = predecessor_candidate_id

        oldest_layer = self._history[0]
        committed_candidate = oldest_layer.candidates_by_id[candidate_id]

        # The old layer is now beyond the configured decision lag. Its candidate
        # will never change under future bounded traceback, so memory can remain
        # fixed throughout a long drive.
        self._history.popleft()

        if confidence < self._config.minimum_publish_confidence:
            return None

        return CommittedRoadMatch(
            timestamp_ns=committed_candidate.timestamp_ns,
            candidate=committed_candidate,
            confidence=confidence,
        )
"""Causal composition of candidates, incremental Viterbi, and match output.

This module is independent of the EKF implementation. It accepts only a
published navigation estimate in the graph's ENU frame, which makes it useful
for replay, simulation, and the later fusion wrapper without allowing map
evidence to change the current EKF state.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace

from idr_backend.sensors.types import NavigationEstimate

from .candidates import (
    CandidateGenerationConfig,
    CandidateGenerationResult,
    RoadCandidateGenerator,
)
from .graph import RoadGraph
from .scoring import MapMatchingScoringConfig
from .viterbi import (
    CommittedRoadMatch,
    IncrementalViterbiConfig,
    IncrementalViterbiMatcher,
    ViterbiDisposition,
    ViterbiUpdateResult,
)


@dataclass(frozen=True, slots=True)
class MapMatchingCycleResult:
    """One map-matching cycle beside its unchanged current EKF estimate.

    ``committed_navigation_estimate`` is deliberately delayed by Viterbi's
    configured backtracking window. Its timestamp is therefore the timestamp
    of the road decision, rather than incorrectly attaching an old road to the
    newest fusion state.
    """

    navigation_estimate: NavigationEstimate
    candidate_generation: CandidateGenerationResult
    viterbi: ViterbiUpdateResult
    committed_navigation_estimate: NavigationEstimate | None


class IncrementalMapMatchingPipeline:
    """Own one bounded, causal HMM session for one immutable road graph."""

    def __init__(
        self,
        *,
        graph: RoadGraph,
        candidate_config: CandidateGenerationConfig,
        scoring_config: MapMatchingScoringConfig,
        viterbi_config: IncrementalViterbiConfig,
    ) -> None:
        """Bind all explicit policies before processing navigation estimates."""

        self._graph = graph
        self._candidate_generator = RoadCandidateGenerator(
            graph=graph,
            config=candidate_config,
        )
        self._matcher = IncrementalViterbiMatcher(
            graph=graph,
            scoring_config=scoring_config,
            config=viterbi_config,
        )
        # A commit is at most this far behind the current layer. Keeping exact
        # source estimates lets the delayed road decision retain its own time.
        self._estimate_history: deque[NavigationEstimate] = deque(
            maxlen=viterbi_config.backtracking_window_steps + 2
        )

    @property
    def graph(self) -> RoadGraph:
        """Expose immutable graph provenance without a mutable matcher handle."""

        return self._graph

    def reset(self) -> None:
        """Forget HMM continuity after a graph/session reset."""

        self._matcher.reset()
        self._estimate_history.clear()

    def update(self, estimate: NavigationEstimate) -> MapMatchingCycleResult:
        """Generate candidates and advance exactly one same-time HMM layer.

        The previous Viterbi belief may rank current geometric candidates, but
        never creates candidates outside the current covariance-bounded search.
        Feedback for future road context belongs to the outer pipeline after
        this result has been completely returned.
        """

        prior_beliefs = (
            ()
            if self._matcher.current_belief is None
            else self._matcher.current_belief.as_previous_traversal_beliefs()
        )
        candidates = self._candidate_generator.generate(
            estimate=estimate,
            prior_beliefs=prior_beliefs,
        )
        viterbi = self._matcher.update(
            estimate=estimate,
            candidates=candidates.candidates,
        )

        if viterbi.disposition in {
            ViterbiDisposition.RESET_NO_CANDIDATES,
            ViterbiDisposition.RESET_AFTER_TIMING_GAP,
            ViterbiDisposition.REINITIALIZED_AFTER_DISCONNECTION,
        }:
            self._estimate_history.clear()
        self._estimate_history.append(estimate)

        committed_estimate = self._decorate_committed_estimate(
            viterbi.committed_match
        )
        return MapMatchingCycleResult(
            navigation_estimate=estimate,
            candidate_generation=candidates,
            viterbi=viterbi,
            committed_navigation_estimate=committed_estimate,
        )

    def _decorate_committed_estimate(
        self,
        committed_match: CommittedRoadMatch | None,
    ) -> NavigationEstimate | None:
        """Attach a stable road only to its original, delayed EKF estimate."""

        if committed_match is None:
            return None
        source = next(
            (
                estimate
                for estimate in self._estimate_history
                if estimate.timestamp_ns == committed_match.timestamp_ns
            ),
            None,
        )
        if source is None:
            raise RuntimeError(
                "Viterbi committed a timestamp absent from bounded estimate history."
            )
        return replace(
            source,
            matched_road_edge_id=committed_match.candidate.edge_id,
            map_match_confidence=committed_match.confidence,
        )

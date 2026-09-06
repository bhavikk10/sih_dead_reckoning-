"""End-to-end composition of committed fusion states and map matching.

Map matching is intentionally downstream-only. It consumes a published EKF
estimate and returns a separate delayed road decision; it never adds a road
measurement to the current filter or changes fusion's covariance.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from idr_backend.fusion.observations import LocalEnuReference
from idr_backend.map_matching.candidates import CandidateGenerationConfig
from idr_backend.map_matching.graph import RoadGraph
from idr_backend.map_matching.pipeline import (
    IncrementalMapMatchingPipeline,
    MapMatchingCycleResult,
)
from idr_backend.map_matching.scoring import MapMatchingScoringConfig
from idr_backend.map_matching.viterbi import IncrementalViterbiConfig
from idr_backend.sensors.gnss import GnssFixQuality
from idr_backend.sensors.types import GnssFix, RawSensorSample

from .feedback import (
    CandidateBelief,
    FeedbackConfig,
    FeedbackLookup,
    MapMatchFeedback,
    MapMatchFeedbackStore,
)
from .fusion import FusionPipelineResult, NavigationFusionPipeline
from .runtime import RuntimeSnapshot


@dataclass(frozen=True, slots=True)
class NavigationMapMatchingResult:
    """One fusion result and optional downstream map-match processing result."""

    fusion: FusionPipelineResult
    map_matching: MapMatchingCycleResult | None
    feedback_published: MapMatchFeedback | None


def local_enu_reference_for_graph(graph: RoadGraph) -> LocalEnuReference:
    """Return the exact graph ENU origin required for compatible fusion setup."""

    reference = graph.metadata.enu_reference
    return LocalEnuReference(
        latitude_deg=reference.latitude_deg,
        longitude_deg=reference.longitude_deg,
        altitude_m=reference.altitude_m,
    )


class NavigationMapMatchingPipeline:
    """Run raw inputs through fusion, then map-match only committed EKF cycles."""

    def __init__(
        self,
        *,
        fusion_pipeline: NavigationFusionPipeline,
        graph: RoadGraph,
        candidate_config: CandidateGenerationConfig,
        scoring_config: MapMatchingScoringConfig,
        viterbi_config: IncrementalViterbiConfig,
        feedback_config: FeedbackConfig,
    ) -> None:
        """Bind compatible fusion and map frames before accepting any samples."""

        _require_matching_enu_reference(
            fusion_reference=fusion_pipeline.local_enu_reference,
            graph=graph,
        )
        self._fusion_pipeline = fusion_pipeline
        self._map_matching_pipeline = IncrementalMapMatchingPipeline(
            graph=graph,
            candidate_config=candidate_config,
            scoring_config=scoring_config,
            viterbi_config=viterbi_config,
        )
        self._feedback_store = MapMatchFeedbackStore(feedback_config)

    @property
    def runtime_snapshot(self) -> RuntimeSnapshot:
        """Expose the fusion runtime state without treating HMM output as EKF state."""

        return self._fusion_pipeline.runtime_snapshot

    @property
    def map_matching_pipeline(self) -> IncrementalMapMatchingPipeline:
        """Expose map feedback/query methods through the owned matcher boundary."""

        return self._map_matching_pipeline

    def prior_feedback_for_cycle(self, *, cycle_timestamp_ns: int) -> FeedbackLookup:
        """Return only a prior completed HMM belief for future road context."""

        return self._feedback_store.prior_for_cycle(
            cycle_timestamp_ns=cycle_timestamp_ns,
            graph_id=self._map_matching_pipeline.graph.metadata.graph_id,
        )

    def push_gnss_fix(self, fix: GnssFix) -> GnssFixQuality:
        """Forward GNSS unchanged to deterministic preprocessing and fusion."""

        return self._fusion_pipeline.push_gnss_fix(fix)

    def push_raw_sample(
        self,
        raw_sample: RawSensorSample,
    ) -> tuple[NavigationMapMatchingResult, ...]:
        """Process raw input and map-match only newly committed fusion estimates."""

        results = self._fusion_pipeline.push_raw_sample(raw_sample)
        return tuple(self._match_if_current(result) for result in results)

    def reset_map_matching(self) -> None:
        """Clear route continuity without altering the live EKF state."""

        self._map_matching_pipeline.reset()
        self._feedback_store.reset()

    def stop(self) -> RuntimeSnapshot:
        """End the owned fusion session after its final map-matching cycle."""

        return self._fusion_pipeline.stop()

    def _match_if_current(
        self,
        fusion: FusionPipelineResult,
    ) -> NavigationMapMatchingResult:
        """Avoid re-matching a stale estimate after rejected preprocessing input."""

        estimate = fusion.navigation_estimate
        sample = fusion.pre_ekf.preprocessing.vehicle_imu_sample
        if (
            estimate is None
            or sample is None
            or fusion.runtime_snapshot.last_cycle_timestamp_ns != sample.timestamp_ns
            or estimate.timestamp_ns != sample.timestamp_ns
        ):
            return NavigationMapMatchingResult(
                fusion=fusion,
                map_matching=None,
                feedback_published=None,
            )
        map_matching = self._map_matching_pipeline.update(estimate)
        return NavigationMapMatchingResult(
            fusion=fusion,
            map_matching=map_matching,
            feedback_published=self._publish_feedback(map_matching),
        )

    def _publish_feedback(
        self,
        map_matching: MapMatchingCycleResult,
    ) -> MapMatchFeedback | None:
        """Publish only completed HMM belief for a strictly later consumer cycle."""

        belief = map_matching.viterbi.current_belief
        if belief is None:
            self._feedback_store.reset()
            return None
        feedback = MapMatchFeedback(
            timestamp_ns=belief.timestamp_ns,
            graph_id=self._map_matching_pipeline.graph.metadata.graph_id,
            candidate_beliefs=tuple(
                CandidateBelief(
                    candidate=entry.candidate,
                    probability=entry.relative_path_probability,
                )
                for entry in belief.entries
            ),
            selected_candidate_id=belief.best_entry.candidate.candidate_id,
            map_match_confidence=belief.best_entry.relative_path_probability,
        )
        self._feedback_store.publish_completed_match(feedback)
        return feedback


def _require_matching_enu_reference(
    *,
    fusion_reference: LocalEnuReference | None,
    graph: RoadGraph,
) -> None:
    """Reject the metre-scale frame mismatch that would corrupt map scores."""

    if fusion_reference is None:
        raise ValueError(
            "Map-matched fusion requires FusionPipelineConfig.local_enu_reference "
            "set from local_enu_reference_for_graph(graph)."
        )
    graph_reference = graph.metadata.enu_reference
    fields = (
        (fusion_reference.latitude_deg, graph_reference.latitude_deg),
        (fusion_reference.longitude_deg, graph_reference.longitude_deg),
        (fusion_reference.altitude_m, graph_reference.altitude_m),
    )
    if not all(isclose(left, right, rel_tol=0.0, abs_tol=1e-9) for left, right in fields):
        raise ValueError(
            "Fusion and road graph use different ENU origins; configure fusion "
            "with local_enu_reference_for_graph(graph)."
        )

"""Runtime-safe assembly of a road-context candidate mixture.

This module deliberately stops at an auditable mixture decision.  It does not
inject an EKF measurement, schedule low-rate updates, or alter the existing
deterministic navigation pipeline.  A future fusion integration may consume
only an ``AVAILABLE`` decision after its own rate/NIS/covariance gates pass.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from idr_backend.map_matching.graph import RoadGraph
from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextEdgeFeatures,
)
from idr_backend.road_context.graph_features import build_road_context_edge_features
from idr_backend.road_context.priors import (
    CandidateRoadContextPrediction,
    RoadContextMixtureConfig,
    RoadContextMixtureDecision,
    build_road_context_mixture,
)
from idr_backend.road_context.quantile_model import RoadContextQuantilePredictor
from idr_backend.road_context.rules import (
    RoadContextRuleConfig,
    apply_road_context_rules,
)
from idr_backend.pipeline.feedback import (
    FeedbackDisposition,
    FeedbackLookup,
)


@dataclass(frozen=True, slots=True)
class RoadContextCandidatePipelineConfig:
    """Versioned conservative policy for candidate-to-mixture assembly."""

    rule_config: RoadContextRuleConfig = RoadContextRuleConfig()
    mixture_config: RoadContextMixtureConfig = RoadContextMixtureConfig()


class RoadContextCandidatePipeline:
    """Convert prior-cycle HMM candidates into one road-context decision.

    The predictor receives static directed-edge facts only. HMM probability is
    used solely by ``build_road_context_mixture`` after prediction and rules.
    """

    def __init__(
        self,
        *,
        graph: RoadGraph,
        predictor: RoadContextQuantilePredictor,
        config: RoadContextCandidatePipelineConfig = RoadContextCandidatePipelineConfig(),
    ) -> None:
        if predictor.metadata.graph_id != graph.metadata.graph_id:
            raise ValueError("Road-context predictor graph_id must match the road graph.")
        if not set(predictor.metadata.feature_names).issubset(
            ROAD_CONTEXT_FEATURE_NAMES
        ):
            raise ValueError("Road-context predictor declares forbidden feature names.")

        edge_features = build_road_context_edge_features(graph)
        self._graph_id = graph.metadata.graph_id
        self._predictor = predictor
        self._config = config
        self._edge_by_traversal = {
            (edge.edge_id, edge.travel_direction): edge
            for edge in edge_features
        }

    def decision_for_cycle(
        self,
        *,
        cycle_timestamp_ns: int,
        feedback_lookup: FeedbackLookup,
    ) -> RoadContextMixtureDecision:
        """Return a causal mixture decision or an explicit safe omission."""

        safe_lookup = self._lookup_for_graph(feedback_lookup)
        if safe_lookup.disposition is not FeedbackDisposition.AVAILABLE:
            return build_road_context_mixture(
                cycle_timestamp_ns=cycle_timestamp_ns,
                feedback_lookup=safe_lookup,
                candidate_predictions=(),
                config=self._config.mixture_config,
            )

        feedback = safe_lookup.feedback
        if feedback is None:
            raise ValueError("Available feedback lookup must include feedback.")

        candidate_edges: list[RoadContextEdgeFeatures] = []
        candidate_ids: list[str] = []
        for belief in feedback.candidate_beliefs:
            candidate = belief.candidate
            edge = self._edge_by_traversal.get(
                (candidate.edge_id, candidate.travel_direction.value)
            )
            if edge is None:
                # Let mixture policy publish the auditable missing-candidate
                # omission instead of inventing an edge or a speed bound.
                return build_road_context_mixture(
                    cycle_timestamp_ns=cycle_timestamp_ns,
                    feedback_lookup=safe_lookup,
                    candidate_predictions=(),
                    config=self._config.mixture_config,
                )
            candidate_ids.append(candidate.candidate_id)
            candidate_edges.append(edge)

        predictions = self._predictor.predict(_feature_frame(candidate_edges))
        if len(predictions) != len(candidate_edges):
            raise RuntimeError("Road-context predictor returned the wrong row count.")

        candidate_predictions = tuple(
            CandidateRoadContextPrediction(
                candidate_id=candidate_id,
                model_id=prediction.model_id,
                rule_speed_limit_mps=edge.speed_limit_mps,
                rule_outcome=apply_road_context_rules(
                    prediction=prediction,
                    edge=edge,
                    config=self._config.rule_config,
                ),
            )
            for candidate_id, edge, prediction in zip(
                candidate_ids,
                candidate_edges,
                predictions,
                strict=True,
            )
        )

        return build_road_context_mixture(
            cycle_timestamp_ns=cycle_timestamp_ns,
            feedback_lookup=safe_lookup,
            candidate_predictions=candidate_predictions,
            config=self._config.mixture_config,
        )

    def _lookup_for_graph(self, feedback_lookup: FeedbackLookup) -> FeedbackLookup:
        """Reject usable feedback from another graph before candidate lookup."""

        feedback = feedback_lookup.feedback
        if (
            feedback_lookup.disposition is FeedbackDisposition.AVAILABLE
            and feedback is not None
            and feedback.graph_id != self._graph_id
        ):
            return FeedbackLookup(
                disposition=FeedbackDisposition.GRAPH_MISMATCH,
                feedback=None,
                age_s=feedback_lookup.age_s,
            )
        return feedback_lookup


def _feature_frame(edges: list[RoadContextEdgeFeatures]) -> pd.DataFrame:
    """Build the same target-free static schema used during offline training."""

    records = [
        {
            "road_class": edge.road_class or "<unknown>",
            "road_class_known": edge.road_class is not None,
            "speed_limit_mps": edge.speed_limit_mps,
            "speed_limit_known": edge.speed_limit_mps is not None,
            "lane_count": edge.lane_count,
            "lane_count_known": edge.lane_count is not None,
            "is_oneway": edge.is_oneway,
            "is_link": edge.is_link,
            "is_tunnel": edge.is_tunnel,
            "is_bridge": edge.is_bridge,
            "is_roundabout": edge.is_roundabout,
            "edge_length_m": edge.edge_length_m,
            "mean_abs_curvature_rad_per_m": edge.mean_abs_curvature_rad_per_m,
            "p95_abs_curvature_rad_per_m": edge.p95_abs_curvature_rad_per_m,
            "from_node_degree": edge.from_node_degree,
            "to_node_degree": edge.to_node_degree,
        }
        for edge in edges
    ]
    return pd.DataFrame.from_records(records, columns=ROAD_CONTEXT_FEATURE_NAMES)


__all__ = [
    "RoadContextCandidatePipeline",
    "RoadContextCandidatePipelineConfig",
]

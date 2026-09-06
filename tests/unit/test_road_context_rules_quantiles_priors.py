from __future__ import annotations

import math

import pandas as pd
import pytest

from idr_backend.pipeline.feedback import (
    CandidateBelief,
    FeedbackDisposition,
    FeedbackLookup,
    MapMatchFeedback,
)
from idr_backend.road_context.features import (
    ROAD_CONTEXT_FEATURE_NAMES,
    RoadContextEdgeFeatures,
    RoadContextFeatureDataset,
)
from idr_backend.road_context.priors import (
    CandidateRoadContextPrediction,
    RoadContextMixtureConfig,
    RoadContextMixtureDisposition,
    build_road_context_mixture,
)
from idr_backend.road_context.quantile_model import (
    fit_road_class_empirical_quantile_baseline,
)
from idr_backend.road_context.rules import (
    RoadContextQuantilePrediction,
    RoadContextRuleDisposition,
    RoadContextRuleOutcome,
    apply_road_context_rules,
)
from idr_backend.sensors.types import RoadCandidate, TravelDirection


_GRAPH_ID = "road-context-test-graph"


def _edge(
    *,
    edge_id: str,
    road_class: str | None = "residential",
    is_link: bool = False,
    is_roundabout: bool = False,
) -> RoadContextEdgeFeatures:
    return RoadContextEdgeFeatures(
        graph_id=_GRAPH_ID,
        edge_id=edge_id,
        travel_direction="forward",
        osm_way_id=f"way-{edge_id}",
        road_class=road_class,
        speed_limit_mps=13.9,
        lane_count=2,
        is_oneway=False,
        is_link=is_link,
        is_tunnel=False,
        is_bridge=False,
        is_roundabout=is_roundabout,
        edge_length_m=150.0,
        mean_abs_curvature_rad_per_m=0.005,
        p95_abs_curvature_rad_per_m=0.010,
        from_node_degree=3,
        to_node_degree=3,
    )


def _candidate(candidate_id: str, edge_id: str) -> RoadCandidate:
    return RoadCandidate(
        timestamp_ns=100,
        candidate_id=candidate_id,
        graph_id=_GRAPH_ID,
        edge_id=edge_id,
        travel_direction=TravelDirection.FORWARD,
        snap_position_enu_m=(0.0, 0.0),
        lateral_distance_m=2.0,
        road_heading_enu_rad=0.0,
    )


def _accepted_outcome(
    *,
    edge: RoadContextEdgeFeatures,
    p10: float,
    p50: float,
    p90: float,
) -> RoadContextRuleOutcome:
    return RoadContextRuleOutcome(
        edge_id=edge.edge_id,
        travel_direction=edge.travel_direction,
        accepted=True,
        speed_p10_mps=p10,
        speed_p50_mps=p50,
        speed_p90_mps=p90,
        uncertainty_inflation=1.0,
        dispositions=(),
    )


def _feature_row(
    *,
    road_class: str,
    target_speed_mps: float,
) -> dict[str, object]:
    return {
        "graph_id": _GRAPH_ID,
        "target_speed_mps": target_speed_mps,
        "road_class": road_class,
        "road_class_known": True,
        "speed_limit_mps": 13.9,
        "speed_limit_known": True,
        "lane_count": 2.0,
        "lane_count_known": True,
        "is_oneway": False,
        "is_link": False,
        "is_tunnel": False,
        "is_bridge": False,
        "is_roundabout": False,
        "edge_length_m": 150.0,
        "mean_abs_curvature_rad_per_m": 0.005,
        "p95_abs_curvature_rad_per_m": 0.010,
        "from_node_degree": 3,
        "to_node_degree": 3,
    }


def test_rules_omit_crossed_quantiles_and_widen_narrow_intervals() -> None:
    edge = _edge(edge_id="edge-a", road_class=None, is_link=True)

    invalid = apply_road_context_rules(
        prediction=RoadContextQuantilePrediction(
            model_id="test-model",
            speed_p10_mps=12.0,
            speed_p50_mps=10.0,
            speed_p90_mps=18.0,
        ),
        edge=edge,
    )

    assert not invalid.accepted
    assert invalid.speed_p50_mps is None
    assert invalid.dispositions == (
        RoadContextRuleDisposition.INVALID_QUANTILES,
    )

    narrow = apply_road_context_rules(
        prediction=RoadContextQuantilePrediction(
            model_id="test-model",
            speed_p10_mps=9.9,
            speed_p50_mps=10.0,
            speed_p90_mps=10.1,
        ),
        edge=edge,
    )

    assert narrow.accepted
    assert narrow.speed_p90_mps is not None
    assert narrow.speed_p10_mps is not None
    assert narrow.speed_p90_mps - narrow.speed_p10_mps >= 2.0
    assert narrow.uncertainty_inflation > 1.0
    assert RoadContextRuleDisposition.INTERVAL_FLOORED in narrow.dispositions
    assert RoadContextRuleDisposition.UNKNOWN_ROAD_CLASS in narrow.dispositions
    assert RoadContextRuleDisposition.ROUNDABOUT_OR_LINK in narrow.dispositions


def test_empirical_baseline_excludes_target_at_prediction_time() -> None:
    frame = pd.DataFrame(
        [
            _feature_row(road_class="motorway", target_speed_mps=24.0),
            _feature_row(road_class="motorway", target_speed_mps=30.0),
            _feature_row(road_class="residential", target_speed_mps=7.0),
            _feature_row(road_class="residential", target_speed_mps=9.0),
        ]
    )
    frame.index = [4, 9, 15, 21]

    dataset = RoadContextFeatureDataset(frame=frame, graph_id=_GRAPH_ID)
    baseline = fit_road_class_empirical_quantile_baseline(
        dataset,
        sample_weight=[1.0, 1.0, 1.0, 1.0],
    )

    predictions = baseline.predict(
        pd.DataFrame(
            {
                "road_class": ["motorway", "unseen-road-class"],
            }
        )
    )

    assert len(predictions) == 2
    assert predictions[0].model_id == "road_class_empirical_quantiles_v1"
    assert predictions[0].speed_p50_mps > predictions[1].speed_p50_mps

    leaking_features = pd.DataFrame(
        {
            "road_class": ["motorway"],
            "target_speed_mps": [999.0],
        }
    )
    with pytest.raises(ValueError, match="must not contain the offline CAN target"):
        baseline.predict(leaking_features)


def test_feature_dataset_keeps_target_out_of_model_schema() -> None:
    frame = pd.DataFrame(
        [_feature_row(road_class="residential", target_speed_mps=8.0)]
    )
    dataset = RoadContextFeatureDataset(frame=frame, graph_id=_GRAPH_ID)

    assert tuple(dataset.model_features.columns) == ROAD_CONTEXT_FEATURE_NAMES
    assert "target_speed_mps" not in dataset.model_features.columns
    assert dataset.targets_mps.tolist() == [8.0]


def test_mixture_uses_between_candidate_disagreement() -> None:
    motorway = _edge(edge_id="motorway")
    service_road = _edge(edge_id="service")

    motorway_candidate = _candidate("candidate-motorway", motorway.edge_id)
    service_candidate = _candidate("candidate-service", service_road.edge_id)

    feedback = MapMatchFeedback(
        timestamp_ns=100,
        graph_id=_GRAPH_ID,
        candidate_beliefs=(
            CandidateBelief(candidate=motorway_candidate, probability=0.7),
            CandidateBelief(candidate=service_candidate, probability=0.3),
        ),
        selected_candidate_id=motorway_candidate.candidate_id,
        map_match_confidence=0.7,
    )
    lookup = FeedbackLookup(
        disposition=FeedbackDisposition.AVAILABLE,
        feedback=feedback,
        age_s=0.1,
    )

    decision = build_road_context_mixture(
        cycle_timestamp_ns=200,
        feedback_lookup=lookup,
                candidate_predictions=(
            CandidateRoadContextPrediction(
                candidate_id=motorway_candidate.candidate_id,
                model_id="test-model",
                rule_speed_limit_mps=motorway.speed_limit_mps,
                rule_outcome=_accepted_outcome(
                    edge=motorway,
                    p10=20.0,
                    p50=25.0,
                    p90=30.0,
                ),
            ),
            CandidateRoadContextPrediction(
                candidate_id=service_candidate.candidate_id,
                model_id="test-model",
                rule_speed_limit_mps=service_road.speed_limit_mps,
                rule_outcome=_accepted_outcome(
                    edge=service_road,
                    p10=2.0,
                    p50=5.0,
                    p90=8.0,
                ),
            ),
        ),
        config=RoadContextMixtureConfig(
            maximum_normalized_entropy=1.0,
        ),
    )

    assert decision.disposition is RoadContextMixtureDisposition.AVAILABLE
    assert decision.speed_mean_mps == pytest.approx(19.0)
    assert decision.speed_variance_m2ps2 is not None

    within_candidate_variance = sum(
        contribution.probability * contribution.effective_variance_m2ps2
        for contribution in decision.contributions
    )
    assert decision.speed_variance_m2ps2 > within_candidate_variance
    assert math.isfinite(decision.speed_variance_m2ps2)


def test_mixture_omits_when_any_credible_candidate_is_missing() -> None:
    edge_a = _edge(edge_id="edge-a")
    edge_b = _edge(edge_id="edge-b")
    candidate_a = _candidate("candidate-a", edge_a.edge_id)
    candidate_b = _candidate("candidate-b", edge_b.edge_id)

    feedback = MapMatchFeedback(
        timestamp_ns=100,
        graph_id=_GRAPH_ID,
        candidate_beliefs=(
            CandidateBelief(candidate=candidate_a, probability=0.6),
            CandidateBelief(candidate=candidate_b, probability=0.4),
        ),
        selected_candidate_id=candidate_a.candidate_id,
        map_match_confidence=0.6,
    )

    decision = build_road_context_mixture(
        cycle_timestamp_ns=200,
        feedback_lookup=FeedbackLookup(
            disposition=FeedbackDisposition.AVAILABLE,
            feedback=feedback,
            age_s=0.1,
        ),
        candidate_predictions=(
            CandidateRoadContextPrediction(
                candidate_id=candidate_a.candidate_id,
                model_id="test-model",
                rule_speed_limit_mps=edge_a.speed_limit_mps,
                rule_outcome=_accepted_outcome(
                    edge=edge_a,
                    p10=5.0,
                    p50=8.0,
                    p90=11.0,
                ),
            ),
        ),
    )

    assert decision.disposition is (
        RoadContextMixtureDisposition.MISSING_CANDIDATE_PREDICTION
    )
    assert decision.speed_mean_mps is None
    assert decision.omitted_candidate_ids == (candidate_b.candidate_id,)
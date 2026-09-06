"""Causal candidate-mixture construction for road-context speed priors.

This module is pure decision logic. It consumes only a completed prior-cycle
HMM belief plus already-rule-checked candidate quantiles. It does not access
IMU, GRU, current EKF speed, same-cycle HMM output, or the EKF itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, log
from typing import Iterable

from idr_backend.pipeline.feedback import (
    FeedbackDisposition,
    FeedbackLookup,
    validate_map_match_feedback,
)
from idr_backend.sensors.types import RoadContextPrior

from .rules import RoadContextRuleDisposition, RoadContextRuleOutcome


_NORMAL_QUANTILE_Z_90 = 1.2815515655446004


class RoadContextMixtureDisposition(StrEnum):
    """Whether a candidate mixture is safe to publish for later fusion."""

    AVAILABLE = "available"
    ABSENT_FEEDBACK = "absent_feedback"
    STALE_FEEDBACK = "stale_feedback"
    GRAPH_MISMATCH = "graph_mismatch"
    SAME_CYCLE_OR_FUTURE_FEEDBACK = "same_cycle_or_future_feedback"
    HIGH_CANDIDATE_ENTROPY = "high_candidate_entropy"
    LOW_TOP_TWO_MARGIN = "low_top_two_margin"
    MISSING_CANDIDATE_PREDICTION = "missing_candidate_prediction"
    CANDIDATE_RULE_OMITTED = "candidate_rule_omitted"
    MIXED_MODEL_IDS = "mixed_model_ids"


@dataclass(frozen=True, slots=True)
class RoadContextMixtureConfig:
    """Initial conservative policy for candidate ambiguity and variance."""

    maximum_normalized_entropy: float = 0.85
    minimum_top_two_margin: float = 0.05
    candidate_variance_floor_m2ps2: float = 1.0
    mixture_variance_floor_m2ps2: float = 1.0
    variance_calibration_multiplier: float = 1.0

    def __post_init__(self) -> None:
        if not (
            isfinite(self.maximum_normalized_entropy)
            and 0.0 <= self.maximum_normalized_entropy <= 1.0
        ):
            raise ValueError("maximum_normalized_entropy must be in [0, 1].")
        if not (
            isfinite(self.minimum_top_two_margin)
            and 0.0 <= self.minimum_top_two_margin <= 1.0
        ):
            raise ValueError("minimum_top_two_margin must be in [0, 1].")

        positive = (
            self.candidate_variance_floor_m2ps2,
            self.mixture_variance_floor_m2ps2,
            self.variance_calibration_multiplier,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("Mixture variance settings must be finite and positive.")
        if self.variance_calibration_multiplier < 1.0:
            raise ValueError(
                "Initial road-context calibration may widen variance but must not shrink it."
            )


@dataclass(frozen=True, slots=True)
class CandidateRoadContextPrediction:
    """One rule-checked model result tied to one HMM candidate identity."""

    candidate_id: str
    model_id: str
    rule_speed_limit_mps: float | None
    rule_outcome: RoadContextRuleOutcome

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.model_id.strip():
            raise ValueError("Candidate prediction IDs must not be blank.")
        if self.rule_speed_limit_mps is not None and (
            not isfinite(self.rule_speed_limit_mps) or self.rule_speed_limit_mps < 0.0
        ):
            raise ValueError("Rule speed limit must be finite and non-negative when known.")


@dataclass(frozen=True, slots=True)
class RoadContextCandidateContribution:
    """One candidate's moment contribution to a published mixture."""

    prior: RoadContextPrior
    travel_direction: str
    probability: float
    base_variance_m2ps2: float
    effective_variance_m2ps2: float
    rule_dispositions: tuple[RoadContextRuleDisposition, ...]

    def __post_init__(self) -> None:
        if self.travel_direction not in ("forward", "reverse"):
            raise ValueError("Candidate contribution direction is invalid.")
        if not isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ValueError("Candidate probability must be in [0, 1].")
        if not all(
            isfinite(value) and value >= 0.0
            for value in (
                self.base_variance_m2ps2,
                self.effective_variance_m2ps2,
            )
        ):
            raise ValueError("Candidate variances must be finite and non-negative.")
        if self.effective_variance_m2ps2 < self.base_variance_m2ps2:
            raise ValueError("Rules must not reduce candidate variance.")


@dataclass(frozen=True, slots=True)
class RoadContextMixtureDecision:
    """Auditable mixture result; later EKF code may consume only AVAILABLE rows."""

    cycle_timestamp_ns: int
    disposition: RoadContextMixtureDisposition
    source_belief_timestamp_ns: int | None
    graph_id: str | None
    model_id: str | None
    feedback_age_s: float | None
    normalized_entropy: float | None
    top_two_margin: float | None
    contributions: tuple[RoadContextCandidateContribution, ...]
    speed_mean_mps: float | None
    speed_variance_m2ps2: float | None
    omitted_candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.cycle_timestamp_ns < 0:
            raise ValueError("Mixture decision timestamp must be non-negative.")

        if self.disposition is RoadContextMixtureDisposition.AVAILABLE:
            if (
                self.source_belief_timestamp_ns is None
                or self.graph_id is None
                or self.model_id is None
                or self.feedback_age_s is None
                or self.normalized_entropy is None
                or self.top_two_margin is None
                or self.speed_mean_mps is None
                or self.speed_variance_m2ps2 is None
                or not self.contributions
                or self.omitted_candidate_ids
            ):
                raise ValueError("Available mixture decisions require complete evidence.")

            if not (
                isfinite(self.speed_mean_mps)
                and self.speed_mean_mps >= 0.0
                and isfinite(self.speed_variance_m2ps2)
                and self.speed_variance_m2ps2 > 0.0
            ):
                raise ValueError("Available mixture moments must be physically valid.")

            total_probability = sum(
                contribution.probability for contribution in self.contributions
            )
            if not abs(total_probability - 1.0) <= 1e-6:
                raise ValueError("Available mixture weights must sum to one.")
        elif (
            self.speed_mean_mps is not None
            or self.speed_variance_m2ps2 is not None
            or self.contributions
        ):
            raise ValueError("Omitted mixture decisions must not publish a speed prior.")


def build_road_context_mixture(
    *,
    cycle_timestamp_ns: int,
    feedback_lookup: FeedbackLookup,
    candidate_predictions: Iterable[CandidateRoadContextPrediction],
    config: RoadContextMixtureConfig = RoadContextMixtureConfig(),
) -> RoadContextMixtureDecision:
    """Build a causal belief-weighted speed mixture or an explicit omission."""

    if cycle_timestamp_ns < 0:
        raise ValueError("Road-context cycle timestamp must be non-negative.")

    if feedback_lookup.disposition is not FeedbackDisposition.AVAILABLE:
        return _omitted_from_feedback(
            cycle_timestamp_ns=cycle_timestamp_ns,
            feedback_lookup=feedback_lookup,
        )

    feedback = feedback_lookup.feedback
    if feedback is None:
        raise ValueError("Available feedback lookup must contain completed feedback.")

    validate_map_match_feedback(feedback)
    if feedback.timestamp_ns >= cycle_timestamp_ns:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.SAME_CYCLE_OR_FUTURE_FEEDBACK,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
        )

    predictions = tuple(candidate_predictions)
    prediction_by_candidate_id = {
        prediction.candidate_id: prediction for prediction in predictions
    }
    if len(prediction_by_candidate_id) != len(predictions):
        raise ValueError("Road-context candidate predictions must have unique IDs.")

    feedback_candidate_ids = {
        belief.candidate.candidate_id for belief in feedback.candidate_beliefs
    }
    missing_candidate_ids = tuple(
        sorted(feedback_candidate_ids.difference(prediction_by_candidate_id))
    )
    unexpected_candidate_ids = set(prediction_by_candidate_id).difference(
        feedback_candidate_ids
    )
    if unexpected_candidate_ids:
        raise ValueError(
            "Road-context predictions contain candidates absent from HMM feedback."
        )
    if missing_candidate_ids:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.MISSING_CANDIDATE_PREDICTION,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
            omitted_candidate_ids=missing_candidate_ids,
        )

    normalized_entropy = _normalized_entropy(
        tuple(belief.probability for belief in feedback.candidate_beliefs)
    )
    if normalized_entropy > config.maximum_normalized_entropy:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.HIGH_CANDIDATE_ENTROPY,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
            normalized_entropy=normalized_entropy,
        )

    top_two_margin = _top_two_margin(
        tuple(belief.probability for belief in feedback.candidate_beliefs)
    )
    if top_two_margin < config.minimum_top_two_margin:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.LOW_TOP_TWO_MARGIN,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
            normalized_entropy=normalized_entropy,
            top_two_margin=top_two_margin,
        )

    model_ids = {prediction.model_id for prediction in predictions}
    if len(model_ids) != 1:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.MIXED_MODEL_IDS,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
            normalized_entropy=normalized_entropy,
            top_two_margin=top_two_margin,
        )

    contributions: list[RoadContextCandidateContribution] = []
    omitted_by_rules: list[str] = []

    for belief in feedback.candidate_beliefs:
        candidate = belief.candidate
        prediction = prediction_by_candidate_id[candidate.candidate_id]
        outcome = prediction.rule_outcome

        if (
            outcome.edge_id != candidate.edge_id
            or outcome.travel_direction != candidate.travel_direction.value
        ):
            raise ValueError(
                "Rule outcome does not describe the HMM candidate's directed edge."
            )

        if not outcome.accepted:
            omitted_by_rules.append(candidate.candidate_id)
            continue

        if (
            outcome.speed_p10_mps is None
            or outcome.speed_p50_mps is None
            or outcome.speed_p90_mps is None
        ):
            raise RuntimeError("Accepted rule outcome unexpectedly lacks quantiles.")

        base_standard_deviation_mps = (
            outcome.speed_p90_mps - outcome.speed_p10_mps
        ) / (2.0 * _NORMAL_QUANTILE_Z_90)
        base_variance_m2ps2 = max(
            config.candidate_variance_floor_m2ps2,
            base_standard_deviation_mps**2,
        )
        effective_variance_m2ps2 = (
            base_variance_m2ps2
            * outcome.uncertainty_inflation
            * config.variance_calibration_multiplier
        )

        prior = RoadContextPrior(
            timestamp_ns=cycle_timestamp_ns,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            candidate_id=candidate.candidate_id,
            edge_id=candidate.edge_id,
            speed_p10_mps=outcome.speed_p10_mps,
            speed_p50_mps=outcome.speed_p50_mps,
            speed_p90_mps=outcome.speed_p90_mps,
            rule_speed_limit_mps=prediction.rule_speed_limit_mps,
            confidence=belief.probability,
        )
        contributions.append(
            RoadContextCandidateContribution(
                prior=prior,
                travel_direction=candidate.travel_direction.value,
                probability=belief.probability,
                base_variance_m2ps2=base_variance_m2ps2,
                effective_variance_m2ps2=effective_variance_m2ps2,
                rule_dispositions=outcome.dispositions,
            )
        )

    if omitted_by_rules:
        return _omitted(
            cycle_timestamp_ns=cycle_timestamp_ns,
            disposition=RoadContextMixtureDisposition.CANDIDATE_RULE_OMITTED,
            source_belief_timestamp_ns=feedback.timestamp_ns,
            graph_id=feedback.graph_id,
            feedback_age_s=feedback_lookup.age_s,
            normalized_entropy=normalized_entropy,
            top_two_margin=top_two_margin,
            omitted_candidate_ids=tuple(sorted(omitted_by_rules)),
        )

    speed_mean_mps = sum(
        contribution.probability * contribution.prior.speed_p50_mps
        for contribution in contributions
    )
    mixture_variance_m2ps2 = sum(
        contribution.probability
        * (
            contribution.effective_variance_m2ps2
            + (contribution.prior.speed_p50_mps - speed_mean_mps) ** 2
        )
        for contribution in contributions
    )

    return RoadContextMixtureDecision(
        cycle_timestamp_ns=cycle_timestamp_ns,
        disposition=RoadContextMixtureDisposition.AVAILABLE,
        source_belief_timestamp_ns=feedback.timestamp_ns,
        graph_id=feedback.graph_id,
        model_id=next(iter(model_ids)),
        feedback_age_s=feedback_lookup.age_s,
        normalized_entropy=normalized_entropy,
        top_two_margin=top_two_margin,
        contributions=tuple(contributions),
        speed_mean_mps=speed_mean_mps,
        speed_variance_m2ps2=max(
            config.mixture_variance_floor_m2ps2,
            mixture_variance_m2ps2,
        ),
        omitted_candidate_ids=(),
    )


def _normalized_entropy(probabilities: tuple[float, ...]) -> float:
    """Return posterior entropy normalized to [0, 1]."""

    if len(probabilities) <= 1:
        return 0.0

    entropy = -sum(
        probability * log(probability)
        for probability in probabilities
        if probability > 0.0
    )
    return entropy / log(len(probabilities))


def _top_two_margin(probabilities: tuple[float, ...]) -> float:
    """Return top-one minus top-two belief probability."""

    ranked = sorted(probabilities, reverse=True)
    return ranked[0] if len(ranked) == 1 else ranked[0] - ranked[1]


def _omitted_from_feedback(
    *,
    cycle_timestamp_ns: int,
    feedback_lookup: FeedbackLookup,
) -> RoadContextMixtureDecision:
    """Translate existing feedback-store causality decisions without guessing."""

    disposition_map = {
        FeedbackDisposition.ABSENT: RoadContextMixtureDisposition.ABSENT_FEEDBACK,
        FeedbackDisposition.STALE: RoadContextMixtureDisposition.STALE_FEEDBACK,
        FeedbackDisposition.GRAPH_MISMATCH: RoadContextMixtureDisposition.GRAPH_MISMATCH,
        FeedbackDisposition.SAME_CYCLE_OR_FUTURE: (
            RoadContextMixtureDisposition.SAME_CYCLE_OR_FUTURE_FEEDBACK
        ),
        FeedbackDisposition.LOW_CONFIDENCE: RoadContextMixtureDisposition.ABSENT_FEEDBACK,
    }
    return _omitted(
        cycle_timestamp_ns=cycle_timestamp_ns,
        disposition=disposition_map[feedback_lookup.disposition],
        feedback_age_s=feedback_lookup.age_s,
    )


def _omitted(
    *,
    cycle_timestamp_ns: int,
    disposition: RoadContextMixtureDisposition,
    source_belief_timestamp_ns: int | None = None,
    graph_id: str | None = None,
    feedback_age_s: float | None = None,
    normalized_entropy: float | None = None,
    top_two_margin: float | None = None,
    omitted_candidate_ids: tuple[str, ...] = (),
) -> RoadContextMixtureDecision:
    """Return a traceable omission with no speed or covariance to fuse."""

    return RoadContextMixtureDecision(
        cycle_timestamp_ns=cycle_timestamp_ns,
        disposition=disposition,
        source_belief_timestamp_ns=source_belief_timestamp_ns,
        graph_id=graph_id,
        model_id=None,
        feedback_age_s=feedback_age_s,
        normalized_entropy=normalized_entropy,
        top_two_margin=top_two_margin,
        contributions=(),
        speed_mean_mps=None,
        speed_variance_m2ps2=None,
        omitted_candidate_ids=omitted_candidate_ids,
    )
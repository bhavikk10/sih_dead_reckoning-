"""Conservative deterministic guards for candidate road-speed quantiles.

This module is pure policy. It does not read HMM belief, mutate the EKF, or
treat OSM speed limits as hard truth. Belief freshness/ambiguity belongs in the
later prior-construction layer; model inference belongs in quantile_model.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from .features import RoadContextEdgeFeatures


class RoadContextRuleDisposition(StrEnum):
    """Reasons an individual candidate is widened or omitted."""

    INVALID_QUANTILES = "invalid_quantiles"
    EXCEEDS_ABSOLUTE_SPEED_LIMIT = "exceeds_absolute_speed_limit"
    INTERVAL_FLOORED = "interval_floored"
    UNKNOWN_ROAD_CLASS = "unknown_road_class"
    MISSING_OSM_TAGS = "missing_osm_tags"
    SHORT_CONNECTOR = "short_connector"
    ROUNDABOUT_OR_LINK = "roundabout_or_link"
    HIGH_CURVATURE = "high_curvature"
    SOFT_SPEED_LIMIT_DISAGREEMENT = "soft_speed_limit_disagreement"


@dataclass(frozen=True, slots=True)
class RoadContextQuantilePrediction:
    """Raw q10/q50/q90 output for exactly one directed road candidate.

    Values are intentionally not validated here. A faulty model output must
    reach the rules layer and become an explicit omission rather than causing a
    runtime exception or being silently corrected.
    """

    model_id: str
    speed_p10_mps: float
    speed_p50_mps: float
    speed_p90_mps: float

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("Road-context prediction model_id must not be blank.")


@dataclass(frozen=True, slots=True)
class RoadContextRuleConfig:
    """Conservative, versioned policy; all multipliers can only widen variance."""

    minimum_interval_width_mps: float = 2.0
    maximum_plausible_speed_mps: float = 75.0
    short_edge_threshold_m: float = 80.0
    high_curvature_threshold_rad_per_m: float = 0.04
    soft_speed_limit_multiplier: float = 1.75

    unknown_road_class_inflation: float = 1.35
    missing_osm_tags_inflation: float = 1.15
    short_connector_inflation: float = 1.25
    roundabout_or_link_inflation: float = 1.35
    high_curvature_inflation: float = 1.20
    soft_speed_limit_inflation: float = 1.20
    maximum_total_inflation: float = 4.0

    def __post_init__(self) -> None:
        positive = (
            self.minimum_interval_width_mps,
            self.maximum_plausible_speed_mps,
            self.short_edge_threshold_m,
            self.high_curvature_threshold_rad_per_m,
            self.soft_speed_limit_multiplier,
            self.unknown_road_class_inflation,
            self.missing_osm_tags_inflation,
            self.short_connector_inflation,
            self.roundabout_or_link_inflation,
            self.high_curvature_inflation,
            self.soft_speed_limit_inflation,
            self.maximum_total_inflation,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("Road-context rule configuration must be finite and positive.")
        if self.maximum_total_inflation < 1.0:
            raise ValueError("maximum_total_inflation must be at least one.")
        if any(
            multiplier < 1.0
            for multiplier in (
                self.unknown_road_class_inflation,
                self.missing_osm_tags_inflation,
                self.short_connector_inflation,
                self.roundabout_or_link_inflation,
                self.high_curvature_inflation,
                self.soft_speed_limit_inflation,
            )
        ):
            raise ValueError("Road-context rule multipliers must never shrink uncertainty.")


@dataclass(frozen=True, slots=True)
class RoadContextRuleOutcome:
    """Safe candidate result for later belief-weighted mixture construction."""

    edge_id: str
    travel_direction: str
    accepted: bool
    speed_p10_mps: float | None
    speed_p50_mps: float | None
    speed_p90_mps: float | None
    uncertainty_inflation: float
    dispositions: tuple[RoadContextRuleDisposition, ...]

    def __post_init__(self) -> None:
        if not self.edge_id.strip():
            raise ValueError("Road-context rule outcome edge_id must not be blank.")
        if self.travel_direction not in ("forward", "reverse"):
            raise ValueError("Road-context rule outcome direction is invalid.")
        if not isfinite(self.uncertainty_inflation) or self.uncertainty_inflation < 1.0:
            raise ValueError("Rule outcomes may only preserve or widen uncertainty.")

        quantiles = (self.speed_p10_mps, self.speed_p50_mps, self.speed_p90_mps)
        if self.accepted:
            if any(value is None for value in quantiles):
                raise ValueError("Accepted rule outcomes require all three quantiles.")
            p10, p50, p90 = (float(value) for value in quantiles)
            if (
                not all(isfinite(value) and value >= 0.0 for value in (p10, p50, p90))
                or p10 > p50
                or p50 > p90
            ):
                raise ValueError("Accepted rule outcomes require ordered finite quantiles.")
        elif any(value is not None for value in quantiles):
            raise ValueError("Omitted rule outcomes must not publish quantiles.")
        

def apply_road_context_rules(
    *,
    prediction: RoadContextQuantilePrediction,
    edge: RoadContextEdgeFeatures,
    config: RoadContextRuleConfig = RoadContextRuleConfig(),
) -> RoadContextRuleOutcome:
    """Return an accepted, widened, or omitted candidate speed distribution."""

    raw_quantiles = (
        prediction.speed_p10_mps,
        prediction.speed_p50_mps,
        prediction.speed_p90_mps,
    )
    if (
        not all(isfinite(value) and value >= 0.0 for value in raw_quantiles)
        or prediction.speed_p10_mps > prediction.speed_p50_mps
        or prediction.speed_p50_mps > prediction.speed_p90_mps
    ):
        return _omitted(
            edge=edge,
            disposition=RoadContextRuleDisposition.INVALID_QUANTILES,
        )

    if prediction.speed_p90_mps > config.maximum_plausible_speed_mps:
        return _omitted(
            edge=edge,
            disposition=RoadContextRuleDisposition.EXCEEDS_ABSOLUTE_SPEED_LIMIT,
        )

    p10 = prediction.speed_p10_mps
    p50 = prediction.speed_p50_mps
    p90 = prediction.speed_p90_mps
    dispositions: list[RoadContextRuleDisposition] = []
    inflation = 1.0

    half_width_mps = max(p50 - p10, p90 - p50)
    minimum_half_width_mps = config.minimum_interval_width_mps / 2.0
    if half_width_mps < minimum_half_width_mps:
        half_width_mps = minimum_half_width_mps
        p10 = max(0.0, p50 - half_width_mps)
        p90 = p50 + half_width_mps
        dispositions.append(RoadContextRuleDisposition.INTERVAL_FLOORED)

    if edge.road_class is None:
        inflation *= config.unknown_road_class_inflation
        dispositions.append(RoadContextRuleDisposition.UNKNOWN_ROAD_CLASS)

    if edge.speed_limit_mps is None or edge.lane_count is None:
        inflation *= config.missing_osm_tags_inflation
        dispositions.append(RoadContextRuleDisposition.MISSING_OSM_TAGS)

    if edge.edge_length_m <= config.short_edge_threshold_m:
        inflation *= config.short_connector_inflation
        dispositions.append(RoadContextRuleDisposition.SHORT_CONNECTOR)

    if edge.is_roundabout or edge.is_link:
        inflation *= config.roundabout_or_link_inflation
        dispositions.append(RoadContextRuleDisposition.ROUNDABOUT_OR_LINK)

    if edge.p95_abs_curvature_rad_per_m >= config.high_curvature_threshold_rad_per_m:
        inflation *= config.high_curvature_inflation
        dispositions.append(RoadContextRuleDisposition.HIGH_CURVATURE)

    if (
        edge.speed_limit_mps is not None
        and p90 > edge.speed_limit_mps * config.soft_speed_limit_multiplier
    ):
        inflation *= config.soft_speed_limit_inflation
        dispositions.append(RoadContextRuleDisposition.SOFT_SPEED_LIMIT_DISAGREEMENT)

    return RoadContextRuleOutcome(
        edge_id=edge.edge_id,
        travel_direction=edge.travel_direction,
        accepted=True,
        speed_p10_mps=p10,
        speed_p50_mps=p50,
        speed_p90_mps=p90,
        uncertainty_inflation=min(inflation, config.maximum_total_inflation),
        dispositions=tuple(dispositions),
    )


def _omitted(
    *,
    edge: RoadContextEdgeFeatures,
    disposition: RoadContextRuleDisposition,
) -> RoadContextRuleOutcome:
    """Publish an explicit safe omission instead of a fabricated prior."""

    return RoadContextRuleOutcome(
        edge_id=edge.edge_id,
        travel_direction=edge.travel_direction,
        accepted=False,
        speed_p10_mps=None,
        speed_p50_mps=None,
        speed_p90_mps=None,
        uncertainty_inflation=1.0,
        dispositions=(disposition,),
    )



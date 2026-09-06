from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from ..sensors.types import RoadCandidate


@dataclass(frozen=True, slots=True)
class FeedbackConfig:
    """Safety policy for reusing a prior map-match belief."""

    # A belief that has not been refreshed is unsafe after this age.
    maximum_feedback_age_s: float

    # Low-confidence HMM output must not steer road-context priors.
    minimum_map_match_confidence: float


@dataclass(frozen=True, slots=True)
class CandidateBelief:
    """One road candidate and its normalized probability after HMM scoring."""

    candidate: RoadCandidate
    probability: float


@dataclass(frozen=True, slots=True)
class MapMatchFeedback:
    """Completed, prior-cycle HMM result safe to expose to road context."""

    timestamp_ns: int
    graph_id: str

    # Keep only a compact posterior, not the full Viterbi trellis/history.
    candidate_beliefs: tuple[CandidateBelief, ...]

    selected_candidate_id: str | None
    map_match_confidence: float


class FeedbackDisposition(StrEnum):
    """Whether a prior belief may be used for the current cycle."""

    AVAILABLE = "available"
    ABSENT = "absent"
    STALE = "stale"
    LOW_CONFIDENCE = "low_confidence"
    GRAPH_MISMATCH = "graph_mismatch"
    SAME_CYCLE_OR_FUTURE = "same_cycle_or_future"


@dataclass(frozen=True, slots=True)
class FeedbackLookup:
    """Result of requesting a prior belief for one new fusion cycle."""

    disposition: FeedbackDisposition
    feedback: MapMatchFeedback | None
    age_s: float | None


def validate_map_match_feedback(
    feedback: MapMatchFeedback,
) -> None:
    """Reject malformed or internally inconsistent HMM output."""

    if feedback.timestamp_ns < 0:
        raise ValueError("Feedback timestamp must be non-negative.")
    if not feedback.graph_id.strip():
        raise ValueError("Feedback graph_id must not be blank.")
    if not (
        isfinite(feedback.map_match_confidence)
        and 0.0 <= feedback.map_match_confidence <= 1.0
    ):
        raise ValueError("Map-match confidence must lie between zero and one.")
    if not feedback.candidate_beliefs:
        raise ValueError("Feedback must contain at least one candidate belief.")

    candidate_ids: set[str] = set()
    probability_sum = 0.0

    for belief in feedback.candidate_beliefs:
        candidate = belief.candidate

        if candidate.timestamp_ns != feedback.timestamp_ns:
            raise ValueError("Candidate timestamp must match feedback timestamp.")
        if candidate.graph_id != feedback.graph_id:
            raise ValueError("All candidates must belong to feedback graph_id.")
        if candidate.candidate_id in candidate_ids:
            raise ValueError("Candidate identifiers must be unique.")
        if not isfinite(belief.probability) or belief.probability < 0.0:
            raise ValueError("Candidate probabilities must be finite and non-negative.")

        candidate_ids.add(candidate.candidate_id)
        probability_sum += belief.probability

    if not abs(probability_sum - 1.0) <= 1e-6:
        raise ValueError("Candidate probabilities must sum to one.")

    if (
        feedback.selected_candidate_id is not None
        and feedback.selected_candidate_id not in candidate_ids
    ):
        raise ValueError("Selected candidate must appear in candidate beliefs.")


class MapMatchFeedbackStore:
    """One-session store for the latest completed and usable HMM belief."""

    def __init__(self, config: FeedbackConfig) -> None:
        if config.maximum_feedback_age_s <= 0.0:
            raise ValueError("maximum_feedback_age_s must be positive.")
        if not (
            0.0
            <= config.minimum_map_match_confidence
            <= 1.0
        ):
            raise ValueError(
                "minimum_map_match_confidence must be between zero and one."
            )

        self._config = config
        self._latest: MapMatchFeedback | None = None


    def publish_completed_match(
        self,
        feedback: MapMatchFeedback,
    ) -> None:
        """Commit HMM output after its entire fusion/map-match cycle completes."""

        validate_map_match_feedback(feedback)

        if (
            self._latest is not None
            and feedback.timestamp_ns <= self._latest.timestamp_ns
        ):
            raise ValueError(
                "Map-match feedback must be committed in strictly increasing time."
            )

        # A weak match is retained nowhere. The next cycle should work without
        # road-context assistance rather than inherit a likely wrong road.
        if (
            feedback.map_match_confidence
            < self._config.minimum_map_match_confidence
        ):
            self._latest = None
            return

        self._latest = feedback


    def prior_for_cycle(
        self,
        *,
        cycle_timestamp_ns: int,
        graph_id: str,
    ) -> FeedbackLookup:
        """Return only belief created before the current cycle."""

        if self._latest is None:
            return FeedbackLookup(
                disposition=FeedbackDisposition.ABSENT,
                feedback=None,
                age_s=None,
            )

        if self._latest.graph_id != graph_id:
            return FeedbackLookup(
                disposition=FeedbackDisposition.GRAPH_MISMATCH,
                feedback=None,
                age_s=None,
            )

        if self._latest.timestamp_ns >= cycle_timestamp_ns:
            return FeedbackLookup(
                disposition=FeedbackDisposition.SAME_CYCLE_OR_FUTURE,
                feedback=None,
                age_s=None,
            )

        age_s = (
            cycle_timestamp_ns - self._latest.timestamp_ns
        ) * 1e-9

        if age_s > self._config.maximum_feedback_age_s:
            return FeedbackLookup(
                disposition=FeedbackDisposition.STALE,
                feedback=None,
                age_s=age_s,
            )

        return FeedbackLookup(
            disposition=FeedbackDisposition.AVAILABLE,
            feedback=self._latest,
            age_s=age_s,
        )


    def reset(self) -> None:
        """Forget map feedback after graph loss, remount/session reset, or reset."""

        self._latest = None
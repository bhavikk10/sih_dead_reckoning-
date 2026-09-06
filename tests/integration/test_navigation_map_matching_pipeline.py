"""Integration tests for the downstream fusion-to-map-matching composition."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from idr_backend.fusion.observations import LocalEnuReference
from idr_backend.map_matching.candidates import CandidateGenerationConfig
from idr_backend.map_matching.graph import (
    MapEnuReference,
    RoadGraph,
    RoadGraphMetadata,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from idr_backend.map_matching.scoring import MapMatchingScoringConfig
from idr_backend.map_matching.viterbi import IncrementalViterbiConfig
from idr_backend.pipeline.feedback import FeedbackConfig
from idr_backend.pipeline.map_matching import (
    NavigationMapMatchingPipeline,
    local_enu_reference_for_graph,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    NavigationEstimate,
    NavigationMode,
)


def _graph() -> RoadGraph:
    """Create a graph whose origin matches the test fusion session exactly."""

    attributes = RoadSegmentAttributes(
        road_class="residential",
        source_way_id="fixture-way",
        speed_limit_mps=12.0,
        lane_count=1,
    )
    return RoadGraph(
        metadata=RoadGraphMetadata(
            graph_id="fusion-map-v1",
            region_id="fixture",
            source_dataset="openstreetmap",
            source_version="fixture",
            enu_reference=MapEnuReference(12.0, 77.0),
            coordinate_frame=CoordinateFrame.NAVIGATION_ENU,
        ),
        nodes=(RoadNode("start", (0.0, 0.0)), RoadNode("end", (0.0, 100.0))),
        segments=(
            RoadSegment(
                edge_id="north-road",
                start_node_id="start",
                end_node_id="end",
                centerline_enu_m=((0.0, 0.0), (0.0, 100.0)),
                attributes=attributes,
                allows_forward=True,
                allows_reverse=True,
            ),
        ),
    )


def _estimate(timestamp_ns: int, north_m: float) -> NavigationEstimate:
    """Return one committed EKF-like estimate with a northbound velocity."""

    return NavigationEstimate(
        timestamp_ns=timestamp_ns,
        mode=NavigationMode.GNSS_AIDED,
        position_enu_m=(0.0, north_m, 0.0),
        velocity_enu_mps=(0.0, 5.0, 0.0),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        position_covariance_enu_m2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        velocity_covariance_enu_m2ps2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        heading_variance_rad2=0.05,
        matched_road_edge_id=None,
        map_match_confidence=None,
    )


@dataclass
class _FusionDouble:
    """Minimal committed-fusion boundary; map code must not inspect EKF internals."""

    local_enu_reference: LocalEnuReference | None
    results: list[object]

    @property
    def runtime_snapshot(self) -> object:
        return SimpleNamespace()

    def push_gnss_fix(self, fix: object) -> object:
        return fix

    def push_raw_sample(self, _sample: object) -> tuple[object, ...]:
        return (self.results.pop(0),)

    def stop(self) -> object:
        return SimpleNamespace()


def _fusion_result(estimate: NavigationEstimate) -> object:
    """Create only the public fields consumed by the downstream wrapper."""

    return SimpleNamespace(
        navigation_estimate=estimate,
        runtime_snapshot=SimpleNamespace(last_cycle_timestamp_ns=estimate.timestamp_ns),
        pre_ekf=SimpleNamespace(
            preprocessing=SimpleNamespace(
                vehicle_imu_sample=SimpleNamespace(timestamp_ns=estimate.timestamp_ns)
            )
        ),
    )


def _pipeline(fusion: _FusionDouble, graph: RoadGraph) -> NavigationMapMatchingPipeline:
    """Build the public wrapper with concise deterministic map policies."""

    return NavigationMapMatchingPipeline(
        fusion_pipeline=fusion,  # type: ignore[arg-type]
        graph=graph,
        candidate_config=CandidateGenerationConfig(8.0, 8.0, 2.0, 3, 0.5, 0.5, 1_000_000_000, 0.2),
        scoring_config=MapMatchingScoringConfig(1.0, 0.5, 0.2, 2.0, 3.0, 0.1, 1.0, 1.0, 5.0, 80.0),
        viterbi_config=IncrementalViterbiConfig(2, 500_000_000, 0.0),
        feedback_config=FeedbackConfig(2.0, 0.0),
    )


def test_wrapper_maps_only_current_committed_fusion_cycles() -> None:
    """Raw fusion results reach HMM and publish a delayed, timestamp-correct edge."""

    graph = _graph()
    fusion = _FusionDouble(
        local_enu_reference=local_enu_reference_for_graph(graph),
        results=[
            _fusion_result(_estimate(1_000_000_000, 0.0)),
            _fusion_result(_estimate(1_100_000_000, 0.5)),
            _fusion_result(_estimate(1_200_000_000, 1.0)),
            _fusion_result(_estimate(1_300_000_000, 1.5)),
        ],
    )
    pipeline = _pipeline(fusion, graph)

    results = [pipeline.push_raw_sample(object())[0] for _ in range(4)]

    committed = results[-1].map_matching.committed_navigation_estimate
    assert committed is not None
    assert committed.timestamp_ns == 1_000_000_000
    assert committed.matched_road_edge_id == "north-road"
    assert results[-1].feedback_published is not None


def test_wrapper_rejects_a_fusion_origin_different_from_map_origin() -> None:
    """The wrapper refuses ENU coordinates that cannot be compared to map metres."""

    graph = _graph()
    fusion = _FusionDouble(
        local_enu_reference=LocalEnuReference(12.001, 77.0),
        results=[],
    )

    with pytest.raises(ValueError, match="different ENU origins"):
        _pipeline(fusion, graph)

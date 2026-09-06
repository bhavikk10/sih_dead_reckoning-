"""Tests for offline OSM graph-artifact loading and validation."""

from __future__ import annotations

import json
from hashlib import sha256
from math import pi
from pathlib import Path

import pytest

from idr_backend.adapters.osm import (
    OfflineOsmGraphAdapter,
    OsmGraphArtifactError,
    OsmGraphArtifactIntegrityError,
    OsmGraphArtifactLocation,
    OsmGraphArtifactSchemaError,
    load_osm_graph_manifest,
)
from idr_backend.map_matching.graph import (
    DirectedRoadTraversal,
    RoadGraphTopologyError,
)
from idr_backend.sensors.types import (
    CoordinateFrame,
    TravelDirection,
)


def _sha256_for_file(path: Path) -> str:
    """Return the SHA-256 digest expected by the adapter manifest."""

    return sha256(path.read_bytes()).hexdigest()


def _write_json(
    path: Path,
    value: object,
) -> None:
    """Write one formatted UTF-8 JSON document for a test artifact."""

    path.write_text(
        json.dumps(value, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_jsonl(
    path: Path,
    records: list[dict[str, object]],
) -> None:
    """Write one JSON object per line, matching the offline artifact format."""

    path.write_text(
        "".join(
            f"{json.dumps(record, sort_keys=True)}\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _manifest(
    *,
    nodes_sha256: str,
    segments_sha256: str,
) -> dict[str, object]:
    """Return valid provenance for the small deterministic fixture graph."""

    return {
        "schema_version": 1,
        "graph_id": "fixture-graph-v1",
        "region_id": "fixture-region",
        "source_dataset": "openstreetmap",
        "source_version": "2026-09-05",
        "coordinate_frame": "navigation_enu",
        "enu_reference": {
            "latitude_deg": 12.9716,
            "longitude_deg": 77.5946,
            "altitude_m": 0.0,
        },
        "nodes_filename": "nodes.jsonl",
        "segments_filename": "segments.jsonl",
        "nodes_sha256": nodes_sha256,
        "segments_sha256": segments_sha256,
    }


def _write_valid_artifact(
    artifact_root: Path,
) -> OsmGraphArtifactLocation:
    """Create a small road graph with a two-way and a one-way segment.

    Topology:

        n0 -- two-way northbound road -- n1 -- one-way eastbound road --> n2
    """

    artifact_root.mkdir()

    nodes_path = artifact_root / "nodes.jsonl"
    segments_path = artifact_root / "segments.jsonl"

    _write_jsonl(
        nodes_path,
        [
            {
                "node_id": "n0",
                "position_enu_m": [0.0, 0.0],
                "is_intersection": False,
                "has_traffic_signal": False,
            },
            {
                "node_id": "n1",
                "position_enu_m": [0.0, 10.0],
                "is_intersection": True,
                "has_traffic_signal": True,
            },
            {
                "node_id": "n2",
                "position_enu_m": [10.0, 10.0],
                "is_intersection": False,
                "has_traffic_signal": False,
            },
        ],
    )

    _write_jsonl(
        segments_path,
        [
            {
                "edge_id": "north-road",
                "start_node_id": "n0",
                "end_node_id": "n1",
                "centerline_enu_m": [
                    [0.0, 0.0],
                    [0.0, 10.0],
                ],
                "allows_forward": True,
                "allows_reverse": True,
                "attributes": {
                    "road_class": "residential",
                    "source_way_id": "way-100",
                    "speed_limit_mps": 8.33,
                    "lane_count": 1,
                    "is_link": False,
                    "is_tunnel": False,
                    "is_bridge": False,
                    "is_roundabout": False,
                },
            },
            {
                "edge_id": "east-road",
                "start_node_id": "n1",
                "end_node_id": "n2",
                "centerline_enu_m": [
                    [0.0, 10.0],
                    [10.0, 10.0],
                ],
                "allows_forward": True,
                "allows_reverse": False,
                "attributes": {
                    "road_class": "primary",
                    "source_way_id": "way-101",
                    "speed_limit_mps": None,
                    "lane_count": 2,
                    "is_link": False,
                    "is_tunnel": False,
                    "is_bridge": False,
                    "is_roundabout": False,
                },
            },
        ],
    )

    _write_json(
        artifact_root / "manifest.json",
        _manifest(
            nodes_sha256=_sha256_for_file(nodes_path),
            segments_sha256=_sha256_for_file(segments_path),
        ),
    )

    return OsmGraphArtifactLocation(
        artifact_root=artifact_root,
    )


def _refresh_member_checksum(
    location: OsmGraphArtifactLocation,
    *,
    manifest_key: str,
    member_filename: str,
) -> None:
    """Update one manifest hash after deliberately changing a fixture member."""

    manifest = json.loads(
        location.manifest_path.read_text(encoding="utf-8")
    )
    manifest[manifest_key] = _sha256_for_file(
        location.artifact_root / member_filename
    )
    _write_json(location.manifest_path, manifest)


def test_adapter_loads_valid_offline_graph(
    tmp_path: Path,
) -> None:
    """A checksummed local artifact becomes a valid immutable RoadGraph."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    graph = OfflineOsmGraphAdapter(
        location=location,
    ).load()

    assert graph.metadata.graph_id == "fixture-graph-v1"
    assert graph.metadata.region_id == "fixture-region"
    assert graph.traversal_count == 3

    assert graph.node("n1").is_intersection is True
    assert graph.node("n1").has_traffic_signal is True
    assert graph.segment("east-road").attributes.speed_limit_mps is None

    northbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.FORWARD,
    )
    southbound = DirectedRoadTraversal(
        edge_id="north-road",
        travel_direction=TravelDirection.REVERSE,
    )
    eastbound = DirectedRoadTraversal(
        edge_id="east-road",
        travel_direction=TravelDirection.FORWARD,
    )

    assert graph.traversal_start_node_id(northbound) == "n0"
    assert graph.traversal_end_node_id(northbound) == "n1"
    assert graph.traversal_start_node_id(southbound) == "n1"
    assert graph.traversal_end_node_id(southbound) == "n0"

    assert graph.traversal_heading_enu_rad(northbound) == pytest.approx(0.0)
    assert graph.traversal_heading_enu_rad(eastbound) == pytest.approx(
        pi / 2.0
    )

    assert graph.shortest_node_path_distance_m(
        start_node_id="n0",
        end_node_id="n2",
        maximum_distance_m=30.0,
    ) == pytest.approx(20.0)

    assert graph.shortest_node_path_distance_m(
        start_node_id="n2",
        end_node_id="n0",
        maximum_distance_m=30.0,
    ) is None


def test_adapter_rejects_member_checksum_mismatch(
    tmp_path: Path,
) -> None:
    """Any edit after manifest generation prevents graph loading."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    nodes_path = location.artifact_root / "nodes.jsonl"
    nodes_path.write_text(
        nodes_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        OsmGraphArtifactIntegrityError,
        match="checksum",
    ):
        OfflineOsmGraphAdapter(location=location).load()


def test_adapter_rejects_malformed_jsonl_after_checksum_verification(
    tmp_path: Path,
) -> None:
    """A matching checksum does not permit invalid JSON records."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    segments_path = location.artifact_root / "segments.jsonl"
    segments_path.write_text(
        "{ definitely-not-valid-json }\n",
        encoding="utf-8",
    )
    _refresh_member_checksum(
        location,
        manifest_key="segments_sha256",
        member_filename="segments.jsonl",
    )

    with pytest.raises(
        OsmGraphArtifactSchemaError,
        match="not valid JSON",
    ):
        OfflineOsmGraphAdapter(location=location).load()


def test_adapter_rejects_segment_with_unknown_endpoint(
    tmp_path: Path,
) -> None:
    """Topology validation rejects graph geometry disconnected from its nodes."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    segments_path = location.artifact_root / "segments.jsonl"
    records = [
        json.loads(line)
        for line in segments_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    records[1]["end_node_id"] = "missing-node"

    _write_jsonl(segments_path, records)
    _refresh_member_checksum(
        location,
        manifest_key="segments_sha256",
        member_filename="segments.jsonl",
    )

    with pytest.raises(
        RoadGraphTopologyError,
        match="unknown node",
    ):
        OfflineOsmGraphAdapter(location=location).load()


def test_manifest_rejects_non_enu_coordinate_frame(
    tmp_path: Path,
) -> None:
    """Map geometry cannot silently use phone-sensor or arbitrary coordinates."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    manifest = json.loads(
        location.manifest_path.read_text(encoding="utf-8")
    )
    manifest["coordinate_frame"] = CoordinateFrame.SENSOR.value
    _write_json(location.manifest_path, manifest)

    with pytest.raises(
        OsmGraphArtifactSchemaError,
        match="navigation ENU",
    ):
        load_osm_graph_manifest(location)


def test_manifest_rejects_invalid_checksum_shape(
    tmp_path: Path,
) -> None:
    """Hashes must be complete SHA-256 strings, not arbitrary text."""

    location = _write_valid_artifact(tmp_path / "fixture-graph")

    manifest = json.loads(
        location.manifest_path.read_text(encoding="utf-8")
    )
    manifest["nodes_sha256"] = "not-a-sha256"
    _write_json(location.manifest_path, manifest)

    with pytest.raises(
        OsmGraphArtifactSchemaError,
        match="SHA-256",
    ):
        load_osm_graph_manifest(location)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.jsonl",
        "..\\outside.jsonl",
        "C:\\outside.jsonl",
        "/outside.jsonl",
    ],
)
def test_artifact_location_rejects_unsafe_member_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    """Manifest-controlled paths must never escape the artifact root."""

    location = OsmGraphArtifactLocation(
        artifact_root=tmp_path / "fixture-graph",
    )

    with pytest.raises(OsmGraphArtifactError):
        location.resolve_member_path(unsafe_path)


def test_artifact_location_resolves_safe_nested_member(
    tmp_path: Path,
) -> None:
    """A normal relative path remains contained under the configured root."""

    location = OsmGraphArtifactLocation(
        artifact_root=tmp_path / "fixture-graph",
    )

    resolved = location.resolve_member_path(
        "prepared/segments.jsonl"
    )

    assert resolved == (
        (tmp_path / "fixture-graph" / "prepared" / "segments.jsonl")
        .resolve()
    )
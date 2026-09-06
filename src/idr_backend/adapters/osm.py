"""Offline OSM road-graph artifact loading.

This adapter reads a prepared local road-graph artifact. It never downloads
tiles, queries Overpass, calls a routing service, or depends on a live traffic
API. OSM extraction and graph preparation happen separately, before deployment.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

from ..map_matching.graph import (
    MapEnuReference,
    RoadGraph,
    RoadGraphMetadata,
    RoadNode,
    RoadSegment,
    RoadSegmentAttributes,
)
from ..sensors.types import CoordinateFrame

OSM_GRAPH_ARTIFACT_SCHEMA_VERSION = 1


class OsmGraphArtifactError(ValueError):
    """Base error for an unreadable or unsafe offline OSM graph artifact."""


class OsmGraphArtifactSchemaError(OsmGraphArtifactError):
    """Raised when artifact records do not match the supported schema."""


class OsmGraphArtifactIntegrityError(OsmGraphArtifactError):
    """Raised when artifact files are missing, altered, or inconsistent."""


@dataclass(frozen=True, slots=True)
class OsmGraphArtifactLocation:
    """Filesystem location of one prepared, versioned offline graph artifact.

    Expected artifact layout:

        <artifact_root>/
            manifest.json
            nodes.jsonl
            segments.jsonl

    ``nodes.jsonl`` and ``segments.jsonl`` are newline-delimited JSON records.
    The format is deliberately portable and inspectable; graph loading converts
    them into the immutable runtime contracts from ``map_matching.graph``.
    """

    artifact_root: Path
    manifest_filename: str = "manifest.json"

    def __post_init__(self) -> None:
        """Require a concrete local artifact directory and a safe manifest name."""

        if not str(self.artifact_root).strip():
            raise OsmGraphArtifactError(
                "OSM graph artifact root must not be blank."
            )

        if (
            not self.manifest_filename.strip()
            or Path(self.manifest_filename).is_absolute()
            or ".." in Path(self.manifest_filename).parts
        ):
            raise OsmGraphArtifactError(
                "Manifest filename must be a safe relative artifact path."
            )

    @property
    def manifest_path(self) -> Path:
        """Return the fixed local path of the graph manifest."""

        return self.artifact_root / self.manifest_filename

    def resolve_member_path(
        self,
        relative_filename: str,
    ) -> Path:
        """Resolve an artifact member while preventing directory traversal."""

        relative_path = Path(relative_filename)
        if (
            not relative_filename.strip()
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise OsmGraphArtifactError(
                "Artifact member filename must be a safe relative path."
            )

        root = self.artifact_root.resolve()
        candidate = (root / relative_path).resolve()

        if root != candidate and root not in candidate.parents:
            raise OsmGraphArtifactError(
                "Artifact member path escapes the configured artifact root."
            )

        return candidate


@dataclass(frozen=True, slots=True)
class OsmGraphArtifactManifest:
    """Validated provenance and file layout for one prepared OSM graph."""

    schema_version: int

    graph_id: str
    region_id: str
    source_dataset: str
    source_version: str

    enu_reference: MapEnuReference

    # The graph is deliberately metric and uses the same ENU convention as the
    # EKF/map-matching boundary. Any other frame is rejected at load time.
    coordinate_frame: CoordinateFrame

    nodes_filename: str
    segments_filename: str

    # SHA-256 hashes are calculated during offline graph preparation. Runtime
    # verifies them before parsing, so a stale or edited map artifact is never
    # silently used for navigation.
    nodes_sha256: str
    segments_sha256: str

    def __post_init__(self) -> None:
        """Reject unsupported, non-reproducible, or unsafe manifest metadata."""

        if self.schema_version != OSM_GRAPH_ARTIFACT_SCHEMA_VERSION:
            raise OsmGraphArtifactSchemaError(
                "Unsupported OSM graph artifact schema version: "
                f"{self.schema_version!r}."
            )

        text_fields = (
            self.graph_id,
            self.region_id,
            self.source_dataset,
            self.source_version,
            self.nodes_filename,
            self.segments_filename,
            self.nodes_sha256,
            self.segments_sha256,
        )

        if not all(value.strip() for value in text_fields):
            raise OsmGraphArtifactSchemaError(
                "Graph provenance and node/segment filenames are required."
            )

        if self.coordinate_frame is not CoordinateFrame.NAVIGATION_ENU:
            raise OsmGraphArtifactSchemaError(
                "Offline graph artifacts must use navigation ENU coordinates."
            )

        for filename in (
            self.nodes_filename,
            self.segments_filename,
        ):
            path = Path(filename)
            if path.is_absolute() or ".." in path.parts:
                raise OsmGraphArtifactSchemaError(
                    "Node and segment filenames must be safe relative paths."
                )
            
        for label, digest in (
            ("nodes_sha256", self.nodes_sha256),
            ("segments_sha256", self.segments_sha256),
        ):
            if (
                len(digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in digest.lower()
                )
            ):
                raise OsmGraphArtifactSchemaError(
                    f"{label} must be a 64-character SHA-256 hex digest."
                )


    def to_graph_metadata(self) -> RoadGraphMetadata:
        """Convert adapter provenance into the core immutable graph metadata."""

        return RoadGraphMetadata(
            graph_id=self.graph_id,
            region_id=self.region_id,
            source_dataset=self.source_dataset,
            source_version=self.source_version,
            enu_reference=self.enu_reference,
            coordinate_frame=self.coordinate_frame,
        )


def load_osm_graph_manifest(
    location: OsmGraphArtifactLocation,
) -> OsmGraphArtifactManifest:
    """Load one manifest JSON object into validated typed provenance metadata."""

    manifest_path = location.manifest_path
    _require_regular_file(manifest_path, label="OSM graph manifest")

    try:
        with manifest_path.open(
            "r",
            encoding="utf-8",
        ) as manifest_file:
            raw_manifest = json.load(manifest_file)
    except json.JSONDecodeError as error:
        raise OsmGraphArtifactSchemaError(
            f"Manifest is not valid JSON: {manifest_path}."
        ) from error
    except OSError as error:
        raise OsmGraphArtifactIntegrityError(
            f"Could not read graph manifest: {manifest_path}."
        ) from error

    manifest_record = _require_mapping(
        raw_manifest,
        description=f"Manifest {manifest_path}",
    )
    return _manifest_from_record(manifest_record)


def _manifest_from_record(
    record: Mapping[str, Any],
) -> OsmGraphArtifactManifest:
    """Convert untrusted manifest JSON into immutable typed metadata."""

    coordinate_frame_text = _require_string(
        record,
        key="coordinate_frame",
        description="Manifest",
    )
    try:
        coordinate_frame = CoordinateFrame(coordinate_frame_text)
    except ValueError as error:
        raise OsmGraphArtifactSchemaError(
            "Manifest coordinate_frame is unsupported: "
            f"{coordinate_frame_text!r}."
        ) from error

    enu_reference_record = _require_mapping(
        _require_field(
            record,
            key="enu_reference",
            description="Manifest",
        ),
        description="Manifest enu_reference",
    )

    try:
        enu_reference = MapEnuReference(
            latitude_deg=_require_finite_number(
                enu_reference_record,
                key="latitude_deg",
                description="Manifest enu_reference",
            ),
            longitude_deg=_require_finite_number(
                enu_reference_record,
                key="longitude_deg",
                description="Manifest enu_reference",
            ),
            altitude_m=_optional_finite_number(
                enu_reference_record,
                key="altitude_m",
                default=0.0,
                description="Manifest enu_reference",
            ),
        )
    except ValueError as error:
        raise OsmGraphArtifactSchemaError(
            "Manifest contains an invalid ENU geographic reference."
        ) from error

    return OsmGraphArtifactManifest(
        schema_version=_require_integer(
            record,
            key="schema_version",
            description="Manifest",
        ),
        graph_id=_require_string(
            record,
            key="graph_id",
            description="Manifest",
        ),
        region_id=_require_string(
            record,
            key="region_id",
            description="Manifest",
        ),
        source_dataset=_require_string(
            record,
            key="source_dataset",
            description="Manifest",
        ),
        source_version=_require_string(
            record,
            key="source_version",
            description="Manifest",
        ),
        enu_reference=enu_reference,
        coordinate_frame=coordinate_frame,
        nodes_filename=_require_string(
            record,
            key="nodes_filename",
            description="Manifest",
        ),
        segments_filename=_require_string(
            record,
            key="segments_filename",
            description="Manifest",
        ),
        nodes_sha256=_require_sha256(
            record,
            key="nodes_sha256",
            description="Manifest",
        ),
        segments_sha256=_require_sha256(
            record,
            key="segments_sha256",
            description="Manifest",
        ),
    )


def _require_field(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> Any:
    """Return one required raw field or raise a schema-specific error."""

    try:
        return record[key]
    except KeyError as error:
        raise OsmGraphArtifactSchemaError(
            f"{description} is missing required field {key!r}."
        ) from error


def _require_mapping(
    value: Any,
    *,
    description: str,
) -> Mapping[str, Any]:
    """Require a JSON object rather than a list, scalar, or null."""

    if not isinstance(value, Mapping):
        raise OsmGraphArtifactSchemaError(
            f"{description} must be a JSON object."
        )
    return value


def _require_string(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> str:
    """Require one non-blank string without inventing a fallback value."""

    value = _require_field(
        record,
        key=key,
        description=description,
    )
    if not isinstance(value, str) or not value.strip():
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be a non-blank string."
        )
    return value


def _require_integer(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> int:
    """Require an integer while refusing Python's boolean-as-integer quirk."""

    value = _require_field(
        record,
        key=key,
        description=description,
    )
    if isinstance(value, bool) or not isinstance(value, int):
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be an integer."
        )
    return value


def _require_finite_number(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> float:
    """Require one finite JSON number and convert it to a float."""

    value = _require_field(
        record,
        key=key,
        description=description,
    )
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
    ):
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be a finite number."
        )
    return float(value)


def _optional_finite_number(
    record: Mapping[str, Any],
    *,
    key: str,
    default: float,
    description: str,
) -> float:
    """Return an optional finite number, using only an explicit safe default."""

    if key not in record or record[key] is None:
        return default

    return _require_finite_number(
        record,
        key=key,
        description=description,
    )


def _require_sha256(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> str:
    """Require and normalize a SHA-256 hexadecimal digest."""

    digest = _require_string(
        record,
        key=key,
        description=description,
    ).lower()

    if (
        len(digest) != 64
        or any(
            character not in "0123456789abcdef"
            for character in digest
        )
    ):
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be a SHA-256 digest."
        )

    return digest


def _require_regular_file(
    path: Path,
    *,
    label: str,
) -> None:
    """Ensure an expected local artifact member exists and is a normal file."""

    if not path.exists():
        raise OsmGraphArtifactIntegrityError(
            f"{label} does not exist: {path}."
        )

    if not path.is_file():
        raise OsmGraphArtifactIntegrityError(
            f"{label} is not a regular file: {path}."
        )


def _sha256_for_file(
    path: Path,
) -> str:
    """Calculate a streaming SHA-256 digest without loading a large file at once."""

    digest = sha256()

    try:
        with path.open("rb") as artifact_file:
            while chunk := artifact_file.read(1_048_576):
                digest.update(chunk)
    except OSError as error:
        raise OsmGraphArtifactIntegrityError(
            f"Could not calculate checksum for {path}."
        ) from error

    return digest.hexdigest()


def _verify_member_checksum(
    *,
    path: Path,
    expected_sha256: str,
    label: str,
) -> None:
    """Reject a stale or altered artifact member before JSON parsing begins."""

    _require_regular_file(path, label=label)

    actual_sha256 = _sha256_for_file(path)
    if actual_sha256 != expected_sha256:
        raise OsmGraphArtifactIntegrityError(
            f"{label} checksum does not match its manifest: {path}."
        )


def _iter_jsonl_records(
    path: Path,
    *,
    label: str,
) -> Iterator[tuple[int, Mapping[str, Any]]]:
    """Yield non-empty JSON-object records with one-based source line numbers."""

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as artifact_file:
            for line_number, line in enumerate(
                artifact_file,
                start=1,
            ):
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                try:
                    raw_record = json.loads(stripped_line)
                except json.JSONDecodeError as error:
                    raise OsmGraphArtifactSchemaError(
                        f"{label} line {line_number} is not valid JSON."
                    ) from error

                yield (
                    line_number,
                    _require_mapping(
                        raw_record,
                        description=f"{label} line {line_number}",
                    ),
                )
    except OSError as error:
        raise OsmGraphArtifactIntegrityError(
            f"Could not read {label}: {path}."
        ) from error


def _require_boolean(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> bool:
    """Require an explicit JSON boolean for direction and topology facts."""

    value = _require_field(
        record,
        key=key,
        description=description,
    )
    if not isinstance(value, bool):
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be true or false."
        )
    return value


def _optional_boolean(
    record: Mapping[str, Any],
    *,
    key: str,
    default: bool,
    description: str,
) -> bool:
    """Return a boolean optional field without interpreting strings like 'yes'."""

    if key not in record or record[key] is None:
        return default

    return _require_boolean(
        record,
        key=key,
        description=description,
    )


def _parse_enu_point(
    value: Any,
    *,
    description: str,
) -> tuple[float, float]:
    """Parse one JSON ``[east_m, north_m]`` point into immutable ENU geometry."""

    if not isinstance(value, list) or len(value) != 2:
        raise OsmGraphArtifactSchemaError(
            f"{description} must be a two-element [east, north] array."
        )

    east_m, north_m = value
    if (
        isinstance(east_m, bool)
        or isinstance(north_m, bool)
        or not isinstance(east_m, int | float)
        or not isinstance(north_m, int | float)
        or not isfinite(east_m)
        or not isfinite(north_m)
    ):
        raise OsmGraphArtifactSchemaError(
            f"{description} must contain finite numeric ENU metres."
        )

    return (float(east_m), float(north_m))


def _road_node_from_record(
    record: Mapping[str, Any],
    *,
    description: str,
) -> RoadNode:
    """Convert one validated JSONL node record into a core graph node."""

    return RoadNode(
        node_id=_require_string(
            record,
            key="node_id",
            description=description,
        ),
        position_enu_m=_parse_enu_point(
            _require_field(
                record,
                key="position_enu_m",
                description=description,
            ),
            description=f"{description} position_enu_m",
        ),
        is_intersection=_optional_boolean(
            record,
            key="is_intersection",
            default=False,
            description=description,
        ),
        has_traffic_signal=_optional_boolean(
            record,
            key="has_traffic_signal",
            default=False,
            description=description,
        ),
    )


def _optional_positive_number(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> float | None:
    """Return an optional positive physical quantity such as a speed limit."""

    if key not in record or record[key] is None:
        return None

    value = _require_finite_number(
        record,
        key=key,
        description=description,
    )
    if value <= 0.0:
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be positive when supplied."
        )

    return value


def _optional_positive_integer(
    record: Mapping[str, Any],
    *,
    key: str,
    description: str,
) -> int | None:
    """Return an optional positive integer such as lane count."""

    if key not in record or record[key] is None:
        return None

    value = _require_integer(
        record,
        key=key,
        description=description,
    )
    if value < 1:
        raise OsmGraphArtifactSchemaError(
            f"{description} field {key!r} must be at least one."
        )

    return value


def _road_segment_attributes_from_record(
    record: Mapping[str, Any],
    *,
    description: str,
) -> RoadSegmentAttributes:
    """Parse static OSM attributes without inventing absent map facts."""

    return RoadSegmentAttributes(
        road_class=_require_string(
            record,
            key="road_class",
            description=description,
        ),
        source_way_id=_require_string(
            record,
            key="source_way_id",
            description=description,
        ),
        speed_limit_mps=_optional_positive_number(
            record,
            key="speed_limit_mps",
            description=description,
        ),
        lane_count=_optional_positive_integer(
            record,
            key="lane_count",
            description=description,
        ),
        is_link=_optional_boolean(
            record,
            key="is_link",
            default=False,
            description=description,
        ),
        is_tunnel=_optional_boolean(
            record,
            key="is_tunnel",
            default=False,
            description=description,
        ),
        is_bridge=_optional_boolean(
            record,
            key="is_bridge",
            default=False,
            description=description,
        ),
        is_roundabout=_optional_boolean(
            record,
            key="is_roundabout",
            default=False,
            description=description,
        ),
    )


def _road_segment_from_record(
    record: Mapping[str, Any],
    *,
    description: str,
) -> RoadSegment:
    """Convert one JSONL road segment record into a validated core segment."""

    raw_centerline = _require_field(
        record,
        key="centerline_enu_m",
        description=description,
    )
    if not isinstance(raw_centerline, list):
        raise OsmGraphArtifactSchemaError(
            f"{description} centerline_enu_m must be a JSON array."
        )

    centerline_enu_m = tuple(
        _parse_enu_point(
            point,
            description=(
                f"{description} centerline_enu_m[{point_index}]"
            ),
        )
        for point_index, point in enumerate(raw_centerline)
    )

    attributes_record = _require_mapping(
        _require_field(
            record,
            key="attributes",
            description=description,
        ),
        description=f"{description} attributes",
    )

    return RoadSegment(
        edge_id=_require_string(
            record,
            key="edge_id",
            description=description,
        ),
        start_node_id=_require_string(
            record,
            key="start_node_id",
            description=description,
        ),
        end_node_id=_require_string(
            record,
            key="end_node_id",
            description=description,
        ),
        centerline_enu_m=centerline_enu_m,
        attributes=_road_segment_attributes_from_record(
            attributes_record,
            description=f"{description} attributes",
        ),
        allows_forward=_require_boolean(
            record,
            key="allows_forward",
            description=description,
        ),
        allows_reverse=_require_boolean(
            record,
            key="allows_reverse",
            description=description,
        ),
    )


@dataclass(frozen=True, slots=True)
class OfflineOsmGraphAdapter:
    """Load one local, checksummed OSM artifact into an immutable RoadGraph."""

    location: OsmGraphArtifactLocation
    endpoint_tolerance_m: float = 0.5

    def __post_init__(self) -> None:
        """Validate only the adapter's graph-geometry loading policy."""

        if (
            not isfinite(self.endpoint_tolerance_m)
            or self.endpoint_tolerance_m < 0.0
        ):
            raise ValueError(
                "endpoint_tolerance_m must be finite and non-negative."
            )

    def load(self) -> RoadGraph:
        """Verify, parse, and validate the complete local graph artifact."""

        manifest = load_osm_graph_manifest(self.location)

        nodes_path = self.location.resolve_member_path(
            manifest.nodes_filename
        )
        segments_path = self.location.resolve_member_path(
            manifest.segments_filename
        )

        _verify_member_checksum(
            path=nodes_path,
            expected_sha256=manifest.nodes_sha256,
            label="OSM graph nodes file",
        )
        _verify_member_checksum(
            path=segments_path,
            expected_sha256=manifest.segments_sha256,
            label="OSM graph segments file",
        )

        nodes = tuple(
            _road_node_from_record(
                record,
                description=(
                    f"Nodes file {nodes_path.name} line {line_number}"
                ),
            )
            for line_number, record in _iter_jsonl_records(
                nodes_path,
                label="OSM graph nodes file",
            )
        )
        segments = tuple(
            _road_segment_from_record(
                record,
                description=(
                    f"Segments file {segments_path.name} "
                    f"line {line_number}"
                ),
            )
            for line_number, record in _iter_jsonl_records(
                segments_path,
                label="OSM graph segments file",
            )
        )

        if not nodes:
            raise OsmGraphArtifactIntegrityError(
                "OSM graph artifact contains no road nodes."
            )

        if not segments:
            raise OsmGraphArtifactIntegrityError(
                "OSM graph artifact contains no road segments."
            )

        # RoadGraph performs the final cross-record checks: duplicate IDs,
        # missing endpoints, geometry-node mismatch, zero-length roads, and
        # invalid one-way topology all fail before runtime navigation begins.
        return RoadGraph(
            metadata=manifest.to_graph_metadata(),
            nodes=nodes,
            segments=segments,
            endpoint_tolerance_m=self.endpoint_tolerance_m,
        )





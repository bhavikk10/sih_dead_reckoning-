"""Per-session ownership and safe estimate projection for the HTTP service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import atan2, degrees, sqrt
from pathlib import Path
from threading import RLock
from typing import Callable, Protocol
from uuid import uuid4

from ..evaluation.replay import (
    ReplayParameterSet,
    build_fusion_config,
    default_preprocessor_config,
)
from ..fusion.observations import LocalEnuReference
from ..pipeline.fusion import FusionPipelineResult, NavigationFusionPipeline
from ..pipeline.orchestrator import DeterministicPipelineConfig
from ..pipeline.selected_velocity import (
    SelectedVelocityRuntimeArtifacts,
    build_selected_velocity_pre_ekf_pipeline,
)
from ..sensors.preprocessing import DeterministicImuPreprocessor
from ..sensors.types import (
    CoordinateFrame,
    GnssFix,
    MeasurementUnit,
    NavigationEstimate,
    RawSensorSample,
    SensorKind,
    SensorSource,
)


class NavigationPipeline(Protocol):
    """Small protocol that keeps service tests independent of ONNX artifacts."""

    @property
    def local_enu_reference(self) -> LocalEnuReference | None: ...

    @property
    def runtime_snapshot(self) -> object: ...

    def push_gnss_fix(self, fix: GnssFix) -> object: ...

    def push_raw_sample(self, raw_sample: RawSensorSample) -> tuple[FusionPipelineResult, ...]: ...

    def stop(self) -> object: ...


@dataclass(frozen=True, slots=True)
class ReviewedRuntimeArtifacts:
    """The reviewed deterministic artifact/profile pair used by live sessions."""

    repository_root: Path
    velocity_artifact_directory: Path
    uncertainty_artifact_directory: Path
    uncertainty_profile_filename: str
    parameters_profile: Path

    @classmethod
    def defaults(cls, repository_root: Path | None = None) -> "ReviewedRuntimeArtifacts":
        root = (
            Path(__file__).resolve().parents[3]
            if repository_root is None
            else repository_root.resolve()
        )
        artifact_directory = root / "artifacts" / "anchored_velocity_comparison"
        return cls(
            repository_root=root,
            velocity_artifact_directory=artifact_directory,
            uncertainty_artifact_directory=artifact_directory,
            uncertainty_profile_filename="anchor_delta_gru_deterministic_uncertainty.json",
            parameters_profile=(
                root
                / "artifacts"
                / "deterministic_navigation_replay_final"
                / "selected_ekf_profile.json"
            ),
        )


def build_reviewed_navigation_pipeline(
    artifacts: ReviewedRuntimeArtifacts,
) -> NavigationFusionPipeline:
    """Construct one clean session using the reviewed default runtime artifacts."""

    try:
        profile = json.loads(artifacts.parameters_profile.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Selected EKF profile is missing: {artifacts.parameters_profile}"
        ) from error
    parameters_payload = profile.get("parameters")
    if not isinstance(parameters_payload, dict):
        raise ValueError("Selected EKF profile needs a top-level 'parameters' object.")

    parameters = ReplayParameterSet(**parameters_payload)
    preprocessor = DeterministicImuPreprocessor(default_preprocessor_config())
    pre_ekf = build_selected_velocity_pre_ekf_pipeline(
        config=DeterministicPipelineConfig(maximum_gnss_anchor_age_ns=120_000_000_000),
        preprocessor=preprocessor,
        artifacts=SelectedVelocityRuntimeArtifacts(
            velocity_artifact_directory=artifacts.velocity_artifact_directory,
            uncertainty_artifact_directory=artifacts.uncertainty_artifact_directory,
            uncertainty_profile_filename=artifacts.uncertainty_profile_filename,
        ),
    )
    return NavigationFusionPipeline(
        pre_ekf_pipeline=pre_ekf,
        config=build_fusion_config(parameters),
    )


@dataclass(frozen=True, slots=True)
class PublicEstimate:
    """Public, WGS-84 form of a committed ``NavigationEstimate``."""

    timestamp_ns: int
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    speed_mps: float
    heading_deg: float
    horizontal_sigma_m: float
    vertical_sigma_m: float
    mode: str
    is_dead_reckoning: bool
    map_match_confidence: float | None


def public_estimate(
    estimate: NavigationEstimate,
    local_enu_reference: LocalEnuReference,
) -> PublicEstimate:
    """Project one committed ENU estimate to a map-ready WGS-84 response."""

    latitude_deg, longitude_deg, altitude_m = local_enu_reference.unproject(
        estimate.position_enu_m
    )
    velocity_east, velocity_north, _ = estimate.velocity_enu_mps
    speed_mps = sqrt(velocity_east * velocity_east + velocity_north * velocity_north)
    heading_deg = _heading_degrees(estimate.vehicle_to_navigation_wxyz)
    covariance = estimate.position_covariance_enu_m2
    horizontal_sigma_m = sqrt(max(0.0, covariance[0][0], covariance[1][1]))
    vertical_sigma_m = sqrt(max(0.0, covariance[2][2]))
    return PublicEstimate(
        timestamp_ns=estimate.timestamp_ns,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
        altitude_m=altitude_m,
        speed_mps=speed_mps,
        heading_deg=heading_deg,
        horizontal_sigma_m=horizontal_sigma_m,
        vertical_sigma_m=vertical_sigma_m,
        mode=estimate.mode.value,
        is_dead_reckoning=estimate.mode.value == "dead_reckoning",
        map_match_confidence=estimate.map_match_confidence,
    )


def _heading_degrees(vehicle_to_navigation_wxyz: tuple[float, float, float, float]) -> float:
    """Return the vehicle-forward direction as clockwise-from-north degrees."""

    w, x, y, z = vehicle_to_navigation_wxyz
    forward_east = 1.0 - 2.0 * (y * y + z * z)
    forward_north = 2.0 * (x * y + w * z)
    return degrees(atan2(forward_east, forward_north)) % 360.0


class NavigationSession:
    """Serial ownership boundary for exactly one mobile navigation drive."""

    def __init__(
        self,
        *,
        session_id: str,
        source_id: str,
        receiver_id: str,
        pipeline: NavigationPipeline,
    ) -> None:
        self.session_id = session_id
        self.source_id = source_id
        self.receiver_id = receiver_id
        self._pipeline = pipeline
        self._lock = RLock()
        self._last_timestamp_by_stream: dict[str, int] = {}
        self._latest_estimate: PublicEstimate | None = None

    @property
    def latest_estimate(self) -> PublicEstimate | None:
        with self._lock:
            return self._latest_estimate

    def push_gnss(self, fix: GnssFix) -> None:
        """Submit one chronological fix; its EKF update waits for a later IMU pair."""

        with self._lock:
            self._require_identifier(fix.receiver_id, self.receiver_id, "receiver")
            self._require_nondecreasing("gnss", fix.timestamp_ns)
            self._pipeline.push_gnss_fix(fix)

    def push_imu(self, sample: RawSensorSample) -> PublicEstimate | None:
        """Submit one raw callback and return an estimate only if a cycle committed."""

        with self._lock:
            self._require_identifier(sample.source_id, self.source_id, "source")
            self._require_nondecreasing(sample.kind.value, sample.timestamp_ns)
            results = self._pipeline.push_raw_sample(sample)
            emitted_estimate: PublicEstimate | None = None
            for result in results:
                committed = _newly_committed_estimate(result)
                if committed is not None:
                    reference = self._pipeline.local_enu_reference
                    if reference is not None:
                        emitted_estimate = public_estimate(committed, reference)
                        self._latest_estimate = emitted_estimate
            return emitted_estimate

    def stop(self) -> None:
        """Release the per-drive pipeline exactly once when the session is deleted."""

        with self._lock:
            self._pipeline.stop()

    def _require_nondecreasing(self, stream: str, timestamp_ns: int) -> None:
        previous = self._last_timestamp_by_stream.get(stream)
        if previous is not None and timestamp_ns < previous:
            raise ValueError(
                f"{stream} timestamp regressed from {previous} to {timestamp_ns}."
            )
        self._last_timestamp_by_stream[stream] = timestamp_ns

    @staticmethod
    def _require_identifier(actual: str, expected: str, label: str) -> None:
        if actual != expected:
            raise ValueError(f"Unexpected {label}_id for this session.")


def _newly_committed_estimate(result: FusionPipelineResult) -> NavigationEstimate | None:
    """Avoid re-emitting a stale snapshot after preprocessing rejects a callback."""

    estimate = result.navigation_estimate
    if (
        estimate is None
        or result.runtime_snapshot.last_cycle_timestamp_ns
        != result.pre_ekf.preprocessing.timestamp_ns
    ):
        return None
    return estimate


PipelineFactory = Callable[[], NavigationPipeline]


class NavigationSessionRegistry:
    """Thread-safe session registry; the service never shares a filter across drives."""

    def __init__(self, pipeline_factory: PipelineFactory) -> None:
        self._pipeline_factory = pipeline_factory
        self._sessions: dict[str, NavigationSession] = {}
        self._lock = RLock()

    def create(self, *, source_id: str, receiver_id: str) -> NavigationSession:
        session = NavigationSession(
            session_id=uuid4().hex,
            source_id=source_id,
            receiver_id=receiver_id,
            pipeline=self._pipeline_factory(),
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> NavigationSession:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as error:
                raise KeyError(f"Unknown navigation session: {session_id}") from error

    def delete(self, session_id: str) -> None:
        with self._lock:
            try:
                session = self._sessions.pop(session_id)
            except KeyError as error:
                raise KeyError(f"Unknown navigation session: {session_id}") from error
        session.stop()

    def stop_all(self) -> None:
        with self._lock:
            sessions = tuple(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.stop()


def raw_imu_from_payload(
    *,
    timestamp_ns: int,
    source_id: str,
    kind: str,
    value: tuple[float, float, float],
    unit: str,
    frame: str,
    vendor_accuracy: int | None,
) -> RawSensorSample:
    """Construct the immutable core contract after JSON schema validation."""

    return RawSensorSample(
        timestamp_ns=timestamp_ns,
        source=SensorSource.PHONE,
        source_id=source_id,
        kind=SensorKind(kind),
        value=value,
        unit=MeasurementUnit(unit),
        frame=CoordinateFrame(frame),
        vendor_accuracy=vendor_accuracy,
    )

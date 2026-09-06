"""Raw phone/CAN replay for the selected deterministic navigation profile.

The supplied recordings contain phone GNSS, phone accelerometer/gyroscope,
and a separately recorded vehicle/CAN trace.  This module has a deliberately
strict data-flow policy:

* Phone IMU and phone GNSS are the *only* inputs to preprocessing and fusion.
* CAN speed/position are held aside as an offline reference only.
* A scheduled GNSS blackout withholds phone GNSS from the pipeline; it never
  synthesises missing fixes or uses CAN values as a substitute.
* The selected ONNX GRU and its hash-bound deterministic uncertainty profile
  are loaded through the normal production composition helper.

It is consequently suitable for development tuning and a one-time independent
replay, but it is not a claim of a new live field collection.  The source data
are pre-existing recorded drives.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite, radians
from pathlib import Path
from time import perf_counter_ns
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from idr_backend.fusion.constraints import NonHolonomicConstraintConfig
from idr_backend.fusion.covariance import ImuNoiseDensity
from idr_backend.fusion.modes import NavigationModeConfig
from idr_backend.fusion.observations import FusionMeasurementConfig, LocalEnuReference
from idr_backend.fusion.propagation import PropagationConfig, PropagationDisposition
from idr_backend.pipeline.fusion import FusionPipelineConfig, NavigationFusionPipeline
from idr_backend.pipeline.orchestrator import DeterministicPipelineConfig
from idr_backend.pipeline.runtime import NavigationRuntimeConfig
from idr_backend.pipeline.selected_velocity import (
    SelectedVelocityRuntimeArtifacts,
    build_selected_velocity_pre_ekf_pipeline,
)
from idr_backend.sensors.calibration_evidence import CalibrationEvidenceLimits
from idr_backend.sensors.gnss import GnssQualityLimits
from idr_backend.sensors.preprocessing import (
    DeterministicImuPreprocessor,
    DeterministicPreprocessorConfig,
)
from idr_backend.sensors.quality import VehicleImuQualityLimits
from idr_backend.sensors.types import (
    CoordinateFrame,
    GnssFix,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
)


_NS_PER_SECOND = 1_000_000_000
_PHONE_GNSS_PERIOD_NS = _NS_PER_SECOND


@dataclass(frozen=True, slots=True)
class RawReplayJourney:
    """Aligned raw phone inputs and CAN-only evaluation references for one trip."""

    journey_id: str
    timestamps_ns: np.ndarray
    acceleration_sensor_mps2: np.ndarray
    angular_velocity_sensor_radps: np.ndarray
    phone_latitude_deg: np.ndarray
    phone_longitude_deg: np.ndarray
    phone_altitude_m: np.ndarray
    phone_speed_mps: np.ndarray
    phone_horizontal_accuracy_m: np.ndarray
    phone_course_rad: np.ndarray
    reference_latitude_deg: np.ndarray
    reference_longitude_deg: np.ndarray
    reference_speed_mps: np.ndarray

    @property
    def duration_s(self) -> float:
        """Return elapsed recording time after timestamp canonicalisation."""

        if len(self.timestamps_ns) < 2:
            return 0.0
        return float((self.timestamps_ns[-1] - self.timestamps_ns[0]) * 1e-9)

    def __post_init__(self) -> None:
        """Reject partial or misaligned input before a replay begins."""

        count = len(self.timestamps_ns)
        arrays = (
            self.acceleration_sensor_mps2,
            self.angular_velocity_sensor_radps,
            self.phone_latitude_deg,
            self.phone_longitude_deg,
            self.phone_altitude_m,
            self.phone_speed_mps,
            self.phone_horizontal_accuracy_m,
            self.phone_course_rad,
            self.reference_latitude_deg,
            self.reference_longitude_deg,
            self.reference_speed_mps,
        )
        if count < 2 or any(len(array) != count for array in arrays):
            raise ValueError("Raw replay arrays must have one common length of at least two.")
        if self.acceleration_sensor_mps2.shape != (count, 3):
            raise ValueError("Acceleration replay input must have shape (n, 3).")
        if self.angular_velocity_sensor_radps.shape != (count, 3):
            raise ValueError("Gyroscope replay input must have shape (n, 3).")
        if not np.all(np.diff(self.timestamps_ns) > 0):
            raise ValueError("Raw replay timestamps must be strictly increasing.")


@dataclass(frozen=True, slots=True)
class BlackoutScenario:
    """GNSS availability schedule for one causal replay episode.

    GNSS is available through ``blackout_start_s``, is withheld for exactly
    ``blackout_duration_s``, then resumes.  The IMU stream is uninterrupted.
    """

    blackout_start_s: float = 100.0
    blackout_duration_s: float = 120.0
    required_recovery_s: float = 30.0

    @property
    def blackout_end_s(self) -> float:
        """Return the elapsed time at which GNSS becomes available again."""

        return self.blackout_start_s + self.blackout_duration_s

    @property
    def minimum_duration_s(self) -> float:
        """Return the full recording length required for fair recovery scoring."""

        return self.blackout_end_s + self.required_recovery_s

    def __post_init__(self) -> None:
        """Keep timings explicit and physically meaningful."""

        if not all(
            isfinite(value) and value > 0.0
            for value in (
                self.blackout_start_s,
                self.blackout_duration_s,
                self.required_recovery_s,
            )
        ):
            raise ValueError("Blackout start, duration, and recovery must be positive.")


@dataclass(frozen=True, slots=True)
class ReplayParameterSet:
    """The only EKF, gate, and NHC knobs eligible for development tuning.

    The values are scales relative to an explicit baseline phone-IMU profile.
    Keeping the dimensions few and named avoids an unreviewable hyperparameter
    search that could simply overfit a small collection of recorded drives.
    """

    name: str
    accelerometer_noise_scale: float = 1.0
    gyroscope_noise_scale: float = 1.0
    bias_random_walk_scale: float = 1.0
    gnss_position_nis_gate: float = 9.21
    gnss_velocity_nis_gate: float = 9.21
    velocity_model_nis_gate: float = 6.63
    nhc_lateral_std_scale: float = 1.0
    nhc_vertical_std_scale: float = 1.0
    nhc_maximum_yaw_rate_radps: float = 0.8

    def __post_init__(self) -> None:
        """Reject a tuning document that would create invalid covariance."""

        if not self.name.strip():
            raise ValueError("Replay parameter sets must have a non-blank name.")
        positive = (
            self.accelerometer_noise_scale,
            self.gyroscope_noise_scale,
            self.bias_random_walk_scale,
            self.gnss_position_nis_gate,
            self.gnss_velocity_nis_gate,
            self.velocity_model_nis_gate,
            self.nhc_lateral_std_scale,
            self.nhc_vertical_std_scale,
            self.nhc_maximum_yaw_rate_radps,
        )
        if not all(isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("All replay parameter values must be finite and positive.")


@dataclass(frozen=True, slots=True)
class ReplayReport:
    """Serializable outcomes from one actual preprocessing-to-EKF replay."""

    journey_id: str
    scenario: BlackoutScenario
    parameters: ReplayParameterSet
    recording_duration_s: float
    raw_samples: int
    synchronized_samples: int
    accepted_preprocessing_samples: int
    calibration_available_samples: int
    final_calibration_phase: str
    final_calibration_confidence: float | None
    preprocessing_disposition_counts: dict[str, int]
    velocity_observations: int
    native_propagation_steps: int
    timing_gap_recoveries: int
    blackout_position_samples: int
    blackout_last_scored_elapsed_s: float | None
    blackout_mean_relative_position_error_m: float | None
    blackout_p95_relative_position_error_m: float | None
    blackout_endpoint_relative_position_error_m: float | None
    blackout_velocity_mae_mps: float | None
    blackout_velocity_mae_kmh: float | None
    velocity_uncertainty_one_sigma_coverage: float | None
    velocity_uncertainty_two_sigma_coverage: float | None
    gnss_position_accepted: int
    gnss_position_rejected: int
    gnss_velocity_accepted: int
    gnss_velocity_rejected: int
    velocity_model_accepted: int
    velocity_model_rejected: int
    nhc_accepted: int
    nhc_rejected: int
    first_recovery_gnss_acceptance_s: float | None
    gnss_aided_recovery_s: float | None
    raw_callback_latency_median_ms: float | None
    raw_callback_latency_p95_ms: float | None
    final_runtime_phase: str
    valid_for_scoring: bool
    scoring_notes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Convert enums/dataclasses to plain JSON-compatible values."""

        return asdict(self)


def default_preprocessor_config() -> DeterministicPreprocessorConfig:
    """Return the audited phone profile used in all raw replay candidates.

    The source recording lacks formal speed/course accuracy fields.  The
    replay adapter therefore uses documented conservative *evaluation
    assumptions* (1.5 m/s speed standard deviation and 15 degree course
    standard deviation), rather than treating those quantities as perfect.
    They are held fixed for every tuned parameter set.
    """

    return DeterministicPreprocessorConfig(
        max_imu_skew_ns=20_000_000,
        max_pending_imu_samples=8,
        accelerometer_correction_gain_per_s=0.5,
        acceleration_trust_tolerance_mps2=1.5,
        minimum_calibration_evidence_count=3,
        minimum_calibration_evidence_confidence=0.45,
        maximum_calibration_disagreement_rad=0.70,
        remount_evidence_count=3,
        minimum_calibration_confidence_for_output=0.60,
        velocity_model_sample_period_ns=100_000_000,
        velocity_model_window_size=50,
        gnss_quality_limits=GnssQualityLimits(
            max_gap_ns=2_500_000_000,
            max_horizontal_accuracy_m=20.0,
            max_speed_accuracy_mps=1.5,
            min_course_speed_mps=2.0,
            max_course_accuracy_rad=radians(15.0),
        ),
        calibration_evidence_limits=CalibrationEvidenceLimits(
            max_imu_gnss_skew_ns=120_000_000,
            min_gnss_interval_ns=800_000_000,
            max_gnss_interval_ns=1_500_000_000,
            min_gnss_longitudinal_acceleration_mps2=0.20,
            min_sensor_linear_acceleration_mps2=0.20,
            max_course_rate_radps=0.35,
        ),
        vehicle_imu_quality_limits=VehicleImuQualityLimits(
            max_gap_ns=250_000_000,
            max_linear_acceleration_mps2=30.0,
            max_angular_velocity_radps=12.0,
            minimum_calibration_confidence=0.60,
        ),
    )


def build_fusion_config(parameters: ReplayParameterSet) -> FusionPipelineConfig:
    """Build one native EKF configuration from a bounded tuning candidate."""

    return FusionPipelineConfig(
        propagation=PropagationConfig(
            noise=ImuNoiseDensity(
                accelerometer_mps2_per_sqrt_hz=(
                    0.12 * parameters.accelerometer_noise_scale
                ),
                gyroscope_radps_per_sqrt_hz=(
                    0.018 * parameters.gyroscope_noise_scale
                ),
                accelerometer_bias_rw_mps2_per_sqrt_s=(
                    0.004 * parameters.bias_random_walk_scale
                ),
                gyroscope_bias_rw_radps_per_sqrt_s=(
                    0.0008 * parameters.bias_random_walk_scale
                ),
            ),
            maximum_delta_time_s=0.25,
        ),
        measurements=FusionMeasurementConfig(
            maximum_gnss_association_age_ns=250_000_000,
            gnss_position_nis_gate=parameters.gnss_position_nis_gate,
            gnss_velocity_nis_gate=parameters.gnss_velocity_nis_gate,
            velocity_model_nis_gate=parameters.velocity_model_nis_gate,
            maximum_velocity_model_association_age_ns=150_000_000,
            recovery_reinitialization_silence_ns=15_000_000_000,
            recovery_required_consecutive_fixes=2,
            recovery_maximum_interfix_distance_m=80.0,
        ),
        non_holonomic_constraint=NonHolonomicConstraintConfig(
            minimum_calibration_confidence=0.60,
            soft_yaw_rate_radps=0.25,
            maximum_yaw_rate_radps=parameters.nhc_maximum_yaw_rate_radps,
            lateral_velocity_std_mps=0.45 * parameters.nhc_lateral_std_scale,
            vertical_velocity_std_mps=0.35 * parameters.nhc_vertical_std_scale,
            nis_gate=9.21,
        ),
        navigation_mode=NavigationModeConfig(
            maximum_accepted_gnss_silence_s=2.5,
            accepted_gnss_updates_for_recovery=2,
        ),
        runtime=NavigationRuntimeConfig(
            maximum_pending_events=32,
            cycle_latency_budget_ms=150.0,
            late_cycles_before_degraded=5,
            trace_history_capacity=512,
        ),
        initial_error_std=(
            8.0,
            8.0,
            12.0,
            3.0,
            3.0,
            2.0,
            0.45,
            0.45,
            0.70,
            0.50,
            0.50,
            0.50,
            0.08,
            0.08,
            0.08,
        ),
    )


def load_raw_replay_journey(raw_directory: Path, journey_id: str) -> RawReplayJourney:
    """Load one paired recording without admitting labels into model inputs.

    Phone and vehicle clocks begin in different representations.  CAN values
    are aligned to phone samples by *relative* elapsed time, exactly as in the
    velocity experiment.  The source's ``GPS SPEED (Kmh)`` label is known to
    be numerically m/s: the existing training experiment verifies this against
    the independent CAN trace, so this data-specific correction is explicit.
    """

    sensor_path = raw_directory / f"S-{journey_id}.csv"
    vehicle_path = raw_directory / f"V-{journey_id}.csv"
    if not sensor_path.is_file() or not vehicle_path.is_file():
        raise FileNotFoundError(f"Missing paired raw recording for {journey_id!r}.")

    sensor = pd.read_csv(sensor_path, encoding="cp1252")
    vehicle = pd.read_csv(vehicle_path, encoding="cp1252")

    sensor_time = _find_column(sensor.columns, "DATE")
    elapsed_ms = _find_column(sensor.columns, "TIME SINCE START")
    acceleration_columns = tuple(
        _find_column(sensor.columns, "ACCELEROMETER", axis)
        for axis in ("X", "Y", "Z")
    )
    # The velocity experiment's established sensor-axis convention is retained:
    # phone roll->vehicle-model gyro x, pitch->y, and yaw->z before dynamic
    # mounting calibration rotates the complete vector into FLU.
    gyroscope_columns = (
        _find_column(sensor.columns, "GYROSCOPE", "Roll"),
        _find_column(sensor.columns, "GYROSCOPE", "Pitch"),
        _find_column(sensor.columns, "GYROSCOPE", "Yaw"),
    )
    latitude = _find_column(sensor.columns, "GPS LATITUDE")
    longitude = _find_column(sensor.columns, "GPS LONGITUDE")
    altitude = _find_column(sensor.columns, "GPS ALTITUDE")
    speed = _find_column(sensor.columns, "GPS SPEED")
    accuracy = _find_column(sensor.columns, "GPS ACCURACY")
    course = _find_column(sensor.columns, "GPS ORIENTATION")

    timestamp = pd.to_datetime(
        sensor[sensor_time], format="%Y-%m-%d %H:%M:%S:%f", errors="coerce"
    )
    phone = pd.DataFrame(
        {
            "timestamp": timestamp,
            "elapsed_ms": pd.to_numeric(sensor[elapsed_ms], errors="coerce"),
            "acceleration_x": pd.to_numeric(sensor[acceleration_columns[0]], errors="coerce"),
            "acceleration_y": pd.to_numeric(sensor[acceleration_columns[1]], errors="coerce"),
            "acceleration_z": pd.to_numeric(sensor[acceleration_columns[2]], errors="coerce"),
            "gyro_x": pd.to_numeric(sensor[gyroscope_columns[0]], errors="coerce"),
            "gyro_y": pd.to_numeric(sensor[gyroscope_columns[1]], errors="coerce"),
            "gyro_z": pd.to_numeric(sensor[gyroscope_columns[2]], errors="coerce"),
            "phone_latitude": pd.to_numeric(sensor[latitude], errors="coerce"),
            "phone_longitude": pd.to_numeric(sensor[longitude], errors="coerce"),
            "phone_altitude": pd.to_numeric(sensor[altitude], errors="coerce"),
            "phone_speed_mps": pd.to_numeric(sensor[speed], errors="coerce"),
            "phone_accuracy": pd.to_numeric(sensor[accuracy], errors="coerce"),
            "phone_course_deg": pd.to_numeric(sensor[course], errors="coerce"),
        }
    )
    # Use the logged elapsed clock when available. It avoids parsing quirks in
    # the dataset's unusual colon-before-millisecond time representation while
    # retaining chronological sensor/GNSS association on a common clock.
    phone = phone.dropna(subset=["elapsed_ms", "timestamp"]).copy()
    phone = phone.sort_values("elapsed_ms").drop_duplicates("elapsed_ms")
    phone["relative_ns"] = (
        (phone["elapsed_ms"] - phone["elapsed_ms"].iloc[0]) * 1e6
    ).round().astype("int64")

    vehicle_time = _find_column(vehicle.columns, "Time Since Start of Day")
    vehicle_speed = _find_column(vehicle.columns, "Indicated Vehicle Speed")
    vehicle_latitude = _find_column(vehicle.columns, "Latitude")
    vehicle_longitude = _find_column(vehicle.columns, "Longitude")
    can = pd.DataFrame(
        {
            "vehicle_elapsed_s": pd.to_numeric(vehicle[vehicle_time], errors="coerce"),
            "reference_speed_kmh": pd.to_numeric(vehicle[vehicle_speed], errors="coerce"),
            "reference_latitude": pd.to_numeric(vehicle[vehicle_latitude], errors="coerce"),
            "reference_longitude": pd.to_numeric(vehicle[vehicle_longitude], errors="coerce"),
        }
    ).dropna()
    can = can.sort_values("vehicle_elapsed_s").drop_duplicates("vehicle_elapsed_s")
    can["relative_ns"] = (
        (can["vehicle_elapsed_s"] - can["vehicle_elapsed_s"].iloc[0]) * 1e9
    ).round().astype("int64")

    aligned = pd.merge_asof(
        phone.sort_values("relative_ns"),
        can[["relative_ns", "reference_speed_kmh", "reference_latitude", "reference_longitude"]],
        on="relative_ns",
        direction="nearest",
        tolerance=75_000_000,
    )
    required = (
        "acceleration_x",
        "acceleration_y",
        "acceleration_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "phone_latitude",
        "phone_longitude",
        "phone_altitude",
        "phone_speed_mps",
        "phone_accuracy",
        "phone_course_deg",
        "reference_speed_kmh",
        "reference_latitude",
        "reference_longitude",
    )
    aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    if len(aligned) < 2:
        raise ValueError(f"{journey_id} has no usable aligned raw/CAN samples.")

    return RawReplayJourney(
        journey_id=journey_id,
        timestamps_ns=aligned["relative_ns"].to_numpy(dtype=np.int64),
        acceleration_sensor_mps2=aligned[
            ["acceleration_x", "acceleration_y", "acceleration_z"]
        ].to_numpy(dtype=float),
        angular_velocity_sensor_radps=aligned[
            ["gyro_x", "gyro_y", "gyro_z"]
        ].to_numpy(dtype=float),
        phone_latitude_deg=aligned["phone_latitude"].to_numpy(dtype=float),
        phone_longitude_deg=aligned["phone_longitude"].to_numpy(dtype=float),
        phone_altitude_m=aligned["phone_altitude"].to_numpy(dtype=float),
        phone_speed_mps=aligned["phone_speed_mps"].to_numpy(dtype=float),
        phone_horizontal_accuracy_m=aligned["phone_accuracy"].to_numpy(dtype=float),
        phone_course_rad=np.deg2rad(aligned["phone_course_deg"].to_numpy(dtype=float)),
        reference_latitude_deg=aligned["reference_latitude"].to_numpy(dtype=float),
        reference_longitude_deg=aligned["reference_longitude"].to_numpy(dtype=float),
        reference_speed_mps=(
            aligned["reference_speed_kmh"].to_numpy(dtype=float) / 3.6
        ),
    )


def replay_journey(
    *,
    journey: RawReplayJourney,
    scenario: BlackoutScenario,
    parameters: ReplayParameterSet,
    velocity_artifact_directory: Path,
    uncertainty_artifact_directory: Path,
    maximum_replay_duration_s: float | None = None,
    velocity_model_family: Literal[
        "anchor_delta_gru", "stateful_anchor_delta_gru"
    ] = "anchor_delta_gru",
    uncertainty_profile_filename: str = "anchor_delta_gru_deterministic_uncertainty.json",
) -> ReplayReport:
    """Replay raw callbacks through native preprocessing, ONNX, UQ, and EKF.

    All events remain causal.  At a given timestamp, the scheduled phone GNSS
    fix is queued first, then the accelerometer and gyroscope callbacks are
    submitted.  This mirrors a receiver observation being available to the
    immediately following synchronized IMU cycle without applying an
    out-of-sequence measurement.
    """

    if journey.duration_s < scenario.minimum_duration_s:
        raise ValueError(
            f"{journey.journey_id} is {journey.duration_s:.1f}s long; "
            f"the scenario requires {scenario.minimum_duration_s:.1f}s."
        )

    preprocessor = DeterministicImuPreprocessor(default_preprocessor_config())
    pre_ekf = build_selected_velocity_pre_ekf_pipeline(
        config=DeterministicPipelineConfig(
            maximum_gnss_anchor_age_ns=120 * _NS_PER_SECOND
        ),
        preprocessor=preprocessor,
        artifacts=SelectedVelocityRuntimeArtifacts(
            velocity_artifact_directory=velocity_artifact_directory,
            uncertainty_artifact_directory=uncertainty_artifact_directory,
            uncertainty_profile_filename=uncertainty_profile_filename,
            model_family=velocity_model_family,
        ),
    )
    pipeline = NavigationFusionPipeline(
        pre_ekf_pipeline=pre_ekf,
        config=build_fusion_config(parameters),
    )

    # A final independent replay uses the complete recording. Development
    # tuning may bound each episode at the recovery horizon so long trips do
    # not dominate both compute and selection weighting.
    included_indices = (
        np.arange(len(journey.timestamps_ns))
        if maximum_replay_duration_s is None
        else np.flatnonzero(
            journey.timestamps_ns
            <= int(maximum_replay_duration_s * _NS_PER_SECOND)
        )
    )
    if len(included_indices) < 2:
        raise ValueError("Scenario contains no raw samples after timestamp clipping.")

    local_reference: LocalEnuReference | None = None
    initial_reference_position: np.ndarray | None = None
    blackout_reference_position: np.ndarray | None = None
    blackout_estimated_position: np.ndarray | None = None
    blackout_relative_position_errors: list[float] = []
    blackout_last_scored_elapsed_s: float | None = None
    blackout_speed_errors: list[float] = []
    one_sigma_hits: list[bool] = []
    two_sigma_hits: list[bool] = []
    callback_latencies_ms: list[float] = []
    synchronized_samples = 0
    accepted_preprocessing_samples = 0
    calibration_available_samples = 0
    preprocessing_disposition_counts: dict[str, int] = {}
    final_calibration_phase = "warming_up"
    final_calibration_confidence: float | None = None
    velocity_observations = 0
    native_propagations = 0
    timing_gap_recoveries = 0
    trace_counts = _TraceCounts()
    last_gnss_timestamp_ns: int | None = None
    first_recovery_gnss_acceptance_s: float | None = None
    gnss_aided_recovery_s: float | None = None
    notes: list[str] = []

    for index in included_indices:
        timestamp_ns = int(journey.timestamps_ns[index])
        elapsed_s = timestamp_ns * 1e-9
        gnss_is_available = not (
            scenario.blackout_start_s < elapsed_s < scenario.blackout_end_s
        )
        if gnss_is_available and _should_emit_gnss(timestamp_ns, last_gnss_timestamp_ns):
            gnss_fix = _phone_gnss_fix(journey, int(index))
            pipeline.push_gnss_fix(gnss_fix)
            last_gnss_timestamp_ns = timestamp_ns
            if local_reference is None:
                local_reference = LocalEnuReference.from_gnss_fix(gnss_fix)
                initial_reference_position = _project_reference_position(
                    local_reference, journey, int(index)
                )

        acceleration = RawSensorSample(
            timestamp_ns=timestamp_ns,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            kind=SensorKind.ACCELEROMETER,
            value=tuple(float(value) for value in journey.acceleration_sensor_mps2[index]),
            unit=MeasurementUnit.METERS_PER_SECOND_SQUARED,
            frame=CoordinateFrame.SENSOR,
        )
        gyroscope = RawSensorSample(
            timestamp_ns=timestamp_ns,
            source=SensorSource.PHONE,
            source_id="phone-primary",
            kind=SensorKind.GYROSCOPE,
            value=tuple(float(value) for value in journey.angular_velocity_sensor_radps[index]),
            unit=MeasurementUnit.RADIANS_PER_SECOND,
            frame=CoordinateFrame.SENSOR,
        )

        started_ns = perf_counter_ns()
        pipeline.push_raw_sample(acceleration)
        results = pipeline.push_raw_sample(gyroscope)
        callback_latencies_ms.append((perf_counter_ns() - started_ns) / 1e6)

        for result in results:
            synchronized_samples += 1
            disposition = result.pre_ekf.preprocessing.disposition.value
            preprocessing_disposition_counts[disposition] = (
                preprocessing_disposition_counts.get(disposition, 0) + 1
            )
            final_calibration_phase = result.pre_ekf.preprocessing.calibration_phase.value
            calibration = result.pre_ekf.preprocessing.calibration
            if calibration is not None:
                calibration_available_samples += 1
                final_calibration_confidence = calibration.confidence
            if result.pre_ekf.preprocessing.quality is not None and (
                result.pre_ekf.preprocessing.quality.is_acceptable
            ):
                accepted_preprocessing_samples += 1
            velocity_observations += len(result.pre_ekf.velocity_observations)
            if result.propagation_disposition is PropagationDisposition.PROPAGATED:
                native_propagations += 1
            elif (
                result.propagation_disposition
                is PropagationDisposition.TIMING_GAP_REQUIRES_RECOVERY
            ):
                timing_gap_recoveries += 1

            _count_measurement_traces(trace_counts, result.measurement_traces)
            estimate = result.navigation_estimate
            # Rejected preprocessing returns the most recently *published*
            # estimate. It is useful to callers, but it must not be counted as
            # a new replay point or make a stalled filter look like it survived
            # an outage. Only score a state committed at this exact IMU time.
            if (
                estimate is None
                or local_reference is None
                or result.runtime_snapshot.last_cycle_timestamp_ns
                != result.pre_ekf.preprocessing.timestamp_ns
            ):
                continue

            reference_position = _project_reference_position(
                local_reference, journey, int(index)
            )
            if elapsed_s >= scenario.blackout_start_s and blackout_reference_position is None:
                blackout_reference_position = reference_position
                blackout_estimated_position = np.asarray(estimate.position_enu_m, dtype=float)

            if scenario.blackout_start_s <= elapsed_s <= scenario.blackout_end_s:
                blackout_last_scored_elapsed_s = elapsed_s
                if (
                    blackout_reference_position is not None
                    and blackout_estimated_position is not None
                ):
                    estimated_displacement = (
                        np.asarray(estimate.position_enu_m, dtype=float)
                        - blackout_estimated_position
                    )
                    reference_displacement = (
                        reference_position - blackout_reference_position
                    )
                    blackout_relative_position_errors.append(
                        float(
                            np.linalg.norm(
                                (estimated_displacement - reference_displacement)[:2]
                            )
                        )
                    )
                reference_speed = float(journey.reference_speed_mps[index])
                estimated_speed = float(
                    np.linalg.norm(np.asarray(estimate.velocity_enu_mps, dtype=float)[:2])
                )
                blackout_speed_errors.append(abs(estimated_speed - reference_speed))

                for observation, uncertainty in zip(
                    result.pre_ekf.velocity_observations,
                    result.pre_ekf.uncertainty_estimates,
                    strict=True,
                ):
                    residual = abs(observation.speed_mps - reference_speed)
                    standard_deviation = float(
                        np.sqrt(uncertainty.speed_variance_m2ps2)
                    )
                    one_sigma_hits.append(residual <= standard_deviation)
                    two_sigma_hits.append(residual <= 2.0 * standard_deviation)

            if elapsed_s >= scenario.blackout_end_s:
                if (
                    first_recovery_gnss_acceptance_s is None
                    and _gnss_position_accepted(result.measurement_traces)
                ):
                    first_recovery_gnss_acceptance_s = elapsed_s - scenario.blackout_end_s
                if estimate.mode.value == "gnss_aided" and gnss_aided_recovery_s is None:
                    gnss_aided_recovery_s = elapsed_s - scenario.blackout_end_s

    pipeline.stop()
    if initial_reference_position is None:
        notes.append("No accepted phone GNSS origin was available for trajectory scoring.")
    if accepted_preprocessing_samples == 0:
        notes.append("The real deterministic preprocessor emitted no quality-accepted samples.")
    if velocity_observations == 0:
        notes.append("No selected-GRU windows were produced from the real preprocessor.")
    if native_propagations == 0:
        notes.append("The native EKF never propagated; replay cannot support tuning.")
    if not blackout_relative_position_errors:
        notes.append("No initialized EKF samples occurred during the requested blackout.")
    elif (
        blackout_last_scored_elapsed_s is None
        or blackout_last_scored_elapsed_s < scenario.blackout_end_s - 1.0
    ):
        notes.append("EKF propagation did not cover the full requested GNSS blackout.")
    if first_recovery_gnss_acceptance_s is None:
        notes.append("No GNSS position measurement was accepted after blackout recovery.")
    if gnss_aided_recovery_s is None:
        notes.append("Navigation mode did not return to GNSS_AIDED after recovery.")

    valid = not notes
    return ReplayReport(
        journey_id=journey.journey_id,
        scenario=scenario,
        parameters=parameters,
        recording_duration_s=journey.duration_s,
        raw_samples=len(included_indices),
        synchronized_samples=synchronized_samples,
        accepted_preprocessing_samples=accepted_preprocessing_samples,
        calibration_available_samples=calibration_available_samples,
        final_calibration_phase=final_calibration_phase,
        final_calibration_confidence=final_calibration_confidence,
        preprocessing_disposition_counts=preprocessing_disposition_counts,
        velocity_observations=velocity_observations,
        native_propagation_steps=native_propagations,
        timing_gap_recoveries=timing_gap_recoveries,
        blackout_position_samples=len(blackout_relative_position_errors),
        blackout_last_scored_elapsed_s=blackout_last_scored_elapsed_s,
        blackout_mean_relative_position_error_m=_mean_or_none(
            blackout_relative_position_errors
        ),
        blackout_p95_relative_position_error_m=_percentile_or_none(
            blackout_relative_position_errors, 95.0
        ),
        blackout_endpoint_relative_position_error_m=(
            None
            if not blackout_relative_position_errors
            else float(blackout_relative_position_errors[-1])
        ),
        blackout_velocity_mae_mps=_mean_or_none(blackout_speed_errors),
        blackout_velocity_mae_kmh=_scaled_mean_or_none(blackout_speed_errors, 3.6),
        velocity_uncertainty_one_sigma_coverage=_mean_or_none(one_sigma_hits),
        velocity_uncertainty_two_sigma_coverage=_mean_or_none(two_sigma_hits),
        gnss_position_accepted=trace_counts.gnss_position_accepted,
        gnss_position_rejected=trace_counts.gnss_position_rejected,
        gnss_velocity_accepted=trace_counts.gnss_velocity_accepted,
        gnss_velocity_rejected=trace_counts.gnss_velocity_rejected,
        velocity_model_accepted=trace_counts.velocity_model_accepted,
        velocity_model_rejected=trace_counts.velocity_model_rejected,
        nhc_accepted=trace_counts.nhc_accepted,
        nhc_rejected=trace_counts.nhc_rejected,
        first_recovery_gnss_acceptance_s=first_recovery_gnss_acceptance_s,
        gnss_aided_recovery_s=gnss_aided_recovery_s,
        raw_callback_latency_median_ms=_percentile_or_none(callback_latencies_ms, 50.0),
        raw_callback_latency_p95_ms=_percentile_or_none(callback_latencies_ms, 95.0),
        final_runtime_phase=pipeline.runtime_snapshot.phase.value,
        valid_for_scoring=valid,
        scoring_notes=tuple(notes),
    )


@dataclass(slots=True)
class _TraceCounts:
    """Mutable private counter for accepted and innovation-rejected updates."""

    gnss_position_accepted: int = 0
    gnss_position_rejected: int = 0
    gnss_velocity_accepted: int = 0
    gnss_velocity_rejected: int = 0
    velocity_model_accepted: int = 0
    velocity_model_rejected: int = 0
    nhc_accepted: int = 0
    nhc_rejected: int = 0


def _find_column(columns: Iterable[str], *required_fragments: str) -> str:
    """Find one legacy CSV header despite spacing or encoding oddities."""

    matches = [
        column
        for column in columns
        if all(fragment.casefold() in column.casefold() for fragment in required_fragments)
    ]
    if len(matches) != 1:
        raise KeyError(
            f"Expected one column containing {required_fragments}; found {matches}."
        )
    return matches[0]


def _should_emit_gnss(timestamp_ns: int, last_timestamp_ns: int | None) -> bool:
    """Downsample the duplicated logged GNSS fields to a realistic 1 Hz feed."""

    return last_timestamp_ns is None or timestamp_ns - last_timestamp_ns >= _PHONE_GNSS_PERIOD_NS


def _phone_gnss_fix(journey: RawReplayJourney, index: int) -> GnssFix:
    """Create one clearly documented phone-receiver fix from a raw row."""

    return GnssFix(
        timestamp_ns=int(journey.timestamps_ns[index]),
        receiver_id="phone-primary",
        latitude_deg=float(journey.phone_latitude_deg[index]),
        longitude_deg=float(journey.phone_longitude_deg[index]),
        altitude_m=float(journey.phone_altitude_m[index]),
        horizontal_accuracy_m=float(journey.phone_horizontal_accuracy_m[index]),
        vertical_accuracy_m=None,
        speed_mps=float(journey.phone_speed_mps[index]),
        # Not present in the public source. These are fixed conservative
        # replay assumptions, declared in default_preprocessor_config().
        speed_accuracy_mps=1.5,
        course_over_ground_rad=float(journey.phone_course_rad[index]),
        course_accuracy_rad=radians(15.0),
    )


def _project_reference_position(
    reference: LocalEnuReference,
    journey: RawReplayJourney,
    index: int,
) -> np.ndarray:
    """Project CAN/GNSS reference geometry without exposing it to the filter."""

    reference_fix = GnssFix(
        timestamp_ns=int(journey.timestamps_ns[index]),
        receiver_id="offline-reference-only",
        latitude_deg=float(journey.reference_latitude_deg[index]),
        longitude_deg=float(journey.reference_longitude_deg[index]),
        altitude_m=None,
        horizontal_accuracy_m=1.0,
        vertical_accuracy_m=None,
    )
    return reference.project(reference_fix)


def _count_measurement_traces(counts: _TraceCounts, traces: Iterable[object]) -> None:
    """Record accepted/rejected traces while leaving timestamp misses visible."""

    for trace in traces:
        kind = getattr(trace.kind, "value", str(trace.kind))
        accepted = getattr(trace.disposition, "value", str(trace.disposition)) == "accepted"
        if kind == "gnss_position":
            counts.gnss_position_accepted += int(accepted)
            counts.gnss_position_rejected += int(not accepted)
        elif kind == "gnss_velocity":
            counts.gnss_velocity_accepted += int(accepted)
            counts.gnss_velocity_rejected += int(not accepted)
        elif kind == "velocity_model":
            counts.velocity_model_accepted += int(accepted)
            counts.velocity_model_rejected += int(not accepted)
        elif kind == "non_holonomic_constraint":
            counts.nhc_accepted += int(accepted)
            counts.nhc_rejected += int(not accepted)


def _gnss_position_accepted(traces: Iterable[object]) -> bool:
    """Return whether a result admitted a GNSS position correction."""

    return any(
        getattr(trace.kind, "value", str(trace.kind)) == "gnss_position"
        and getattr(trace.disposition, "value", str(trace.disposition)) == "accepted"
        for trace in traces
    )


def _mean_or_none(values: Iterable[float | bool]) -> float | None:
    """Return a finite mean only when the replay produced observations."""

    array = np.asarray(tuple(values), dtype=float)
    return None if len(array) == 0 else float(np.mean(array))


def _scaled_mean_or_none(values: Iterable[float], scale: float) -> float | None:
    """Return a unit-converted mean without conflating missing with zero."""

    mean = _mean_or_none(values)
    return None if mean is None else mean * scale


def _percentile_or_none(values: Iterable[float], percentile: float) -> float | None:
    """Return one percentile only when a replay produced observations."""

    array = np.asarray(tuple(values), dtype=float)
    return None if len(array) == 0 else float(np.percentile(array, percentile))

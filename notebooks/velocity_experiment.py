"""Reusable machinery for the velocity-retraining notebook.

This module is intentionally experiment-local rather than part of the stable
``idr_backend`` API.  It connects the repository's deterministic sensor
pipeline to leakage-safe blackout experiments, but it does not define the
runtime velocity-predictor contract yet.

The central modelling idea is simple: IMU data describes *changes* in motion
much better than it describes absolute road speed.  Every training example
therefore starts with the last trustworthy GNSS speed, integrates cleaned
forward acceleration, and asks a model to correct the remaining integration
error.  CAN-bus speed is used only as the supervised target.
"""

from __future__ import annotations

import copy
import itertools
import random
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, ParameterGrid, ParameterSampler
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from idr_backend.sensors.calibration import (
    CalibrationEvidence,
    DynamicVehicleCalibrator,
    derive_sensor_to_vehicle_quaternion,
    rotate_imu_to_vehicle,
)
from idr_backend.sensors.gravity_removal import remove_gravity_from_vehicle_imu
from idr_backend.sensors.normalization import normalize_raw_sample
from idr_backend.sensors.orientation import ImuOrientationEstimator, normalize_vector
from idr_backend.sensors.quality import VehicleImuQualityLimits, VehicleImuQualityMonitor
from idr_backend.sensors.resampling import FixedRateVehicleImuResampler
from idr_backend.sensors.synchronization import synchronize_pair
from idr_backend.sensors.types import (
    CoordinateFrame,
    MeasurementUnit,
    RawSensorSample,
    SensorKind,
    SensorSource,
    VehicleCalibration,
)
from idr_backend.sensors.windowing import VELOCITY_MODEL_FEATURE_NAMES, vehicle_imu_feature_row


GRAVITY_MPS2 = 9.80665
RAW_FEATURE_NAMES = (
    "raw_acceleration_x_mps2",
    "raw_acceleration_y_mps2",
    "raw_acceleration_z_mps2",
    "raw_angular_velocity_x_radps",
    "raw_angular_velocity_y_radps",
    "raw_angular_velocity_z_radps",
)
CONTEXT_FEATURE_NAMES = (
    "anchor_speed_mps",
    "integrated_speed_mps",
    "seconds_since_anchor",
    "mean_calibration_confidence",
    "minimum_calibration_confidence",
)


def _integrate_trapezoid(values: np.ndarray, *, dx: float) -> float:
    """Integrate a one-dimensional signal without NumPy-version-specific APIs."""

    samples = np.asarray(values, dtype=float)
    if samples.ndim != 1:
        raise ValueError("Trapezoidal integration expects one-dimensional data.")
    if not np.isfinite(dx) or dx <= 0.0:
        raise ValueError("dx must be finite and positive.")
    if len(samples) < 2:
        return 0.0

    return float(
        dx
        * (
            0.5 * samples[0]
            + samples[1:-1].sum()
            + 0.5 * samples[-1]
        )
    )


@dataclass(frozen=True)
class ExperimentConfig:
    """All choices that affect examples, folds, training, or timing.

    ``search_profile`` is deliberately explicit.  ``full`` performs the
    requested 20-sample neural searches and complete 108-point RF grid.
    ``smoke`` is only for checking that every cell and data path works.
    """

    sample_period_ns: int = 100_000_000
    window_size: int = 50
    calibration_history_s: float = 30.0
    calibration_update_every_samples: int = 10
    minimum_calibration_samples: int = 5
    minimum_calibration_confidence: float = 0.60
    label_alignment_tolerance_ms: float = 75.0
    max_gap_ns: int = 250_000_000
    max_linear_acceleration_mps2: float = 30.0
    max_angular_velocity_radps: float = 12.0

    blackout_horizons_s: tuple[int, ...] = (5, 10, 20, 30, 60, 90, 120)
    anchor_stride_s: int = 10
    test_fraction: float = 0.15
    cv_folds: int = 5
    seed: int = 42

    batch_size: int = 128
    maximum_epochs: int = 200
    early_stopping_patience: int = 20
    weight_decay: float = 1e-4
    huber_beta_mps: float = 1.0
    neural_candidates_per_family: int = 20
    inference_warmup_calls: int = 30
    inference_measurement_calls: int = 200
    search_profile: str = "full"

    def __post_init__(self) -> None:
        if self.search_profile not in {"full", "smoke"}:
            raise ValueError("search_profile must be 'full' or 'smoke'.")
        if self.window_size <= 1 or self.sample_period_ns <= 0:
            raise ValueError("Window size and sample period must be positive.")
        if self.cv_folds < 2:
            raise ValueError("At least two grouped CV folds are required.")
        if not 0.0 < self.test_fraction < 1.0:
            raise ValueError("test_fraction must lie between zero and one.")

    @property
    def sample_period_s(self) -> float:
        return self.sample_period_ns * 1e-9


@dataclass(frozen=True)
class ProcessedJourney:
    """One recording after deterministic preprocessing and fixed-rate sampling."""

    journey_id: str
    timestamps_ns: np.ndarray
    segment_ids: np.ndarray
    raw_imu: np.ndarray
    vehicle_imu_before_gravity_removal: np.ndarray
    clean_imu: np.ndarray
    gps_speed_mps: np.ndarray
    target_speed_mps: np.ndarray
    calibration_confidence: np.ndarray
    audit: dict[str, int | float | str]


@dataclass(frozen=True)
class BlackoutDataset:
    """Independent prediction examples built from journey-contained outages.

    Windows can overlap inside one journey, which is expected.  Grouped
    splitting later guarantees that all overlapping relatives stay together.
    """

    clean_windows: np.ndarray
    raw_windows: np.ndarray
    context: np.ndarray
    target_speed_mps: np.ndarray
    residual_target_mps: np.ndarray
    journey_ids: np.ndarray
    anchor_timestamps_ns: np.ndarray
    end_timestamps_ns: np.ndarray
    horizons_s: np.ndarray

    def __len__(self) -> int:
        return len(self.target_speed_mps)


def anchor_delta_target(dataset: BlackoutDataset) -> np.ndarray:
    """Return the speed change to learn from the trustworthy outage anchor.

    The prior experiment learned a correction to a long acceleration integral.
    That makes a neural model spend most of its capacity undoing deterministic
    drift when forward calibration is imperfect.  Learning delta-v from the
    anchor keeps the output in the same physical units while allowing the
    integral to remain a useful *input feature*, not a forced base estimate.
    """

    return dataset.target_speed_mps - dataset.context[:, 0]


@dataclass(frozen=True)
class FoldScalers:
    """Training-only transformations used by one model fold."""

    sequence: StandardScaler
    context: StandardScaler | None


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy, and PyTorch for repeatable candidate comparisons."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def find_column(columns: Iterable[str], *required_fragments: str) -> str:
    """Find one source column without hard-coding mojibake-prone CSV headers."""

    matches = [
        column
        for column in columns
        if all(fragment.casefold() in column.casefold() for fragment in required_fragments)
    ]
    if len(matches) != 1:
        raise KeyError(f"Expected one column containing {required_fragments}; found {matches}")
    return matches[0]


def paired_paths(raw_dir: Path) -> list[tuple[str, Path, Path]]:
    """Return only complete phone/vehicle recording pairs."""

    pairs: list[tuple[str, Path, Path]] = []
    for sensor_path in sorted(raw_dir.glob("S-*.csv")):
        vehicle_path = raw_dir / f"V-{sensor_path.name[2:]}"
        if vehicle_path.exists():
            pairs.append((sensor_path.stem[2:], sensor_path, vehicle_path))
    if not pairs:
        raise RuntimeError(f"No S-/V- pairs found under {raw_dir}")
    return pairs


def read_aligned_journey(
    journey_id: str,
    sensor_path: Path,
    vehicle_path: Path,
    config: ExperimentConfig,
) -> pd.DataFrame:
    """Read one pair and align CAN labels to phone samples by relative time.

    The clocks begin from different representations, so matching absolute clock
    values would be unsafe.  ``merge_asof`` instead aligns elapsed recording
    time and rejects a CAN label farther than the configured tolerance.
    """

    sensor = pd.read_csv(sensor_path, encoding="cp1252")
    vehicle = pd.read_csv(vehicle_path, encoding="cp1252")

    date = find_column(sensor.columns, "DATE")
    acc_x, acc_y, acc_z = (
        find_column(sensor.columns, "ACCELEROMETER", axis) for axis in ("X", "Y", "Z")
    )
    gyro_x = find_column(sensor.columns, "GYROSCOPE", "Roll")
    gyro_y = find_column(sensor.columns, "GYROSCOPE", "Pitch")
    gyro_z = find_column(sensor.columns, "GYROSCOPE", "Yaw")
    gps_speed = find_column(sensor.columns, "GPS SPEED")
    target_time = find_column(vehicle.columns, "Time Since Start of Day")
    target_speed = find_column(vehicle.columns, "Indicated Vehicle Speed")

    sensor_time = pd.to_datetime(
        sensor[date], format="%Y-%m-%d %H:%M:%S:%f", errors="coerce"
    )
    phone = pd.DataFrame(
        {
            "timestamp": sensor_time,
            "acc_x": pd.to_numeric(sensor[acc_x], errors="coerce"),
            "acc_y": pd.to_numeric(sensor[acc_y], errors="coerce"),
            "acc_z": pd.to_numeric(sensor[acc_z], errors="coerce"),
            "gyro_x": pd.to_numeric(sensor[gyro_x], errors="coerce"),
            "gyro_y": pd.to_numeric(sensor[gyro_y], errors="coerce"),
            "gyro_z": pd.to_numeric(sensor[gyro_z], errors="coerce"),
            # The source header says Kmh, but its numerical values match m/s:
            # multiplying by 3.6 aligns them with the independent CAN km/h
            # trace on the large, strongly correlated journeys. Preserve a
            # neutral name here and make the dataset-specific correction below.
            "gps_speed_file_value": pd.to_numeric(sensor[gps_speed], errors="coerce"),
        }
    ).dropna(subset=["timestamp"]).sort_values("timestamp").drop_duplicates("timestamp")
    phone["relative_ns"] = (
        (phone["timestamp"] - phone["timestamp"].iloc[0])
        .dt.total_seconds().mul(1e9).round().astype("int64")
    )

    can = pd.DataFrame(
        {
            "vehicle_relative_s": pd.to_numeric(vehicle[target_time], errors="coerce"),
            "target_speed_kmh": pd.to_numeric(vehicle[target_speed], errors="coerce"),
        }
    ).dropna().sort_values("vehicle_relative_s")
    can["relative_ns"] = (
        (can["vehicle_relative_s"] - can["vehicle_relative_s"].iloc[0])
        .mul(1e9).round().astype("int64")
    )
    can = can.drop_duplicates("relative_ns")[["relative_ns", "target_speed_kmh"]]

    aligned = pd.merge_asof(
        phone.sort_values("relative_ns"),
        can,
        on="relative_ns",
        direction="nearest",
        tolerance=int(config.label_alignment_tolerance_ms * 1e6),
    )
    numeric = [
        "acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z",
        "gps_speed_file_value", "target_speed_kmh",
    ]
    aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna(subset=numeric).copy()
    aligned["timestamp_ns"] = aligned["timestamp"].astype("int64")
    aligned["gps_speed_mps"] = aligned["gps_speed_file_value"]
    aligned["gps_speed_kmh"] = aligned["gps_speed_file_value"] * 3.6
    aligned["target_speed_mps"] = aligned["target_speed_kmh"] / 3.6
    aligned["journey_id"] = journey_id
    return aligned.reset_index(drop=True)


def rolling_calibration_evidence(
    history: deque[tuple[float, ...]],
    source_id: str,
    config: ExperimentConfig,
) -> CalibrationEvidence | None:
    """Infer mounting axes from past-only quiet and accelerating observations.

    Gravity supplies the vehicle-up candidate.  Correlation between phone-GPS
    speed change and gravity-compensated acceleration supplies signed forward.
    CAN speed is deliberately absent, so the feature pipeline cannot learn from
    its target while preparing inputs.
    """

    if len(history) < config.minimum_calibration_samples:
        return None
    timestamps_ns = np.fromiter((int(item[0]) for item in history), dtype=np.int64)
    values = np.asarray([item[1:] for item in history], dtype=float)
    acceleration, gyro, gps_speed_mps = values[:, :3], values[:, 3:6], values[:, 6]
    acceleration_norm = np.linalg.norm(acceleration, axis=1)
    gyro_norm = np.linalg.norm(gyro, axis=1)
    quiet = (np.abs(acceleration_norm - GRAVITY_MPS2) <= 2.0) & (gyro_norm <= 1.5)
    if int(quiet.sum()) < config.minimum_calibration_samples:
        return None

    vehicle_up_in_sensor = normalize_vector(tuple(np.median(acceleration[quiet], axis=0)))
    time_s = (timestamps_ns - timestamps_ns[0]) * 1e-9
    if not np.all(np.diff(time_s) > 0.0):
        return None

    # Phone GPS speed is a low-rate, staircase-like observation. Taking a raw
    # 100 ms derivative makes the forward-axis estimate chase GPS quantisation
    # noise instead of real acceleration.  Smooth it causally over 1.5 seconds
    # and use a one-second backward difference; each value still depends only
    # on readings available at this evidence timestamp.
    smooth_window = max(3, round(1.5 / config.sample_period_s))
    cumulative = np.concatenate(([0.0], np.cumsum(gps_speed_mps)))
    positions = np.arange(len(gps_speed_mps))
    starts = np.maximum(0, positions - smooth_window + 1)
    counts = positions - starts + 1
    smoothed_speed = (cumulative[positions + 1] - cumulative[starts]) / counts
    derivative_steps = max(1, round(1.0 / config.sample_period_s))
    longitudinal_acceleration = np.full(len(smoothed_speed), np.nan)
    elapsed = time_s[derivative_steps:] - time_s[:-derivative_steps]
    longitudinal_acceleration[derivative_steps:] = (
        smoothed_speed[derivative_steps:] - smoothed_speed[:-derivative_steps]
    ) / elapsed
    linear_sensor = acceleration - GRAVITY_MPS2 * np.asarray(vehicle_up_in_sensor)

    # GPS speed commonly arrives after the physical acceleration it describes.
    # Search a small, fully past-only delay range and retain the direction with
    # strongest centred correlation.  Centering removes static accelerometer
    # bias, leaving changes that actually identify vehicle forward.
    best_vector: np.ndarray | None = None
    best_score = 0.0
    maximum_delay_steps = round(2.0 / config.sample_period_s)
    for delay_steps in range(maximum_delay_steps + 1):
        if delay_steps:
            sensor_values = linear_sensor[:-delay_steps]
            gps_acceleration = longitudinal_acceleration[delay_steps:]
            candidate_gyro = gyro_norm[:-delay_steps]
        else:
            sensor_values = linear_sensor
            gps_acceleration = longitudinal_acceleration
            candidate_gyro = gyro_norm
        useful = (
            np.isfinite(gps_acceleration)
            & (np.abs(gps_acceleration) >= 0.15)
            & (np.abs(gps_acceleration) <= 5.0)
            & (candidate_gyro <= 1.5)
        )
        if int(useful.sum()) < config.minimum_calibration_samples:
            continue
        centred_sensor = sensor_values[useful] - np.median(sensor_values[useful], axis=0)
        centred_acceleration = gps_acceleration[useful] - np.median(gps_acceleration[useful])
        candidate_vector = centred_sensor.T @ centred_acceleration
        denominator = np.sqrt(
            np.sum(centred_sensor**2) * np.sum(centred_acceleration**2)
        )
        score = float(np.linalg.norm(candidate_vector) / max(denominator, 1e-12))
        if score > best_score:
            best_vector, best_score = candidate_vector, score
    if best_vector is None or best_score < 0.20:
        return None
    try:
        vehicle_forward_in_sensor = normalize_vector(tuple(best_vector))
        derive_sensor_to_vehicle_quaternion(vehicle_up_in_sensor, vehicle_forward_in_sensor)
    except ValueError:
        return None

    # A correlation score at the acceptance boundary maps to the calibrator's
    # minimum confidence. Strong, repeated evidence can approach one.
    confidence = min(1.0, 0.5 + 0.5 * best_score)
    return CalibrationEvidence(
        int(timestamps_ns[-1]),
        SensorSource.PHONE,
        source_id,
        vehicle_up_in_sensor,
        vehicle_forward_in_sensor,
        confidence,
    )


def _interpolate_columns(
    source_timestamps_ns: np.ndarray,
    source_values: np.ndarray,
    requested_timestamps_ns: np.ndarray,
) -> np.ndarray:
    """Interpolate columns using relative seconds to preserve timestamp precision."""

    origin = int(source_timestamps_ns[0])
    source_s = (source_timestamps_ns.astype(np.int64) - origin) * 1e-9
    requested_s = (requested_timestamps_ns.astype(np.int64) - origin) * 1e-9
    return np.column_stack(
        [np.interp(requested_s, source_s, source_values[:, column]) for column in range(source_values.shape[1])]
    )


def replay_clean_journey(frame: pd.DataFrame, config: ExperimentConfig) -> ProcessedJourney:
    """Replay one recording through the real deterministic sensor pipeline.

    The returned audit attributes every dropped input row to a stage.  This is
    important because an apparently accurate model trained on a tiny surviving
    subset can fail badly when it sees the full variety of a new journey.
    """

    journey_id = str(frame.journey_id.iloc[0])
    source_id = f"dataset-phone-{journey_id}"
    orientation = ImuOrientationEstimator(
        accelerometer_correction_gain_per_s=0.5,
        acceleration_trust_tolerance_mps2=1.5,
    )
    quality_monitor = VehicleImuQualityMonitor(
        VehicleImuQualityLimits(
            config.max_gap_ns,
            config.max_linear_acceleration_mps2,
            config.max_angular_velocity_radps,
            config.minimum_calibration_confidence,
        )
    )
    resampler = FixedRateVehicleImuResampler(config.sample_period_ns)
    calibrator = DynamicVehicleCalibrator(
        minimum_evidence_count=3,
        minimum_evidence_confidence=config.minimum_calibration_confidence,
        maximum_disagreement_rad=0.70,
        remount_evidence_count=3,
    )
    history: deque[tuple[float, ...]] = deque(
        maxlen=max(2, round(config.calibration_history_s / config.sample_period_s))
    )
    last_trusted_calibration: VehicleCalibration | None = None

    output_timestamps: list[int] = []
    clean_rows: list[tuple[float, ...]] = []
    confidences: list[float] = []
    vehicle_timestamps: list[int] = []
    vehicle_rows: list[tuple[float, ...]] = []
    stage_counts: Counter[str] = Counter()

    for sample_number, row in enumerate(frame.itertuples(index=False), start=1):
        stage_counts["source_rows"] += 1
        raw_acceleration = RawSensorSample(
            int(row.timestamp_ns), SensorSource.PHONE, source_id,
            SensorKind.ACCELEROMETER,
            (float(row.acc_x), float(row.acc_y), float(row.acc_z)),
            MeasurementUnit.METERS_PER_SECOND_SQUARED, CoordinateFrame.SENSOR,
        )
        raw_gyro = RawSensorSample(
            int(row.timestamp_ns), SensorSource.PHONE, source_id,
            SensorKind.GYROSCOPE,
            (float(row.gyro_x), float(row.gyro_y), float(row.gyro_z)),
            MeasurementUnit.RADIANS_PER_SECOND, CoordinateFrame.SENSOR,
        )
        synchronized = synchronize_pair(
            normalize_raw_sample(raw_acceleration), normalize_raw_sample(raw_gyro), max_skew_ns=0
        )
        stage_counts["normalized_and_synchronized"] += 1
        orientation_estimate = orientation.update(synchronized)
        history.append(
            (
                int(row.timestamp_ns), float(row.acc_x), float(row.acc_y), float(row.acc_z),
                float(row.gyro_x), float(row.gyro_y), float(row.gyro_z), float(row.gps_speed_mps),
            )
        )
        if sample_number % config.calibration_update_every_samples == 0:
            evidence = rolling_calibration_evidence(history, source_id, config)
            if evidence is None:
                stage_counts["calibration_updates_without_evidence"] += 1
            else:
                stage_counts["calibration_evidence_updates"] += 1
                calibrator.update(evidence)
        calibration = calibrator.calibration
        if calibration is not None and calibration.confidence >= config.minimum_calibration_confidence:
            # A newly trusted estimate either strengthens the known mounting or
            # confirms a coherent remount. It becomes the new held reference.
            last_trusted_calibration = calibration
        elif last_trusted_calibration is not None:
            # The offline recordings use a fixed phone mounting for a complete
            # journey. One weak or disagreeing evidence window should not erase
            # a rotation that was established from several earlier windows.
            # Keep the rotation, but lower its confidence to the acceptance
            # boundary so models can see that this is held rather than fresh.
            calibration = VehicleCalibration(
                timestamp_ns=last_trusted_calibration.timestamp_ns,
                source=last_trusted_calibration.source,
                source_id=last_trusted_calibration.source_id,
                sensor_to_vehicle_wxyz=last_trusted_calibration.sensor_to_vehicle_wxyz,
                confidence=config.minimum_calibration_confidence,
            )
            stage_counts["rows_using_held_calibration"] += 1

        if calibration is None:
            stage_counts["rows_before_calibration"] += 1
            continue
        if calibration.confidence < config.minimum_calibration_confidence:
            stage_counts["rows_below_calibration_confidence"] += 1
            continue

        vehicle_sample = rotate_imu_to_vehicle(
            synchronized, calibration, config.minimum_calibration_confidence
        )
        vehicle_timestamps.append(vehicle_sample.timestamp_ns)
        vehicle_rows.append(
            (*vehicle_sample.acceleration_mps2, *vehicle_sample.angular_velocity_radps)
        )
        clean_sample = remove_gravity_from_vehicle_imu(
            vehicle_sample, orientation_estimate, calibration
        )
        quality = quality_monitor.assess(clean_sample)
        if not quality.is_acceptable:
            stage_counts["quality_rejected_rows"] += 1
            for flag in quality.flags:
                stage_counts[f"quality_{flag.value}"] += 1
        else:
            stage_counts["quality_accepted_rows"] += 1

        for fixed_sample in resampler.push(clean_sample, quality):
            output_timestamps.append(fixed_sample.timestamp_ns)
            clean_rows.append(vehicle_imu_feature_row(fixed_sample))
            confidences.append(fixed_sample.calibration_confidence)
            stage_counts["resampled_rows"] += 1

    if len(clean_rows) < config.window_size + round(max(config.blackout_horizons_s) / config.sample_period_s):
        raise ValueError("Journey produced too little contiguous cleaned data for blackout examples.")

    timestamps_ns = np.asarray(output_timestamps, dtype=np.int64)
    clean_imu = np.asarray(clean_rows, dtype=np.float32)
    confidence = np.asarray(confidences, dtype=np.float32)
    source_timestamps = frame["timestamp_ns"].to_numpy(np.int64)
    raw_values = frame[["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]].to_numpy(float)
    raw_imu = _interpolate_columns(source_timestamps, raw_values, timestamps_ns).astype(np.float32)
    vehicle_imu = _interpolate_columns(
        np.asarray(vehicle_timestamps, dtype=np.int64),
        np.asarray(vehicle_rows, dtype=float),
        timestamps_ns,
    ).astype(np.float32)
    speed_values = frame[["gps_speed_mps", "target_speed_mps"]].to_numpy(float)
    speeds = _interpolate_columns(source_timestamps, speed_values, timestamps_ns).astype(np.float32)

    # A discontinuity defines a new segment.  Blackout episodes are never
    # allowed to integrate or create a model window across this boundary.
    segment_ids = np.zeros(len(timestamps_ns), dtype=np.int32)
    if len(timestamps_ns) > 1:
        discontinuity = np.diff(timestamps_ns) != config.sample_period_ns
        segment_ids[1:] = np.cumsum(discontinuity, dtype=np.int32)

    audit: dict[str, int | float | str] = {
        "journey_id": journey_id,
        **dict(stage_counts),
        "contiguous_segments": int(segment_ids.max()) + 1,
        "final_calibration_confidence": float(confidence[-1]),
        "calibration_phase": str(calibrator.phase),
    }
    return ProcessedJourney(
        journey_id=journey_id,
        timestamps_ns=timestamps_ns,
        segment_ids=segment_ids,
        raw_imu=raw_imu,
        vehicle_imu_before_gravity_removal=vehicle_imu,
        clean_imu=clean_imu,
        gps_speed_mps=speeds[:, 0],
        target_speed_mps=speeds[:, 1],
        calibration_confidence=confidence,
        audit=audit,
    )


def build_blackout_dataset(
    journeys: Sequence[ProcessedJourney], config: ExperimentConfig
) -> BlackoutDataset:
    """Create past-only simulated outages at several elapsed-time horizons."""

    clean_windows: list[np.ndarray] = []
    raw_windows: list[np.ndarray] = []
    contexts: list[tuple[float, ...]] = []
    targets: list[float] = []
    residuals: list[float] = []
    journey_ids: list[str] = []
    anchor_timestamps: list[int] = []
    end_timestamps: list[int] = []
    horizons: list[int] = []
    anchor_stride = max(1, round(config.anchor_stride_s / config.sample_period_s))

    for journey in journeys:
        for segment_id in np.unique(journey.segment_ids):
            segment_indices = np.flatnonzero(journey.segment_ids == segment_id)
            if len(segment_indices) < config.window_size:
                continue
            segment_start, segment_end = int(segment_indices[0]), int(segment_indices[-1])
            for anchor in range(segment_start, segment_end + 1, anchor_stride):
                anchor_speed = float(journey.gps_speed_mps[anchor])
                if not np.isfinite(anchor_speed) or anchor_speed < 0.0:
                    continue
                for horizon_s in config.blackout_horizons_s:
                    horizon_steps = round(horizon_s / config.sample_period_s)
                    end = anchor + horizon_steps
                    window_start = end - config.window_size + 1
                    if end > segment_end or window_start < segment_start:
                        continue

                    acceleration = journey.clean_imu[anchor : end + 1, 0].astype(float)
                    # Trapezoidal integration uses every cleaned forward-
                    # acceleration sample since the GNSS anchor.  It is the
                    # deterministic baseline that the residual model corrects.
                    delta_speed = _integrate_trapezoid(
                        acceleration,
                        dx=config.sample_period_s,
                    )
                    integrated_speed = max(0.0, anchor_speed + delta_speed)
                    confidence_slice = journey.calibration_confidence[anchor : end + 1]
                    target = float(journey.target_speed_mps[end])

                    clean_windows.append(journey.clean_imu[window_start : end + 1])
                    raw_windows.append(journey.raw_imu[window_start : end + 1])
                    contexts.append(
                        (
                            anchor_speed,
                            integrated_speed,
                            float(horizon_s),
                            float(confidence_slice.mean()),
                            float(confidence_slice.min()),
                        )
                    )
                    targets.append(target)
                    residuals.append(target - integrated_speed)
                    journey_ids.append(journey.journey_id)
                    anchor_timestamps.append(int(journey.timestamps_ns[anchor]))
                    end_timestamps.append(int(journey.timestamps_ns[end]))
                    horizons.append(horizon_s)

    if not targets:
        raise ValueError("No blackout examples were produced.")
    return BlackoutDataset(
        clean_windows=np.asarray(clean_windows, dtype=np.float32),
        raw_windows=np.asarray(raw_windows, dtype=np.float32),
        context=np.asarray(contexts, dtype=np.float32),
        target_speed_mps=np.asarray(targets, dtype=np.float32),
        residual_target_mps=np.asarray(residuals, dtype=np.float32),
        journey_ids=np.asarray(journey_ids, dtype=str),
        anchor_timestamps_ns=np.asarray(anchor_timestamps, dtype=np.int64),
        end_timestamps_ns=np.asarray(end_timestamps, dtype=np.int64),
        horizons_s=np.asarray(horizons, dtype=np.int16),
    )


def preprocessing_physics_audit(
    journeys: Sequence[ProcessedJourney], config: ExperimentConfig
) -> pd.DataFrame:
    """Measure whether preprocessing produces physically plausible IMU signals.

    This is a preflight diagnostic, not a learned metric.  A short full-model
    search is not meaningful if samples that look quiet before gravity removal
    retain several metres per second squared of acceleration afterwards, or if
    cleaned forward acceleration cannot approximately explain five-second CAN
    speed changes.
    """

    rows: list[dict[str, float | str | bool]] = []
    five_second_steps = round(5.0 / config.sample_period_s)
    for journey in journeys:
        specific_force = np.linalg.norm(
            journey.vehicle_imu_before_gravity_removal[:, :3], axis=1
        )
        angular_rate = np.linalg.norm(journey.clean_imu[:, 3:], axis=1)
        clean_magnitude = np.linalg.norm(journey.clean_imu[:, :3], axis=1)
        quiet = (
            (np.abs(specific_force - GRAVITY_MPS2) <= 0.5)
            & (angular_rate <= 0.15)
        )
        quiet_clean = clean_magnitude[quiet]

        integration_errors: list[float] = []
        for segment_id in np.unique(journey.segment_ids):
            indices = np.flatnonzero(journey.segment_ids == segment_id)
            for start in range(int(indices[0]), int(indices[-1]) - five_second_steps + 1, five_second_steps):
                end = start + five_second_steps
                observed_delta = (
                    journey.target_speed_mps[end] - journey.target_speed_mps[start]
                )
                integrated_delta = _integrate_trapezoid(
                    journey.clean_imu[start : end + 1, 0],
                    dx=config.sample_period_s,
                )
                integration_errors.append(abs(integrated_delta - observed_delta))

        quiet_median = float(np.median(quiet_clean)) if len(quiet_clean) else float("nan")
        integration_mae = (
            float(np.mean(integration_errors)) if integration_errors else float("nan")
        )
        # The limits are intentionally lenient: they only catch a broken frame
        # or gravity convention, not normal phone noise or road grade.
        passed = (
            np.isfinite(quiet_median)
            and quiet_median <= 2.0
            and np.isfinite(integration_mae)
            and integration_mae <= 2.0
        )
        rows.append(
            {
                "journey_id": journey.journey_id,
                "quiet_samples": int(quiet.sum()),
                "quiet_clean_acceleration_median_mps2": quiet_median,
                "clean_acceleration_p95_mps2": float(np.quantile(clean_magnitude, 0.95)),
                "five_second_delta_v_mae_mps": integration_mae,
                "preflight_pass": passed,
            }
        )
    return pd.DataFrame(rows)


def speed_bins(speed_mps: np.ndarray) -> np.ndarray:
    """Return broad road-speed categories used only for balancing/reporting."""

    speed_kmh = np.asarray(speed_mps) * 3.6
    return np.digitize(speed_kmh, bins=[10.0, 30.0, 50.0, 70.0, 90.0])


def choose_grouped_holdout(
    dataset: BlackoutDataset, config: ExperimentConfig, attempts: int = 512
) -> tuple[np.ndarray, np.ndarray]:
    """Choose one journey-only test split with representative speed coverage.

    GroupShuffleSplit generates legal candidates.  We select the candidate
    closest to the complete dataset in size, mean speed, high-speed share, and
    horizon mix.  The test set is frozen after this one deterministic choice.
    """

    groups = dataset.journey_ids
    if len(np.unique(groups)) < config.cv_folds + 1:
        raise ValueError("Need at least cv_folds + 1 usable journeys.")
    splitter = GroupShuffleSplit(
        n_splits=attempts, test_size=config.test_fraction, random_state=config.seed
    )
    all_speed = dataset.target_speed_mps
    all_high = float(np.mean(all_speed * 3.6 >= 70.0))
    all_horizon = np.array([np.mean(dataset.horizons_s == h) for h in config.blackout_horizons_s])
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for development, test in splitter.split(np.zeros(len(dataset)), groups=groups):
        test_speed = all_speed[test]
        test_horizon = np.array([np.mean(dataset.horizons_s[test] == h) for h in config.blackout_horizons_s])
        score = (
            3.0 * abs(len(test) / len(dataset) - config.test_fraction)
            + abs(float(test_speed.mean() - all_speed.mean())) / max(float(all_speed.std()), 1e-6)
            + abs(float(np.mean(test_speed * 3.6 >= 70.0)) - all_high)
            + float(np.abs(test_horizon - all_horizon).sum())
        )
        if best is None or score < best[0]:
            best = (score, development.copy(), test.copy())
    assert best is not None
    return np.sort(best[1]), np.sort(best[2])


def make_grouped_cv_folds(
    dataset: BlackoutDataset, development_index: np.ndarray, config: ExperimentConfig
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Build deterministic journey folds balanced by size, speed, and horizon.

    Generic stratified group splitting can satisfy class proportions while
    leaving one fold with a tiny journey. Here the independent units really
    are journeys, so we greedily allocate whole journey descriptors and give
    total example count the largest weight in the balancing objective.
    """

    development_groups = dataset.journey_ids[development_index]
    unique_groups = np.unique(development_groups)
    if len(unique_groups) < config.cv_folds:
        raise ValueError("There must be at least one journey per CV fold.")

    speed_category = speed_bins(dataset.target_speed_mps)
    speed_values = np.arange(6)
    horizon_values = np.asarray(config.blackout_horizons_s)
    descriptors: dict[str, np.ndarray] = {}
    for group in unique_groups:
        index = development_index[development_groups == group]
        descriptors[str(group)] = np.concatenate(
            [
                [len(index)],
                [np.sum(speed_category[index] == value) for value in speed_values],
                [np.sum(dataset.horizons_s[index] == value) for value in horizon_values],
            ]
        ).astype(float)

    total = np.sum(list(descriptors.values()), axis=0)
    target = np.maximum(total / config.cv_folds, 1.0)
    weights = np.concatenate([[5.0], np.full(len(speed_values), 0.75), np.full(len(horizon_values), 0.35)])
    order = sorted(unique_groups.astype(str), key=lambda group: (-descriptors[group][0], group))
    fold_load = np.zeros((config.cv_folds, len(target)), dtype=float)
    fold_groups: list[list[str]] = [[] for _ in range(config.cv_folds)]
    for position, group in enumerate(order):
        if position < config.cv_folds:
            chosen = position
        else:
            candidate_scores = []
            for fold_id in range(config.cv_folds):
                proposed = fold_load.copy()
                proposed[fold_id] += descriptors[group]
                relative_error = (proposed - target) / target
                candidate_scores.append(float(np.sum(relative_error**2 * weights)))
            chosen = int(np.argmin(candidate_scores))
        fold_load[chosen] += descriptors[group]
        fold_groups[chosen].append(group)

    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for validation_groups in fold_groups:
        validation_mask = np.isin(dataset.journey_ids[development_index], validation_groups)
        validation = development_index[validation_mask]
        train = development_index[~validation_mask]
        folds.append((train, validation))
    assert_group_isolation(dataset, folds)
    return folds


def assert_group_isolation(
    dataset: BlackoutDataset, folds: Sequence[tuple[np.ndarray, np.ndarray]]
) -> None:
    """Fail loudly if journeys or exact source timestamps leak across a fold."""

    for fold_id, (train_index, validation_index) in enumerate(folds):
        train_groups = set(dataset.journey_ids[train_index])
        validation_groups = set(dataset.journey_ids[validation_index])
        overlap = train_groups & validation_groups
        if overlap:
            raise AssertionError(f"Fold {fold_id} leaks journeys: {sorted(overlap)}")
        train_keys = set(
            zip(dataset.journey_ids[train_index], dataset.end_timestamps_ns[train_index], strict=True)
        )
        validation_keys = set(
            zip(dataset.journey_ids[validation_index], dataset.end_timestamps_ns[validation_index], strict=True)
        )
        if train_keys & validation_keys:
            raise AssertionError(f"Fold {fold_id} leaks source timestamps.")


def fold_audit_frame(
    dataset: BlackoutDataset,
    development_index: np.ndarray,
    test_index: np.ndarray,
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
) -> pd.DataFrame:
    """Make split composition visible instead of merely claiming no leakage."""

    rows: list[dict[str, object]] = []
    partitions = [("frozen_test", test_index)] + [
        (f"cv_validation_{fold_id}", validation) for fold_id, (_, validation) in enumerate(folds)
    ]
    for name, indices in partitions:
        speeds_kmh = dataset.target_speed_mps[indices] * 3.6
        rows.append(
            {
                "partition": name,
                "journeys": ", ".join(sorted(np.unique(dataset.journey_ids[indices]))),
                "journey_count": int(len(np.unique(dataset.journey_ids[indices]))),
                "examples": int(len(indices)),
                "median_speed_kmh": float(np.median(speeds_kmh)),
                "high_speed_percent": float(100.0 * np.mean(speeds_kmh >= 70.0)),
                "horizons_s": ", ".join(map(str, sorted(np.unique(dataset.horizons_s[indices])))),
            }
        )
    return pd.DataFrame(rows)


def rf_imu_features(windows: np.ndarray, sample_period_s: float) -> np.ndarray:
    """Extract 52 interpretable shape/frequency features from six IMU channels.

    The FFT ratio excludes the DC bin.  Otherwise a channel's mean could
    dominate the quantity that is meant to distinguish slow vehicle motion
    from higher-frequency vibration.
    """

    values = np.asarray(windows, dtype=float)
    if values.ndim != 3 or values.shape[2] != 6:
        raise ValueError("Expected windows with shape (examples, time, 6).")
    demeaned = values - values.mean(axis=1, keepdims=True)
    crossings = np.mean(demeaned[:, 1:, :] * demeaned[:, :-1, :] < 0.0, axis=1)
    spectrum = np.fft.rfft(demeaned, axis=1)
    power = np.abs(spectrum) ** 2
    frequencies = np.fft.rfftfreq(values.shape[1], d=sample_period_s)
    non_dc = frequencies > 0.0
    low_frequency = non_dc & (frequencies <= 3.0)
    low_ratio = power[:, low_frequency, :].sum(axis=1) / np.maximum(
        power[:, non_dc, :].sum(axis=1), 1e-12
    )
    per_channel = np.stack(
        [
            values.mean(axis=1),
            values.std(axis=1),
            values.min(axis=1),
            values.max(axis=1),
            np.sqrt(np.mean(values**2, axis=1)),
            np.quantile(values, 0.75, axis=1) - np.quantile(values, 0.25, axis=1),
            crossings,
            low_ratio,
        ],
        axis=2,
    ).reshape(len(values), -1)
    acceleration_magnitude = np.linalg.norm(values[:, :, :3], axis=2)
    gyro_magnitude = np.linalg.norm(values[:, :, 3:], axis=2)
    magnitude_features = np.column_stack(
        [
            acceleration_magnitude.mean(axis=1), acceleration_magnitude.std(axis=1),
            gyro_magnitude.mean(axis=1), gyro_magnitude.std(axis=1),
        ]
    )
    result = np.column_stack([per_channel, magnitude_features]).astype(np.float32)
    if result.shape[1] != 52 or not np.isfinite(result).all():
        raise AssertionError("RF feature extraction must produce 52 finite IMU features.")
    return result


def fit_fold_scalers(
    sequence: np.ndarray, context: np.ndarray | None, train_index: np.ndarray
) -> FoldScalers:
    """Fit scalers on one fold's training journeys and nowhere else."""

    sequence_scaler = StandardScaler().fit(sequence[train_index].reshape(-1, sequence.shape[-1]))
    context_scaler = (
        StandardScaler().fit(context[train_index])
        if context is not None and context.shape[1] > 0
        else None
    )
    return FoldScalers(sequence_scaler, context_scaler)


def transform_sequence(scaler: StandardScaler, windows: np.ndarray) -> np.ndarray:
    """Apply a channel scaler without changing the time/window structure."""

    return scaler.transform(windows.reshape(-1, windows.shape[-1])).reshape(windows.shape).astype(np.float32)


def transform_context(scaler: StandardScaler | None, context: np.ndarray | None) -> np.ndarray:
    """Scale context or return a zero-width matrix for context-free baselines."""

    if context is None:
        raise ValueError("A context array is required, even when it has zero columns.")
    if context.shape[1] == 0:
        return context.astype(np.float32)
    if scaler is None:
        raise ValueError("Non-empty context requires a fitted scaler.")
    return scaler.transform(context).astype(np.float32)


def sample_weights(dataset: BlackoutDataset, indices: np.ndarray) -> np.ndarray:
    """Reduce domination by long journeys, common horizons, and speed ranges."""

    groups = dataset.journey_ids[indices]
    horizons = dataset.horizons_s[indices]
    bins = speed_bins(dataset.target_speed_mps[indices])
    group_counts, horizon_counts, bin_counts = Counter(groups), Counter(horizons), Counter(bins)
    weights = np.asarray(
        [
            (1.0 / group_counts[group] * 1.0 / horizon_counts[horizon] * 1.0 / bin_counts[bin_id]) ** (1.0 / 3.0)
            for group, horizon, bin_id in zip(groups, horizons, bins, strict=True)
        ],
        dtype=np.float32,
    )
    weights /= weights.mean()
    return np.clip(weights, 0.25, 4.0)


class GruRegressor(nn.Module):
    """Small sequence regressor with optional anchor/context features."""

    def __init__(
        self,
        n_channels: int,
        context_dim: int,
        hidden_size: int,
        num_layers: int,
        bidirectional: bool,
        dropout: float,
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(
            n_channels,
            hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=bidirectional,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        encoded = hidden_size * (2 if bidirectional else 1)
        self.context = nn.Sequential(nn.Linear(context_dim, 16), nn.ReLU()) if context_dim else None
        self.head = nn.Sequential(
            nn.Linear(encoded + (16 if context_dim else 0), 32),
            nn.ReLU(), nn.Dropout(dropout), nn.Linear(32, 1),
        )

    def forward(self, sequence: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        _, hidden = self.gru(sequence)
        directions = 2 if self.gru.bidirectional else 1
        encoded = hidden[-directions:].transpose(0, 1).reshape(sequence.shape[0], -1)
        if self.context is not None:
            encoded = torch.cat([encoded, self.context(context)], dim=1)
        return self.head(encoded).squeeze(1)


class CausalConvBlock(nn.Module):
    """One temporal convolution that pads only the observed past."""

    def __init__(self, input_channels: int, output_channels: int, kernel_size: int, dropout: float) -> None:
        super().__init__()
        self.left_padding = kernel_size - 1
        self.conv = nn.Conv1d(input_channels, output_channels, kernel_size)
        self.norm = nn.BatchNorm1d(output_channels)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        values = nn.functional.pad(values, (self.left_padding, 0))
        return self.dropout(self.activation(self.norm(self.conv(values))))


class CausalCnnRegressor(nn.Module):
    """Phone-sized causal temporal CNN with optional anchor/context features."""

    def __init__(
        self,
        n_channels: int,
        context_dim: int,
        filters: tuple[int, ...],
        kernel_size: int,
        dropout: float,
    ) -> None:
        super().__init__()
        blocks: list[nn.Module] = []
        current = n_channels
        for output in filters:
            blocks.append(CausalConvBlock(current, output, kernel_size, dropout))
            current = output
        self.features = nn.Sequential(*blocks)
        self.context = nn.Sequential(nn.Linear(context_dim, 16), nn.ReLU()) if context_dim else None
        self.head = nn.Sequential(
            nn.Linear(current + (16 if context_dim else 0), 32),
            nn.ReLU(), nn.Dropout(dropout), nn.Linear(32, 1),
        )

    def forward(self, sequence: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        encoded = self.features(sequence.transpose(1, 2)).mean(dim=2)
        if self.context is not None:
            encoded = torch.cat([encoded, self.context(context)], dim=1)
        return self.head(encoded).squeeze(1)


def macro_journey_mae(
    actual: np.ndarray, predicted: np.ndarray, journey_ids: np.ndarray
) -> float:
    """Give every journey equal influence, regardless of its window count."""

    return float(
        np.mean(
            [
                mean_absolute_error(actual[journey_ids == journey], predicted[journey_ids == journey])
                for journey in np.unique(journey_ids)
            ]
        )
    )


def regression_metrics(
    actual: np.ndarray, predicted: np.ndarray, journey_ids: np.ndarray
) -> dict[str, float]:
    """Report all errors in physical units after clipping impossible speeds."""

    predicted = np.maximum(np.asarray(predicted), 0.0)
    rmse_mps = float(mean_squared_error(actual, predicted) ** 0.5)
    # R-squared is undefined for a slice containing a single example. Returning
    # NaN is clearer than emitting a warning or manufacturing a perfect score.
    r2 = float(r2_score(actual, predicted)) if len(actual) >= 2 else float("nan")
    return {
        "mae_mps": float(mean_absolute_error(actual, predicted)),
        "mae_kmh": float(mean_absolute_error(actual, predicted) * 3.6),
        "rmse_mps": rmse_mps,
        "rmse_kmh": rmse_mps * 3.6,
        "macro_journey_mae_mps": macro_journey_mae(actual, predicted, journey_ids),
        "macro_journey_mae_kmh": macro_journey_mae(actual, predicted, journey_ids) * 3.6,
        "r2": r2,
    }


def detailed_error_frame(
    dataset: BlackoutDataset, indices: np.ndarray, predictions: dict[str, np.ndarray]
) -> pd.DataFrame:
    """Return per-model, per-horizon and per-speed-bin diagnostics."""

    rows: list[dict[str, object]] = []
    actual = dataset.target_speed_mps[indices]
    journeys = dataset.journey_ids[indices]
    bins = speed_bins(actual)
    for model_name, predicted in predictions.items():
        for horizon in np.unique(dataset.horizons_s[indices]):
            mask = dataset.horizons_s[indices] == horizon
            rows.append({"model": model_name, "slice": "horizon", "value": int(horizon), **regression_metrics(actual[mask], predicted[mask], journeys[mask])})
        for bin_id in np.unique(bins):
            mask = bins == bin_id
            rows.append({"model": model_name, "slice": "speed_bin", "value": int(bin_id), **regression_metrics(actual[mask], predicted[mask], journeys[mask])})
    return pd.DataFrame(rows)


def neural_parameter_samples(family: str, config: ExperimentConfig) -> list[dict[str, object]]:
    """Sample the requested bounded phone-deployable architecture grid."""

    common = {"dropout": [0.1, 0.2], "learning_rate": [1e-3, 3e-4]}
    if family == "gru":
        space = {
            **common,
            "num_layers": [1, 2],
            "hidden_size": [32, 64],
            # Bidirectional processing is still causal here: the complete
            # five-second window lies before its prediction timestamp.  It is
            # less convenient for a state-carrying streaming implementation,
            # so the report keeps this flag visible as a deployment trade-off.
            "bidirectional": [False, True],
        }
    elif family == "cnn":
        space = {
            **common,
            "conv_blocks": [2, 3],
            "filter_base": [16, 32],
            "kernel_size": [3, 5],
        }
    else:
        raise ValueError(f"Unknown family: {family}")
    available = len(list(ParameterGrid(space)))
    requested = 1 if config.search_profile == "smoke" else config.neural_candidates_per_family
    return list(ParameterSampler(space, n_iter=min(requested, available), random_state=config.seed))


def rf_parameter_grid(config: ExperimentConfig) -> list[dict[str, object]]:
    """Return the full requested RF grid, or one candidate for a smoke run."""

    grid = list(
        ParameterGrid(
            {
                "n_estimators": [200, 400, 600],
                "max_depth": [8, 12, 16, None],
                "min_samples_leaf": [1, 3, 5],
                "max_features": ["sqrt", 0.5, None],
            }
        )
    )
    return grid[:1] if config.search_profile == "smoke" else grid


def build_neural_model(
    family: str, parameters: dict[str, object], context_dim: int
) -> nn.Module:
    """Construct one residual model candidate from a serializable dictionary."""

    if family == "gru":
        return GruRegressor(
            6, context_dim,
            int(parameters["hidden_size"]), int(parameters["num_layers"]),
            bool(parameters["bidirectional"]), float(parameters["dropout"]),
        )
    if family == "cnn":
        blocks = int(parameters["conv_blocks"])
        base = int(parameters["filter_base"])
        filters = tuple(base * 2**min(block, 1) for block in range(blocks))
        return CausalCnnRegressor(
            6, context_dim, filters, int(parameters["kernel_size"]), float(parameters["dropout"])
        )
    raise ValueError(f"Unknown family: {family}")


def _predict_neural(
    model: nn.Module,
    sequence: np.ndarray,
    context: np.ndarray,
    device: torch.device,
    batch_size: int,
) -> np.ndarray:
    model.eval()
    predictions: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(sequence), batch_size):
            x = torch.from_numpy(sequence[start : start + batch_size]).to(device)
            c = torch.from_numpy(context[start : start + batch_size]).to(device)
            predictions.append(model(x, c).cpu().numpy())
    return np.concatenate(predictions)


def train_neural_fold(
    *,
    family: str,
    parameters: dict[str, object],
    sequence: np.ndarray,
    context: np.ndarray,
    target: np.ndarray,
    base_speed: np.ndarray,
    dataset: BlackoutDataset,
    train_index: np.ndarray,
    validation_index: np.ndarray,
    config: ExperimentConfig,
    device: torch.device,
    seed: int,
) -> tuple[nn.Module, FoldScalers, dict[str, float | int]]:
    """Train one fold with weighted Huber loss and restore its best weights."""

    seed_everything(seed)
    scalers = fit_fold_scalers(sequence, context, train_index)
    x_train = transform_sequence(scalers.sequence, sequence[train_index])
    x_validation = transform_sequence(scalers.sequence, sequence[validation_index])
    c_train = transform_context(scalers.context, context[train_index])
    c_validation = transform_context(scalers.context, context[validation_index])
    weights = sample_weights(dataset, train_index)
    loader = DataLoader(
        TensorDataset(
            torch.from_numpy(x_train), torch.from_numpy(c_train),
            torch.from_numpy(target[train_index].astype(np.float32)), torch.from_numpy(weights),
        ),
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    model = build_neural_model(family, parameters, context.shape[1]).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=config.weight_decay
    )
    loss_function = nn.SmoothL1Loss(beta=config.huber_beta_mps, reduction="none")
    best_state: dict[str, torch.Tensor] | None = None
    best_score, best_epoch, stale = float("inf"), 0, 0
    started = time.perf_counter()

    maximum_epochs = 3 if config.search_profile == "smoke" else config.maximum_epochs
    patience = 2 if config.search_profile == "smoke" else config.early_stopping_patience
    for epoch in range(1, maximum_epochs + 1):
        model.train()
        for batch_sequence, batch_context, batch_target, batch_weight in loader:
            optimizer.zero_grad(set_to_none=True)
            output = model(batch_sequence.to(device), batch_context.to(device))
            loss = (
                loss_function(output, batch_target.to(device)) * batch_weight.to(device)
            ).mean()
            loss.backward()
            optimizer.step()
        residual_or_speed = _predict_neural(
            model, x_validation, c_validation, device, config.batch_size
        )
        prediction = np.maximum(0.0, base_speed[validation_index] + residual_or_speed)
        score = macro_journey_mae(
            dataset.target_speed_mps[validation_index], prediction,
            dataset.journey_ids[validation_index],
        )
        if score < best_score - 1e-6:
            best_score, best_epoch, stale = score, epoch, 0
            best_state = copy.deepcopy({key: value.detach().cpu() for key, value in model.state_dict().items()})
        else:
            stale += 1
            if stale >= patience:
                break
    if best_state is None:
        raise RuntimeError("Training did not produce a finite validation checkpoint.")
    model.load_state_dict(best_state)
    return model, scalers, {
        "best_epoch": best_epoch,
        "validation_macro_mae_mps": best_score,
        "training_s": time.perf_counter() - started,
    }


def tune_neural_family(
    family: str,
    dataset: BlackoutDataset,
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    config: ExperimentConfig,
    device: torch.device,
) -> pd.DataFrame:
    """Evaluate reproducibly sampled candidates on the exact shared folds."""

    candidates = neural_parameter_samples(family, config)
    rows: list[dict[str, object]] = []
    sequence = dataset.clean_windows
    context = dataset.context
    target = anchor_delta_target(dataset)
    base_speed = dataset.context[:, 0]
    for candidate_id, parameters in enumerate(candidates):
        scores: list[float] = []
        epochs: list[int] = []
        seconds = 0.0
        for fold_id, (train_index, validation_index) in enumerate(folds):
            _, _, evidence = train_neural_fold(
                family=family, parameters=parameters, sequence=sequence, context=context,
                target=target, base_speed=base_speed, dataset=dataset,
                train_index=train_index, validation_index=validation_index,
                config=config, device=device,
                seed=config.seed + 10_000 * candidate_id + fold_id,
            )
            scores.append(float(evidence["validation_macro_mae_mps"]))
            epochs.append(int(evidence["best_epoch"]))
            seconds += float(evidence["training_s"])
            print(
                f"{family} candidate {candidate_id + 1}/{len(candidates)}, "
                f"fold {fold_id + 1}/{len(folds)}: {scores[-1] * 3.6:.2f} km/h"
            )
        rows.append(
            {
                "model": f"anchor_delta_{family}", "candidate_id": candidate_id,
                "parameters": parameters,
                "cv_macro_mae_mps": float(np.mean(scores)),
                "cv_macro_mae_std_mps": float(np.std(scores)),
                "fold_best_epochs": epochs, "training_s": seconds,
            }
        )
    return pd.DataFrame(rows).sort_values("cv_macro_mae_mps").reset_index(drop=True)


def tune_absolute_neural_baseline(
    *,
    label: str,
    family: str,
    sequence: np.ndarray,
    parameters: dict[str, object],
    dataset: BlackoutDataset,
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    config: ExperimentConfig,
    device: torch.device,
) -> pd.DataFrame:
    """Evaluate one historical absolute-speed formulation on shared folds.

    These baselines intentionally receive neither anchor speed nor integrated
    speed.  Their purpose is to quantify how much the target reformulation
    helps, not to receive an equally expensive hyperparameter search.
    """

    empty_context = np.empty((len(dataset), 0), dtype=np.float32)
    zero_base = np.zeros(len(dataset), dtype=np.float32)
    scores: list[float] = []
    epochs: list[int] = []
    seconds = 0.0
    for fold_id, (train_index, validation_index) in enumerate(folds):
        _, _, evidence = train_neural_fold(
            family=family,
            parameters=parameters,
            sequence=sequence,
            context=empty_context,
            target=dataset.target_speed_mps,
            base_speed=zero_base,
            dataset=dataset,
            train_index=train_index,
            validation_index=validation_index,
            config=config,
            device=device,
            seed=config.seed + fold_id,
        )
        scores.append(float(evidence["validation_macro_mae_mps"]))
        epochs.append(int(evidence["best_epoch"]))
        seconds += float(evidence["training_s"])
    return pd.DataFrame(
        [
            {
                "model": label,
                "candidate_id": 0,
                "parameters": parameters,
                "cv_macro_mae_mps": float(np.mean(scores)),
                "cv_macro_mae_std_mps": float(np.std(scores)),
                "fold_best_epochs": epochs,
                "training_s": seconds,
            }
        ]
    )


def tune_random_forest(
    dataset: BlackoutDataset,
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    config: ExperimentConfig,
) -> pd.DataFrame:
    """Run the 52-IMU-feature plus five-context-feature RF grid."""

    imu_features = rf_imu_features(dataset.clean_windows, config.sample_period_s)
    features = np.column_stack([imu_features, dataset.context]).astype(np.float32)
    rows: list[dict[str, object]] = []
    candidates = rf_parameter_grid(config)
    for candidate_id, parameters in enumerate(candidates):
        scores: list[float] = []
        started = time.perf_counter()
        for fold_id, (train_index, validation_index) in enumerate(folds):
            model = RandomForestRegressor(
                **parameters, n_jobs=4, random_state=config.seed + candidate_id
            )
            model.fit(
                features[train_index], anchor_delta_target(dataset)[train_index],
                sample_weight=sample_weights(dataset, train_index),
            )
            residual = model.predict(features[validation_index])
            prediction = np.maximum(0.0, dataset.context[validation_index, 0] + residual)
            scores.append(
                macro_journey_mae(
                    dataset.target_speed_mps[validation_index], prediction,
                    dataset.journey_ids[validation_index],
                )
            )
        rows.append(
            {
                "model": "anchor_delta_random_forest", "candidate_id": candidate_id,
                "parameters": parameters,
                "cv_macro_mae_mps": float(np.mean(scores)),
                "cv_macro_mae_std_mps": float(np.std(scores)),
                "fold_best_epochs": [], "training_s": time.perf_counter() - started,
            }
        )
        print(
            f"RF candidate {candidate_id + 1}/{len(candidates)}: "
            f"{np.mean(scores) * 3.6:.2f} km/h"
        )
    return pd.DataFrame(rows).sort_values("cv_macro_mae_mps").reset_index(drop=True)


def fit_final_neural(
    family: str,
    parameters: dict[str, object],
    epochs: int,
    dataset: BlackoutDataset,
    development_index: np.ndarray,
    config: ExperimentConfig,
    device: torch.device,
) -> tuple[nn.Module, FoldScalers]:
    """Refit one selected architecture on all development journeys.

    The epoch count is the median best epoch from CV.  This allows all
    development journeys into the final fit without consulting the frozen test
    set or inventing a second validation split.
    """

    seed_everything(config.seed)
    scalers = fit_fold_scalers(dataset.clean_windows, dataset.context, development_index)
    sequence = transform_sequence(scalers.sequence, dataset.clean_windows[development_index])
    context = transform_context(scalers.context, dataset.context[development_index])
    weights = sample_weights(dataset, development_index)
    loader = DataLoader(
        TensorDataset(
            torch.from_numpy(sequence), torch.from_numpy(context),
            torch.from_numpy(anchor_delta_target(dataset)[development_index].astype(np.float32)), torch.from_numpy(weights),
        ),
        batch_size=config.batch_size, shuffle=True, num_workers=0,
        pin_memory=device.type == "cuda",
    )
    model = build_neural_model(family, parameters, dataset.context.shape[1]).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=config.weight_decay
    )
    loss_function = nn.SmoothL1Loss(beta=config.huber_beta_mps, reduction="none")
    for _ in range(max(1, epochs)):
        model.train()
        for batch_sequence, batch_context, batch_target, batch_weight in loader:
            optimizer.zero_grad(set_to_none=True)
            output = model(batch_sequence.to(device), batch_context.to(device))
            loss = (
                loss_function(output, batch_target.to(device)) * batch_weight.to(device)
            ).mean()
            loss.backward()
            optimizer.step()
    return model, scalers


def fit_final_absolute_neural(
    *,
    family: str,
    sequence: np.ndarray,
    parameters: dict[str, object],
    epochs: int,
    dataset: BlackoutDataset,
    development_index: np.ndarray,
    config: ExperimentConfig,
    device: torch.device,
) -> tuple[nn.Module, FoldScalers]:
    """Refit a context-free absolute-speed baseline on development journeys."""

    seed_everything(config.seed)
    empty_context = np.empty((len(dataset), 0), dtype=np.float32)
    scalers = fit_fold_scalers(sequence, empty_context, development_index)
    transformed = transform_sequence(scalers.sequence, sequence[development_index])
    weights = sample_weights(dataset, development_index)
    loader = DataLoader(
        TensorDataset(
            torch.from_numpy(transformed),
            torch.from_numpy(empty_context[development_index]),
            torch.from_numpy(dataset.target_speed_mps[development_index]),
            torch.from_numpy(weights),
        ),
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=0,
        pin_memory=device.type == "cuda",
    )
    model = build_neural_model(family, parameters, 0).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=config.weight_decay
    )
    loss_function = nn.SmoothL1Loss(beta=config.huber_beta_mps, reduction="none")
    for _ in range(max(1, epochs)):
        model.train()
        for batch_sequence, batch_context, batch_target, batch_weight in loader:
            optimizer.zero_grad(set_to_none=True)
            output = model(batch_sequence.to(device), batch_context.to(device))
            loss = (
                loss_function(output, batch_target.to(device)) * batch_weight.to(device)
            ).mean()
            loss.backward()
            optimizer.step()
    return model, scalers


def predict_final_absolute_neural(
    model: nn.Module,
    scalers: FoldScalers,
    sequence: np.ndarray,
    indices: np.ndarray,
    config: ExperimentConfig,
    device: torch.device,
) -> np.ndarray:
    """Predict absolute speed for a deliberately anchor-free baseline."""

    transformed = transform_sequence(scalers.sequence, sequence[indices])
    empty_context = np.empty((len(indices), 0), dtype=np.float32)
    return np.maximum(
        0.0,
        _predict_neural(model, transformed, empty_context, device, config.batch_size),
    )


def predict_final_neural(
    model: nn.Module,
    scalers: FoldScalers,
    dataset: BlackoutDataset,
    indices: np.ndarray,
    config: ExperimentConfig,
    device: torch.device,
) -> np.ndarray:
    """Predict physical speed from the GNSS anchor plus learned delta-v."""

    sequence = transform_sequence(scalers.sequence, dataset.clean_windows[indices])
    context = transform_context(scalers.context, dataset.context[indices])
    delta_v = _predict_neural(model, sequence, context, device, config.batch_size)
    return np.maximum(0.0, dataset.context[indices, 0] + delta_v)


def fit_final_forest(
    parameters: dict[str, object],
    dataset: BlackoutDataset,
    development_index: np.ndarray,
    config: ExperimentConfig,
) -> RandomForestRegressor:
    """Fit the selected anchor-delta RF on every development journey."""

    features = np.column_stack(
        [rf_imu_features(dataset.clean_windows, config.sample_period_s), dataset.context]
    )
    model = RandomForestRegressor(**parameters, n_jobs=4, random_state=config.seed)
    model.fit(
        features[development_index], anchor_delta_target(dataset)[development_index],
        sample_weight=sample_weights(dataset, development_index),
    )
    return model


def predict_final_forest(
    model: RandomForestRegressor,
    dataset: BlackoutDataset,
    indices: np.ndarray,
    config: ExperimentConfig,
) -> np.ndarray:
    """Apply RF anchor-delta prediction and clamp impossible negatives."""

    features = np.column_stack(
        [rf_imu_features(dataset.clean_windows[indices], config.sample_period_s), dataset.context[indices]]
    )
    return np.maximum(0.0, dataset.context[indices, 0] + model.predict(features))


def measure_latency_ms(
    predict_one: Callable[[], object], config: ExperimentConfig, device: torch.device | None = None
) -> dict[str, float]:
    """Measure warmed batch-size-one latency and report median and p95."""

    for _ in range(config.inference_warmup_calls):
        predict_one()
    if device is not None and device.type == "cuda":
        torch.cuda.synchronize()
    timings: list[float] = []
    for _ in range(config.inference_measurement_calls):
        if device is not None and device.type == "cuda":
            torch.cuda.synchronize()
        started = time.perf_counter_ns()
        predict_one()
        if device is not None and device.type == "cuda":
            torch.cuda.synchronize()
        timings.append((time.perf_counter_ns() - started) / 1e6)
    return {"median_ms": float(np.median(timings)), "p95_ms": float(np.quantile(timings, 0.95))}


def config_dict(config: ExperimentConfig) -> dict[str, object]:
    """Return a JSON-safe configuration dictionary for the artifact manifest."""

    result = asdict(config)
    result["blackout_horizons_s"] = list(config.blackout_horizons_s)
    return result

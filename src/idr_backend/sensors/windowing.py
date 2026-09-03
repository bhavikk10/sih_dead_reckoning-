"""Causal fixed-length windows for the velocity-prediction model.

This module accepts only fixed-rate, quality-gated vehicle-frame IMU samples.
It never creates a window across a resampling reset, timing discontinuity, or
device boundary. It contains no scaler, NumPy, PyTorch, or model inference.
"""

from collections import deque
from dataclasses import dataclass
from math import isfinite

from .types import SensorSource, VehicleImuSample


VELOCITY_MODEL_FEATURE_NAMES = (
    "linear_acceleration_x_mps2",
    "linear_acceleration_y_mps2",
    "linear_acceleration_z_mps2",
    "angular_velocity_x_radps",
    "angular_velocity_y_radps",
    "angular_velocity_z_radps",
)


@dataclass(frozen=True, slots=True)
class VelocityModelInputWindow:
    """One contiguous, fixed-rate sequence ready for model feature scaling."""

    end_timestamp_ns: int
    source: SensorSource
    source_id: str
    sample_period_ns: int
    samples: tuple[VehicleImuSample, ...]

    def __post_init__(self) -> None:
        """Validate that all samples form one chronological model window."""

        if self.sample_period_ns <= 0:
            raise ValueError("sample_period_ns must be positive.")

        if not self.samples:
            raise ValueError("A velocity-model window must contain samples.")

        if self.samples[-1].timestamp_ns != self.end_timestamp_ns:
            raise ValueError(
                "end_timestamp_ns must equal the final sample timestamp."
            )

        previous_timestamp_ns: int | None = None

        for sample in self.samples:
            if (
                sample.source != self.source
                or sample.source_id != self.source_id
            ):
                raise ValueError(
                    "All window samples must belong to the declared device."
                )

            if previous_timestamp_ns is not None:
                if (
                    sample.timestamp_ns - previous_timestamp_ns
                    != self.sample_period_ns
                ):
                    raise ValueError(
                        "Window samples must be exactly fixed-rate and contiguous."
                    )

            previous_timestamp_ns = sample.timestamp_ns


def vehicle_imu_feature_row(
    sample: VehicleImuSample,
) -> tuple[float, float, float, float, float, float]:
    """Extract one clean velocity-model feature row in the fixed six-channel order."""

    values = (
        sample.linear_acceleration_mps2[0],
        sample.linear_acceleration_mps2[1],
        sample.linear_acceleration_mps2[2],
        sample.angular_velocity_radps[0],
        sample.angular_velocity_radps[1],
        sample.angular_velocity_radps[2],
    )

    if not all(isfinite(value) for value in values):
        raise ValueError("Velocity-model features must all be finite.")

    return values


def velocity_model_feature_rows(
    window: VelocityModelInputWindow,
) -> tuple[tuple[float, float, float, float, float, float], ...]:
    """Extract every sample in a window as ordered model feature rows."""

    return tuple(
        vehicle_imu_feature_row(sample)
        for sample in window.samples
    )


class CausalVehicleImuWindowBuilder:
    """Build sliding velocity-model windows from one resampled IMU stream."""

    def __init__(
        self,
        *,
        window_size: int,
        sample_period_ns: int,
    ) -> None:
        """Create a builder with a fixed model-window shape."""

        if window_size <= 0:
            raise ValueError("window_size must be positive.")

        if sample_period_ns <= 0:
            raise ValueError("sample_period_ns must be positive.")

        self._window_size = window_size
        self._sample_period_ns = sample_period_ns

        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_timestamp_ns: int | None = None

        self._samples: deque[VehicleImuSample] = deque(
            maxlen=window_size
        )


    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind the window builder to one physical IMU stream."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one window builder."
            )


    def push(
        self,
        sample: VehicleImuSample,
    ) -> VelocityModelInputWindow | None:
        """Accept one resampled sample and emit a complete causal window if ready."""

        self._register_or_validate_stream(sample)

        if self._last_timestamp_ns is not None:
            if sample.timestamp_ns <= self._last_timestamp_ns:
                raise ValueError(
                    "Window-builder timestamps must be strictly increasing."
                )

            if (
                sample.timestamp_ns - self._last_timestamp_ns
                != self._sample_period_ns
            ):
                # A resampling reset or discontinuity occurred. Keep the current
                # sample as the start of a new sequence, never join it to old data.
                self._samples.clear()

        self._samples.append(sample)
        self._last_timestamp_ns = sample.timestamp_ns

        if len(self._samples) < self._window_size:
            return None

        return VelocityModelInputWindow(
            end_timestamp_ns=sample.timestamp_ns,
            source=sample.source,
            source_id=sample.source_id,
            sample_period_ns=self._sample_period_ns,
            samples=tuple(self._samples),
        )


    def reset(self) -> None:
        """Forget the current device sequence after a confirmed session restart."""

        self._source = None
        self._source_id = None
        self._last_timestamp_ns = None
        self._samples.clear()
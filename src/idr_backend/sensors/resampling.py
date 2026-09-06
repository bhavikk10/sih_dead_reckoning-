"""Causal fixed-rate resampling for cleaned vehicle-frame IMU data.

Velocity models require evenly spaced inputs, but sensor callbacks can jitter or
arrive at a different rate. This module resamples only between consecutive
acceptable samples and never bridges a quality failure or sensor gap.
"""


from dataclasses import dataclass
from math import acos, isfinite, sin

from .orientation import normalize_quaternion
from .quality import VehicleImuQuality
from .types import (
    QuaternionWxyz,
    SensorSource,
    Vector3,
    VehicleImuSample,
)


@dataclass(frozen=True, slots=True)
class ResampledVehicleImuSample:
    """One fixed-rate IMU sample and the conservative quality facts it inherits.

    Interpolation is allowed only between two acceptable real samples. The
    output therefore keeps the lower endpoint score and union of endpoint
    flags, so it never appears healthier than the readings that bound it.
    """

    sample: VehicleImuSample
    quality: VehicleImuQuality

    def __post_init__(self) -> None:
        """Ensure the quality report belongs to this exact emitted sample."""

        if (
            self.quality.timestamp_ns != self.sample.timestamp_ns
            or self.quality.source != self.sample.source
            or self.quality.source_id != self.sample.source_id
        ):
            raise ValueError(
                "Resampled quality must belong to the exact emitted IMU sample."
            )
        if not self.quality.is_acceptable:
            raise ValueError("Resampled output must have acceptable quality.")


def _interpolate_vector(
    before: Vector3,
    after: Vector3,
    fraction: float,
) -> Vector3:
    """Linearly interpolate a finite vector from before toward after."""

    if not isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be finite and between 0.0 and 1.0.")

    if not all(isfinite(component) for component in (*before, *after)):
        raise ValueError("Interpolation vectors must contain only finite values.")

    return (
        before[0] + fraction * (after[0] - before[0]),
        before[1] + fraction * (after[1] - before[1]),
        before[2] + fraction * (after[2] - before[2]),
    )


def _interpolate_quaternion(
    before: QuaternionWxyz,
    after: QuaternionWxyz,
    fraction: float,
) -> QuaternionWxyz:
    """Spherically interpolate two unit rotation quaternions."""

    if not isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be finite and between 0.0 and 1.0.")

    before_unit = normalize_quaternion(before)
    after_unit = normalize_quaternion(after)

    dot_product = (
        before_unit[0] * after_unit[0]
        + before_unit[1] * after_unit[1]
        + before_unit[2] * after_unit[2]
        + before_unit[3] * after_unit[3]
    )

    # q and -q represent the same rotation. Negating one chooses the shortest
    # rotational path instead of taking the long way around the quaternion sphere.
    if dot_product < 0.0:
        after_unit = (
            -after_unit[0],
            -after_unit[1],
            -after_unit[2],
            -after_unit[3],
        )
        dot_product = -dot_product

    dot_product = max(-1.0, min(1.0, dot_product))

    # Nearly identical rotations are numerically safer with linear blending.
    if dot_product > 0.9995:
        return normalize_quaternion(
            (
                before_unit[0] + fraction * (after_unit[0] - before_unit[0]),
                before_unit[1] + fraction * (after_unit[1] - before_unit[1]),
                before_unit[2] + fraction * (after_unit[2] - before_unit[2]),
                before_unit[3] + fraction * (after_unit[3] - before_unit[3]),
            )
        )

    angle_rad = acos(dot_product)
    sin_angle = sin(angle_rad)

    before_weight = sin((1.0 - fraction) * angle_rad) / sin_angle
    after_weight = sin(fraction * angle_rad) / sin_angle

    return normalize_quaternion(
        (
            before_weight * before_unit[0] + after_weight * after_unit[0],
            before_weight * before_unit[1] + after_weight * after_unit[1],
            before_weight * before_unit[2] + after_weight * after_unit[2],
            before_weight * before_unit[3] + after_weight * after_unit[3],
        )
    )


def _interpolate_vehicle_imu_sample(
    before: VehicleImuSample,
    after: VehicleImuSample,
    timestamp_ns: int,
) -> VehicleImuSample:
    """Create one fixed-rate vehicle IMU sample between two real samples."""

    if before.source != after.source or before.source_id != after.source_id:
        raise ValueError(
            "Cannot interpolate samples from different physical IMU devices."
        )

    if after.timestamp_ns <= before.timestamp_ns:
        raise ValueError(
            "Interpolation requires strictly increasing sample timestamps."
        )

    if not before.timestamp_ns <= timestamp_ns <= after.timestamp_ns:
        raise ValueError(
            "Interpolation timestamp must lie between the input timestamps."
        )

    fraction = (
        (timestamp_ns - before.timestamp_ns)
        / (after.timestamp_ns - before.timestamp_ns)
    )

    return VehicleImuSample(
        timestamp_ns=timestamp_ns,
        source=before.source,
        source_id=before.source_id,
        linear_acceleration_mps2=_interpolate_vector(
            before.linear_acceleration_mps2,
            after.linear_acceleration_mps2,
            fraction,
        ),
        angular_velocity_radps=_interpolate_vector(
            before.angular_velocity_radps,
            after.angular_velocity_radps,
            fraction,
        ),
        vehicle_to_navigation_wxyz=_interpolate_quaternion(
            before.vehicle_to_navigation_wxyz,
            after.vehicle_to_navigation_wxyz,
            fraction,
        ),
        # An interpolated result cannot be more trustworthy than either real
        # sample that produced it.
        calibration_confidence=min(
            before.calibration_confidence,
            after.calibration_confidence,
        ),
    )


def _interpolate_quality(
    *,
    before: VehicleImuQuality,
    after: VehicleImuQuality,
    timestamp_ns: int,
) -> VehicleImuQuality:
    """Carry conservative endpoint quality facts to an interpolated point."""

    if before.source != after.source or before.source_id != after.source_id:
        raise ValueError("Cannot combine quality from different IMU devices.")
    if not before.is_acceptable or not after.is_acceptable:
        raise ValueError("Interpolation requires two quality-accepted endpoints.")

    intervals = tuple(
        interval
        for interval in (before.sample_interval_ns, after.sample_interval_ns)
        if interval is not None
    )
    return VehicleImuQuality(
        timestamp_ns=timestamp_ns,
        source=before.source,
        source_id=before.source_id,
        flags=before.flags | after.flags,
        sample_interval_ns=max(intervals) if intervals else None,
        score=min(before.score, after.score),
        is_acceptable=True,
    )


class FixedRateVehicleImuResampler:
    """Causally resample one acceptable vehicle IMU stream at a fixed period."""

    def __init__(
        self,
        target_period_ns: int,
    ) -> None:
        """Create a resampler whose output grid begins at its first sample."""

        if target_period_ns <= 0:
            raise ValueError("target_period_ns must be positive.")

        self._target_period_ns = target_period_ns
        self._source: SensorSource | None = None
        self._source_id: str | None = None
        self._last_received_timestamp_ns: int | None = None
        self._previous_sample: VehicleImuSample | None = None
        self._previous_quality: VehicleImuQuality | None = None
        self._next_output_timestamp_ns: int | None = None


    def _register_or_validate_stream(
        self,
        sample: VehicleImuSample,
    ) -> None:
        """Bind this resampler to one physical IMU stream."""

        if self._source is None:
            self._source = sample.source
            self._source_id = sample.source_id
            return

        if (
            sample.source != self._source
            or sample.source_id != self._source_id
        ):
            raise ValueError(
                "Cannot mix multiple physical IMU streams in one resampler."
            )


    def push(
        self,
        sample: VehicleImuSample,
        quality: VehicleImuQuality,
    ) -> tuple[ResampledVehicleImuSample, ...]:
        """Accept one cleaned sample and emit any newly available grid samples."""

        if (
            quality.timestamp_ns != sample.timestamp_ns
            or quality.source != sample.source
            or quality.source_id != sample.source_id
        ):
            raise ValueError(
                "Quality report must belong to the exact vehicle IMU sample."
            )

        self._register_or_validate_stream(sample)

        if (
            self._last_received_timestamp_ns is not None
            and sample.timestamp_ns <= self._last_received_timestamp_ns
        ):
            raise ValueError(
                "Resampler input timestamps must be strictly increasing."
            )

        self._last_received_timestamp_ns = sample.timestamp_ns

        # Never interpolate across a sensor gap, invalid value, or poor
        # calibration. The next acceptable sample starts a fresh window.
        if not quality.is_acceptable:
            self._previous_sample = None
            self._previous_quality = None
            self._next_output_timestamp_ns = None
            return ()

        if self._previous_sample is None:
            self._previous_sample = sample
            self._previous_quality = quality
            self._next_output_timestamp_ns = (
                sample.timestamp_ns + self._target_period_ns
            )

            # The first accepted real sample anchors this new fixed-rate grid.
            return (ResampledVehicleImuSample(sample=sample, quality=quality),)

        if self._previous_quality is None:
            raise RuntimeError("Accepted previous IMU sample has no quality report.")

        output_samples: list[ResampledVehicleImuSample] = []

        while (
            self._next_output_timestamp_ns is not None
            and self._next_output_timestamp_ns <= sample.timestamp_ns
        ):
            resampled_sample = _interpolate_vehicle_imu_sample(
                    self._previous_sample,
                    sample,
                    self._next_output_timestamp_ns,
                )
            output_samples.append(
                ResampledVehicleImuSample(
                    sample=resampled_sample,
                    quality=_interpolate_quality(
                        before=self._previous_quality,
                        after=quality,
                        timestamp_ns=resampled_sample.timestamp_ns,
                    ),
                )
            )
            self._next_output_timestamp_ns += self._target_period_ns

        self._previous_sample = sample
        self._previous_quality = quality

        return tuple(output_samples)


    def reset(self) -> None:
        """Forget resampling state after a confirmed device-session restart."""

        self._source = None
        self._source_id = None
        self._last_received_timestamp_ns = None
        self._previous_sample = None
        self._previous_quality = None
        self._next_output_timestamp_ns = None


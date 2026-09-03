"""Unit conversion and basic validation for raw inertial sensor readings."""


from math import pi, isfinite

from .types import (
    MeasurementUnit, NormalizedSensorSample, RawSensorSample, SensorKind
)

STD_GRAV = 9.80665  #in msp2


def normalize_raw_sample(sample: RawSensorSample) -> NormalizedSensorSample:
    """Validate one raw IMU reading and convert it into IDR's SI convention."""

    if sample.timestamp_ns < 0:
        raise ValueError("timestamp_ns must be non neg")

    if not sample.source_id.strip():
        raise ValueError("source_id must not be empty")

    if not all(isfinite(component) for component in sample.value):
        raise ValueError("sensor values should be finite")

    if sample.kind is SensorKind.ACCELEROMETER:
        if sample.unit is MeasurementUnit.METERS_PER_SECOND_SQUARED:
            scale = 1.0
        elif sample.unit is MeasurementUnit.STANDARD_GRAVITY:
            scale = STD_GRAV
        else:
            raise ValueError(f"accelerometer cannot use hte unit {sample.unit}")

    elif sample.kind is SensorKind.GYROSCOPE:
        if sample.unit is MeasurementUnit.RADIANS_PER_SECOND:
            scale = 1.0
        elif sample.unit is MeasurementUnit.DEGREES_PER_SECOND:
            scale = pi/180.0
        else:
            raise ValueError(f"gyro cannot use the unit {sample.unit}")

    else:
        raise ValueError(f"unsupported sensor kind {sample.kind}")

    x,y,z = sample.value

    return NormalizedSensorSample(
        timestamp_ns= sample.timestamp_ns,
        source = sample.source,
        source_id = sample.source_id,
        kind = sample.kind,
        value = (x*scale, y*scale, z*scale),
        frame = sample.frame,
    )
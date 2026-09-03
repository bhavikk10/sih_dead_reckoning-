"""Gravity compensation for calibrated vehicle-frame IMU data.

An accelerometer measures specific force, not linear acceleration directly.
This module uses the vehicle-to-navigation orientation to express local gravity
in vehicle FLU, then adds it back to recover vehicle linear acceleration.
"""



from .orientation import (
    normalize_quaternion,
    quaternion_conjugate,
    quaternion_multiply,
    rotate_vector,
)


from .types import (
    CoordinateFrame,
    OrientationEstimate,
    QuaternionWxyz,
    SynchronizedImuSample,
    Vector3,
    VehicleCalibration,
    VehicleImuSample,
)


from math import isfinite


def derive_vehicle_to_navigation_quaternion(
    orientation: OrientationEstimate,
    calibration: VehicleCalibration,
) -> QuaternionWxyz:
    """Compose SENSOR-to-navigation and SENSOR-to-vehicle rotations."""

    if orientation.source != calibration.source:
        raise ValueError(
            "Orientation and calibration must belong to the same sensor source."
        )

    if orientation.source_id != calibration.source_id:
        raise ValueError(
            "Orientation and calibration must belong to the same physical device."
        )

    if calibration.timestamp_ns > orientation.timestamp_ns:
        raise ValueError(
            "Cannot use a calibration estimate newer than the orientation sample."
        )

    # SENSOR -> NAVIGATION, composed with VEHICLE -> SENSOR.
    # The inverse of SENSOR -> VEHICLE is VEHICLE -> SENSOR.
    vehicle_to_sensor = quaternion_conjugate(
        calibration.sensor_to_vehicle_wxyz
    )

    return normalize_quaternion(
        quaternion_multiply(
            orientation.sensor_to_navigation_wxyz,
            vehicle_to_sensor,
        )
    )


def gravity_vector_in_vehicle_frame(vehicle_to_navigation_wxyz: QuaternionWxyz, gravity_mps2: float = 9.80665) -> Vector3:
    """Express navigation gravity in the vehicle Forward-Left-Up frame."""

    if not isfinite(gravity_mps2) or gravity_mps2 <= 0.0:
        raise ValueError("gravity_mps2 must be finite and positive.")

    # Gravity points down in navigation ENU: z = -g.
    gravity_in_navigation: Vector3 = (0.0, 0.0, -gravity_mps2)

    # vehicle_to_navigation maps vehicle vectors into ENU. Its inverse maps
    # ENU vectors, including gravity, back into vehicle FLU.
    navigation_to_vehicle = quaternion_conjugate(
        normalize_quaternion(vehicle_to_navigation_wxyz)
    )

    return rotate_vector(
        navigation_to_vehicle,
        gravity_in_navigation,
    )


def remove_gravity_from_vehicle_imu(
    vehicle_sample: SynchronizedImuSample,
    orientation: OrientationEstimate,
    calibration: VehicleCalibration,
    gravity_mps2: float = 9.80665,
) -> VehicleImuSample:
    """Produce cleaned vehicle-frame IMU data for velocity prediction."""

    if vehicle_sample.frame is not CoordinateFrame.VEHICLE_FLU:
        raise ValueError(
            "Gravity removal expects a VEHICLE_FLU-frame IMU sample."
        )

    if (
        vehicle_sample.source != orientation.source
        or vehicle_sample.source_id != orientation.source_id
    ):
        raise ValueError(
            "Vehicle sample and orientation must belong to the same device."
        )

    if (
        vehicle_sample.source != calibration.source
        or vehicle_sample.source_id != calibration.source_id
    ):
        raise ValueError(
            "Vehicle sample and calibration must belong to the same device."
        )

    if orientation.timestamp_ns != vehicle_sample.timestamp_ns:
        raise ValueError(
            "Orientation and vehicle IMU sample must have the same timestamp."
        )

    if calibration.timestamp_ns > vehicle_sample.timestamp_ns:
        raise ValueError(
            "Calibration must not be newer than the vehicle IMU sample."
        )

    if (
        not isfinite(calibration.confidence)
        or not 0.0 <= calibration.confidence <= 1.0
    ):
        raise ValueError(
            "Calibration confidence must be finite and between 0.0 and 1.0."
        )

    vehicle_to_navigation = derive_vehicle_to_navigation_quaternion(
        orientation,
        calibration,
    )
    gravity_in_vehicle = gravity_vector_in_vehicle_frame(
        vehicle_to_navigation,
        gravity_mps2,
    )

    # Accelerometer values are specific force. Adding the correctly oriented
    # gravity vector recovers the vehicle's physical linear acceleration.
    linear_acceleration_mps2 = (
        vehicle_sample.acceleration_mps2[0] + gravity_in_vehicle[0],
        vehicle_sample.acceleration_mps2[1] + gravity_in_vehicle[1],
        vehicle_sample.acceleration_mps2[2] + gravity_in_vehicle[2],
    )

    return VehicleImuSample(
        timestamp_ns=vehicle_sample.timestamp_ns,
        source=vehicle_sample.source,
        source_id=vehicle_sample.source_id,
        linear_acceleration_mps2=linear_acceleration_mps2,
        angular_velocity_radps=vehicle_sample.angular_velocity_radps,
        vehicle_to_navigation_wxyz=vehicle_to_navigation,
        calibration_confidence=calibration.confidence,
    )

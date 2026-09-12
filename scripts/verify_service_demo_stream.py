"""Feed one designated recorded phone stream through the actual service routes.

This is a transport/integration verification, not a fresh accuracy experiment:
the script submits only phone GNSS and IMU facts to the same FastAPI handlers a
mobile client uses.  It deliberately does not inspect CAN/reference columns.

The historic VTA phone recordings do not carry GNSS speed/course uncertainty.
For this *recorded-data adapter only*, the documented replay assumptions of
1.5 m/s speed accuracy and 15 degree course accuracy are supplied so the
existing calibrated phone-mounting pipeline can be exercised.  A live phone
client preserves those absent Expo fields as null rather than applying these
dataset-specific assumptions.
"""

from __future__ import annotations

import argparse
from math import radians
from pathlib import Path

from fastapi.testclient import TestClient

from idr_backend.evaluation.replay import RawReplayJourney, load_raw_replay_journey
from idr_backend.service.api import create_app


_DEMO_JOURNEYS = ("Vta4", "Vta22", "Vta27")


def main() -> None:
    """Run a deterministic service-route verification for one selected journey."""

    arguments = _parse_arguments()
    root = Path(__file__).resolve().parents[1]
    journey = load_raw_replay_journey(arguments.data_root / "raw", arguments.journey)

    with TestClient(create_app()) as client:
        created = client.post(
            "/v1/navigation-sessions",
            json={"sourceId": "phone-primary", "receiverId": "phone-primary"},
        )
        created.raise_for_status()
        session_id = str(created.json()["sessionId"])
        try:
            result = _stream_phone_callbacks(
                client=client,
                session_id=session_id,
                journey=journey,
                maximum_duration_s=arguments.maximum_replay_duration_s,
            )
            print(
                " | ".join(
                    (
                        f"journey={journey.journey_id}",
                        f"raw_phone_samples={result.raw_phone_samples}",
                        f"gnss_callbacks={result.gnss_callbacks}",
                        f"committed_estimates={result.committed_estimates}",
                        f"last_mode={result.last_mode or 'unavailable'}",
                    )
                )
            )
        finally:
            deleted = client.delete(f"/v1/navigation-sessions/{session_id}")
            deleted.raise_for_status()


class _ServiceVerificationResult:
    """Small aggregate only; raw coordinates and sensor values never enter logs."""

    def __init__(self) -> None:
        self.raw_phone_samples = 0
        self.gnss_callbacks = 0
        self.committed_estimates = 0
        self.last_mode: str | None = None


def _stream_phone_callbacks(
    *,
    client: TestClient,
    session_id: str,
    journey: RawReplayJourney,
    maximum_duration_s: float | None,
) -> _ServiceVerificationResult:
    """Submit chronological GNSS, acceleration, then gyro via service HTTP routes."""

    result = _ServiceVerificationResult()
    last_gnss_timestamp_ns: int | None = None
    for index, timestamp_value in enumerate(journey.timestamps_ns):
        timestamp_ns = int(timestamp_value)
        if (
            maximum_duration_s is not None
            and timestamp_ns > int(maximum_duration_s * 1_000_000_000)
        ):
            break
        if last_gnss_timestamp_ns is None or timestamp_ns - last_gnss_timestamp_ns >= 1_000_000_000:
            gnss = client.post(
                f"/v1/navigation-sessions/{session_id}/gnss",
                json={
                    "timestampNs": timestamp_ns,
                    "receiverId": "phone-primary",
                    "latitudeDeg": float(journey.phone_latitude_deg[index]),
                    "longitudeDeg": float(journey.phone_longitude_deg[index]),
                    "altitudeM": float(journey.phone_altitude_m[index]),
                    "horizontalAccuracyM": float(journey.phone_horizontal_accuracy_m[index]),
                    "speedMps": float(journey.phone_speed_mps[index]),
                    "speedAccuracyMps": 1.5,
                    "courseOverGroundRad": float(journey.phone_course_rad[index]),
                    "courseAccuracyRad": radians(15.0),
                },
            )
            gnss.raise_for_status()
            result.gnss_callbacks += 1
            last_gnss_timestamp_ns = timestamp_ns

        acceleration = client.post(
            f"/v1/navigation-sessions/{session_id}/imu",
            json={
                "timestampNs": timestamp_ns,
                "sourceId": "phone-primary",
                "kind": "accelerometer",
                "value": [float(value) for value in journey.acceleration_sensor_mps2[index]],
                "unit": "m/s^2",
                "frame": "sensor",
            },
        )
        acceleration.raise_for_status()
        gyroscope = client.post(
            f"/v1/navigation-sessions/{session_id}/imu",
            json={
                "timestampNs": timestamp_ns,
                "sourceId": "phone-primary",
                "kind": "gyroscope",
                "value": [float(value) for value in journey.angular_velocity_sensor_radps[index]],
                "unit": "rad/s",
                "frame": "sensor",
            },
        )
        gyroscope.raise_for_status()
        estimate = gyroscope.json().get("estimate")
        if isinstance(estimate, dict):
            result.committed_estimates += 1
            mode = estimate.get("mode")
            result.last_mode = mode if isinstance(mode, str) else result.last_mode
        result.raw_phone_samples += 1
    return result


def _parse_arguments() -> argparse.Namespace:
    """Keep source data and optional duration explicit for repeatable smoke runs."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journey", choices=_DEMO_JOURNEYS, default="Vta4")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=root / "SIH-2-main" / "SIH-2-main" / "IOVNBD-Speed-Prediction" / "data",
    )
    parser.add_argument("--maximum-replay-duration-s", type=float, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    main()

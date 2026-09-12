"""Service-boundary tests without loading a real ONNX artifact."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from idr_backend.fusion.observations import LocalEnuReference
from idr_backend.service.api import create_app
from idr_backend.service.runtime import public_estimate
from idr_backend.sensors.types import NavigationEstimate, NavigationMode


def _estimate(timestamp_ns: int = 200) -> NavigationEstimate:
    return NavigationEstimate(
        timestamp_ns=timestamp_ns,
        mode=NavigationMode.DEAD_RECKONING,
        position_enu_m=(12.0, -7.0, 3.0),
        velocity_enu_mps=(4.0, 3.0, 0.0),
        vehicle_to_navigation_wxyz=(1.0, 0.0, 0.0, 0.0),
        position_covariance_enu_m2=((4.0, 0.0, 0.0), (0.0, 9.0, 0.0), (0.0, 0.0, 16.0)),
        velocity_covariance_enu_m2ps2=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        heading_variance_rad2=0.1,
        matched_road_edge_id=None,
        map_match_confidence=None,
    )


class _FakePipeline:
    """Minimal deterministic fake: GNSS then a gyro commits a known state."""

    def __init__(self) -> None:
        self._reference = LocalEnuReference(12.9716, 77.5946, 920.0)
        self.gnss_count = 0
        self.stopped = False

    @property
    def local_enu_reference(self) -> LocalEnuReference:
        return self._reference

    @property
    def runtime_snapshot(self) -> object:
        return SimpleNamespace()

    def push_gnss_fix(self, _fix: object) -> object:
        self.gnss_count += 1
        return SimpleNamespace()

    def push_raw_sample(self, sample: object) -> tuple[object, ...]:
        if getattr(sample, "kind").value != "gyroscope":
            return ()
        timestamp_ns = getattr(sample, "timestamp_ns")
        return (
            SimpleNamespace(
                navigation_estimate=_estimate(timestamp_ns),
                runtime_snapshot=SimpleNamespace(last_cycle_timestamp_ns=timestamp_ns),
                pre_ekf=SimpleNamespace(
                    preprocessing=SimpleNamespace(timestamp_ns=timestamp_ns)
                ),
            ),
        )

    def stop(self) -> object:
        self.stopped = True
        return SimpleNamespace()


def test_local_enu_reference_round_trip_is_map_safe() -> None:
    reference = LocalEnuReference(12.9716, 77.5946, 920.0)
    from idr_backend.sensors.types import GnssFix

    original = GnssFix(
        timestamp_ns=1,
        receiver_id="phone-primary",
        latitude_deg=12.9721,
        longitude_deg=77.5950,
        altitude_m=924.0,
        horizontal_accuracy_m=5.0,
        vertical_accuracy_m=None,
    )
    latitude_deg, longitude_deg, altitude_m = reference.unproject(reference.project(original))

    assert latitude_deg == pytest.approx(original.latitude_deg, abs=1e-9)
    assert longitude_deg == pytest.approx(original.longitude_deg, abs=1e-9)
    assert altitude_m == pytest.approx(original.altitude_m, abs=1e-4)


def test_public_estimate_exposes_wgs84_speed_heading_and_covariance() -> None:
    public = public_estimate(_estimate(), LocalEnuReference(12.9716, 77.5946, 920.0))

    assert public.speed_mps == 5.0
    assert public.heading_deg == 90.0
    assert public.horizontal_sigma_m == 3.0
    assert public.vertical_sigma_m == 4.0
    assert public.is_dead_reckoning is True


def test_http_and_websocket_session_transport_emit_only_new_estimates() -> None:
    app = create_app(pipeline_factory=_FakePipeline)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "roadContextEnabled": False}
        created = client.post(
            "/v1/navigation-sessions",
            json={"sourceId": "phone-primary", "receiverId": "phone-primary"},
        )
        assert created.status_code == 200
        session_id = created.json()["sessionId"]

        gnss = {
            "timestampNs": 100,
            "receiverId": "phone-primary",
            "latitudeDeg": 12.9716,
            "longitudeDeg": 77.5946,
            "altitudeM": 920.0,
            "horizontalAccuracyM": 5.0,
        }
        assert client.post(f"/v1/navigation-sessions/{session_id}/gnss", json=gnss).status_code == 200

        with client.websocket_connect(
            f"/v1/navigation-sessions/{session_id}/stream"
        ) as websocket:
            websocket.send_json(
                {
                    "type": "imu",
                    "sample": {
                        "timestampNs": 200,
                        "sourceId": "phone-primary",
                        "kind": "accelerometer",
                        "value": [0.0, 0.0, 9.81],
                        "unit": "m/s^2",
                        "frame": "sensor",
                    },
                }
            )
            websocket.send_json(
                {
                    "type": "imu",
                    "sample": {
                        "timestampNs": 200,
                        "sourceId": "phone-primary",
                        "kind": "gyroscope",
                        "value": [0.0, 0.0, 0.0],
                        "unit": "rad/s",
                        "frame": "sensor",
                    },
                }
            )
            event = websocket.receive_json()

        assert event["type"] == "estimate"
        assert event["estimate"]["mode"] == "dead_reckoning"
        assert event["estimate"]["speedMps"] == 5.0
        assert client.delete(f"/v1/navigation-sessions/{session_id}").status_code == 204

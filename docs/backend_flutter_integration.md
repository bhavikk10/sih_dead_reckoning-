# Backend, Replay, and Mobile Integration Guide

**Status:** The deterministic Python runtime is available through a
session-scoped FastAPI/WebSocket service. BetterMaps now has an opt-in React
Native transport client; its screens and visual design are unchanged. Road
context remains **in progress** and is disabled in the live service.

## What is live

```text
BetterMaps GNSS + raw sensor-frame accelerometer/gyroscope
  -> one HTTP-created navigation session
  -> ordered WebSocket messages
  -> Python validation, calibration and clean-IMU preparation
  -> reviewed ONNX velocity model + hash-bound uncertainty profile
  -> 15-state error-state EKF
  -> map-ready WGS-84 estimate returned over WebSocket
  -> existing BetterMaps map/HUD/diagnostics
```

The server creates exactly one `NavigationFusionPipeline` for each drive.
It never accepts CAN/reference data at runtime. Recorded CAN is used solely by
offline replay reports. The server currently starts the reviewed
`anchor_delta_gru` artifact, not the stateful 13.42 km/h development candidate:
the latter did not pass downstream replay gates despite its grouped OOF score.

## Service API

Run from `E:\dead reckoning`:

```powershell
$env:PYTHONPATH = "src"
# Use 127.0.0.1 for local tools. Use 0.0.0.0 only when a phone on your trusted
# development LAN needs to reach this computer.
$env:IDR_HOST = "0.0.0.0"
$env:IDR_PORT = "8000"
python -m idr_backend.service
```

`GET /health` returns `{"status":"ok","roadContextEnabled":false}`.

| Route | Purpose |
|---|---|
| `POST /v1/navigation-sessions` | Create a clean session. Optional `sourceId` and `receiverId` default to `phone-primary`. |
| `POST /v1/navigation-sessions/{id}/gnss` | Submit one GNSS fix over HTTP. Useful for diagnostics. |
| `POST /v1/navigation-sessions/{id}/imu` | Submit one raw accelerometer or gyroscope callback over HTTP. Useful for diagnostics. |
| `GET /v1/navigation-sessions/{id}/estimate` | Read the last committed estimate, or `estimate: null` before initialization. |
| `WS /v1/navigation-sessions/{id}/stream` | Preferred live path: send GNSS/IMU envelopes and receive only newly committed estimates. |
| `DELETE /v1/navigation-sessions/{id}` | Stop and release the drive session. |

The creation response includes `sessionId` and `websocketPath`. All JSON uses
camelCase and rejects unknown fields, non-finite values, invalid units, frames,
and malformed geographic bounds. The service does not return raw location or
sensor traces in acknowledgements.

### WebSocket input and output

GNSS events retain missing receiver quality as `null` rather than fabricating
certainty:

```json
{"type":"gnss","fix":{"timestampNs":1234000000,"receiverId":"phone-primary","latitudeDeg":12.9716,"longitudeDeg":77.5946,"altitudeM":920.0,"horizontalAccuracyM":6.0,"verticalAccuracyM":9.0,"speedMps":11.4,"speedAccuracyMps":null,"courseOverGroundRad":1.57,"courseAccuracyRad":null}}
```

Each physical IMU callback is sent in its original phone sensor frame:

```json
{"type":"imu","sample":{"timestampNs":1234005000,"source":"phone","sourceId":"phone-primary","kind":"accelerometer","value":[0.12,-0.08,9.72],"unit":"m/s^2","frame":"sensor","vendorAccuracy":null}}
```

For gyroscope, use `kind: "gyroscope"` and `unit: "rad/s"`. Every timestamp
must come from one monotonic session clock; send events in order within each
GNSS/IMU stream. The backend pairs accelerometer and gyroscope samples itself.

After an EKF state commits, the service sends:

```json
{"type":"estimate","estimate":{"timestampNs":1234010000,"latitudeDeg":12.97161,"longitudeDeg":77.59459,"altitudeM":920.3,"speedMps":11.1,"headingDeg":88.2,"horizontalSigmaM":4.8,"verticalSigmaM":7.2,"mode":"gnss_aided","isDeadReckoning":false,"mapMatchConfidence":null}}
```

Validation/rejection messages have `type: "error"`, a stable `code`, and a
human-readable message. A client should surface diagnostics and drop/recover
cleanly; it must not resend stale samples into a new session.

## BetterMaps integration

The frontend integration is in:

- `bettermaps-main/bettermaps-main/src/services/idr/RemoteIdrPositioningEngine.ts`
- `bettermaps-main/bettermaps-main/src/core/state/NavigationManager.ts`

If `EXPO_PUBLIC_IDR_BACKEND_URL` is absent, BetterMaps keeps its existing
on-device positioning stack exactly as before. If it is set, the app creates a
server session, streams GNSS and both raw IMU callbacks over the WebSocket, and
renders only server-committed WGS-84 estimates through the same map/HUD path.
The UI layout, map, controls, and diagnostics components were not redesigned.

Copy `.env.example` to `.env` in `bettermaps-main/bettermaps-main` and set the
PC's reachable address, never `127.0.0.1` for a physical phone:

```dotenv
EXPO_PUBLIC_IDR_BACKEND_URL=http://192.168.1.10:8000
# Development LAN only. Production must use authenticated HTTPS/WSS instead.
EXPO_PUBLIC_IDR_ALLOW_CLEARTEXT=true
```

Because the clear-text Android setting is a native configuration, rebuild the
custom Android development client after changing it:

```powershell
cd "E:\dead reckoning\bettermaps-main\bettermaps-main"
npx expo prebuild --platform android
npx expo run:android --device
```

For an Android emulator, use `http://10.0.2.2:8000`. For a physical Android
phone, connect the phone and computer to the same trusted Wi-Fi (or configure
USB reverse explicitly) and use the PC LAN address. Production must add TLS,
authentication/authorization, session expiry, rate limiting, and privacy-safe
observability before exposing the service beyond a development network.

### Present phone-sensor limitation

Expo's location callback exposes position, coarse accuracy, speed, and heading,
but not GNSS speed accuracy or bearing/course accuracy. BetterMaps therefore
preserves those two unavailable values as `null`; it does **not** invent them.
That is correct transport behavior, but it prevents the deterministic backend's
quality-gated mounting/velocity path from reaching its fully calibrated live
configuration on an Expo-only client. A native Android location bridge that
exposes `Location.getSpeedAccuracyMetersPerSecond()` and bearing accuracy (or
an equivalent trusted source) is required before claiming calibrated live-phone
navigation performance. This does not affect offline VTA replays, whose test
harness provides documented replay-only quality assumptions.

## Recorded service and replay verification

`Vta4`, `Vta22`, and `Vta27` are development/demo journeys, not held-out
performance data. They are appropriate for a functional demo, and must not be
reported as generalization results.

The service-contract verification streams recorded phone GNSS/IMU through the
same HTTP session creation and WebSocket event path used by BetterMaps:

```powershell
cd "E:\dead reckoning"
$env:PYTHONPATH = "src"
python scripts/verify_service_demo_stream.py --journey Vta4
python scripts/verify_service_demo_stream.py --journey Vta22
python scripts/verify_service_demo_stream.py --journey Vta27
```

These checks verify sensor ordering, session lifecycle, and committed estimate
delivery. They do not use CAN as an input. They use documented *replay-only*
speed/course uncertainty assumptions because the recorded VTA phone files do
not contain those facts; do not transfer those assumptions to a live device.

For the full blackout/recovery evaluation (separate from transport testing):

```powershell
$env:PYTHONPATH = "src"
python scripts/replay.py --journey Vta4 --output artifacts/demo_replays/Vta4.json
python scripts/replay.py --journey Vta22 --output artifacts/demo_replays/Vta22.json
python scripts/replay.py --journey Vta27 --output artifacts/demo_replays/Vta27.json
```

Current baseline reports exist in `artifacts/demo_replays/`. They show that the
three journeys exercise the pipeline but are uneven: `Vta4` is poor under its
scheduled blackout, `Vta22` is materially better, and `Vta27` lacks initialized
blackout scoring samples. Do not present them as a single accuracy claim.

## Road context

Road context is intentionally not part of any endpoint, mobile message, or EKF
update today. Its offline data/split/features/quantile/mixture/evaluation work
is in `src/idr_backend/road_context/` and the one-time workflow notebook.
Enablement requires calibrated held-out and spatial-held-out uncertainty plus
downstream replay evidence. Until then, `/health` truthfully reports
`roadContextEnabled: false`.

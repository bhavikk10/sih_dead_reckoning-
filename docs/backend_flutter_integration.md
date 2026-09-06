# Backend, Replay, and Flutter Integration Guide

**Status:** The deterministic Python backend and offline replay are available.
There is no HTTP/WebSocket server or Flutter application integration in this
repository yet. Road context is **in progress** and is not in the live pipeline.

## What exists today

The backend receives chronological phone GNSS and raw phone IMU data, then:

```text
GNSS + accelerometer/gyroscope callbacks
  -> validation, unit/frame handling, synchronization
  -> orientation, mounting calibration, gravity removal
  -> causal clean-IMU windows
  -> selected ONNX velocity inference + hash-bound uncertainty profile
  -> 15-state error-state EKF + GNSS and non-holonomic updates
  -> NavigationEstimate
  -> optional downstream HMM map matching
```

The backend never uses CAN/reference data in this runtime path. CAN position
and speed are used only by offline replay to calculate an error report.

The road-context work is separate and currently offline only: raw-dataset
facts, candidate-match audit contracts, and static directed road features are
implemented. Its quantile model, mixture, calibration, and EKF update do not
exist in the runtime yet.

## Repository map

| Location | Responsibility |
|---|---|
| `src/idr_backend/sensors/` | Immutable sensor/GNSS contracts, normalization, synchronization, orientation, mounting calibration, gravity removal, and quality gates. |
| `src/idr_backend/adapters/` | Model-facing adapters. `frontend.py` is intentionally only a future contract placeholder. |
| `src/idr_backend/pipeline/selected_velocity.py` | Builds the selected ONNX velocity model and the matching uncertainty profile as one validated pair. |
| `src/idr_backend/pipeline/orchestrator.py` | Connects clean IMU windows, speed-anchor context, velocity inference, and uncertainty before fusion. |
| `src/idr_backend/pipeline/fusion.py` | Owns causal GNSS queuing, EKF initialization/propagation/measurement updates, and published navigation state. |
| `src/idr_backend/pipeline/map_matching.py` | Wraps fusion with a downstream-only incremental HMM map matcher. It cannot alter the current EKF state. |
| `src/idr_backend/fusion/` | Error-state EKF state, propagation, covariance, NIS gating, GNSS/velocity measurements, non-holonomic constraint, and runtime state machine. |
| `src/idr_backend/map_matching/` | Versioned road graph, candidate generation/scoring, and incremental Viterbi/HMM logic. |
| `src/idr_backend/evaluation/replay.py` | Loads paired raw recordings and replays phone-only inputs through the complete deterministic path. |
| `src/idr_backend/road_context/` | In-progress offline road-context data/matching/feature preparation; not a live feature. |
| `scripts/replay.py` | Command-line wrapper for the agreed demo journeys. |

## Actual backend entry points

These are Python methods, not network endpoints. A service layer must create
one pipeline instance per mobile navigation session and call them in timestamp
order.

| Entry point | Input | Result / responsibility |
|---|---|---|
| `NavigationFusionPipeline.push_gnss_fix` | `GnssFix` | Quality-assesses and queues a GNSS fix for the next valid IMU/EKF cycle. |
| `NavigationFusionPipeline.push_raw_sample` | `RawSensorSample` | Accepts one accelerometer or gyroscope callback and returns zero or more `FusionPipelineResult` objects once an IMU pair is synchronized. |
| `NavigationFusionPipeline.runtime_snapshot` | none | Reads the last atomically committed `NavigationEstimate` without adding data. |
| `NavigationFusionPipeline.stop` | none | Closes the session runtime and returns its final snapshot. |
| `NavigationMapMatchingPipeline.push_gnss_fix` / `.push_raw_sample` | same inputs | Performs the same fusion calls and then, only for a newly committed estimate, performs downstream HMM map matching. |
| `NavigationMapMatchingPipeline.prior_feedback_for_cycle` | future cycle timestamp | Retrieves only a previously completed HMM belief. It exists for future road context and must not influence same-cycle fusion. |
| `replay_journey` | recorded journey plus blackout scenario | Offline integration/evaluation path; never a mobile runtime endpoint. |

`FusionPipelineResult.navigation_estimate` exposes the committed value intended
for an application layer. It contains `timestamp_ns`, `mode`, ENU position and
velocity, orientation, compact position/velocity covariance matrices, heading
variance, and optional matched-road id/confidence.

## Input contracts the Flutter side must preserve

The service layer should translate platform callbacks directly into the Python
contracts—without guessing units, coordinate frames, or timestamps.

### IMU callback

Each callback maps to `RawSensorSample`:

```json
{
  "timestampNs": 123456789000,
  "source": "phone",
  "sourceId": "phone-primary",
  "kind": "accelerometer",
  "value": [0.12, -0.08, 9.72],
  "unit": "m/s^2",
  "frame": "sensor",
  "vendorAccuracy": 3
}
```

For gyroscope callbacks, use `kind: "gyroscope"`, `unit: "rad/s"`, and the
same three-axis ordering delivered by the device. `timestampNs` must come from
one monotonic session clock—not wall-clock time. The platform bridge must not
mix Android/iOS elapsed clocks, reorder callbacks, relabel uncalibrated axes as
vehicle axes, or invent samples when a callback is missing.

### GNSS callback

Each fix maps to `GnssFix`:

```json
{
  "timestampNs": 123456789000,
  "receiverId": "phone-primary",
  "latitudeDeg": 12.9716,
  "longitudeDeg": 77.5946,
  "altitudeM": 920.0,
  "horizontalAccuracyM": 6.0,
  "verticalAccuracyM": 9.0,
  "speedMps": 11.4,
  "speedAccuracyMps": 0.8,
  "courseOverGroundRad": 1.57,
  "courseAccuracyRad": 0.2
}
```

Optional accuracy/motion fields must stay `null` when the device does not
provide them. They must not be replaced by zero, because zero means impossible
certainty. Latitude/longitude stay WGS-84 degrees at this boundary; the backend
creates its local ENU frame internally.

## Flutter integration required

1. **A transport/service wrapper.** This repository has no FastAPI, Flask,
   HTTP, WebSocket, authentication, or session store. Add a thin server that
   owns a pipeline object per active session; do not put EKF or model logic in
   Dart.
2. **A platform sensor bridge.** Flutter must obtain raw accelerometer,
   gyroscope, and location callbacks from Android/iOS, preserve their monotonic
   timestamp and units, and serialise the fields above.
3. **Session lifecycle.** Start a new backend session when navigation begins;
   terminate it on stop, app logout, or unrecoverable ordering/clock failure.
   Do not reuse a filter instance for a later drive.
4. **Ordered, bounded delivery.** Buffer briefly to handle the two IMU callback
   streams, preserve chronological order per session, use bounded queues, and
   surface dropped/late samples to diagnostics rather than silently replaying
   stale data.
5. **Output mapping.** Render the returned ENU estimate only after converting
   it to the map/display coordinate system associated with that session. Show
   `mode` (`gnss_aided`, `dead_reckoning`, or `recovery`) and quality/age so a
   user can distinguish an extrapolated state from a GNSS-aided one.
6. **Permissions and operating conditions.** Implement foreground/background
   location, motion-sensor permissions, battery policy, reconnect behaviour,
   TLS/authentication, device identity, and privacy retention in the app and
   service layer. None of these are currently provided here.

## Proposed transport endpoints (not implemented)

The following is a recommended contract for the service wrapper. It is not an
existing API and must not be described to the frontend team as already live.

| Proposed route | Purpose |
|---|---|
| `POST /v1/navigation-sessions` | Create a session, declare device/source ids and any graph/map configuration. |
| `POST /v1/navigation-sessions/{sessionId}/gnss` | Submit one ordered GNSS fix. |
| `POST /v1/navigation-sessions/{sessionId}/imu` | Submit one ordered raw accelerometer or gyroscope callback. |
| `GET /v1/navigation-sessions/{sessionId}/estimate` | Read the latest committed estimate and its mode/diagnostics. |
| `WS /v1/navigation-sessions/{sessionId}/estimates` | Stream only newly committed navigation estimates to Flutter. |
| `DELETE /v1/navigation-sessions/{sessionId}` | Stop and release the owned pipeline instance. |

The service should validate payload schema before constructing backend
dataclasses, return clear 4xx errors for bad units/frames/timestamps, keep
per-session ordering and limits, and avoid returning raw sensor traces by
default. The current `adapters/frontend.py` is intentionally the place to turn
the backend estimate into a stable response schema once that contract is agreed.

## Designated demo journeys and replay commands

`Vta4`, `Vta22`, and `Vta27` are the agreed demonstration journeys. They are
development data used during model work, so a replay of them is suitable for a
functional/demo presentation but is **not** a held-out accuracy result.

The default replay command uses the reviewed deterministic EKF profile,
`anchor_delta_gru.onnx`, and the matching deterministic uncertainty profile
from `artifacts/anchored_velocity_comparison`. It applies a 30-second GNSS
warm-up, a 60-second scheduled GNSS blackout, then 30 seconds of recovery.

Run from `E:\dead reckoning` in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python scripts/replay.py --journey Vta4 --output artifacts/demo_replays/Vta4.json
python scripts/replay.py --journey Vta22 --output artifacts/demo_replays/Vta22.json
python scripts/replay.py --journey Vta27 --output artifacts/demo_replays/Vta27.json
```

Each invocation feeds the full recorded phone callback stream through
preprocessing, ONNX velocity inference, uncertainty estimation, EKF fusion,
and recovery. It writes the complete report as JSON and prints useful logs:
blackout velocity MAE, blackout endpoint relative position error, accepted
velocity-model updates, and whether the replay was valid for scoring.

For a shorter smoke run, retain enough data for the complete scenario and set
an explicit end time:

```powershell
$env:PYTHONPATH = "src"
python scripts/replay.py --journey Vta4 --maximum-replay-duration-s 150
```

The offline replay is the closest current equivalent to a “mock backend
session.” It does not start a network server and it does not use CAN labels as
inputs.

### Experimental stateful artifact

The separately exported stateful candidate has a 13.42 km/h grouped
out-of-fold macro MAE from its development search. That is a model-level
development statistic, not a downstream promotion result: its raw replay has
not met the gate to replace the reviewed default. It is therefore opt-in for
engineering comparison only, never the default service/demo configuration.

If that exact artifact needs to be exercised through the same complete replay,
make every part of the pair explicit:

```powershell
$env:PYTHONPATH = "src"
python scripts/replay.py --journey Vta4 `
  --velocity-model-family stateful_anchor_delta_gru `
  --velocity-artifact-directory artifacts/final_velocity_search_v2/stateful_macro_mae_13_42_experimental `
  --uncertainty-artifact-directory artifacts/final_velocity_search_v2/stateful_macro_mae_13_42_experimental/uncertainty `
  --uncertainty-profile-filename deterministic_velocity_uncertainty.json
```

Do not mix an ONNX file, metadata file, or uncertainty profile from different
artifact directories; the backend's strict hash and model-id checks are meant
to reject precisely that mismatch.

## Before calling the mobile integration complete

- Implement and test the proposed service wrapper with one pipeline per
  session.
- Agree and version a JSON/protobuf response schema in `adapters/frontend.py`.
- Add end-to-end tests for ordering, duplicate callbacks, missing IMU pairs,
  invalid units/frames, reconnects, and session cleanup.
- Decide map/ENU origin ownership and map-matching graph selection per session.
- Add observability that records safe aggregate dispositions and latency without
  logging raw location/sensor data by default.
- Keep road context disabled until its calibration and downstream replay gates
  are complete.

# Intelligent Dead Reckoning Backend

This repository contains the Python backend for the Intelligent Dead Reckoning
(IDR) system proposed for SIH 2026 Problem Statement 26168.

## Current status

The deterministic core is implemented and can be exercised against paired raw
phone/CAN recordings: phone IMU and GNSS are preprocessed, an ONNX velocity
model and its uncertainty profile are applied, and a 15-state error-state EKF
publishes navigation estimates. Incremental HMM map matching is also available
as a downstream-only composition.

The repository provides both an offline-replay tool and a session-scoped
FastAPI/WebSocket service for a mobile client.  The service owns one clean
fusion pipeline per drive and receives raw phone-frame IMU and WGS-84 GNSS;
the mobile application never reimplements calibration, velocity inference, or
the EKF. Road context is in progress: its offline dataset/matching/static-feature pipeline,
empirical and LightGBM quantile-model contracts, safety rules, candidate
mixture, grouped evaluation, and calibration gate are implemented. It has no
trained production artifact and is not yet connected to runtime or the EKF.

## Runtime data flow

`IMU/GNSS -> preprocessing -> selected velocity + uncertainty -> 15-state`
`error-state EKF -> navigation estimate -> incremental HMM map matching`

Phone GNSS and IMU are the only runtime inputs. Recorded CAN position and speed
are held aside as offline replay references; they are never fed into fusion.

## Repository map

- `src/idr_backend/sensors/` defines sensor/GNSS contracts and deterministic
  preprocessing.
- `src/idr_backend/service/` owns the versioned HTTP/WebSocket contract,
  session registry, reviewed-runtime construction, and safe public estimates.
- `src/idr_backend/adapters/` owns model/runtime adapters; it contains no UI
  or network behavior.
- `src/idr_backend/pipeline/` composes preprocessing, selected velocity,
  uncertainty, EKF fusion, optional downstream map matching, and the
  decision-only road-context candidate adapter. The adapter is not wired into
  EKF fusion.
- `src/idr_backend/fusion/` implements the error-state EKF, measurements,
  constraints, covariance, and runtime policies.
- `src/idr_backend/map_matching/` contains graph, candidate, scoring, and HMM
  components.
- `src/idr_backend/road_context/` contains the in-progress offline
  road-context dataset, feature, quantile-model, mixture, split, evaluation,
  and experiment layers. It is not a runtime fusion feature.
- `src/idr_backend/evaluation/` contains causal raw-replay evaluation.
- `scripts/replay.py` runs one complete designated demo replay.
- `notebooks/road_context_one_time_workflow.ipynb` is the staged, one-time
  offline road-context dataset/training/evaluation workflow. It stops before
  artifact export and live fusion until its real-data gates pass.

## Quick demo replay

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python scripts/replay.py --journey Vta4 --output artifacts/demo_replays/Vta4.json
```

`Vta4`, `Vta22`, and `Vta27` are agreed development/demo journeys. Use them for
UI and integration demonstrations only; they are not held-out performance
evidence.

See [the backend and Flutter integration guide](docs/backend_flutter_integration.md)
for the live API, mobile transport contract, data payloads, replay commands,
and the road-context status. The BetterMaps React Native integration is in
`bettermaps-main/bettermaps-main/`; it preserves the existing UI and selects
the Python backend only when `EXPO_PUBLIC_IDR_BACKEND_URL` is configured. See
[the road-context model document](docs/road_context_model.md) for its detailed
methodology and gating plan.

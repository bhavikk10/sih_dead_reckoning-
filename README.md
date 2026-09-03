# Intelligent Dead Reckoning Backend

This repository is the Python backend scaffold for the Intelligent Dead Reckoning
(IDR) system proposed for SIH 2026 Problem Statement 26168.

## Current status

The repository intentionally contains no navigation, filtering, machine-learning,
map-processing, or data-ingestion implementation. It establishes ownership,
module boundaries, configuration placeholders, and a verification plan before
implementation begins.

## Owned scope

The backend will own the deterministic navigation pipeline and two learned
supporting engines:

- IMU ingestion, synchronization, calibration, orientation, gravity removal,
  navigation fusion, non-holonomic constraints, GNSS handoff, and map matching.
- A standalone uncertainty engine that converts the externally supplied velocity
  observation into a calibrated covariance or reliability signal.
- A hybrid road-context engine that combines deterministic road rules with a
  quantile-regression model.

The proposed data flow is:

`IMU/GNSS -> preprocessing -> 15-state error-state EKF -> road candidates ->`
`road context -> EKF update -> incremental HMM map matching -> navigation estimate`

The previous HMM road belief supplies the next cycle's road candidates. This
prevents the road-context engine from depending on a same-cycle map match that
does not exist yet.

## Explicitly excluded

- Velocity-prediction model architecture, training, and inference. Another team
  owns that component; this backend will later receive its output through an
  adapter boundary.
- Mobile/frontend implementation, map rendering, and UI integration.
- Datasets, trained weights, live traffic services, native/mobile binaries, and
  production algorithms.
- Git initialization, remote configuration, virtual-environment creation, and
  dependency installation.

## Layout

- `src/idr_backend/` contains the future backend packages.
- `configs/` contains commented TOML templates only.
- `docs/` records architecture, decisions, and the future verification strategy.
- `scripts/` reserves future replay, training, and evaluation entry points.
- `tests/` records the test structure and planned scenarios.

Read the package and directory README files before adding behavior. They describe
the intended contracts without prematurely defining stable APIs.

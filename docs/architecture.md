# Backend architecture

## Ownership boundary

The backend owns deterministic phone-sensor navigation, selected ONNX velocity
inference, uncertainty handling, and optional downstream HMM map matching. The
implemented FastAPI service owns the session lifecycle and transport validation;
the BetterMaps React Native client is responsible only for ordered sensor
delivery and presentation. It must not reproduce EKF or model logic.

Road context is a separate, offline-only supporting engine at present. Its
implemented code does not change the live deterministic pipeline or EKF.

## Implemented deterministic runtime order

1. Receive chronological raw accelerometer, gyroscope, and GNSS callbacks.
2. Validate timestamps, units, frames, and quality; synchronize IMU pairs.
3. Estimate orientation, apply mounting calibration, and remove gravity.
4. Build causal clean-IMU windows and selected velocity/uncertainty inputs.
5. Propagate the 15-state error-state EKF, then apply eligible GNSS, velocity,
   and non-holonomic updates.
6. Publish the committed `NavigationEstimate`.
7. Optionally run incremental HMM map matching downstream of that committed
   estimate. It cannot modify the same EKF cycle.

## Implemented offline road-context layer

`src/idr_backend/road_context/` currently provides:

- sparse raw journey facts and offline map-match audit records;
- static legal-directed-edge graph features and a strict model feature boundary;
- deterministic q10/q50/q90 rule validation and candidate-mixture uncertainty;
- road-class empirical and LightGBM static-feature quantile predictors;
- journey-held-out and directed-edge-held-out splits with fold-local,
  journey-balanced weights;
- out-of-fold metric, coverage, calibration-gate, and baseline experiment
  contracts.

`src/idr_backend/pipeline/road_context.py` also implements a decision-only
adapter: it turns an already-completed prior-cycle HMM feedback lookup into an
auditable candidate mixture using static edge features, a compatible predictor,
and deterministic rules. It has no EKF dependency, does not schedule updates,
and is not called by the deterministic runtime yet.

These components use CAN speed only as an offline target. They exclude IMU,
GRU output, EKF speed, runtime CAN, and same-cycle HMM output from learned
features.

## Required future road-context fusion order

Road context may be connected only after real grouped evaluation and replay
gates pass. At cycle `t`, it must consume map-match feedback completed at
`t-1`, then use candidate road features and calibrated quantiles to form a
weak low-rate speed prior:

```text
completed HMM belief at t-1
  -> candidate quantiles + deterministic rules
  -> HMM-weighted mixture and safety gates
  -> optional low-rate road-speed EKF update at t
  -> committed navigation estimate
  -> HMM update for t+1
```

The future update remains optional, rate-limited, NIS-gated, covariance-floored,
and disabled by default. It must never use the current cycle's HMM result.

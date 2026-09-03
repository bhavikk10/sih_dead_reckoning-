# Architecture decisions

## Confirmed

- Python 3.12 is the backend target.
- The deterministic core is designed around a 15-state error-state EKF.
- The velocity predictor is owned externally and enters through an adapter.
- The uncertainty engine is separately owned. It will begin with Gaussian NLL
  training for measurement covariance, with a later option to fine-tune through
  a differentiable EKF trajectory loss.
- Road context is a hybrid of deterministic rules and quantile regression. It
  supplies a soft plausibility prior, never a replacement position estimate.
- Road context consumes the previous HMM belief and candidate roads, avoiding a
  same-cycle map-matching/fusion circular dependency.

## Intentionally unresolved

- LightGBM versus XGBoost is not selected. Both are declared dependencies so a
  future comparison can use one common quantile-model abstraction.
- Exact road city, offline-map extract, dataset sources, and feature schema are
  deferred until data quality is assessed.
- EKF frame convention, tuning, gating policy, and measurement equations are
  deferred until the implementation design stage.
- The scope of external high-rate IMU support is deferred, but adapters and the
  15-state fusion design must not preclude it.

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
- LightGBM is the initial learned road-context quantile implementation. It fits
  separate q10/q50/q90 models over static road features only, with quantile
  ordering repaired at prediction time. The empirical road-class model remains
  the required leakage/debug baseline.
- Road-context model selection uses both journey-held-out and directed-edge-
  held-out folds, with fold-local journey-balanced sample weights.

## Intentionally unresolved

- XGBoost is not yet implemented or compared under the same grouped-fold
  protocol; it remains an optional later challenger, not the selected path.
- Exact road city, offline-map extract, external dataset sources, and the
  optional time/junction/signal feature expansion remain deferred. The initial
  static directed-edge feature schema is implemented.
- EKF frame convention, tuning, gating policy, and measurement equations are
  deferred until the implementation design stage.
- The scope of external high-rate IMU support is deferred, but adapters and the
  15-state fusion design must not preclude it.

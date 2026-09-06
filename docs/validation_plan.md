# Validation status and remaining plan

The repository contains executable deterministic and road-context unit tests.
Passing those tests proves local contracts, not production navigation accuracy
or road-context readiness for fusion.

## Implemented road-context unit evidence

- Dataset/matching/feature tests cover provenance boundaries and static feature
  construction.
- Rules, raw q10/q50/q90 validation, candidate-mixture uncertainty, and
  omission dispositions are unit tested.
- Grouped journey and directed-edge splits, fold-local weights, metrics,
  calibration gates, and the empirical out-of-fold experiment runner are unit
  tested.
- The LightGBM quantile predictor has a dedicated test module; it requires the
  declared LightGBM dependency in the active environment.

## Remaining evidence before functionality is accepted

## Deterministic pipeline

- Reject or explicitly handle out-of-order IMU samples, timestamp gaps, unit
  mismatches, invalid coordinate frames, and calibration-quality changes.
- Validate gravity removal and phone-to-vehicle frame transforms against known
  stationary, acceleration, braking, and turning fixtures.
- Verify error-state EKF covariance symmetry, positive semidefiniteness,
  numerical stability, and recovery after rejected measurements.
- Exercise NHC, GNSS quality gating, blackout mode, and GNSS reacquisition.

## Learned-support engines

- Check positive and bounded uncertainty outputs, Gaussian-NLL behavior,
  calibration curves, and conservative heuristic fallback behavior.
- Check road-context quantile ordering, rule gating, speed-limit quality
  caveats, unseen-road behavior, and disconnected/ambiguous road candidates.
- Build the real first-party road-context table and run both journey-held-out
  and directed-edge-held-out experiments.
- Record p50 MAE, pinball loss, p10-p90 coverage, interval width, and worst
  journey/road-class outcomes. A nominal 80% interval must pass its calibration
  gate on untouched grouped data.
- Compare the empirical baseline and LightGBM under the identical folds before
  selecting or exporting any learned artifact.

## End-to-end replay

- Replay synchronized sensor/GNSS data with controlled blackouts.
- Test HMM ambiguity where parallel roads, service roads, and junctions compete.
- Measure trajectory and endpoint drift, latency, mode transitions, and
  degradation when velocity or road-context inputs are missing.
- Keep road context shadow-only until candidate inference, low-rate injection,
  NIS/covariance/rate gates, and downstream blackout replay all demonstrate a
  non-regressing result.

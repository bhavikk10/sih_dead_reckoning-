# Future validation plan

No tests are implemented in this scaffold. Before functionality is accepted,
the backend must add evidence for the following areas.

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

## End-to-end replay

- Replay synchronized sensor/GNSS data with controlled blackouts.
- Test HMM ambiguity where parallel roads, service roads, and junctions compete.
- Measure trajectory and endpoint drift, latency, mode transitions, and
  degradation when velocity or road-context inputs are missing.

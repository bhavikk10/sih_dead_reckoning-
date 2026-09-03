"""Future deterministic uncertainty safety fallback.

TODO:
- derive conservative covariance scaling from observable roughness, turn rate, timing,
  calibration, and GNSS-quality proxies;
- define lower/upper variance bounds and outlier behavior;
- use the fallback when the learned model is missing, stale, uncalibrated, or rejected;
- ensure the fallback does not claim learned confidence it cannot justify.
"""

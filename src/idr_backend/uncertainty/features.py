"""Future uncertainty-feature construction.

TODO:
- combine velocity output metadata with IMU-window statistics, sensor quality, yaw rate,
  acceleration variance, recent innovations, and calibration confidence;
- prevent leakage of unavailable GNSS ground truth into blackout-time inference;
- define feature freshness and missing-value treatment explicitly;
- version feature definitions alongside datasets and trained artifacts.
"""

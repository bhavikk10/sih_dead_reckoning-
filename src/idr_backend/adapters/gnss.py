"""Future GNSS observation adapter.

TODO:
- map GNSS fixes, velocities, satellite metrics, HDOP, and freshness indicators;
- define coordinate, covariance, timestamp, and invalid-fix conventions;
- distinguish unavailable, degraded, and rejected GNSS from a valid low-confidence fix;
- avoid calling live services or assuming cellular connectivity.
"""

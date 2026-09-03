"""Future cycle-level pipeline orchestration.

TODO:
- define event ordering for IMU, GNSS, velocity, and road-context observations;
- coordinate preprocessing, EKF propagation/update, candidate generation, and HMM updates;
- make missing optional inputs explicit and keep the deterministic backbone operational;
- measure latency and queue backpressure without inventing asynchronous behavior yet.
"""

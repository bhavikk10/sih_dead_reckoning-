"""Future asynchronous EKF measurement-update boundary.

TODO:
- specify GNSS position/velocity, external velocity, and road-context measurement models;
- validate observation timestamps, frame compatibility, covariance, and freshness;
- centralize innovation calculation, gating, rejection reasons, and accepted-update traces;
- ensure road context remains a weak probabilistic prior rather than a position substitute.
"""

"""Future optional differentiable-EKF fine-tuning boundary.

TODO:
- wrap a validated EKF update path for trajectory-level gradient computation;
- retain a separately testable Gaussian-NLL training path as the baseline;
- define gradient clipping, rollout length, and numerical failure handling;
- treat this as an enhancement, not a replacement for deterministic fusion validation.
"""

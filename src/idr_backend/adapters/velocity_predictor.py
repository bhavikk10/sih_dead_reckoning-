"""Future adapter for the separately owned velocity-prediction component.

TODO:
- define a versioned observation handoff containing speed, timestamp, frame, and metadata;
- accept optional predictor confidence without requiring it;
- reject stale, unit-ambiguous, or unsupported model outputs;
- leave model architecture, inference, weights, and training outside this repository.
"""

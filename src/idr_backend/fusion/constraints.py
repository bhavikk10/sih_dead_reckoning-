"""Future physical pseudo-measurements, including non-holonomic constraints.

TODO:
- express lateral and vertical vehicle velocity constraints with documented assumptions;
- define when skids, phone-motion anomalies, or poor calibration disable NHC updates;
- keep constraints separate from learned measurements for transparent tuning and diagnostics;
- validate behavior against turns, slopes, bumps, and deliberately adversarial fixtures.
"""

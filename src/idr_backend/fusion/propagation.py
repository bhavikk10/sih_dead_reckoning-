"""Future inertial propagation for the error-state EKF.

TODO:
- propagate nominal state using normalized, calibrated inertial observations;
- derive the discrete error-state transition and process-noise model;
- support variable sample periods and conservative behavior around timing gaps;
- retain propagation diagnostics for replay and numerical-stability analysis.
"""

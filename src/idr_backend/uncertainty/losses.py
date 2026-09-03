"""Future uncertainty-model objectives.

TODO:
- implement Gaussian negative log likelihood against velocity residuals;
- define variance parameterization, numerical floors, and reduction policy;
- add calibration diagnostics and penalties only when supported by held-out evidence;
- avoid using trajectory loss here until the differentiable-fusion path is specified.
"""

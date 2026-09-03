"""Future uncertainty-data preparation and training orchestration.

TODO:
- derive velocity labels and residuals from approved synchronized datasets;
- split by drive, device, route, and source before windowing to prevent leakage;
- track dataset provenance, units, transforms, and model-calibration metadata;
- leave all dataset loading and experiment execution unimplemented for now.
"""

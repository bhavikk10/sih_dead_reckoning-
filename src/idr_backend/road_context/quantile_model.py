"""Future quantile-regression abstraction for road-context speed ranges.

TODO:
- expose one backend-neutral interface for ordered low/median/high speed quantiles;
- compare LightGBM and XGBoost under the same data splits and calibration metrics;
- preserve model provenance, feature schema, and quantile-monotonicity checks;
- do not select a library or implement inference in the scaffold.
"""

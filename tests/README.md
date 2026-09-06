# Test layout

Executable tests cover deterministic contracts and the implemented offline
road-context layer. The directories retain these boundaries:

- `unit/`: isolated math, data validation, feature, and rule tests.
- `integration/`: asynchronous pipeline, replay, fusion, and map-matching tests.
- `fixtures/`: synthetic and licensed test-only sensor, GNSS, graph, and dataset
  fixtures. Do not place production, private, or unlicensed data here.

Road-context unit tests currently cover dataset/feature preparation, rules,
candidate mixtures, grouped splits, training weights, evaluation/calibration,
the empirical experiment runner, and the LightGBM predictor. Remaining replay
and runtime-fusion evidence is listed in `docs/validation_plan.md`.

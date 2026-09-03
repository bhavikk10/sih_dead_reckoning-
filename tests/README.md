# Test layout

No executable tests are included while the project contains only documentation
stubs. The directories below reserve the intended test boundaries:

- `unit/`: isolated math, data validation, feature, and rule tests.
- `integration/`: asynchronous pipeline, replay, fusion, and map-matching tests.
- `fixtures/`: synthetic and licensed test-only sensor, GNSS, graph, and dataset
  fixtures. Do not place production, private, or unlicensed data here.

The validation scenarios are listed in `docs/validation_plan.md`.

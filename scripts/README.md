# Command entry points

- `replay.py` is runnable. It replays a designated raw journey through the
  deterministic navigation pipeline and writes a JSON report. See the root
  README or `docs/backend_flutter_integration.md` for commands.

The following command wrappers do not exist yet. Their logic is currently
being developed as library-level road-context components and must not be
described as runnable scripts:

- `train_uncertainty.py`: train and calibrate the uncertainty model.
- `train_road_context.py`: build the real road-context dataset and compare
  empirical/LightGBM quantile models under grouped folds.
- `evaluate.py`: calculate consolidated drift, calibration, map-matching, and
  latency metrics.

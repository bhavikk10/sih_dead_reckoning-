# Unit tests

Unit tests cover individual preprocessing, fusion, uncertainty, map-matching,
and offline road-context contracts. Add behavior and its tests together; do not
add tests that assert fabricated placeholder outputs.

Road-context tests are intentionally synthetic: they verify leakage boundaries,
mathematical contracts, and deterministic behavior without treating synthetic
numbers as model-performance evidence.

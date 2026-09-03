"""Future next-cycle feedback between map matching and road context.

TODO:
- persist the prior HMM belief and candidate provenance after each accepted cycle;
- provide it to future road-context prior construction on the following cycle;
- prevent same-timestep circular dependencies and stale-belief misuse;
- define reset behavior when graph coverage, state, or map-match confidence is lost.
"""

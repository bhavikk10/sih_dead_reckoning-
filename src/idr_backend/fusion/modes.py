"""Future GNSS-aided, degraded, dead-reckoning, and recovery mode management.

TODO:
- define transitions from GNSS quality, data freshness, innovation health, and elapsed blackout time;
- use measurement weighting and gating rather than abrupt coordinate jumps;
- record transition reasons for UI and replay diagnostics;
- coordinate mode state with map matching and optional road-context availability.
"""

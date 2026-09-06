"""Offline raw-data replay and development-only navigation tuning.

This package is intentionally an evaluation boundary, not a live-data adapter.
It replays the public paired phone/CAN recordings through the same production
objects used at runtime, applies controlled GNSS blackouts, and records the
resulting diagnostics without allowing CAN labels into the filter.
"""

from .replay import (
    BlackoutScenario,
    ReplayParameterSet,
    RawReplayJourney,
    load_raw_replay_journey,
    replay_journey,
)

__all__ = (
    "BlackoutScenario",
    "ReplayParameterSet",
    "RawReplayJourney",
    "load_raw_replay_journey",
    "replay_journey",
)

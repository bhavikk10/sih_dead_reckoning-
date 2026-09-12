"""Network service boundary for the deterministic IDR navigation runtime.

The service owns session lifecycle and JSON/WebSocket transport only.  It does
not alter preprocessing, fusion, selected-model, or road-context behaviour.
"""

from .api import create_app

__all__ = ("create_app",)

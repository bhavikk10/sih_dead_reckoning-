"""Public runtime boundaries for IDR integration.

The windowed anchor-delta GRU is the selected velocity artifact: it outperformed
the stateful experiment on the frozen test set. Stateful experiment modules
remain available by their explicit module paths for research, but are not
exported here and cannot be mistaken for the runtime default.
"""

from .anchor_delta_gru import (
    AnchorDeltaGruArtifact,
    AnchorDeltaGruPredictor,
    load_anchor_delta_gru_adapter,
)
__all__ = [
    "AnchorDeltaGruArtifact",
    "AnchorDeltaGruPredictor",
    "load_anchor_delta_gru_adapter",
]

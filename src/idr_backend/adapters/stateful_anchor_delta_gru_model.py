"""PyTorch mirror of the selected stateful anchor-delta GRU for ONNX export.

The runtime never imports this module.  It exists solely so the exporter can
load the experiment checkpoint into a small, explicit recurrent ONNX graph.
"""

from __future__ import annotations

import torch
from torch import nn


class StatefulAnchorDeltaGruNetwork(nn.Module):
    """Causal GRU producing one anchor-relative speed delta per IMU sample."""

    def __init__(
        self,
        *,
        feature_count: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=feature_count,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=False,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(
        self,
        features: torch.Tensor,
        hidden_state: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return each delta-v prediction and the state for the next call."""

        encoded, next_hidden_state = self.gru(features, hidden_state)
        return self.head(encoded).squeeze(-1), next_hidden_state

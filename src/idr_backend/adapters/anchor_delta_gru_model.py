"""Exact PyTorch architecture used only to export the selected GRU to ONNX."""

import torch
from torch import nn


class AnchorDeltaGruNetwork(nn.Module):
    """Mirror the selected experiment GRU without importing notebook code."""

    def __init__(
        self,
        *,
        hidden_size: int,
        num_layers: int,
        bidirectional: bool,
        dropout: float,
        context_dimension: int = 5,
    ) -> None:
        """Construct the selected six-channel, context-aware speed-delta GRU."""

        super().__init__()
        self.gru = nn.GRU(
            input_size=6,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=bidirectional,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        encoded_size = hidden_size * (2 if bidirectional else 1)
        self.context = nn.Sequential(
            nn.Linear(context_dimension, 16),
            nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(encoded_size + 16, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(
        self,
        imu_window: torch.Tensor,
        context: torch.Tensor,
    ) -> torch.Tensor:
        """Return predicted speed delta from the trusted GNSS anchor in m/s."""

        _, hidden = self.gru(imu_window)
        directions = 2 if self.gru.bidirectional else 1
        encoded = hidden[-directions:].transpose(0, 1).reshape(
            imu_window.shape[0],
            -1,
        )
        encoded = torch.cat([encoded, self.context(context)], dim=1)
        return self.head(encoded).squeeze(1)

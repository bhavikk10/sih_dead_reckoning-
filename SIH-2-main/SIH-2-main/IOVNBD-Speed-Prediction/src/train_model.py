"""
Step 5: Main AI model - GRU regressor.

Architecture:
    IMU sequence (batch, 20, 6)
        -> GRU (2 layers, hidden_size=64, dropout=0.2)
        -> take final timestep's hidden state
        -> Dense(64 -> 32) + ReLU
        -> Dense(32 -> 1)
        -> Predicted vehicle speed (batch, 1)

Why GRU over LSTM
------------------
GRU has fewer parameters than LSTM (no separate cell state / no output
gate) while typically matching LSTM performance on short sequences like
ours (20 timesteps / 2 seconds). Given the modest dataset size (~14.8k
training windows) and the CPU-only compatibility requirement, GRU trains
faster and is less prone to overfitting here, so it's the more appropriate
choice for this lightweight prototype stage.

Runs on GPU automatically if available, otherwise CPU (see `device`
below).
"""
import os
import sys
import json
import time

import numpy as np
import joblib
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

torch.manual_seed(cfg.RANDOM_SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(cfg.RANDOM_SEED)


class GRUSpeedRegressor(nn.Module):
    def __init__(self, n_features, hidden_size=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.gru = nn.GRU(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        out, h_n = self.gru(x)          # out: (batch, timesteps, hidden)
        last = out[:, -1, :]            # final timestep's hidden state ("now")
        return self.head(last).squeeze(-1)


def _load_windows():
    path = os.path.join(cfg.PROCESSED_DATA_DIR, "windows.npz")
    if not os.path.exists(path):
        from create_sequences import create_sequences
        create_sequences()
    d = np.load(path)
    return d["X_train"], d["y_train"], d["X_val"], d["y_val"], d["X_test"], d["y_test"]


def train_model(
    hidden_size=64,
    num_layers=2,
    dropout=0.2,
    lr=5e-4,
    batch_size=64,
    max_epochs=100,
    patience=12,
):
    X_train, y_train, X_val, y_val, X_test, y_test = _load_windows()
    n_features = X_train.shape[2]

    # Load the target scaler (fit on TRAIN ONLY in create_sequences.py) and
    # scale targets for training stability; metrics are always computed
    # after inverse-transforming back to km/h.
    target_scaler_path = os.path.join(cfg.ARTIFACTS_DIR, "target_scaler.joblib")
    target_scaler = joblib.load(target_scaler_path)
    y_train_s = target_scaler.transform(y_train.reshape(-1, 1)).astype(np.float32).ravel()
    y_val_s = target_scaler.transform(y_val.reshape(-1, 1)).astype(np.float32).ravel()

    print("=" * 70)
    print("MAIN MODEL: GRU")
    print("=" * 70)
    print(f"Device: {device}")
    print(f"Input shape: (batch, {X_train.shape[1]} timesteps, {n_features} features)")
    print("Target (vehicle speed) is standardized for training; metrics reported in km/h.")

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train_s))
    val_ds = TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val_s))
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    model = GRUSpeedRegressor(n_features, hidden_size, num_layers, dropout).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None
    epochs_no_improve = 0
    history = {"train_loss": [], "val_loss": []}

    t0 = time.time()
    for epoch in range(1, max_epochs + 1):
        model.train()
        train_losses = []
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            train_losses.append(loss.item())

        model.eval()
        val_losses = []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                val_losses.append(criterion(pred, yb).item())

        train_loss = float(np.mean(train_losses))
        val_loss = float(np.mean(val_losses))
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        print(f"Epoch {epoch:3d}/{max_epochs}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}")

        if val_loss < best_val_loss - 1e-4:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                print(f"Early stopping at epoch {epoch} (no improvement for {patience} epochs)")
                break

    train_time = time.time() - t0
    print(f"\nTotal training time: {train_time:.1f}s")

    if best_state is not None:
        model.load_state_dict(best_state)

    os.makedirs(cfg.MODELS_DIR, exist_ok=True)
    model_path = os.path.join(cfg.MODELS_DIR, "gru_speed_model.pt")
    torch.save({
        "model_state_dict": model.state_dict(),
        "n_features": n_features,
        "hidden_size": hidden_size,
        "num_layers": num_layers,
        "dropout": dropout,
        "window_size": X_train.shape[1],
    }, model_path)
    print(f"Saved GRU model -> {model_path}")

    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    with open(os.path.join(cfg.RESULTS_DIR, "training_history.json"), "w") as f:
        json.dump(history, f, indent=2)

    config_out = {
        "feature_names": cfg.FEATURE_COLUMNS,
        "target_name": cfg.TARGET_COLUMN,
        "sampling_rate_hz": cfg.SAMPLING_RATE_HZ,
        "window_duration_s": cfg.WINDOW_DURATION_S,
        "window_size_timesteps": cfg.WINDOW_SIZE,
        "window_stride": cfg.WINDOW_STRIDE,
        "normalization": "StandardScaler (mean/std), fit on training split only",
        "model": {
            "type": "GRU",
            "hidden_size": hidden_size,
            "num_layers": num_layers,
            "dropout": dropout,
            "learning_rate": lr,
            "batch_size": batch_size,
            "max_epochs": max_epochs,
            "patience": patience,
            "epochs_trained": len(history["train_loss"]),
            "best_val_loss_mse": best_val_loss,
            "device_used": str(device),
        },
    }
    with open(os.path.join(cfg.ARTIFACTS_DIR, "config.json"), "w") as f:
        json.dump(config_out, f, indent=2)
    print(f"Saved run configuration -> {os.path.join(cfg.ARTIFACTS_DIR, 'config.json')}")

    return model, history


if __name__ == "__main__":
    train_model()

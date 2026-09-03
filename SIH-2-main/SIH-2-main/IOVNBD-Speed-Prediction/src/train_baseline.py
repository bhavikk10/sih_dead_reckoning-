"""
Step 4: Baseline model.

A Random Forest Regressor trained on simple per-window statistical
features (mean, std, min, max) of each of the 6 IMU channels, i.e. 24
features per window. This gives a fast, interpretable baseline to compare
the LSTM/GRU against.
"""
import os
import sys
import json
import time

import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg


def _load_windows():
    path = os.path.join(cfg.PROCESSED_DATA_DIR, "windows.npz")
    if not os.path.exists(path):
        from create_sequences import create_sequences
        create_sequences()
    d = np.load(path)
    return d["X_train"], d["y_train"], d["X_val"], d["y_val"], d["X_test"], d["y_test"]


def _window_stats_features(X: np.ndarray) -> np.ndarray:
    """X: (n, timesteps, features) -> (n, features*4) using mean/std/min/max
    per channel across the window."""
    mean = X.mean(axis=1)
    std = X.std(axis=1)
    mn = X.min(axis=1)
    mx = X.max(axis=1)
    return np.concatenate([mean, std, mn, mx], axis=1)


def train_baseline():
    X_train, y_train, X_val, y_val, X_test, y_test = _load_windows()

    Xtr = _window_stats_features(X_train)
    Xva = _window_stats_features(X_val)
    Xte = _window_stats_features(X_test)

    print("=" * 70)
    print("BASELINE MODEL: Random Forest Regressor")
    print("=" * 70)
    print(f"Feature matrix (train): {Xtr.shape}  (24 stats features: mean/std/min/max x 6 channels)")

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=16,
        min_samples_leaf=3,
        n_jobs=-1,
        random_state=cfg.RANDOM_SEED,
    )

    t0 = time.time()
    model.fit(Xtr, y_train)
    train_time = time.time() - t0
    print(f"Training time: {train_time:.1f}s")

    val_pred = model.predict(Xva)
    test_pred = model.predict(Xte)

    def metrics(y_true, y_pred):
        return {
            "MAE": float(mean_absolute_error(y_true, y_pred)),
            "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "R2": float(r2_score(y_true, y_pred)),
        }

    val_m = metrics(y_val, val_pred)
    test_m = metrics(y_test, test_pred)

    print("\nValidation metrics:", val_m)
    print("Test metrics      :", test_m)

    os.makedirs(cfg.MODELS_DIR, exist_ok=True)
    model_path = os.path.join(cfg.MODELS_DIR, "baseline_random_forest.joblib")
    joblib.dump(model, model_path)
    print(f"\nSaved baseline model -> {model_path}")

    os.makedirs(cfg.RESULTS_DIR, exist_ok=True)
    results = {"validation": val_m, "test": test_m, "train_time_s": train_time}
    with open(os.path.join(cfg.RESULTS_DIR, "baseline_metrics.json"), "w") as f:
        json.dump(results, f, indent=2)

    np.savez(
        os.path.join(cfg.RESULTS_DIR, "baseline_test_predictions.npz"),
        y_true=y_test, y_pred=test_pred,
    )

    return model, results


if __name__ == "__main__":
    train_baseline()

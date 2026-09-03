"""
Step 6: Evaluation and required plots.

Evaluates the trained GRU model on the held-out TEST set only, computes
MAE/RMSE/R2/max-abs-error, and generates all required plots under
results/plots/. Works whether the test set is one held-out chronological
slice (single-sequence fallback) or one or more whole held-out sequences
(multi-sequence split).
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg
from train_model import GRUSpeedRegressor, device


def _load_windows():
    path = os.path.join(cfg.PROCESSED_DATA_DIR, "windows.npz")
    return np.load(path, allow_pickle=True)


def _load_clean_df():
    parquet_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.parquet")
    csv_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.csv")
    if os.path.exists(parquet_path):
        return pd.read_parquet(parquet_path)
    return pd.read_csv(csv_path, parse_dates=["timestamp"])


def _metrics(y_true, y_pred):
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
        "max_abs_error": float(np.max(np.abs(y_true - y_pred))),
    }


def evaluate():
    os.makedirs(cfg.PLOTS_DIR, exist_ok=True)

    d = _load_windows()
    X_test, y_test = d["X_test"], d["y_test"]
    t_test, seq_test = d["t_test"], d["seq_test"]

    # --- load GRU model ------------------------------------------------
    ckpt_path = os.path.join(cfg.MODELS_DIR, "gru_speed_model.pt")
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model = GRUSpeedRegressor(
        ckpt["n_features"], ckpt["hidden_size"], ckpt["num_layers"], ckpt["dropout"]
    ).to(device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    target_scaler = joblib.load(os.path.join(cfg.ARTIFACTS_DIR, "target_scaler.joblib"))

    with torch.no_grad():
        test_pred_scaled = model(torch.from_numpy(X_test).to(device)).cpu().numpy()
    test_pred = target_scaler.inverse_transform(test_pred_scaled.reshape(-1, 1)).ravel()

    gru_metrics = _metrics(y_test, test_pred)

    # skip MAPE-style metric entirely: many test speeds are 0 km/h, so
    # percentage error is undefined/explodes near zero (see task notes).

    print("=" * 70)
    print("TEST SET EVALUATION (GRU)")
    print("=" * 70)
    print(f"Test sequences: {sorted(set(seq_test.tolist())) if len(seq_test) else '(none)'}")
    for k, v in gru_metrics.items():
        print(f"  {k:15s}: {v:.4f}")

        with open(os.path.join(cfg.RESULTS_DIR, "gru_test_metrics.json"), "w") as f:
          json.dump(gru_metrics, f, indent=2)
        np.savez(os.path.join(cfg.RESULTS_DIR, "gru_test_predictions.npz"), y_true=y_test, y_pred=test_pred)

    # Human-readable CSV of every test-set prediction (easy to open in
    # Excel/VS Code, unlike the .npz above).
        pred_csv = pd.DataFrame({
         "sequence_id": seq_test,
         "timestamp": pd.to_datetime(t_test),
         "actual_speed_kmh": y_test,
         "predicted_speed_kmh": test_pred,
         "error_kmh": test_pred - y_test,
    }).sort_values(["sequence_id", "timestamp"]).reset_index(drop=True)
        pred_csv_path = os.path.join(cfg.RESULTS_DIR, "predictions.csv")
        pred_csv.to_csv(pred_csv_path, index=False)
        print(f"Saved human-readable predictions -> {pred_csv_path}")
    # --- combined results table -----------------------------------------
        baseline_metrics_path = os.path.join(cfg.RESULTS_DIR, "baseline_metrics.json")
        combined = {"gru": gru_metrics}
        if os.path.exists(baseline_metrics_path):
            with open(baseline_metrics_path) as f:
                combined["baseline_random_forest"] = json.load(f)["test"]
        with open(os.path.join(cfg.RESULTS_DIR, "final_results.json"), "w") as f:
            json.dump(combined, f, indent=2)

    # =====================================================================
    # PLOTS
    # =====================================================================
    df = _load_clean_df()
    sequence_names = list(df["sequence_id"].unique())
    multi = len(sequence_names) > 1

    # Build a common x-axis (sample index) with sequence-boundary markers,
    # since raw timestamps are not comparable across different recordings.
    df_sorted_parts = []
    boundaries = []
    offset = 0
    for name in sequence_names:
        sub = df[df["sequence_id"] == name].sort_values("timestamp").reset_index(drop=True)
        sub = sub.copy()
        sub["_x"] = np.arange(len(sub)) + offset
        boundaries.append((offset, name))
        offset += len(sub)
        df_sorted_parts.append(sub)
    df_plot = pd.concat(df_sorted_parts, ignore_index=True)

    def _mark_boundaries(ax):
        if multi:
            for pos, name in boundaries[1:]:
                ax.axvline(pos, color="gray", linestyle=":", linewidth=0.8)
            for pos, name in boundaries:
                ax.text(pos, ax.get_ylim()[1], f" {name}", fontsize=7, va="top", rotation=90)

    xlabel = "Sample index (dotted lines = sequence boundaries)" if multi else "Time"
    x_axis = df_plot["_x"] if multi else df_plot["timestamp"]

    # Plot 1: Accelerometer vs time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(x_axis, df_plot["acc_x"], label="acc_x", linewidth=0.4)
    ax.plot(x_axis, df_plot["acc_y"], label="acc_y", linewidth=0.4)
    ax.plot(x_axis, df_plot["acc_z"], label="acc_z", linewidth=0.4)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Acceleration (m/s^2)")
    ax.set_title("Accelerometer X/Y/Z vs Time" + (f" ({len(sequence_names)} sequences)" if multi else ""))
    ax.legend()
    _mark_boundaries(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "01_accelerometer_vs_time.png"), dpi=120)
    plt.close(fig)

    # Plot 2: Gyroscope vs time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(x_axis, df_plot["gyro_x"], label="gyro_x (roll)", linewidth=0.4)
    ax.plot(x_axis, df_plot["gyro_y"], label="gyro_y (pitch)", linewidth=0.4)
    ax.plot(x_axis, df_plot["gyro_z"], label="gyro_z (yaw)", linewidth=0.4)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Angular rate (rad/s)")
    ax.set_title("Gyroscope X/Y/Z vs Time" + (f" ({len(sequence_names)} sequences)" if multi else ""))
    ax.legend()
    _mark_boundaries(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "02_gyroscope_vs_time.png"), dpi=120)
    plt.close(fig)

    # Plot 3: Ground-truth vehicle speed vs time
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(x_axis, df_plot["vehicle_speed"], linewidth=0.5, color="darkgreen")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Vehicle speed (km/h)")
    ax.set_title("Ground-truth Vehicle Speed vs Time" + (f" ({len(sequence_names)} sequences)" if multi else " (full sequence)"))
    _mark_boundaries(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "03_groundtruth_speed_vs_time.png"), dpi=120)
    plt.close(fig)

    # Plot 4: Training loss vs validation loss
    with open(os.path.join(cfg.RESULTS_DIR, "training_history.json")) as f:
        history = json.load(f)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(history["train_loss"], label="train loss (MSE)")
    ax.plot(history["val_loss"], label="val loss (MSE)")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE loss")
    ax.set_title("GRU Training vs Validation Loss")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "04_train_val_loss.png"), dpi=120)
    plt.close(fig)

    # Plots 5-7 use the TEST windows directly, ordered by (sequence, time)
    # using the timestamps/sequence ids saved by create_sequences.py - this
    # works correctly regardless of split strategy.
    order = np.lexsort((t_test.astype("datetime64[ns]").astype(np.int64), seq_test))
    y_true_o = y_test[order]
    y_pred_o = test_pred[order]
    seq_o = seq_test[order]

    # x-axis: sample index within the ordered test set, with boundaries
    # between different test sequences marked
    test_x = np.arange(len(y_true_o))
    test_boundaries = []
    if len(seq_o):
        prev = seq_o[0]
        test_boundaries.append((0, prev))
        for i in range(1, len(seq_o)):
            if seq_o[i] != prev:
                test_boundaries.append((i, seq_o[i]))
                prev = seq_o[i]

    def _mark_test_boundaries(ax):
        if multi and len(test_boundaries) > 1:
            for pos, name in test_boundaries[1:]:
                ax.axvline(pos, color="gray", linestyle=":", linewidth=0.8)

    test_xlabel = "Test window index (ordered by sequence, then time)" if multi else "Time (test set)"

    # Plot 5: Ground-truth vs predicted speed over time (MOST IMPORTANT)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(test_x, y_true_o, label="Ground truth", linewidth=1.0)
    ax.plot(test_x, y_pred_o, label="GRU prediction", linewidth=1.0, alpha=0.8)
    ax.set_xlabel(test_xlabel)
    ax.set_ylabel("Vehicle speed (km/h)")
    ax.set_title("Test Set: Ground-truth vs Predicted Vehicle Speed")
    ax.legend()
    _mark_test_boundaries(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "05_groundtruth_vs_predicted_speed.png"), dpi=120)
    plt.close(fig)

    # Plot 6: Prediction error vs time
    error = y_pred_o - y_true_o
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(test_x, error, linewidth=0.7, color="firebrick")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel(test_xlabel)
    ax.set_ylabel("Prediction error (km/h)")
    ax.set_title("Prediction Error vs Time (predicted - actual)")
    _mark_test_boundaries(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "06_prediction_error_vs_time.png"), dpi=120)
    plt.close(fig)

    # Plot 7: Ground-truth vs predicted scatter with y=x line
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_test, test_pred, s=4, alpha=0.4)
    lims = [min(y_test.min(), test_pred.min()), max(y_test.max(), test_pred.max())]
    ax.plot(lims, lims, color="red", linestyle="--", label="y = x (ideal)")
    ax.set_xlabel("Ground-truth speed (km/h)")
    ax.set_ylabel("Predicted speed (km/h)")
    ax.set_title("Ground-truth vs Predicted Speed (Test Set)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "07_scatter_groundtruth_vs_predicted.png"), dpi=120)
    plt.close(fig)

    # Bonus: GPS trajectory plot for data verification (GPS exists in S-file)
    from inspect_data import load_all_raw
    all_raw = load_all_raw()
    fig, ax = plt.subplots(figsize=(6, 6))
    for name, (s_raw, _) in all_raw.items():
        ax.plot(s_raw[cfg.S_COLS["gps_lon"]], s_raw[cfg.S_COLS["gps_lat"]], linewidth=0.5, label=name)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("GPS Trajectory (Smartphone) - Data Verification")
    ax.set_aspect("equal", adjustable="datalim")
    if multi:
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(cfg.PLOTS_DIR, "08_gps_trajectory.png"), dpi=120)
    plt.close(fig)

    print(f"\nAll plots saved to {cfg.PLOTS_DIR}")
    return gru_metrics


if __name__ == "__main__":
    evaluate()

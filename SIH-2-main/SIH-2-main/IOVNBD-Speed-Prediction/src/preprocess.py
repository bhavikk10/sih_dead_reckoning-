"""
Step 2: Preprocessing.

Takes every discovered S-<name>.csv / V-<name>.csv pair and produces one
clean, standardized dataframe (all sequences concatenated) with columns:

    sequence_id, timestamp, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z, vehicle_speed

Each sequence is cleaned INDEPENDENTLY (its own timestamp parsing,
duplicate/NaN handling) before being concatenated, so no cleaning step
ever mixes rows across two different recordings.

Preprocessing steps (each with a stated reason), applied per sequence:

1. Parse timestamps from the S-file DATE column (the only reliable,
   monotonic timestamp source - see inspect_data.py notes).
2. Sort by timestamp (defensive; data was already monotonic on inspection,
   but we do not assume this holds for future data drops).
3. Row-align S and V. Every sequence pair was confirmed (inspect_data.py)
   to have matching row counts, consistent with them being the
   pre-synchronized "Synchronised V and S dataset" pairs. We therefore
   treat row index as the synchronization key within each sequence (row i
   of S == row i of V), matching how the dataset publishers describe this
   folder.
4. Drop rows with missing/NaN/infinite values in any feature or target
   column (guards against future data drops that may contain gaps).
5. Remove exact duplicate timestamps (guarded for, per sequence).
6. Unit verification: acceleration is already in m/s^2, gyroscope in
   rad/s, target speed in km/h - matching the mapping documented in
   config.py. No unit conversion needed.
7. Light sensor filtering: NONE applied by default (kept conservative, as
   instructed). A commented-out optional low-pass filter hook is provided
   for future experimentation but is OFF by default so raw dynamics are
   preserved for the model to learn from.
8. Feature scaling (StandardScaler) is fit ONLY on the training split's
   rows inside create_sequences.py (not here), to avoid any leakage from
   validation/test sequences into the training statistics.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg
from inspect_data import load_all_raw


def _preprocess_one(name: str, s: pd.DataFrame, v: pd.DataFrame, apply_lowpass: bool = False) -> pd.DataFrame:
    timestamp = pd.to_datetime(s[cfg.S_COLS["date"]], format=cfg.DATE_FORMAT)

    df = pd.DataFrame({
        "sequence_id": name,
        "timestamp": timestamp,
        "acc_x": s[cfg.S_COLS["acc_x"]].astype(float),
        "acc_y": s[cfg.S_COLS["acc_y"]].astype(float),
        "acc_z": s[cfg.S_COLS["acc_z"]].astype(float),
        "gyro_x": s[cfg.S_COLS["gyro_x"]].astype(float),
        "gyro_y": s[cfg.S_COLS["gyro_y"]].astype(float),
        "gyro_z": s[cfg.S_COLS["gyro_z"]].astype(float),
        "vehicle_speed": v[cfg.V_COLS["vehicle_speed"]].astype(float),
    })

    n_before = len(df)

    df = df.sort_values("timestamp").reset_index(drop=True)

    n_dup = int(df["timestamp"].duplicated().sum())
    if n_dup > 0:
        df = df.drop_duplicates(subset="timestamp", keep="first").reset_index(drop=True)

    numeric_cols = [c for c in df.columns if c not in ("timestamp", "sequence_id")]
    n_nan = int(df[numeric_cols].isna().sum().sum())
    n_inf = int(np.isinf(df[numeric_cols]).sum().sum())
    if n_nan > 0 or n_inf > 0:
        df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
        df = df.dropna(subset=numeric_cols).reset_index(drop=True)

    n_after = len(df)

    if apply_lowpass:
        from scipy.signal import butter, filtfilt
        b, a = butter(N=2, Wn=3.0 / (cfg.SAMPLING_RATE_HZ / 2), btype="low")
        for c in ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]:
            df[c] = filtfilt(b, a, df[c].values)

    print(f"  [{name}] rows before={n_before}  dup_removed={n_dup}  "
          f"nan_inf_removed={n_before - n_dup - n_after}  rows after={n_after}")

    return df


def preprocess(apply_lowpass: bool = False) -> pd.DataFrame:
    all_raw = load_all_raw()

    print("=" * 70)
    print("PREPROCESSING SUMMARY (per sequence)")
    print("=" * 70)

    cleaned = []
    for name, (s, v) in all_raw.items():
        cleaned.append(_preprocess_one(name, s, v, apply_lowpass=apply_lowpass))

    df = pd.concat(cleaned, ignore_index=True)

    print(f"\nSequences processed : {len(cleaned)}")
    print(f"Total rows (all sequences): {len(df)}")
    print(f"Low-pass filter applied: {apply_lowpass}")
    print(f"Columns: {list(df.columns)}")

    os.makedirs(cfg.PROCESSED_DATA_DIR, exist_ok=True)
    out_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.parquet")
    try:
        df.to_parquet(out_path, index=False)
    except Exception:
        out_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.csv")
        df.to_csv(out_path, index=False)
    print(f"Saved cleaned dataframe -> {out_path}")

    return df


if __name__ == "__main__":
    preprocess()

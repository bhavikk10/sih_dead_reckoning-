"""
Step 1: Dataset inspection.

Auto-discovers every matched S-<name>.csv / V-<name>.csv pair under
data/raw/ and inspects each one (structure, sampling rate, duration,
missing values, duplicate timestamps, speed range).

Run directly:
    python src/inspect_data.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg


def load_raw_pair(s_path: str, v_path: str):
    s = pd.read_csv(s_path, encoding="latin1")
    v = pd.read_csv(v_path, encoding="latin1")
    s.columns = [c.strip() for c in s.columns]
    v.columns = [c.strip() for c in v.columns]
    return s, v


def load_raw():
    """Backward-compatible helper: loads the FIRST discovered sequence
    pair. Prefer load_all_raw() for multi-sequence use."""
    pairs = cfg.discover_sequence_pairs()
    if not pairs:
        raise FileNotFoundError(
            f"No matched S-*.csv / V-*.csv pairs found in {cfg.RAW_DATA_DIR}.\n"
            f"Place real (non-Git-LFS-pointer) files there, e.g. S-M.csv + V-M.csv."
        )
    name, s_path, v_path = pairs[0]
    return load_raw_pair(s_path, v_path)


def load_all_raw():
    """Loads every discovered sequence pair. Returns a dict:
    {sequence_name: (s_df, v_df)}"""
    pairs = cfg.discover_sequence_pairs()
    if not pairs:
        raise FileNotFoundError(
            f"No matched S-*.csv / V-*.csv pairs found in {cfg.RAW_DATA_DIR}.\n"
            f"Place real (non-Git-LFS-pointer) files there, e.g. S-M.csv + V-M.csv."
        )
    out = {}
    for name, s_path, v_path in pairs:
        out[name] = load_raw_pair(s_path, v_path)
    return out


def _inspect_one(name, s, v):
    print("\n" + "-" * 70)
    print(f"SEQUENCE: {name}")
    print("-" * 70)
    print(f"  S-file shape   : {s.shape}")
    print(f"  V-file shape   : {v.shape}")

    same_len = len(s) == len(v)
    print(f"  Row counts match (S == V): {same_len} ({len(s)} vs {len(v)})")

    print("  Missing values (S):", int(s.isna().sum().sum()))
    print("  Missing values (V):", int(v.isna().sum().sum()))

    s_num = s.select_dtypes(include=[np.number])
    v_num = v.select_dtypes(include=[np.number])
    print("  Infinite values (S):", int(np.isinf(s_num).sum().sum()))
    print("  Infinite values (V):", int(np.isinf(v_num).sum().sum()))

    dt = pd.to_datetime(s[cfg.S_COLS["date"]], format=cfg.DATE_FORMAT)
    dup_dates = int(dt.duplicated().sum())
    diffs = dt.diff().dt.total_seconds().dropna()
    duration_s = (dt.iloc[-1] - dt.iloc[0]).total_seconds()

    print(f"  Duration (s)   : {duration_s:.1f}  (~{duration_s/60:.1f} min)")
    print(f"  Duplicate dates: {dup_dates}")
    if len(diffs):
        print(f"  Median sample period (s): {diffs.median():.4f}  "
              f"(~{1.0/diffs.median():.2f} Hz)")
        print(f"  Gaps > 0.5s    : {int((diffs > 0.5).sum())}")

    speed = v[cfg.V_COLS["vehicle_speed"]]
    print(f"  Speed range (km/h): min={speed.min():.2f} max={speed.max():.2f} mean={speed.mean():.2f}")
    print(f"  % near-zero speed (<1 km/h): {(speed < 1).mean()*100:.1f}%")

    return {
        "name": name,
        "n_rows": len(s),
        "duration_s": duration_s,
        "sampling_hz": 1.0 / diffs.median() if len(diffs) else float("nan"),
        "dup_dates": dup_dates,
        "missing_s": int(s.isna().sum().sum()),
        "missing_v": int(v.isna().sum().sum()),
        "speed_min": float(speed.min()),
        "speed_max": float(speed.max()),
        "speed_mean": float(speed.mean()),
    }


def inspect():
    all_raw = load_all_raw()

    print("=" * 70)
    print("DATASET INSPECTION REPORT")
    print("=" * 70)
    print(f"Discovered {len(all_raw)} sequence pair(s): {list(all_raw.keys())}")

    summaries = []
    for name, (s, v) in all_raw.items():
        summaries.append(_inspect_one(name, s, v))

    print("\n" + "=" * 70)
    print("SUMMARY ACROSS ALL SEQUENCES")
    print("=" * 70)
    summary_df = pd.DataFrame(summaries)
    print(summary_df.to_string(index=False))
    total_rows = summary_df["n_rows"].sum()
    total_duration_h = summary_df["duration_s"].sum() / 3600
    print(f"\nTotal rows across all sequences: {total_rows}")
    print(f"Total duration: {total_duration_h:.2f} hours")

    # -- column mapping table (same mapping applies to every sequence) -----
    print("\n" + "=" * 70)
    print("COLUMN MAPPING (applies to every sequence)")
    print("=" * 70)
    rows = [
        ("Timestamp", cfg.S_COLS["date"] + " (S-file)", "datetime, 10 Hz"),
        ("Accelerometer X", cfg.S_COLS["acc_x"], "m/s^2"),
        ("Accelerometer Y", cfg.S_COLS["acc_y"], "m/s^2"),
        ("Accelerometer Z", cfg.S_COLS["acc_z"], "m/s^2"),
        ("Gyroscope X (~Roll)", cfg.S_COLS["gyro_x"], "rad/s"),
        ("Gyroscope Y (~Pitch)", cfg.S_COLS["gyro_y"], "rad/s"),
        ("Gyroscope Z (~Yaw)", cfg.S_COLS["gyro_z"], "rad/s"),
        ("Vehicle speed (target)", cfg.V_COLS["vehicle_speed"] + " (V-file)", "km/h"),
        ("(unused) GPS speed", cfg.S_COLS["gps_speed"] + " (S-file)", "km/h"),
        ("(unused) GPS velocity", cfg.V_COLS["gps_velocity"] + " (V-file)", "km/h"),
    ]
    for purpose, colname, unit in rows:
        print(f"  {purpose:26s} | {colname:45s} | {unit}")

    return all_raw, summary_df


if __name__ == "__main__":
    inspect()

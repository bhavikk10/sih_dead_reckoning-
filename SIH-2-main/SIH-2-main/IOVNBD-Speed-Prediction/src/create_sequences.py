"""
Step 3: Training-data creation.

Task: smartphone IMU (6 channels) -> vehicle speed (1 value), using a
sliding window of past IMU samples ending at the prediction instant (no
future information is used).

Leakage-prevention strategy
----------------------------
**With 2+ sequences (recommended):** whole driving sequences are assigned
to train / val / test - never split within a sequence. This is the
strongest form of leakage prevention: it also protects against a model
that "memorizes" a specific route/driver/vehicle rather than learning a
general IMU -> speed relationship, since test sequences are entirely
unseen recordings. Sequences are greedily assigned to whichever split is
currently furthest below its target proportion (by row count), so the
achieved train/val/test sizes approximate 70/15/15 as closely as possible
given the available sequence sizes.

**With exactly 1 sequence (fallback):** there is no way to hold out a
whole unseen sequence, so we fall back to a chronological split of the
single continuous timeline: first 70% of rows -> train, next 15% -> val,
last 15% -> test. No shuffling of raw rows.

**In both cases:** windows are only created AFTER the split is decided,
and independently within each split's own row-ranges per sequence, so no
window ever mixes rows from two different splits or two different
sequences. The StandardScalers (features and target) are fit ONLY on the
training split's rows.

Window size
-----------
Sampling rate = 10 Hz (verified in inspect_data.py). We use a
WINDOW_DURATION_S = 2.0 s window (20 timesteps), which is long enough to
capture short-term acceleration/deceleration dynamics relevant to speed
but short enough to keep the model lightweight and responsive. Consecutive
windows are spaced WINDOW_STRIDE = 5 samples (0.5 s) apart to reduce
redundancy between neighboring windows.
"""
import os
import sys

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg
from preprocess import preprocess


def _load_clean_df() -> pd.DataFrame:
    parquet_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.parquet")
    csv_path = os.path.join(cfg.PROCESSED_DATA_DIR, "clean_sequence.csv")
    if os.path.exists(parquet_path):
        return pd.read_parquet(parquet_path)
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path, parse_dates=["timestamp"])
    return preprocess()


def _assign_sequences_to_splits(df: pd.DataFrame):
    """Greedily assign whole sequences to train/val/test so the resulting
    row-count proportions approximate TRAIN/VAL/TEST_FRACTION as closely
    as possible. Returns a dict {split_name: [sequence_id, ...]}."""
    counts = df.groupby("sequence_id").size().sort_values(ascending=False)
    total = counts.sum()
    targets = {
        "train": cfg.TRAIN_FRACTION * total,
        "val": cfg.VAL_FRACTION * total,
        "test": cfg.TEST_FRACTION * total,
    }
    current = {"train": 0, "val": 0, "test": 0}
    assignment = {"train": [], "val": [], "test": []}

    for seq_id, n in counts.items():
        # assign to whichever split is currently furthest below its target
        deficits = {k: targets[k] - current[k] for k in current}
        best_split = max(deficits, key=deficits.get)
        assignment[best_split].append(seq_id)
        current[best_split] += n

    return assignment, current, total


def _make_windows(df_block: pd.DataFrame, window_size: int, stride: int):
    """Slide a window of `window_size` IMU rows within a SINGLE sequence's
    contiguous rows; the label is the vehicle speed at the LAST timestep
    of the window (i.e. "now"), so only past and present IMU samples are
    used - never future ones. Windows never cross a sequence boundary.

    Also returns, for each window, the timestamp and sequence_id at the
    window's last timestep, so downstream plotting/evaluation can align
    predictions back to real time without re-deriving split boundaries."""
    all_X, all_y, all_t, all_seq = [], [], [], []
    for seq_id, sub in df_block.groupby("sequence_id", sort=False):
        sub = sub.sort_values("timestamp")
        feats = sub[cfg.FEATURE_COLUMNS].values.astype(np.float32)
        target = sub[cfg.TARGET_COLUMN].values.astype(np.float32)
        times = sub["timestamp"].values
        n = len(sub)
        starts = range(0, n - window_size + 1, stride)
        for i in starts:
            all_X.append(feats[i:i + window_size])
            all_y.append(target[i + window_size - 1])
            all_t.append(times[i + window_size - 1])
            all_seq.append(seq_id)

    if not all_X:
        return (
            np.empty((0, window_size, len(cfg.FEATURE_COLUMNS)), dtype=np.float32),
            np.empty((0,), dtype=np.float32),
            np.empty((0,), dtype="datetime64[ns]"),
            np.empty((0,), dtype=object),
        )
    return (
        np.stack(all_X),
        np.array(all_y, dtype=np.float32),
        np.array(all_t, dtype="datetime64[ns]"),
        np.array(all_seq, dtype=object),
    )


def create_sequences():
    df = _load_clean_df()
    n_sequences = df["sequence_id"].nunique()

    print("=" * 70)
    print(f"SPLIT STRATEGY: {'by whole sequence' if n_sequences > 1 else 'chronological (single sequence fallback)'}")
    print("=" * 70)

    if n_sequences > 1:
        if n_sequences == 2:
            # Special case: with only 2 sequences, a clean 3-way whole-
            # sequence split isn't possible. We hold out the SMALLER
            # sequence entirely as the test set (a fully unseen
            # driver/route - strong leakage protection for testing), and
            # carve a chronological tail off the END of the larger
            # sequence to serve as the validation set (used only for
            # early stopping, not for reporting final metrics).
            counts = df.groupby("sequence_id").size().sort_values(ascending=False)
            big_seq, small_seq = counts.index[0], counts.index[1]
            print(f"Only 2 sequences found ({list(counts.index)}) -> hybrid split:")
            print(f"  test  = whole sequence '{small_seq}' ({counts[small_seq]} rows, fully unseen)")
            print(f"  train/val = sequence '{big_seq}' ({counts[big_seq]} rows), "
                  f"chronological tail ({cfg.VAL_FRACTION*100:.0f}%) held out as val")

            big_df = df[df["sequence_id"] == big_seq].sort_values("timestamp").reset_index(drop=True)
            n_big = len(big_df)
            n_val = int(n_big * cfg.VAL_FRACTION)
            train_df = big_df.iloc[:n_big - n_val].reset_index(drop=True)
            val_df = big_df.iloc[n_big - n_val:].reset_index(drop=True)
            test_df = df[df["sequence_id"] == small_seq].reset_index(drop=True)
        else:
            assignment, current, total = _assign_sequences_to_splits(df)
            for split in ("train", "val", "test"):
                pct = 100 * current[split] / total
                print(f"{split:5s}: sequences={assignment[split]}  rows={current[split]} ({pct:.1f}%)")

            train_df = df[df["sequence_id"].isin(assignment["train"])].reset_index(drop=True)
            val_df = df[df["sequence_id"].isin(assignment["val"])].reset_index(drop=True)
            test_df = df[df["sequence_id"].isin(assignment["test"])].reset_index(drop=True)

            if len(assignment["val"]) == 0 or len(assignment["test"]) == 0:
                raise RuntimeError(
                    "Sequence-level split left val or test with zero sequences even "
                    f"with {n_sequences} sequences available. Add a few more sequences "
                    "(ideally not wildly different in size) so each split gets at "
                    "least one whole sequence."
                )
    else:
        # single-sequence fallback: chronological split
        seq_id = df["sequence_id"].iloc[0]
        df = df.sort_values("timestamp").reset_index(drop=True)
        n = len(df)
        n_train = int(n * cfg.TRAIN_FRACTION)
        n_val = int(n * cfg.VAL_FRACTION)
        train_df = df.iloc[:n_train].reset_index(drop=True)
        val_df = df.iloc[n_train:n_train + n_val].reset_index(drop=True)
        test_df = df.iloc[n_train + n_val:].reset_index(drop=True)
        print(f"Only 1 sequence ({seq_id}) found -> chronological split:")
        print(f"  train rows={len(train_df)} ({cfg.TRAIN_FRACTION*100:.0f}%)  "
              f"[{train_df['timestamp'].iloc[0]} -> {train_df['timestamp'].iloc[-1]}]")
        print(f"  val   rows={len(val_df)} ({cfg.VAL_FRACTION*100:.0f}%)  "
              f"[{val_df['timestamp'].iloc[0]} -> {val_df['timestamp'].iloc[-1]}]")
        print(f"  test  rows={len(test_df)} ({100-cfg.TRAIN_FRACTION*100-cfg.VAL_FRACTION*100:.0f}%)  "
              f"[{test_df['timestamp'].iloc[0]} -> {test_df['timestamp'].iloc[-1]}]")

    # --- fit scalers ONLY on training rows -----------------------------------
    scaler = StandardScaler()
    scaler.fit(train_df[cfg.FEATURE_COLUMNS].values)

    train_df = train_df.copy()
    val_df = val_df.copy()
    test_df = test_df.copy()
    train_df[cfg.FEATURE_COLUMNS] = scaler.transform(train_df[cfg.FEATURE_COLUMNS].values)
    val_df[cfg.FEATURE_COLUMNS] = scaler.transform(val_df[cfg.FEATURE_COLUMNS].values) if len(val_df) else val_df[cfg.FEATURE_COLUMNS]
    test_df[cfg.FEATURE_COLUMNS] = scaler.transform(test_df[cfg.FEATURE_COLUMNS].values) if len(test_df) else test_df[cfg.FEATURE_COLUMNS]

    os.makedirs(cfg.ARTIFACTS_DIR, exist_ok=True)
    scaler_path = os.path.join(cfg.ARTIFACTS_DIR, "feature_scaler.joblib")
    joblib.dump(scaler, scaler_path)
    print(f"\nFitted feature StandardScaler on TRAIN ONLY -> saved to {scaler_path}")

    target_scaler = StandardScaler()
    target_scaler.fit(train_df[[cfg.TARGET_COLUMN]].values)
    target_scaler_path = os.path.join(cfg.ARTIFACTS_DIR, "target_scaler.joblib")
    joblib.dump(target_scaler, target_scaler_path)
    print(f"Fitted target StandardScaler on TRAIN ONLY -> saved to {target_scaler_path}")

    # --- windowing (independently per sequence => no leakage across splits/sequences)
    X_train, y_train, t_train, seq_train = _make_windows(train_df, cfg.WINDOW_SIZE, cfg.WINDOW_STRIDE)
    X_val, y_val, t_val, seq_val = _make_windows(val_df, cfg.WINDOW_SIZE, cfg.WINDOW_STRIDE)
    X_test, y_test, t_test, seq_test = _make_windows(test_df, cfg.WINDOW_SIZE, cfg.WINDOW_STRIDE)

    print("\n" + "=" * 70)
    print("WINDOWED TRAINING DATA")
    print("=" * 70)
    print(f"Window duration      : {cfg.WINDOW_DURATION_S} s ({cfg.WINDOW_SIZE} timesteps)")
    print(f"Window stride        : {cfg.WINDOW_STRIDE} samples ({cfg.WINDOW_STRIDE * cfg.SAMPLE_PERIOD_S:.2f} s)")
    print(f"Number of features   : {len(cfg.FEATURE_COLUMNS)} ({cfg.FEATURE_COLUMNS})")
    print(f"X_train shape        : {X_train.shape}")
    print(f"y_train shape        : {y_train.shape}")
    print(f"X_val shape          : {X_val.shape}")
    print(f"y_val shape          : {y_val.shape}")
    print(f"X_test shape         : {X_test.shape}")
    print(f"y_test shape         : {y_test.shape}")

    os.makedirs(cfg.PROCESSED_DATA_DIR, exist_ok=True)
    np.savez_compressed(
        os.path.join(cfg.PROCESSED_DATA_DIR, "windows.npz"),
        X_train=X_train, y_train=y_train, t_train=t_train, seq_train=seq_train,
        X_val=X_val, y_val=y_val, t_val=t_val, seq_val=seq_val,
        X_test=X_test, y_test=y_test, t_test=t_test, seq_test=seq_test,
    )
    print(f"\nSaved windowed arrays -> {os.path.join(cfg.PROCESSED_DATA_DIR, 'windows.npz')}")

    return X_train, y_train, X_val, y_val, X_test, y_test, scaler


if __name__ == "__main__":
    create_sequences()

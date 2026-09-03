# IOVNBD Speed Prediction

**Stage 1–6 of the ISRO Smart India Hackathon "AI-ML based Intelligent Dead
Reckoning system" project.**

This module implements only:
`IO-VNBD dataset -> inspection -> preprocessing -> synchronization ->
training data -> AI model -> vehicle-speed prediction -> evaluation`

It does **not** implement EKF/UKF, GNSS+INS fusion, dead reckoning, GNSS
outage simulation, map matching, NHC, or any mobile/Android component —
those are later stages, out of scope here.

---

## 1. Installation (Windows)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

(On Mac/Linux: `source .venv/bin/activate` instead.)

The project automatically uses your GPU if `torch.cuda.is_available()`
returns `True`, otherwise it runs on CPU. No manual configuration needed.

## 2. Dataset placement

Put the two real, synchronized IO-VNBD CSV files here:

```
data/raw/S-M.csv     <- smartphone IMU + GPS
data/raw/V-M.csv     <- vehicle/reference CAN-bus + GPS
```

See `data/README.md` for exactly how to get the *real* file content from
the IO-VNBD GitHub repo (it uses Git LFS — a plain "Download ZIP" only
gives you placeholder pointer files, not the actual sensor data).

**Adding more driving sequences (recommended for better results):** the
pipeline auto-discovers every matched `S-<name>.csv` / `V-<name>.csv`
pair in `data/raw/`. Just download more sequence pairs from the IO-VNBD
repo the same way, drop them in, and re-run `python run_pipeline.py` —
no code changes needed. See "Dataset used" and "Training data" below for
how the split strategy adapts automatically as you add sequences.

## 3. Running

```bash
python run_pipeline.py
```

This runs, in order: inspect data -> preprocess -> create training
windows -> train baseline (Random Forest) -> train main model (GRU) ->
evaluate on the test set -> generate all plots. Each step can also be run
individually for debugging, e.g. `python src/inspect_data.py`.

---

## Dataset used

- **Source**: IO-VNBD ("Inertial and Odometry Vehicle Navigation Benchmark
  Dataset"), `Synchronised V and S datasets/Categorised IOVNB Dataset/`
  sequences.
- **Currently included**: `S-M.csv` / `V-M.csv` ("M / Driver B" sequence,
  105,974 rows × 24 / 29 columns).
- **Want better results? Add more sequences.** The pipeline auto-discovers
  every matched `S-<name>.csv` / `V-<name>.csv` pair placed in
  `data/raw/` — just drop more files in and re-run `python
  run_pipeline.py`, no code changes needed. See `data/README.md` for
  details and why this is the single biggest lever for improving accuracy
  beyond this stage's current single-sequence baseline (a model trained
  on one driver/vehicle/route has no way to prove it generalizes; more
  sequences let it actually be tested on unseen driving).
- **Why the M sequence was selected first**: it is one of the
  pre-synchronized S/V pairs provided by the dataset authors (equal row
  counts, matching duration), has a long continuous recording (~2.94
  hours, ~106k samples at 10 Hz), and covers a wide speed range (0–100.8
  km/h, mean 36.0 km/h) with realistic stop/go city and higher-speed
  driving — good variation for learning a speed model.
- **Sampling rate**: 10 Hz (verified from both the S-file `DATE` column
  and the V-file `Time Since Start of Day` column; matches the dataset
  paper's stated 10 Hz).
- **Data quality**: 0 missing values, 0 infinite values, 0 duplicate
  timestamps. The S-file's `TIME SINCE START (ms)` column resets partway
  through the recording (logging-app restart artifact) and was **not**
  used for timing — the monotonic `DATE` column was used instead.

## Column mapping (from actual inspection — see `src/config.py` / `src/inspect_data.py`)

| Purpose | Original file / column | Unit |
|---|---|---|
| Timestamp | `DATE (YYYY-MO-DD HH-MI-SS_SSS)` (S-file) | datetime, 10 Hz |
| Accelerometer X | `ACCELEROMETER X (m/s²)` (S-file) | m/s² |
| Accelerometer Y | `ACCELEROMETER Y (m/s²)` (S-file) | m/s² |
| Accelerometer Z | `ACCELEROMETER Z (m/s²)` (S-file) | m/s² |
| Gyroscope X (~Roll) | `GYROSCOPE Roll (rad/s)` (S-file) | rad/s |
| Gyroscope Y (~Pitch) | `GYROSCOPE Pitch (rad/s)` (S-file) | rad/s |
| Gyroscope Z (~Yaw) | `GYROSCOPE Yaw (rad/s)` (S-file) | rad/s |
| Vehicle speed (target) | `Indicated Vehicle Speed (km/hr)` (V-file) | km/h |

Notes:
- The S-file's gyroscope columns are named by rotation axis
  (Yaw/Pitch/Roll), not X/Y/Z. We map Roll→x, Pitch→y, Yaw→z by
  convention; the raw values themselves are unmodified.
- `Indicated Vehicle Speed (km/hr)` was chosen as the target because it
  comes from the vehicle's own CAN-bus/ECU — **not** derived from GPS
  (unlike `Velocity (km/hr)` in the V-file, which comes from the
  GPS-based VBOX unit). This keeps GPS out of both the inputs and the
  target, per the task's requirements.
- Magnetometer, GPS coordinates, wheel-speed channels, and other V-file
  channels (engine speed, gear, brake pressure, etc.) exist in the raw
  files but are **not** used in this stage.

## Preprocessing

1. Parse timestamps from the S-file `DATE` column.
2. Sort by timestamp (defensive check; data was already monotonic).
3. Row-align S and V (both files have identical row counts/durations,
   consistent with being the dataset authors' pre-synchronized pair).
4. Drop rows with missing/NaN/infinite values (none were found).
5. Remove duplicate timestamps (none were found).
6. Units verified against the dataset documentation — no conversion
   needed (accel in m/s², gyro in rad/s, speed in km/h).
7. No sensor filtering applied (kept conservative, per task instructions,
   to preserve raw dynamics) — an optional low-pass filter hook exists in
   `preprocess.py` but is off by default.
8. Feature scaling (`StandardScaler`) fit **only** on the training split.

## Training data

- **Task**: smartphone IMU (6 channels) → vehicle speed (1 value).
- **Window**: 2.0 s (20 timesteps at 10 Hz), stride 0.5 s (5 samples)
  between window starts.
- **Leakage prevention / split strategy**:
  - **1 sequence available** (current default): the raw, continuous
    timeline is split chronologically (70% / 15% / 15%,
    train/val/test) **before** any windowing happens, so no window
    spans two splits.
  - **2 sequences available**: the smaller sequence is held out
    *entirely* as the test set (a fully unseen driver/route), and a
    chronological tail of the larger sequence becomes the validation
    set.
  - **3+ sequences available**: whole sequences are greedily assigned
    to train/val/test to approximate 70/15/15 by row count — the
    strongest leakage protection, since test sequences are entirely
    unseen recordings, not just unseen timestamps within one recording.
  - In every case, windowing happens per-sequence and only after the
    split is fixed, and the feature/target scalers are fit only on the
    training split.

| | Train | Val | Test |
|---|---:|---:|---:|
| Rows (raw, 10 Hz) | 74,181 | 15,896 | 15,897 |
| Windows (X, y) | 14,833 | 3,176 | 3,176 |

`X` shape: `(n_windows, 20, 6)`, `y` shape: `(n_windows,)`. (Numbers above
are for the current single-sequence default; adding sequences changes
these — see `run_pipeline.py` output.)

## Models

**Baseline — Random Forest Regressor** (200 trees, max_depth=16) on
24 hand-crafted per-window statistics (mean/std/min/max × 6 channels).

**Main model — GRU** (chosen over LSTM for its smaller parameter count
and faster/less overfit-prone training on this modest dataset size and
short 20-step sequences, while running fully on CPU):

```
IMU sequence (batch, 20, 6)
    -> GRU(hidden_size=64, num_layers=2, dropout=0.2)
    -> final timestep hidden state
    -> Dense(64->32) + ReLU + Dropout
    -> Dense(32->1)
    -> Predicted vehicle speed (batch, 1)
```

Trained with Adam (lr=1e-3), batch size 64, MSE loss on **standardized**
targets (inverse-transformed back to km/h before any metric is computed),
early stopping on validation loss (patience 8), with a fixed random seed
for reproducibility. Training stopped at epoch 23 of a 60-epoch budget
(~76s on CPU).

## Results (test set, actually measured — not fabricated)

| Model | MAE (km/h) | RMSE (km/h) | R² |
|---|---:|---:|---:|
| Baseline (Random Forest) | 10.81 | 13.87 | 0.644 |
| GRU | 10.48 | 13.71 | 0.652 |

GRU max absolute error on test set: 53.2 km/h.

MAPE was **not** computed: a meaningful fraction of test-set speeds are
at or near 0 km/h (vehicle stopped), which makes percentage error
undefined/explosive — exactly the case the task instructions flagged to
watch for.

**Interpretation**: both models explain roughly 64–65% of the variance in
vehicle speed from 2-second IMU windows alone, with a typical error of
~10.5–11 km/h, and the GRU slightly edges out the Random Forest baseline.
The GRU tracks overall speed trends (accelerating, braking, stopping)
reasonably well but is noisier than the ground truth at any single
instant — expected for a first, lightweight prototype using raw IMU only
(no GPS, no wheel data, no longer temporal context). See
`results/plots/05_groundtruth_vs_predicted_speed.png`.

Note: since GRU weight initialization and data-loader shuffling are
randomized, re-running `train_model.py` without the fixed seed (or with a
different seed) will produce slightly different numbers in the same
ballpark (observed range across runs: MAE ~10.5–12.7 km/h, R² ~0.53–0.65)
— this run-to-run variance itself is a useful signal that a longer
sequence, more data, or hyperparameter tuning would likely stabilize and
improve results in a later iteration.

## Files produced

- **Model**: `models/gru_speed_model.pt` (main model),
  `models/baseline_random_forest.joblib` (baseline)
- **Scalers**: `artifacts/feature_scaler.joblib`,
  `artifacts/target_scaler.joblib`
- **Run configuration**: `artifacts/config.json` (feature names, target,
  sampling rate, window size, normalization info, model hyperparameters)
- **Metrics**: `results/baseline_metrics.json`, `results/gru_test_metrics.json`,
  `results/final_results.json`, `results/training_history.json`
- **Processed data**: `data/processed/clean_sequence.parquet`,
  `data/processed/windows.npz`
- **Plots**: `results/plots/01`–`08` (accelerometer, gyroscope,
  ground-truth speed, train/val loss, predicted-vs-actual over time,
  error over time, scatter with y=x line, GPS trajectory)

## Reproduction

From a fresh terminal in the project root, with `data/raw/S-M.csv` and
`data/raw/V-M.csv` in place:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_pipeline.py
```

## Project structure

```
IOVNBD-Speed-Prediction/
├── data/
│   ├── raw/              <- put S-M.csv / V-M.csv here
│   ├── processed/        <- generated by the pipeline
│   └── README.md
├── src/
│   ├── config.py          <- paths, column mapping, hyperparameters
│   ├── inspect_data.py    <- Step 1: dataset inspection
│   ├── preprocess.py      <- Step 2: cleaning + standardized dataframe
│   ├── create_sequences.py<- Step 3: leakage-safe split + windowing
│   ├── train_baseline.py  <- Step 4: Random Forest baseline
│   ├── train_model.py     <- Step 5: GRU model
│   └── evaluate.py        <- Step 6: test metrics + all plots
├── models/                <- saved trained models
├── artifacts/             <- scalers + run configuration
├── results/
│   └── plots/              <- all required plots
├── requirements.txt
├── run_pipeline.py
└── README.md
```

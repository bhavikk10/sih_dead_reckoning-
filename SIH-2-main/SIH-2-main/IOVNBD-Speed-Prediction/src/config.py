"""
Central configuration for the IO-VNBD speed-prediction pipeline.

All paths are relative to the project root so the project runs unchanged
on any machine (Windows/Linux/Mac), as long as it's launched from the
project root (e.g. `python run_pipeline.py` from IOVNBD-Speed-Prediction/).
"""
import os
import glob

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(ROOT_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, "processed")

MODELS_DIR = os.path.join(ROOT_DIR, "models")
ARTIFACTS_DIR = os.path.join(ROOT_DIR, "artifacts")
RESULTS_DIR = os.path.join(ROOT_DIR, "results")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")


def discover_sequence_pairs():
    """Auto-discover all matched S-<name>.csv / V-<name>.csv pairs under
    data/raw/. Returns a sorted list of (sequence_name, s_path, v_path)
    tuples. A sequence is only included if BOTH its S- and V- file exist.
    This lets you add more driving sequences just by dropping matching
    files into data/raw/ - no code changes needed beyond re-running the
    pipeline."""
    pairs = []
    for s_path in sorted(glob.glob(os.path.join(RAW_DATA_DIR, "S-*.csv"))):
        name = os.path.basename(s_path)[len("S-"):-len(".csv")]
        v_path = os.path.join(RAW_DATA_DIR, f"V-{name}.csv")
        if os.path.exists(v_path):
            pairs.append((name, s_path, v_path))
        else:
            print(f"[config] WARNING: found {s_path} but no matching V-{name}.csv - skipping this sequence.")
    return pairs

# ---------------------------------------------------------------------------
# Column mapping (verified by actually inspecting S-M.csv / V-M.csv headers)
# ---------------------------------------------------------------------------
# Smartphone (S) file columns of interest
S_COLS = {
    "acc_x": "ACCELEROMETER X (m/s²)",
    "acc_y": "ACCELEROMETER Y (m/s²)",
    "acc_z": "ACCELEROMETER Z (m/s²)",
    # The S-file's gyroscope columns are labelled by rotation axis name
    # (Yaw/Pitch/Roll) rather than X/Y/Z. We map them onto x/y/z using the
    # conventional aerospace correspondence roll->x, pitch->y, yaw->z.
    # This is a naming-convention assumption (the raw values themselves are
    # not altered) and is documented here for transparency.
    "gyro_x": "GYROSCOPE Roll (rad/s)",
    "gyro_y": "GYROSCOPE Pitch (rad/s)",
    "gyro_z": "GYROSCOPE Yaw (rad/s)",
    "date": "DATE (YYYY-MO-DD HH-MI-SS_SSS)",
    # Present but NOT used as model inputs/targets in this stage:
    "gps_speed": "GPS SPEED (Kmh)",
    "gps_lat": "GPS LATITUDE (degrees)",
    "gps_lon": "GPS LONGITUDE (degrees)",
    "time_since_start_ms": "TIME SINCE START (ms)",  # unreliable: resets mid-file, do not use for timing
}

# Vehicle/reference (V) file columns of interest
V_COLS = {
    # Non-GPS, CAN-bus/ECU-derived reference vehicle speed. Chosen as the
    # prediction target because it is NOT derived from GPS (unlike
    # "Velocity (km/hr)", which comes from the GPS-based VBOX unit).
    "vehicle_speed": "Indicated Vehicle Speed (km/hr)",
    "time_since_start_s": "Time Since Start of Day (seconds)",
    # Present but NOT used in this stage:
    "gps_velocity": "Velocity (km/hr)",
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S:%f"

# ---------------------------------------------------------------------------
# Standardized dataframe column order (after preprocessing)
# ---------------------------------------------------------------------------
STANDARD_COLUMNS = [
    "sequence_id",
    "timestamp",
    "acc_x", "acc_y", "acc_z",
    "gyro_x", "gyro_y", "gyro_z",
    "vehicle_speed",
]

FEATURE_COLUMNS = ["acc_x", "acc_y", "acc_z", "gyro_x", "gyro_y", "gyro_z"]
TARGET_COLUMN = "vehicle_speed"

# ---------------------------------------------------------------------------
# Sampling / windowing (determined from actual data inspection: both S and V
# files are sampled at 10 Hz -> sample period 0.1 s)
# ---------------------------------------------------------------------------
SAMPLING_RATE_HZ = 10.0
SAMPLE_PERIOD_S = 1.0 / SAMPLING_RATE_HZ

WINDOW_DURATION_S = 5.0
WINDOW_SIZE = int(round(WINDOW_DURATION_S * SAMPLING_RATE_HZ))  # 20 timesteps

# Stride between successive windows, in samples. A stride > 1 reduces the
# number of near-duplicate overlapping windows (helps generalization and
# keeps training lightweight on CPU) while still using every part of the
# sequence.
WINDOW_STRIDE = 5  # 0.5 s between window starts

# ---------------------------------------------------------------------------
# Chronological split fractions (train / val / test), applied to the single
# available sequence in time order to avoid leakage.
# ---------------------------------------------------------------------------
TRAIN_FRACTION = 0.70
VAL_FRACTION = 0.15
TEST_FRACTION = 0.15

RANDOM_SEED = 42

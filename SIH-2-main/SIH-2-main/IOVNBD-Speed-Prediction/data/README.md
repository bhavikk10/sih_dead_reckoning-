# Data folder

## data/raw/

Place matched pairs of real (already-synchronized) IO-VNBD CSV files here,
one `S-<name>.csv` + `V-<name>.csv` pair per driving sequence:

```
data/raw/S-M.csv        <- smartphone IMU + GPS data ("S-" file)
data/raw/V-M.csv        <- vehicle/reference CAN-bus + GPS data ("V-" file)

# add more sequences the same way - just drop matching files in here:
data/raw/S-Vfa01.csv    data/raw/V-Vfa01.csv
data/raw/S-Vtb5.csv     data/raw/V-Vtb5.csv
```

The pipeline **auto-discovers every matched pair** in this folder (see
`src/config.py:discover_sequence_pairs()`) - no code changes needed to
add more sequences, just add the files and re-run `python run_pipeline.py`.
A file is only used if both its `S-` and `V-` counterpart are present; an
unmatched file is skipped with a warning.

**Why add more sequences?** With only one sequence, train/val/test come
from one continuous recording (one driver, one vehicle, one route) split
chronologically. With 2+ sequences, the pipeline instead holds out whole
sequences for validation/testing (see "Split strategy" in the main
README) - a stronger test of whether the model generalizes to unseen
driving, and the biggest lever for improving results beyond what a single
recording can teach the model.

These come from the IO-VNBD dataset's "Synchronised V and S datasets"
folder, from https://github.com/onyekpeu/IO-VNBD.

**Important — GitHub LFS gotcha:** this repository stores its CSVs with
Git LFS. If you download the repo using GitHub's green "Code -> Download
ZIP" button, or fetch a `raw.githubusercontent.com` URL directly, you will
only get small ~130-byte placeholder/pointer text files, not the real
data. To get the real CSV content, either:

- Open the file's page on GitHub directly (e.g.
  `.../blob/master/Synchronised%20V%20abd%20S%20datasets/.../S-M.csv`) and
  use the **"Download"** button shown on the "Stored with Git LFS" banner
  (this fetches the real content, several MB), or
- Clone with Git LFS installed: `git lfs install && git clone https://github.com/onyekpeu/IO-VNBD.git`

You can verify you have the real files by checking their size — they
should be several MB each (~20-25 MB for the M sequence used by this
project), not ~130 bytes.

## data/processed/

Created automatically by `src/preprocess.py` and `src/create_sequences.py`.
Contains:
- `clean_sequence.parquet` (or `.csv` fallback) — the standardized,
  cleaned dataframe for ALL discovered sequences concatenated, tagged
  with a `sequence_id` column.
- `windows.npz` — the windowed train/val/test arrays (plus per-window
  timestamps and sequence ids) used for model training and evaluation.

Both are regenerated each time you run the pipeline, so they don't need
to be committed/shared.


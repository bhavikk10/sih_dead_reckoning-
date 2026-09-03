"""
One-command pipeline: inspect -> preprocess -> create training data ->
train baseline -> train GRU -> evaluate -> save plots.

Run from the project root:
    python run_pipeline.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from inspect_data import inspect
from preprocess import preprocess
from create_sequences import create_sequences
from train_baseline import train_baseline
from train_model import train_model
from evaluate import evaluate


def main():
    print("\n" + "#" * 70)
    print("# STEP 1/6: INSPECT DATA")
    print("#" * 70)
    inspect()

    print("\n" + "#" * 70)
    print("# STEP 2/6: PREPROCESS")
    print("#" * 70)
    preprocess()

    print("\n" + "#" * 70)
    print("# STEP 3/6: CREATE TRAINING WINDOWS (leakage-safe chronological split)")
    print("#" * 70)
    create_sequences()

    print("\n" + "#" * 70)
    print("# STEP 4/6: TRAIN BASELINE (Random Forest)")
    print("#" * 70)
    train_baseline()

    print("\n" + "#" * 70)
    print("# STEP 5/6: TRAIN MAIN MODEL (GRU)")
    print("#" * 70)
    train_model()

    print("\n" + "#" * 70)
    print("# STEP 6/6: EVALUATE + GENERATE PLOTS")
    print("#" * 70)
    evaluate()

    print("\n" + "#" * 70)
    print("# PIPELINE COMPLETE")
    print("#" * 70)
    print("Models    -> models/")
    print("Artifacts -> artifacts/")
    print("Results   -> results/  (metrics .json)")
    print("Plots     -> results/plots/")


if __name__ == "__main__":
    main()

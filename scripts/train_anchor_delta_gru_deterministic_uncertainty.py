"""Fit and cross-validate deterministic uncertainty for the selected GRU.

The input is the selected GRU's development-only, grouped out-of-fold residual
table.  The script never reads frozen-test predictions.  It fits one monotone
standard-deviation schedule per GNSS-blackout horizon and then checks that the
schedule improves on a constant-variance baseline under a second grouped
cross-validation loop before writing a runtime artifact.

Run from the repository root:

    E:\\ANACONDA\\python.exe scripts\\train_anchor_delta_gru_deterministic_uncertainty.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from idr_backend.uncertainty.calibration import (  # noqa: E402
    expected_gaussian_coverage,
    gaussian_interval_coverage,
)
from idr_backend.uncertainty.deterministic import (  # noqa: E402
    DeterministicVelocityUncertaintyProfile,
)


DEFAULT_VELOCITY_DIRECTORY = (
    REPOSITORY_ROOT / "artifacts" / "anchored_velocity_comparison"
)
DEFAULT_TRAINING_CSV = (
    DEFAULT_VELOCITY_DIRECTORY
    / "anchor_delta_gru_uncertainty"
    / "anchor_delta_gru_uncertainty_training.csv"
)
DEFAULT_OUTPUT_PATH = (
    DEFAULT_VELOCITY_DIRECTORY / "anchor_delta_gru_deterministic_uncertainty.json"
)
DEFAULT_DIAGNOSTICS_PATH = (
    DEFAULT_VELOCITY_DIRECTORY
    / "anchor_delta_gru_deterministic_uncertainty_diagnostics.json"
)

_REQUIRED_COLUMNS = frozenset(
    {
        "journey_id",
        "horizon_s",
        "residual_mps",
        "linear_acceleration_magnitude_std_mps2",
        "angular_velocity_rms_radps",
        "minimum_calibration_confidence",
        "final_quality_score",
    }
)
_QUANTILE_FOR_TWO_SIGMA = 0.95
_TWO_SIGMA_DIVISOR = 1.96


def _sha256_file(path: Path) -> str:
    """Hash one immutable velocity artifact for covariance binding."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_training_frame(frame: pd.DataFrame) -> None:
    """Reject a replay table that cannot support causal profile fitting."""

    missing = _REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Uncertainty training table is missing: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Uncertainty training table must not be empty.")
    if frame["journey_id"].nunique() < 5:
        raise ValueError("At least five journeys are required for grouped validation.")

    numeric_columns = tuple(_REQUIRED_COLUMNS - {"journey_id"})
    numeric = frame.loc[:, numeric_columns].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("Uncertainty training table contains non-finite numeric values.")
    if (frame["horizon_s"] < 0).any():
        raise ValueError("Uncertainty horizons must be non-negative.")
    for column in (
        "linear_acceleration_magnitude_std_mps2",
        "angular_velocity_rms_radps",
    ):
        if (frame[column] < 0.0).any():
            raise ValueError(f"Uncertainty feature {column!r} must be non-negative.")
    for column in ("minimum_calibration_confidence", "final_quality_score"):
        if ((frame[column] < 0.0) | (frame[column] > 1.0)).any():
            raise ValueError(f"Uncertainty feature {column!r} must be in [0, 1].")


def fit_profile(frame: pd.DataFrame, *, model_id: str) -> DeterministicVelocityUncertaintyProfile:
    """Fit a monotone, 95%-coverage-oriented schedule on development rows."""

    horizons = np.sort(frame["horizon_s"].unique().astype(float))
    standard_deviations: list[float] = []
    for horizon in horizons:
        residuals = frame.loc[frame["horizon_s"] == horizon, "residual_mps"].to_numpy(
            dtype=float
        )
        root_mean_square = float(np.sqrt(np.mean(np.square(residuals))))
        two_sigma_std = float(
            np.quantile(np.abs(residuals), _QUANTILE_FOR_TWO_SIGMA)
            / _TWO_SIGMA_DIVISOR
        )
        # RMS keeps Gaussian NLL meaningful; the absolute-error quantile makes
        # the nominal two-sigma interval conservative for non-Gaussian tails.
        standard_deviations.append(max(root_mean_square, two_sigma_std, 0.1))

    monotone_standard_deviations = tuple(
        float(value) for value in np.maximum.accumulate(standard_deviations)
    )
    reference_acceleration = max(
        0.05,
        float(
            frame["linear_acceleration_magnitude_std_mps2"].quantile(0.75)
        ),
    )
    reference_turn_rate = max(
        0.02,
        float(frame["angular_velocity_rms_radps"].quantile(0.75)),
    )
    reference_calibration = max(
        0.05,
        float(frame["minimum_calibration_confidence"].quantile(0.25)),
    )
    reference_quality = max(
        0.05,
        float(frame["final_quality_score"].quantile(0.25)),
    )

    return DeterministicVelocityUncertaintyProfile(
        model_id=model_id,
        horizon_seconds=tuple(float(horizon) for horizon in horizons),
        base_standard_deviation_mps=monotone_standard_deviations,
        variance_ceiling_m2ps2=400.0,
        reference_acceleration_std_mps2=reference_acceleration,
        reference_angular_velocity_rms_radps=reference_turn_rate,
        reference_minimum_calibration_confidence=reference_calibration,
        reference_final_quality_score=reference_quality,
        # These only activate above/below robust reference values, rather than
        # systematically re-inflating a schedule already fitted to normal rows.
        roughness_std_multiplier=0.35,
        turn_std_multiplier=0.25,
        calibration_std_multiplier=0.50,
        quality_std_multiplier=0.75,
    )


def profile_variances(
    profile: DeterministicVelocityUncertaintyProfile,
    frame: pd.DataFrame,
) -> np.ndarray:
    """Apply one profile to causal feature rows without using residual labels."""

    return np.asarray(
        [
            profile.variance_m2ps2(
                seconds_since_anchor=float(row.horizon_s),
                linear_acceleration_magnitude_std_mps2=float(
                    row.linear_acceleration_magnitude_std_mps2
                ),
                angular_velocity_rms_radps=float(row.angular_velocity_rms_radps),
                minimum_calibration_confidence=float(
                    row.minimum_calibration_confidence
                ),
                final_quality_score=float(row.final_quality_score),
            )
            for row in frame.itertuples(index=False)
        ],
        dtype=float,
    )


def _mean_gaussian_nll(residuals: np.ndarray, variances: np.ndarray) -> float:
    """Calculate comparable Gaussian NLL using physical speed units."""

    return float(
        np.mean(
            0.5
            * (
                np.log(2.0 * np.pi * variances)
                + np.square(residuals) / variances
            )
        )
    )


def _metrics(
    *,
    residuals: np.ndarray,
    variances: np.ndarray,
    journey_ids: np.ndarray,
) -> dict[str, float]:
    """Report row- and journey-balanced calibration quality."""

    metric_frame = pd.DataFrame(
        {
            "journey_id": journey_ids,
            "nll": 0.5
            * (
                np.log(2.0 * np.pi * variances)
                + np.square(residuals) / variances
            ),
            "one_sigma_covered": np.abs(residuals) <= np.sqrt(variances),
            "two_sigma_covered": np.abs(residuals) <= 2.0 * np.sqrt(variances),
        }
    )
    return {
        "nll": _mean_gaussian_nll(residuals, variances),
        "macro_journey_nll": float(metric_frame.groupby("journey_id")["nll"].mean().mean()),
        "one_sigma_coverage": gaussian_interval_coverage(
            residuals_mps=residuals.tolist(),
            predicted_variances_m2ps2=variances.tolist(),
            standard_deviations=1.0,
        ),
        "two_sigma_coverage": gaussian_interval_coverage(
            residuals_mps=residuals.tolist(),
            predicted_variances_m2ps2=variances.tolist(),
            standard_deviations=2.0,
        ),
        "macro_journey_two_sigma_coverage": float(
            metric_frame.groupby("journey_id")["two_sigma_covered"].mean().mean()
        ),
    }


def grouped_cross_validation(
    frame: pd.DataFrame,
    *,
    model_id: str,
    folds: int,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Cross-fit the full schedule so no journey calibrates its own variance."""

    groups = frame["journey_id"].to_numpy()
    if folds < 2 or folds > len(set(groups)):
        raise ValueError("Grouped uncertainty folds must be between 2 and journey count.")

    splitter = GroupKFold(n_splits=folds)
    parts: list[pd.DataFrame] = []
    for fold, (train_indices, validation_indices) in enumerate(
        splitter.split(frame, groups=groups), start=1
    ):
        train_frame = frame.iloc[train_indices]
        validation_frame = frame.iloc[validation_indices].copy()
        profile = fit_profile(train_frame, model_id=model_id)
        validation_frame["deterministic_variance_m2ps2"] = profile_variances(
            profile, validation_frame
        )
        validation_frame["constant_variance_m2ps2"] = float(
            np.mean(np.square(train_frame["residual_mps"].to_numpy(dtype=float)))
        )
        validation_frame["fold"] = fold
        parts.append(validation_frame)

    cross_fitted = pd.concat(parts, ignore_index=True)
    residuals = cross_fitted["residual_mps"].to_numpy(dtype=float)
    journey_ids = cross_fitted["journey_id"].to_numpy()
    metrics = {
        "deterministic": _metrics(
            residuals=residuals,
            variances=cross_fitted["deterministic_variance_m2ps2"].to_numpy(
                dtype=float
            ),
            journey_ids=journey_ids,
        ),
        "constant": _metrics(
            residuals=residuals,
            variances=cross_fitted["constant_variance_m2ps2"].to_numpy(dtype=float),
            journey_ids=journey_ids,
        ),
    }
    return cross_fitted, metrics


def _profile_document(
    *,
    profile: DeterministicVelocityUncertaintyProfile,
    velocity_directory: Path,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    """Create a compact runtime artifact without serializing training data."""

    return {
        "schema_version": 1,
        "profile_kind": "anchor_delta_gru_deterministic_uncertainty",
        "velocity_model_id": profile.model_id,
        "velocity_onnx_sha256": _sha256_file(
            velocity_directory / "anchor_delta_gru.onnx"
        ),
        "velocity_metadata_sha256": _sha256_file(
            velocity_directory / "anchor_delta_gru.metadata.json"
        ),
        "horizon_seconds": list(profile.horizon_seconds),
        "base_standard_deviation_mps": list(profile.base_standard_deviation_mps),
        "variance_ceiling_m2ps2": profile.variance_ceiling_m2ps2,
        "risk_inflation": {
            "reference_acceleration_std_mps2": profile.reference_acceleration_std_mps2,
            "reference_angular_velocity_rms_radps": profile.reference_angular_velocity_rms_radps,
            "reference_minimum_calibration_confidence": profile.reference_minimum_calibration_confidence,
            "reference_final_quality_score": profile.reference_final_quality_score,
            "roughness_std_multiplier": profile.roughness_std_multiplier,
            "turn_std_multiplier": profile.turn_std_multiplier,
            "calibration_std_multiplier": profile.calibration_std_multiplier,
            "quality_std_multiplier": profile.quality_std_multiplier,
        },
        "training_scope": (
            "Development-only selected-GRU grouped out-of-fold residuals; "
            "frozen test excluded."
        ),
        "cross_validation": diagnostics,
    }


def main() -> None:
    """Fit, validate, and export the deterministic selected-GRU profile."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--training-csv", type=Path, default=DEFAULT_TRAINING_CSV)
    parser.add_argument(
        "--velocity-artifact-directory",
        type=Path,
        default=DEFAULT_VELOCITY_DIRECTORY,
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--diagnostics-path", type=Path, default=DEFAULT_DIAGNOSTICS_PATH)
    parser.add_argument("--folds", type=int, default=5)
    arguments = parser.parse_args()

    frame = pd.read_csv(arguments.training_csv)
    _validate_training_frame(frame)
    metadata_path = arguments.velocity_artifact_directory / "anchor_delta_gru.metadata.json"
    velocity_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_id = velocity_metadata.get("model_id")
    if model_id != "anchor_delta_gru_onnx_v1":
        raise ValueError("Deterministic profile requires the selected anchor-delta GRU.")

    cross_fitted, validation_metrics = grouped_cross_validation(
        frame,
        model_id=model_id,
        folds=arguments.folds,
    )
    deterministic_metrics = validation_metrics["deterministic"]
    constant_metrics = validation_metrics["constant"]
    accepted = bool(
        deterministic_metrics["nll"] <= constant_metrics["nll"]
        and deterministic_metrics["two_sigma_coverage"] >= 0.93
    )
    diagnostics: dict[str, object] = {
        "model_id": model_id,
        "rows": int(len(frame)),
        "journeys": int(frame["journey_id"].nunique()),
        "folds": arguments.folds,
        "frozen_test_used": False,
        "expected_one_sigma_coverage": expected_gaussian_coverage(1.0),
        "expected_two_sigma_coverage": expected_gaussian_coverage(2.0),
        "cross_fitted_metrics": validation_metrics,
        "acceptance": {
            "nll_not_worse_than_constant": bool(
                deterministic_metrics["nll"] <= constant_metrics["nll"]
            ),
            "two_sigma_coverage_at_least_0_93": bool(
                deterministic_metrics["two_sigma_coverage"] >= 0.93
            ),
            "accepted_for_runtime": accepted,
        },
    }
    arguments.diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2), encoding="utf-8"
    )
    cross_fitted.to_csv(
        arguments.diagnostics_path.with_name(
            "anchor_delta_gru_deterministic_uncertainty_cross_fitted.csv"
        ),
        index=False,
    )
    if not accepted:
        print(json.dumps(diagnostics, indent=2))
        raise RuntimeError(
            "Deterministic profile did not pass grouped validation; no runtime profile exported."
        )

    profile = fit_profile(frame, model_id=model_id)
    profile_document = _profile_document(
        profile=profile,
        velocity_directory=arguments.velocity_artifact_directory,
        diagnostics=diagnostics["cross_fitted_metrics"],
    )
    arguments.output_path.write_text(
        json.dumps(profile_document, indent=2), encoding="utf-8"
    )
    print("Deterministic uncertainty profile exported:", arguments.output_path)
    print("Base standard deviations (m/s):", profile.base_standard_deviation_mps)
    print(json.dumps(diagnostics["cross_fitted_metrics"], indent=2))


if __name__ == "__main__":
    main()

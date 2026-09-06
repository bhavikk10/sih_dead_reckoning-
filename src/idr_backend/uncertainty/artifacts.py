"""Validated artifact loaders for velocity-observation uncertainty.

The selected windowed GRU uses a deterministic, development-calibrated
uncertainty profile.  Its loader binds the profile to exact ONNX and metadata
hashes before it can reach fusion.  The older stateful learned-artifact loader
is retained below for reproducibility only.
"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
from .deterministic import DeterministicVelocityUncertaintyProfile


_ANCHOR_DELTA_PROFILE_FILENAME = "anchor_delta_gru_deterministic_uncertainty.json"


def load_deterministic_velocity_uncertainty_estimator(
    *,
    artifact_directory: Path,
    velocity_artifact_directory: Path,
    profile_filename: str = _ANCHOR_DELTA_PROFILE_FILENAME,
    velocity_onnx_filename: str = "anchor_delta_gru.onnx",
    velocity_metadata_filename: str = "anchor_delta_gru.metadata.json",
) -> DeterministicVelocityUncertaintyProfile:
    """Load a deterministic profile after strict velocity-artifact binding checks.

    A profile is meaningful only for the exact ONNX graph and feature metadata
    that produced its out-of-fold residuals. The hashes prevent a retrained
    velocity model from silently reusing the prior model's covariance.
    """

    filenames = (profile_filename, velocity_onnx_filename, velocity_metadata_filename)
    if any(Path(filename).name != filename for filename in filenames):
        raise ValueError("Uncertainty artifact filenames must not contain directories.")
    path = artifact_directory / profile_filename
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"Deterministic anchor-GRU uncertainty profile is missing: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Deterministic anchor-GRU uncertainty profile is invalid JSON: {path}"
        ) from error

    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported deterministic uncertainty profile schema.")
    if document.get("profile_kind") not in {
        "anchor_delta_gru_deterministic_uncertainty",
        "deterministic_velocity_uncertainty",
    }:
        raise ValueError("Artifact is not a supported deterministic uncertainty profile.")

    onnx_path = velocity_artifact_directory / velocity_onnx_filename
    metadata_path = velocity_artifact_directory / velocity_metadata_filename
    if document.get("velocity_onnx_sha256") != _sha256_file(onnx_path):
        raise ValueError("Deterministic uncertainty does not match the GRU ONNX file.")
    if document.get("velocity_metadata_sha256") != _sha256_file(metadata_path):
        raise ValueError("Deterministic uncertainty does not match GRU metadata.")

    try:
        velocity_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Anchor-GRU metadata is not valid JSON.") from error
    if velocity_metadata.get("model_id") != document["velocity_model_id"]:
        raise ValueError("Velocity metadata model ID differs from uncertainty profile.")

    inflation = document.get("risk_inflation")
    if not isinstance(inflation, dict):
        raise ValueError("Deterministic uncertainty profile lacks risk inflation.")
    return DeterministicVelocityUncertaintyProfile(
        model_id=_non_blank_string(document, "velocity_model_id"),
        horizon_seconds=_finite_tuple(
            document.get("horizon_seconds"),
            _list_length(document, "horizon_seconds"),
            "horizon_seconds",
        ),
        base_standard_deviation_mps=_positive_tuple(
            document.get("base_standard_deviation_mps"),
            _list_length(document, "base_standard_deviation_mps"),
            "base_standard_deviation_mps",
        ),
        variance_ceiling_m2ps2=_positive_float(document, "variance_ceiling_m2ps2"),
        reference_acceleration_std_mps2=_positive_float(
            inflation, "reference_acceleration_std_mps2"
        ),
        reference_angular_velocity_rms_radps=_positive_float(
            inflation, "reference_angular_velocity_rms_radps"
        ),
        reference_minimum_calibration_confidence=_unit_interval_positive_float(
            inflation, "reference_minimum_calibration_confidence"
        ),
        reference_final_quality_score=_unit_interval_positive_float(
            inflation, "reference_final_quality_score"
        ),
        roughness_std_multiplier=_non_negative_float(
            inflation, "roughness_std_multiplier"
        ),
        turn_std_multiplier=_non_negative_float(inflation, "turn_std_multiplier"),
        calibration_std_multiplier=_non_negative_float(
            inflation, "calibration_std_multiplier"
        ),
        quality_std_multiplier=_non_negative_float(
            inflation, "quality_std_multiplier"
        ),
    )


def load_anchor_delta_gru_deterministic_uncertainty_estimator(
    *,
    artifact_directory: Path,
    velocity_artifact_directory: Path,
) -> DeterministicVelocityUncertaintyProfile:
    """Load the legacy selected-GRU profile using the standard filename.

    New production-preprocessor retraining runs should use the generic loader
    above with a new model ID and a freshly fitted residual profile. This
    wrapper preserves the existing selected runtime contract unchanged.
    """

    return load_deterministic_velocity_uncertainty_estimator(
        artifact_directory=artifact_directory,
        velocity_artifact_directory=velocity_artifact_directory,
    )


def load_stateful_velocity_uncertainty_estimator(
    artifact_directory: Path,
) -> LearnedVelocityUncertaintyEstimator:
    """Load the OOF-trained, held-out-calibrated variance model for pre-EKF use.

    The ``.pt`` file is a trusted local project artifact produced by
    ``scripts/train_stateful_velocity_uncertainty.py``. It contains sklearn's
    fitted scaler, so it must not be replaced with an untrusted downloaded file.
    """

    # This older experimental loader is deliberately lazy: the selected
    # deterministic runtime should not import PyTorch merely because a legacy
    # learned artifact happens to be present in the repository.
    import torch

    from .calibration import VarianceScaleCalibration
    from .features import UNCERTAINTY_FEATURE_NAMES
    from .heuristics import HeuristicUncertaintyConfig
    from .inference import LearnedVelocityUncertaintyEstimator
    from .model import HeteroscedasticVarianceNetwork

    path = artifact_directory / "stateful_velocity_uncertainty.pt"
    if not path.is_file():
        raise FileNotFoundError(f"Stateful uncertainty artifact is missing: {path}")
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1:
        raise ValueError("Unsupported stateful uncertainty artifact schema.")
    if checkpoint.get("model_id") != "stateful_anchor_delta_gru_onnx_v1":
        raise ValueError("Uncertainty artifact belongs to a different velocity model.")
    if tuple(checkpoint.get("feature_names", ())) != UNCERTAINTY_FEATURE_NAMES:
        raise ValueError("Uncertainty feature order differs from the runtime contract.")
    scaler = checkpoint.get("feature_scaler")
    mean = getattr(scaler, "mean_", None)
    scale = getattr(scaler, "scale_", None)
    feature_mean = _finite_tuple(mean, len(UNCERTAINTY_FEATURE_NAMES), "mean")
    feature_scale = _positive_tuple(scale, len(UNCERTAINTY_FEATURE_NAMES), "scale")
    model = HeteroscedasticVarianceNetwork(
        feature_count=len(UNCERTAINTY_FEATURE_NAMES),
        hidden_size=_positive_int(checkpoint, "hidden_size"),
        variance_floor_m2ps2=_positive_float(checkpoint, "variance_floor_m2ps2"),
        variance_ceiling_m2ps2=_positive_float(
            checkpoint, "variance_ceiling_m2ps2"
        ),
    )
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("Uncertainty artifact has no neural-network state.")
    model.load_state_dict(state_dict)
    heuristic_document = checkpoint.get("heuristic_safety_config")
    if not isinstance(heuristic_document, dict):
        raise ValueError("Uncertainty artifact lacks heuristic safety settings.")
    return LearnedVelocityUncertaintyEstimator(
        network=model,
        calibration=VarianceScaleCalibration(
            scale=_positive_float(checkpoint, "variance_scale")
        ),
        variance_floor_m2ps2=_positive_float(checkpoint, "variance_floor_m2ps2"),
        variance_ceiling_m2ps2=_positive_float(
            checkpoint, "variance_ceiling_m2ps2"
        ),
        feature_mean=feature_mean,
        feature_scale=feature_scale,
        heuristic_config=HeuristicUncertaintyConfig(**heuristic_document),
    )


def _finite_tuple(value: object, length: int, name: str) -> tuple[float, ...]:
    values = tuple(float(item) for item in np.asarray(value).reshape(-1))
    if len(values) != length or not all(isfinite(item) for item in values):
        raise ValueError(f"Uncertainty artifact scaler {name} is incompatible.")
    return values


def _positive_tuple(value: object, length: int, name: str) -> tuple[float, ...]:
    values = _finite_tuple(value, length, name)
    if not all(item > 0.0 for item in values):
        raise ValueError(f"Uncertainty artifact scaler {name} must be positive.")
    return values


def _positive_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
        raise ValueError(f"Uncertainty artifact field {key!r} must be positive.")
    return item


def _positive_float(value: dict[str, Any], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, (int, float)) or not isfinite(float(item)) or item <= 0.0:
        raise ValueError(f"Uncertainty artifact field {key!r} must be positive.")
    return float(item)


def _non_negative_float(value: dict[str, Any], key: str) -> float:
    """Read one finite deterministic-inflation multiplier."""

    item = value.get(key)
    if not isinstance(item, (int, float)) or not isfinite(float(item)) or item < 0.0:
        raise ValueError(f"Uncertainty artifact field {key!r} must be non-negative.")
    return float(item)


def _unit_interval_positive_float(value: dict[str, Any], key: str) -> float:
    """Read a finite reference confidence in the interval ``(0, 1]``."""

    item = value.get(key)
    if (
        not isinstance(item, (int, float))
        or not isfinite(float(item))
        or not 0.0 < item <= 1.0
    ):
        raise ValueError(
            f"Uncertainty artifact field {key!r} must be in the interval (0, 1]."
        )
    return float(item)


def _non_blank_string(value: dict[str, Any], key: str) -> str:
    """Read a required non-empty artifact identifier."""

    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"Uncertainty artifact field {key!r} must be non-blank.")
    return item


def _list_length(value: dict[str, Any], key: str) -> int:
    """Return the non-zero length of one numeric JSON list."""

    item = value.get(key)
    if not isinstance(item, list) or not item:
        raise ValueError(f"Uncertainty artifact field {key!r} must be a non-empty list.")
    return len(item)


def _sha256_file(path: Path) -> str:
    """Hash one selected velocity artifact without loading its implementation."""

    try:
        stream = path.open("rb")
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Required velocity artifact is missing: {path}") from error
    with stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

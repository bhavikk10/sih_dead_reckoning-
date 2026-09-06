"""Run one complete deterministic replay for a designated demo journey.

This is an offline integration exercise, not a live-service command. It feeds
recorded phone GNSS and phone IMU callbacks through the deterministic
preprocessing, selected ONNX velocity model, uncertainty profile, and EKF. A
scheduled GNSS blackout makes dead-reckoning behaviour visible; CAN/reference
values remain evaluation-only.

Usage from the repository root::

    $env:PYTHONPATH = "src"
    python scripts/replay.py --journey Vta4 --output artifacts/demo_replays/Vta4.json

The permitted journeys are the agreed UI/integration demos. They are
development journeys, so their replay results are not independent accuracy
claims.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from idr_backend.evaluation.replay import (
    BlackoutScenario,
    ReplayParameterSet,
    load_raw_replay_journey,
    replay_journey,
)


_DEMO_JOURNEYS = ("Vta4", "Vta22", "Vta27")


def main() -> None:
    """Replay a designated demo journey and optionally persist its report."""

    arguments = _parse_arguments()
    root = Path(__file__).resolve().parents[1]
    parameters = _load_parameters(arguments.parameters_profile)
    scenario = BlackoutScenario(
        blackout_start_s=arguments.blackout_start_s,
        blackout_duration_s=arguments.blackout_duration_s,
        required_recovery_s=arguments.recovery_s,
    )
    journey = load_raw_replay_journey(arguments.data_root / "raw", arguments.journey)
    report = replay_journey(
        journey=journey,
        scenario=scenario,
        parameters=parameters,
        velocity_artifact_directory=arguments.velocity_artifact_directory,
        uncertainty_artifact_directory=arguments.uncertainty_artifact_directory,
        maximum_replay_duration_s=arguments.maximum_replay_duration_s,
        velocity_model_family=arguments.velocity_model_family,
        uncertainty_profile_filename=arguments.uncertainty_profile_filename,
    )
    payload = report.as_dict()

    if arguments.output is not None:
        output_path = arguments.output
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote replay report: {output_path}")

    print(
        " | ".join(
            (
                f"journey={report.journey_id}",
                f"velocity_model_family={arguments.velocity_model_family}",
                f"blackout_velocity_mae_kmh={_format_metric(report.blackout_velocity_mae_kmh)}",
                f"blackout_endpoint_error_m={_format_metric(report.blackout_endpoint_relative_position_error_m)}",
                f"velocity_updates={report.velocity_model_accepted}/{report.velocity_observations}",
                f"valid_for_scoring={report.valid_for_scoring}",
            )
        )
    )
    print(json.dumps(payload, indent=2))


def _parse_arguments() -> argparse.Namespace:
    """Parse only explicit replay inputs; this command never trains a model."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journey", choices=_DEMO_JOURNEYS, default="Vta4")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=root / "SIH-2-main" / "SIH-2-main" / "IOVNBD-Speed-Prediction" / "data",
    )
    parser.add_argument(
        "--velocity-artifact-directory",
        type=Path,
        default=root / "artifacts" / "anchored_velocity_comparison",
    )
    parser.add_argument(
        "--uncertainty-artifact-directory",
        type=Path,
        default=root / "artifacts" / "anchored_velocity_comparison",
    )
    parser.add_argument(
        "--velocity-model-family",
        choices=("anchor_delta_gru", "stateful_anchor_delta_gru"),
        default="anchor_delta_gru",
        help="Use the reviewed windowed default unless explicitly evaluating stateful artifacts.",
    )
    parser.add_argument(
        "--uncertainty-profile-filename",
        default="anchor_delta_gru_deterministic_uncertainty.json",
        help="Profile filename relative to --uncertainty-artifact-directory.",
    )
    parser.add_argument(
        "--parameters-profile",
        type=Path,
        default=root
        / "artifacts"
        / "deterministic_navigation_replay_final"
        / "selected_ekf_profile.json",
        help="JSON profile with a top-level 'parameters' object.",
    )
    parser.add_argument("--blackout-start-s", type=float, default=30.0)
    parser.add_argument("--blackout-duration-s", type=float, default=60.0)
    parser.add_argument("--recovery-s", type=float, default=30.0)
    parser.add_argument(
        "--maximum-replay-duration-s",
        type=float,
        default=None,
        help="Optional upper bound for a quick smoke replay; omit for the full recording.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON report path, relative to the repository root if not absolute.",
    )
    return parser.parse_args()


def _load_parameters(profile_path: Path) -> ReplayParameterSet:
    """Load the reviewed EKF profile rather than silently using fresh defaults."""

    try:
        document = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Replay parameter profile is missing: {profile_path}") from error

    payload = document.get("parameters")
    if not isinstance(payload, dict):
        raise ValueError("Replay parameter profile needs a top-level 'parameters' object.")
    return ReplayParameterSet(**payload)


def _format_metric(value: float | None) -> str:
    """Keep a missing score visibly distinct from a numerical zero."""

    return "unavailable" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    main()

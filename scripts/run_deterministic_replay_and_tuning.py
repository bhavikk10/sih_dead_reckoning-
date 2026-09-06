r"""Tune native EKF settings on development drives, then replay a fresh holdout.

Usage from the repository root::

    $env:PYTHONPATH = "src"
    E:\ANACONDA\python.exe scripts\run_deterministic_replay_and_tuning.py

The command has a strict split policy.  It uses only the already-designated
development journeys to select process-noise, measurement-gate, and NHC
settings.  `Vta6` is an independent raw journey: it is loaded exactly once,
after the selection has been written, and no result from it alters a setting.
The earlier velocity frozen-test trips are deliberately not read by this tool.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from statistics import mean
from typing import Iterable

import pandas as pd

from idr_backend.evaluation.replay import (
    BlackoutScenario,
    RawReplayJourney,
    ReplayParameterSet,
    ReplayReport,
    load_raw_replay_journey,
    replay_journey,
)


_DEVELOPMENT_JOURNEYS = (
    # Each is at least the 250 seconds required by the standard raw replay
    # scenario. These were part of model development already, so they cannot
    # serve as a new final holdout but are valid for EKF policy selection.
    "M",
    "S1",
    "S2",
    "S4",
    "Vfa02",
    "Vta16",
    "Vta1a",
    "Vta2",
    "Vta29",
    "Y1",
)
# Stage-wise tuning uses a heterogeneous, predeclared subset so a 3x3x3
# search does not repeatedly overfit every development trip. The selected
# profile is then replayed across the complete development list below.
_TUNING_JOURNEYS = ("M", "S1", "Vfa02", "Vta2")
_FRESH_HOLDOUT_JOURNEY = "Vta6"
_FRESH_HOLDOUT_SCENARIO = BlackoutScenario(
    blackout_start_s=30.0,
    blackout_duration_s=60.0,
    required_recovery_s=30.0,
)


def main() -> None:
    """Run reproducible stage-wise tuning and a post-selection holdout replay."""

    arguments = _parse_arguments()
    raw_directory = arguments.data_root / "raw"
    output_directory = arguments.output_directory
    output_directory.mkdir(parents=True, exist_ok=True)

    scenario = BlackoutScenario(
        blackout_start_s=arguments.blackout_start_s,
        blackout_duration_s=arguments.blackout_duration_s,
        required_recovery_s=arguments.recovery_s,
    )
    velocity_directory = arguments.velocity_artifact_directory
    uncertainty_directory = arguments.uncertainty_artifact_directory

    development_ids = tuple(arguments.development_journeys) or _DEVELOPMENT_JOURNEYS
    if _FRESH_HOLDOUT_JOURNEY in development_ids:
        raise ValueError("Vta6 is the independent holdout and must not be tuned on.")
    development = _load_eligible_journeys(raw_directory, development_ids, scenario)
    if len(development) < 3:
        raise ValueError("At least three eligible development drives are required.")
    tuning_development = tuple(
        journey for journey in development if journey.journey_id in _TUNING_JOURNEYS
    )
    if len(tuning_development) < 3:
        # A caller who intentionally replaces the development list gets a
        # transparent fallback, not an accidental empty predeclared subset.
        tuning_development = development

    base = ReplayParameterSet(name="baseline")
    if arguments.skip_tuning:
        selected = base
        selection_rows: list[dict[str, object]] = []
        development_reports = _replay_many(
            development,
            scenario,
            selected,
            velocity_directory,
            uncertainty_directory,
        )
    else:
        selected, selection_rows = _stagewise_tune(
            tuning_development,
            scenario,
            base,
            velocity_directory,
            uncertainty_directory,
        )
        development_reports = _replay_many(
            development,
            scenario,
            selected,
            velocity_directory,
            uncertainty_directory,
        )

    _write_json(
        output_directory / "selected_ekf_profile.json",
        {
            "schema_version": 1,
            "selection_data": "development journeys only",
            "development_journeys": list(development_ids),
            "stagewise_tuning_journeys": [
                journey.journey_id for journey in tuning_development
            ],
            "excluded_previously_exposed_velocity_test_journeys": [
                "S3a",
                "S3c",
                "Vfa01",
                "Vta30",
            ],
            "fresh_holdout_journey": _FRESH_HOLDOUT_JOURNEY,
            "fresh_holdout_scenario": asdict(_FRESH_HOLDOUT_SCENARIO),
            "scenario": asdict(scenario),
            "parameters": asdict(selected),
            "selection_objective": _selection_objective_description(),
        },
    )
    pd.DataFrame(selection_rows).to_csv(
        output_directory / "development_tuning_candidates.csv", index=False
    )
    _reports_frame(development_reports).to_csv(
        output_directory / "development_selected_profile_replays.csv", index=False
    )

    # Important ordering guarantee: fresh Vta6 is not loaded until the
    # development-only decision exists on disk. It cannot influence the winner.
    holdout = load_raw_replay_journey(raw_directory, _FRESH_HOLDOUT_JOURNEY)
    holdout_report = replay_journey(
        journey=holdout,
        scenario=_FRESH_HOLDOUT_SCENARIO,
        parameters=selected,
        velocity_artifact_directory=velocity_directory,
        uncertainty_artifact_directory=uncertainty_directory,
    )
    _write_json(output_directory / "fresh_holdout_replay.json", holdout_report.as_dict())
    _reports_frame((holdout_report,)).to_csv(
        output_directory / "fresh_holdout_replay.csv", index=False
    )

    _print_summary(selected, development_reports, holdout_report, output_directory)


def _parse_arguments() -> argparse.Namespace:
    """Parse only paths/timing choices; no hidden training or download action."""

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
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
        "--output-directory",
        type=Path,
        default=root / "artifacts" / "deterministic_navigation_replay",
    )
    parser.add_argument("--blackout-start-s", type=float, default=100.0)
    parser.add_argument("--blackout-duration-s", type=float, default=120.0)
    parser.add_argument("--recovery-s", type=float, default=30.0)
    parser.add_argument(
        "--development-journeys",
        nargs="*",
        default=(),
        help="Optional replacement list; Vta6 is always forbidden here.",
    )
    parser.add_argument(
        "--skip-tuning",
        action="store_true",
        help="Replay baseline plus independent holdout without selecting a profile.",
    )
    return parser.parse_args()


def _load_eligible_journeys(
    raw_directory: Path,
    journey_ids: Iterable[str],
    scenario: BlackoutScenario,
) -> tuple[RawReplayJourney, ...]:
    """Load only complete recordings that can support the full requested scenario."""

    journeys: list[RawReplayJourney] = []
    skipped: list[str] = []
    for journey_id in journey_ids:
        journey = load_raw_replay_journey(raw_directory, journey_id)
        if journey.duration_s < scenario.minimum_duration_s:
            skipped.append(f"{journey_id} ({journey.duration_s:.1f}s)")
            continue
        journeys.append(journey)
    if skipped:
        print("Skipping short development recordings:", ", ".join(skipped))
    return tuple(journeys)


def _stagewise_tune(
    development: tuple[RawReplayJourney, ...],
    scenario: BlackoutScenario,
    base: ReplayParameterSet,
    velocity_directory: Path,
    uncertainty_directory: Path,
) -> tuple[ReplayParameterSet, list[dict[str, object]]]:
    """Tune three named parameter families without a combinatorial search.

    A full 3x3x3 grid would select among 27 profiles from a modest number of
    drives and is more likely to exploit noise than improve field transfer.
    Stage-wise selection makes each trade-off inspectable: first IMU process
    covariance, then measurement gates, then NHC trust. Every stage uses the
    exact same raw development blackout scenario and objective.
    """

    all_rows: list[dict[str, object]] = []
    process_candidates = (
        replace(
            base,
            name="process_low",
            accelerometer_noise_scale=0.70,
            gyroscope_noise_scale=0.70,
            bias_random_walk_scale=0.70,
        ),
        base,
        replace(
            base,
            name="process_high",
            accelerometer_noise_scale=1.50,
            gyroscope_noise_scale=1.50,
            bias_random_walk_scale=1.50,
        ),
    )
    selected = _select_stage(
        "process_noise", process_candidates, development, scenario,
        velocity_directory, uncertainty_directory, all_rows
    )

    gate_candidates = (
        replace(
            selected,
            name="gates_strict",
            gnss_position_nis_gate=5.99,
            gnss_velocity_nis_gate=5.99,
            velocity_model_nis_gate=3.84,
        ),
        replace(selected, name="gates_balanced"),
        replace(
            selected,
            name="gates_permissive",
            gnss_position_nis_gate=13.82,
            gnss_velocity_nis_gate=13.82,
            velocity_model_nis_gate=10.83,
        ),
    )
    selected = _select_stage(
        "measurement_gates", gate_candidates, development, scenario,
        velocity_directory, uncertainty_directory, all_rows
    )

    nhc_candidates = (
        replace(
            selected,
            name="nhc_tight",
            nhc_lateral_std_scale=0.70,
            nhc_vertical_std_scale=0.70,
            nhc_maximum_yaw_rate_radps=0.55,
        ),
        replace(selected, name="nhc_balanced"),
        replace(
            selected,
            name="nhc_loose",
            nhc_lateral_std_scale=1.50,
            nhc_vertical_std_scale=1.50,
            nhc_maximum_yaw_rate_radps=1.10,
        ),
    )
    selected = _select_stage(
        "non_holonomic_constraint", nhc_candidates, development, scenario,
        velocity_directory, uncertainty_directory, all_rows
    )
    return replace(selected, name="development_selected_v1"), all_rows


def _select_stage(
    stage: str,
    candidates: Iterable[ReplayParameterSet],
    development: tuple[RawReplayJourney, ...],
    scenario: BlackoutScenario,
    velocity_directory: Path,
    uncertainty_directory: Path,
    all_rows: list[dict[str, object]],
) -> ReplayParameterSet:
    """Replay every candidate on every development trip and select visibly."""

    candidate_scores: list[tuple[float, ReplayParameterSet]] = []
    for candidate in candidates:
        print(f"Tuning {stage}: {candidate.name}")
        reports = _replay_many(
            development, scenario, candidate, velocity_directory, uncertainty_directory
        )
        score, summary = _aggregate_score(reports)
        all_rows.append(
            {
                "stage": stage,
                "candidate": candidate.name,
                "score": score,
                **asdict(candidate),
                **summary,
            }
        )
        print(
            f"  score={score:.3f}; valid={summary['valid_journeys']}/"
            f"{len(reports)}; endpoint={summary['mean_endpoint_drift_m']:.2f}m"
        )
        candidate_scores.append((score, candidate))
    return min(candidate_scores, key=lambda item: item[0])[1]


def _replay_many(
    journeys: Iterable[RawReplayJourney],
    scenario: BlackoutScenario,
    parameters: ReplayParameterSet,
    velocity_directory: Path,
    uncertainty_directory: Path,
) -> tuple[ReplayReport, ...]:
    """Run a completely fresh causal pipeline per journey, never sharing state."""

    return tuple(
        replay_journey(
            journey=journey,
            scenario=scenario,
            parameters=parameters,
            velocity_artifact_directory=velocity_directory,
            uncertainty_artifact_directory=uncertainty_directory,
            maximum_replay_duration_s=scenario.minimum_duration_s,
        )
        for journey in journeys
    )


def _aggregate_score(reports: Iterable[ReplayReport]) -> tuple[float, dict[str, object]]:
    """Rank viable profiles by drift, speed, rejection, and recovery behavior.

    Endpoint drift dominates because it is the dead-reckoning failure that the
    EKF must control. Velocity MAE, a persistent measurement-rejection rate,
    and time-to-GNSS_AIDED act as modest tie-breakers. Any invalid replay gets
    a large fixed penalty; it cannot win merely by omitting bad samples.
    """

    materialised = tuple(reports)
    valid = tuple(report for report in materialised if report.valid_for_scoring)
    if not valid:
        return 1_000_000.0, {
            "valid_journeys": 0,
            "mean_endpoint_drift_m": float("nan"),
            "mean_velocity_mae_mps": float("nan"),
            "mean_gnss_aided_recovery_s": float("nan"),
            "velocity_model_rejection_rate": float("nan"),
        }

    endpoint = mean(_required(report.blackout_endpoint_relative_position_error_m) for report in valid)
    velocity = mean(_required(report.blackout_velocity_mae_mps) for report in valid)
    recovery = mean(_required(report.gnss_aided_recovery_s) for report in valid)
    velocity_updates = sum(
        report.velocity_model_accepted + report.velocity_model_rejected for report in valid
    )
    velocity_rejections = sum(report.velocity_model_rejected for report in valid)
    rejection_rate = velocity_rejections / max(1, velocity_updates)
    invalid_penalty = 1_000.0 * (len(materialised) - len(valid))
    score = endpoint + 3.0 * velocity + 2.0 * recovery + 20.0 * rejection_rate + invalid_penalty
    return score, {
        "valid_journeys": len(valid),
        "mean_endpoint_drift_m": endpoint,
        "mean_velocity_mae_mps": velocity,
        "mean_gnss_aided_recovery_s": recovery,
        "velocity_model_rejection_rate": rejection_rate,
    }


def _required(value: float | None) -> float:
    """Make an incomplete report ineligible instead of silently treating it as zero."""

    if value is None:
        raise ValueError("A valid replay report unexpectedly lacks a scored metric.")
    return value


def _reports_frame(reports: Iterable[ReplayReport]) -> pd.DataFrame:
    """Flatten immutable reports for quick inspection in spreadsheet/notebook form."""

    rows: list[dict[str, object]] = []
    for report in reports:
        row = report.as_dict()
        row["scenario"] = json.dumps(row["scenario"], sort_keys=True)
        row["parameters"] = json.dumps(row["parameters"], sort_keys=True)
        row["scoring_notes"] = " | ".join(row["scoring_notes"])
        rows.append(row)
    return pd.DataFrame(rows)


def _write_json(path: Path, document: object) -> None:
    """Write a stable, readable artifact without serialising NumPy internals."""

    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _selection_objective_description() -> str:
    """Record the exact scale-free objective beside the selected profile."""

    return (
        "mean endpoint relative horizontal drift in m + 3 * mean blackout "
        "speed MAE in m/s + 2 * mean seconds to GNSS_AIDED recovery + 20 * "
        "velocity-model update rejection rate; invalid journeys add 1000. "
        "This is stage-wise development tuning, not a model-performance claim."
    )


def _print_summary(
    selected: ReplayParameterSet,
    development_reports: Iterable[ReplayReport],
    holdout_report: ReplayReport,
    output_directory: Path,
) -> None:
    """Print short run evidence while keeping full per-trip evidence on disk."""

    _, development = _aggregate_score(tuple(development_reports))
    print("\nSelected native-EKF profile:", asdict(selected))
    print("Development selection summary:", development)
    print("Fresh independent Vta6 replay:")
    print(json.dumps(holdout_report.as_dict(), indent=2, default=str))
    print(f"\nArtifacts written to {output_directory}")


if __name__ == "__main__":
    main()

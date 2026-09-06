"""Efficient development-only experiment for an anchor-to-blackout GRU.

The existing deployed GRU sees only the latest five seconds.  This experiment
keeps every cleaned 10 Hz IMU sample from the last trusted GNSS anchor and
carries a unidirectional GRU state through the complete blackout.  Training
uses 30-second truncated backpropagation: hidden state crosses chunk boundaries
but the gradient graph does not.  Inference therefore retains the complete
history while training stays practical on a 4 GB laptop GPU.

This module is notebook-local.  It does not change the deployed velocity
adapter, inspect frozen-test journeys during model selection, or fuse anything
into the EKF.
"""

from __future__ import annotations

import copy
import json
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import ParameterSampler
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset, Sampler

from velocity_experiment import ExperimentConfig, ProcessedJourney, regression_metrics


STATEFUL_FEATURE_NAMES = (
    "linear_acceleration_x_mps2",
    "linear_acceleration_y_mps2",
    "linear_acceleration_z_mps2",
    "angular_velocity_x_radps",
    "angular_velocity_y_radps",
    "angular_velocity_z_radps",
    "anchor_speed_mps",
    "integrated_speed_mps",
    "seconds_since_anchor",
    "running_mean_calibration_confidence",
    "running_minimum_calibration_confidence",
)


@dataclass(frozen=True)
class StatefulBlackoutSequence:
    """One contiguous 10 Hz sequence starting at a trusted GNSS anchor."""

    journey_id: str
    anchor_timestamp_ns: int
    anchor_speed_mps: float
    features: np.ndarray
    # Kept separately because a rolling 5 s uncertainty window needs actual
    # per-sample confidence, not the stateful model's running minimum alone.
    calibration_confidence: np.ndarray
    target_delta_mps: np.ndarray
    training_mask: np.ndarray
    evaluation_mask: np.ndarray


@dataclass(frozen=True)
class StatefulTrainingConfig:
    """Training-resource policy separate from model hyperparameters."""

    chunk_steps: int = 300
    batch_size: int = 16
    maximum_epochs: int = 150
    early_stopping_patience: int = 15
    gradient_clip_norm: float = 5.0

    def __post_init__(self) -> None:
        if self.chunk_steps <= 0 or self.batch_size <= 0:
            raise ValueError("Chunk and batch sizes must be positive.")
        if self.maximum_epochs <= 0 or self.early_stopping_patience <= 0:
            raise ValueError("Epoch limits must be positive.")


@dataclass(frozen=True)
class StatefulFoldResult:
    """Best validation state from one journey-isolated fold."""

    model: StatefulAnchorDeltaGru
    scaler: StandardScaler
    best_epoch: int
    macro_journey_mae_mps: float
    predictions: pd.DataFrame
    elapsed_seconds: float


@dataclass(frozen=True)
class StatefulFinalizationResult:
    """Development-only OOF evidence and one refit stateful-GRU candidate.

    This remains an experiment artifact.  In particular, it is deliberately
    separate from the deployed five-second ONNX velocity adapter until the
    frozen-test evaluation and runtime-state contract have been reviewed.
    """

    oof_predictions: pd.DataFrame
    oof_metrics: dict[str, float]
    final_model: StatefulAnchorDeltaGru
    final_scaler: StandardScaler
    final_epochs: int


def build_stateful_blackout_sequences(
    journeys: Sequence[ProcessedJourney],
    *,
    config: ExperimentConfig,
    permitted_journeys: set[str],
    label_period_s: float = 1.0,
) -> list[StatefulBlackoutSequence]:
    """Build raw-10-Hz anchor sequences using no post-anchor GNSS values."""

    label_steps = max(1, round(label_period_s / config.sample_period_s))
    horizon_steps = {
        round(horizon_s / config.sample_period_s)
        for horizon_s in config.blackout_horizons_s
    }
    minimum_steps = min(horizon_steps)
    maximum_steps = max(horizon_steps)
    anchor_stride = max(1, round(config.anchor_stride_s / config.sample_period_s))
    sequences: list[StatefulBlackoutSequence] = []

    for journey in journeys:
        if journey.journey_id not in permitted_journeys:
            continue

        for segment_id in np.unique(journey.segment_ids):
            segment = np.flatnonzero(journey.segment_ids == segment_id)
            segment_start, segment_end = int(segment[0]), int(segment[-1])

            for anchor in range(segment_start, segment_end + 1, anchor_stride):
                end = min(anchor + maximum_steps, segment_end)
                if end - anchor < minimum_steps:
                    continue

                anchor_speed = float(journey.gps_speed_mps[anchor])
                if not np.isfinite(anchor_speed) or anchor_speed < 0.0:
                    continue

                clean_imu = np.asarray(journey.clean_imu[anchor : end + 1], dtype=np.float32)
                targets = np.asarray(
                    journey.target_speed_mps[anchor : end + 1], dtype=np.float32
                )
                confidence = np.asarray(
                    journey.calibration_confidence[anchor : end + 1],
                    dtype=np.float32,
                )
                if not (
                    np.isfinite(clean_imu).all()
                    and np.isfinite(targets).all()
                    and np.isfinite(confidence).all()
                ):
                    continue

                steps = np.arange(len(clean_imu), dtype=np.int64)
                integrated_delta = np.zeros(len(clean_imu), dtype=np.float32)
                integrated_delta[1:] = np.cumsum(
                    0.5
                    * (clean_imu[1:, 0] + clean_imu[:-1, 0])
                    * config.sample_period_s,
                    dtype=np.float32,
                )
                integrated_speed = np.maximum(
                    0.0, anchor_speed + integrated_delta
                ).astype(np.float32)
                running_mean_confidence = np.cumsum(
                    confidence, dtype=np.float32
                ) / (steps + 1)
                running_minimum_confidence = np.minimum.accumulate(confidence)

                features = np.column_stack(
                    (
                        clean_imu,
                        np.full(len(clean_imu), anchor_speed, dtype=np.float32),
                        integrated_speed,
                        steps.astype(np.float32) * config.sample_period_s,
                        running_mean_confidence,
                        running_minimum_confidence,
                    )
                ).astype(np.float32)
                training_mask = (steps > 0) & (steps % label_steps == 0)
                evaluation_mask = np.isin(steps, list(horizon_steps))
                if not evaluation_mask.any():
                    continue

                sequences.append(
                    StatefulBlackoutSequence(
                        journey_id=journey.journey_id,
                        anchor_timestamp_ns=int(journey.timestamps_ns[anchor]),
                        anchor_speed_mps=anchor_speed,
                        features=features,
                        calibration_confidence=confidence,
                        target_delta_mps=(targets - anchor_speed).astype(np.float32),
                        training_mask=training_mask,
                        evaluation_mask=evaluation_mask,
                    )
                )

    if not sequences:
        raise ValueError("No development stateful-blackout sequences were produced.")
    return sequences


def map_existing_grouped_folds(
    sequences: Sequence[StatefulBlackoutSequence],
    *,
    blackout_dataset: object,
    blackout_folds: Sequence[tuple[np.ndarray, np.ndarray]],
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Reuse the exact journey assignment from the existing fair comparison."""

    journey_ids = np.asarray([item.journey_id for item in sequences], dtype=str)
    source_journeys = np.asarray(getattr(blackout_dataset, "journey_ids"))
    mapped: list[tuple[np.ndarray, np.ndarray]] = []

    for train, validation in blackout_folds:
        train_groups = set(source_journeys[train])
        validation_groups = set(source_journeys[validation])
        train_indices = np.flatnonzero(np.isin(journey_ids, list(train_groups)))
        validation_indices = np.flatnonzero(
            np.isin(journey_ids, list(validation_groups))
        )
        if not len(train_indices) or not len(validation_indices):
            raise ValueError("Mapped stateful fold contains an empty side.")
        if set(journey_ids[train_indices]) & set(journey_ids[validation_indices]):
            raise AssertionError("Stateful grouped fold leaks a journey.")
        mapped.append((train_indices, validation_indices))
    return mapped


class StatefulAnchorDeltaGru(nn.Module):
    """Unidirectional GRU that emits anchor-relative speed at every sample."""

    def __init__(
        self,
        *,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=len(STATEFUL_FEATURE_NAMES),
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=False,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )


@dataclass(frozen=True)
class _ScaledSequence:
    sequence_index: int
    source: StatefulBlackoutSequence
    features: np.ndarray
    weight: float


class _ScaledSequenceDataset(Dataset[_ScaledSequence]):
    def __init__(self, items: Sequence[_ScaledSequence]) -> None:
        self.items = tuple(items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> _ScaledSequence:
        return self.items[index]


class _LengthBucketBatchSampler(Sampler[list[int]]):
    """Batch nearby sequence lengths to avoid repeated padded 120-second work."""

    def __init__(self, lengths: Sequence[int], *, batch_size: int, seed: int) -> None:
        self._batch_size = batch_size
        self._seed = seed
        self._epoch = 0
        ordered = sorted(range(len(lengths)), key=lambda index: lengths[index])
        self._batches = [
            ordered[start : start + batch_size]
            for start in range(0, len(ordered), batch_size)
        ]

    def __iter__(self) -> Iterator[list[int]]:
        order = list(range(len(self._batches)))
        random.Random(self._seed + self._epoch).shuffle(order)
        self._epoch += 1
        for index in order:
            yield self._batches[index]

    def __len__(self) -> int:
        return len(self._batches)


def _fit_scaler(
    sequences: Sequence[StatefulBlackoutSequence], indices: np.ndarray
) -> StandardScaler:
    scaler = StandardScaler()
    for index in indices:
        scaler.partial_fit(sequences[int(index)].features)
    return scaler


def _prepare_scaled_items(
    sequences: Sequence[StatefulBlackoutSequence],
    indices: np.ndarray,
    scaler: StandardScaler,
) -> list[_ScaledSequence]:
    counts = Counter(sequences[int(index)].journey_id for index in indices)
    raw_weights = np.asarray(
        [1.0 / counts[sequences[int(index)].journey_id] for index in indices],
        dtype=np.float32,
    )
    raw_weights /= raw_weights.mean()
    return [
        _ScaledSequence(
            sequence_index=int(index),
            source=sequences[int(index)],
            features=scaler.transform(sequences[int(index)].features).astype(np.float32),
            weight=float(weight),
        )
        for index, weight in zip(indices, raw_weights, strict=True)
    ]


def _collate(items: Sequence[_ScaledSequence]) -> dict[str, object]:
    maximum_length = max(len(item.features) for item in items)
    batch_size = len(items)
    features = torch.zeros(
        batch_size, maximum_length, len(STATEFUL_FEATURE_NAMES), dtype=torch.float32
    )
    targets = torch.zeros(batch_size, maximum_length, dtype=torch.float32)
    training_mask = torch.zeros(batch_size, maximum_length, dtype=torch.bool)
    evaluation_mask = torch.zeros(batch_size, maximum_length, dtype=torch.bool)
    lengths = torch.empty(batch_size, dtype=torch.long)

    for row, item in enumerate(items):
        length = len(item.features)
        lengths[row] = length
        features[row, :length] = torch.from_numpy(item.features)
        targets[row, :length] = torch.from_numpy(item.source.target_delta_mps)
        training_mask[row, :length] = torch.from_numpy(item.source.training_mask)
        evaluation_mask[row, :length] = torch.from_numpy(item.source.evaluation_mask)

    return {
        "items": items,
        "features": features,
        "targets": targets,
        "training_mask": training_mask,
        "evaluation_mask": evaluation_mask,
        "lengths": lengths,
        "weights": torch.tensor([item.weight for item in items]),
    }


def _loader(
    items: Sequence[_ScaledSequence],
    *,
    batch_size: int,
    seed: int,
    shuffle_buckets: bool,
) -> DataLoader:
    dataset = _ScaledSequenceDataset(items)
    if shuffle_buckets:
        batch_sampler: Sampler[list[int]] = _LengthBucketBatchSampler(
            [len(item.features) for item in items],
            batch_size=batch_size,
            seed=seed,
        )
        return DataLoader(
            dataset, batch_sampler=batch_sampler, collate_fn=_collate, num_workers=0
        )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=_collate,
        num_workers=0,
    )


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _chunk_outputs(
    model: StatefulAnchorDeltaGru,
    features: torch.Tensor,
    *,
    chunk_steps: int,
) -> torch.Tensor:
    """Infer all steps while carrying hidden state across bounded chunks."""

    outputs: list[torch.Tensor] = []
    hidden: torch.Tensor | None = None
    for start in range(0, features.shape[1], chunk_steps):
        encoded, hidden = model.gru(features[:, start : start + chunk_steps], hidden)
        outputs.append(model.head(encoded).squeeze(-1))
    return torch.cat(outputs, dim=1)


@torch.inference_mode()
def _predict(
    model: StatefulAnchorDeltaGru,
    loader: DataLoader,
    *,
    device: torch.device,
    chunk_steps: int,
    sample_period_s: float,
) -> pd.DataFrame:
    model.eval()
    rows: list[dict[str, object]] = []
    for batch in loader:
        outputs = _chunk_outputs(
            model,
            batch["features"].to(device),
            chunk_steps=chunk_steps,
        ).cpu().numpy()
        targets = batch["targets"].numpy()
        masks = batch["evaluation_mask"].numpy()
        for row, item in enumerate(batch["items"]):
            for step in np.flatnonzero(masks[row]):
                rows.append(
                    {
                        "sequence_index": item.sequence_index,
                        "journey_id": item.source.journey_id,
                        "anchor_timestamp_ns": item.source.anchor_timestamp_ns,
                        "horizon_s": int(round(step * sample_period_s)),
                        "actual_speed_mps": max(
                            0.0, item.source.anchor_speed_mps + float(targets[row, step])
                        ),
                        "prediction_speed_mps": max(
                            0.0, item.source.anchor_speed_mps + float(outputs[row, step])
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _macro_journey_mae(frame: pd.DataFrame) -> float:
    return float(
        np.mean(
            [
                mean_absolute_error(
                    rows.actual_speed_mps, rows.prediction_speed_mps
                )
                for _, rows in frame.groupby("journey_id")
            ]
        )
    )


def train_stateful_fold(
    sequences: Sequence[StatefulBlackoutSequence],
    *,
    train_indices: np.ndarray,
    validation_indices: np.ndarray,
    parameters: dict[str, object],
    experiment_config: ExperimentConfig,
    training_config: StatefulTrainingConfig,
    device: torch.device,
    seed: int,
    checkpoint_path: Path | None = None,
    log_prefix: str = "",
) -> StatefulFoldResult:
    """Train one fold with raw 10 Hz input and bounded-gradient state carry."""

    started = time.perf_counter()
    _seed_everything(seed)
    scaler = _fit_scaler(sequences, train_indices)
    train_items = _prepare_scaled_items(sequences, train_indices, scaler)
    validation_items = _prepare_scaled_items(sequences, validation_indices, scaler)
    train_loader = _loader(
        train_items,
        batch_size=training_config.batch_size,
        seed=seed,
        shuffle_buckets=True,
    )
    validation_loader = _loader(
        validation_items,
        batch_size=training_config.batch_size,
        seed=seed,
        shuffle_buckets=False,
    )
    model = StatefulAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        dropout=float(parameters["dropout"]),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(parameters["learning_rate"]),
        weight_decay=float(parameters["weight_decay"]),
    )
    best_score = float("inf")
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    stale = 0

    for epoch in range(1, training_config.maximum_epochs + 1):
        model.train()
        total_loss = 0.0
        batch_count = 0
        for batch in train_loader:
            features = batch["features"].to(device)
            targets = batch["targets"].to(device)
            full_mask = batch["training_mask"].to(device).float()
            weights = batch["weights"].to(device)
            denominator = (full_mask * weights[:, None]).sum().clamp_min(1.0)
            hidden: torch.Tensor | None = None
            optimizer.zero_grad(set_to_none=True)
            batch_loss = 0.0

            for start in range(0, features.shape[1], training_config.chunk_steps):
                stop = start + training_config.chunk_steps
                encoded, hidden = model.gru(features[:, start:stop], hidden)
                predicted = model.head(encoded).squeeze(-1)
                chunk_mask = full_mask[:, start:stop]
                if bool(chunk_mask.any()):
                    pointwise = F.smooth_l1_loss(
                        predicted,
                        targets[:, start:stop],
                        beta=experiment_config.huber_beta_mps,
                        reduction="none",
                    )
                    chunk_loss = (
                        pointwise * chunk_mask * weights[:, None]
                    ).sum() / denominator
                    chunk_loss.backward()
                    batch_loss += float(chunk_loss.detach().cpu())
                # Preserve numerical state but cut the gradient graph here.
                hidden = hidden.detach()

            nn.utils.clip_grad_norm_(
                model.parameters(), training_config.gradient_clip_norm
            )
            optimizer.step()
            total_loss += batch_loss
            batch_count += 1

        validation = _predict(
            model,
            validation_loader,
            device=device,
            chunk_steps=training_config.chunk_steps,
            sample_period_s=experiment_config.sample_period_s,
        )
        score = _macro_journey_mae(validation)
        print(
            f"{log_prefix} epoch {epoch:03d} | "
            f"train loss {total_loss / max(batch_count, 1):.4f} | "
            f"validation macro MAE {score * 3.6:.2f} km/h",
            flush=True,
        )
        if score < best_score:
            best_score = score
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale = 0
            if checkpoint_path is not None:
                torch.save(
                    {
                        "state_dict": best_state,
                        "parameters": parameters,
                        "best_epoch": best_epoch,
                        "validation_macro_mae_mps": best_score,
                    },
                    checkpoint_path,
                )
        else:
            stale += 1
            if stale >= training_config.early_stopping_patience:
                break

    if best_state is None:
        raise RuntimeError("Stateful fold produced no valid checkpoint.")
    model.load_state_dict(best_state)
    predictions = _predict(
        model,
        validation_loader,
        device=device,
        chunk_steps=training_config.chunk_steps,
        sample_period_s=experiment_config.sample_period_s,
    )
    return StatefulFoldResult(
        model=model,
        scaler=scaler,
        best_epoch=best_epoch,
        macro_journey_mae_mps=best_score,
        predictions=predictions,
        elapsed_seconds=time.perf_counter() - started,
    )


def stateful_parameter_candidates(
    *, profile: str, count: int, seed: int
) -> list[dict[str, object]]:
    """Return one smoke candidate or the requested bounded 20-candidate search."""

    if profile not in {"smoke", "full"}:
        raise ValueError("profile must be 'smoke' or 'full'.")
    space = {
        "hidden_size": [32, 64],
        "num_layers": [1, 2],
        "dropout": [0.1, 0.2],
        "learning_rate": [1e-3, 3e-4],
        "weight_decay": [1e-4, 3e-4],
    }
    requested = 1 if profile == "smoke" else count
    return list(ParameterSampler(space, n_iter=requested, random_state=seed))


def run_stateful_search(
    sequences: Sequence[StatefulBlackoutSequence],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    experiment_config: ExperimentConfig,
    device: torch.device,
    artifact_directory: Path,
    profile: str = "smoke",
    candidate_count: int = 20,
) -> pd.DataFrame:
    """Run a visible smoke check or full grouped-CV candidate search."""

    artifact_directory.mkdir(parents=True, exist_ok=True)
    candidates = stateful_parameter_candidates(
        profile=profile, count=candidate_count, seed=experiment_config.seed
    )
    selected_folds = folds[:1] if profile == "smoke" else folds
    training = (
        StatefulTrainingConfig(maximum_epochs=3, early_stopping_patience=2)
        if profile == "smoke"
        else StatefulTrainingConfig()
    )
    completed_folds: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for candidate_id, parameters in enumerate(candidates, start=1):
        scores: list[float] = []
        epochs: list[int] = []
        durations: list[float] = []
        for fold_id, (train, validation) in enumerate(selected_folds, start=1):
            prefix = (
                f"candidate {candidate_id}/{len(candidates)}, "
                f"fold {fold_id}/{len(selected_folds)}"
            )
            result = train_stateful_fold(
                sequences,
                train_indices=train,
                validation_indices=validation,
                parameters=parameters,
                experiment_config=experiment_config,
                training_config=training,
                device=device,
                seed=experiment_config.seed + candidate_id * 100 + fold_id,
                checkpoint_path=artifact_directory / "active_fold_best.pt",
                log_prefix=prefix,
            )
            scores.append(result.macro_journey_mae_mps)
            epochs.append(result.best_epoch)
            durations.append(result.elapsed_seconds)
            completed_folds.append(
                {
                    "profile": profile,
                    "candidate_id": candidate_id,
                    "fold_id": fold_id,
                    "parameters": json.dumps(parameters, sort_keys=True),
                    "best_epoch": result.best_epoch,
                    "macro_journey_mae_mps": result.macro_journey_mae_mps,
                    "elapsed_seconds": result.elapsed_seconds,
                }
            )
            pd.DataFrame(completed_folds).to_csv(
                artifact_directory / "completed_folds.csv", index=False
            )
            del result
            if device.type == "cuda":
                torch.cuda.empty_cache()

        candidate_rows.append(
            {
                "model": "stateful_anchor_delta_gru",
                "candidate_id": candidate_id,
                "parameters": json.dumps(parameters, sort_keys=True),
                "cv_macro_mae_mps": float(np.mean(scores)),
                "cv_macro_mae_kmh": float(np.mean(scores) * 3.6),
                "cv_macro_mae_std_mps": float(np.std(scores)),
                "fold_best_epochs": json.dumps(epochs),
                "mean_fold_seconds": float(np.mean(durations)),
            }
        )
        pd.DataFrame(candidate_rows).to_csv(
            artifact_directory / f"{profile}_selection_partial.csv", index=False
        )

    return pd.DataFrame(candidate_rows).sort_values(
        "cv_macro_mae_mps"
    ).reset_index(drop=True)


def run_stateful_successive_search(
    sequences: Sequence[StatefulBlackoutSequence],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    experiment_config: ExperimentConfig,
    device: torch.device,
    artifact_directory: Path,
    candidate_count: int = 20,
    finalists: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Screen 20 candidates cheaply, then run the best two on all five folds.

    Every screening candidate sees the same grouped fold.  The frozen test set
    remains absent.  Advancing two rather than one protects against selecting a
    configuration that happened to suit the screening fold, while avoiding 100
    full fold trainings on a laptop GPU.
    """

    if len(folds) < 2:
        raise ValueError("Successive search requires multiple grouped folds.")
    if not 1 <= finalists <= candidate_count:
        raise ValueError("finalists must be between one and candidate_count.")
    artifact_directory.mkdir(parents=True, exist_ok=True)
    candidates = stateful_parameter_candidates(
        profile="full", count=candidate_count, seed=experiment_config.seed
    )
    manifest_path = artifact_directory / "successive_search_manifest.json"
    run_manifest = {
        "schema_version": 1,
        "seed": experiment_config.seed,
        "candidate_count": candidate_count,
        "finalists": finalists,
        "candidate_parameters": candidates,
        "screening_training": {
            "chunk_steps": 300,
            "batch_size": 16,
            "maximum_epochs": 20,
            "early_stopping_patience": 5,
        },
        "confirmation_training": {
            "chunk_steps": 300,
            "batch_size": 16,
            "maximum_epochs": 150,
            "early_stopping_patience": 15,
        },
    }
    if manifest_path.exists():
        previous_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous_manifest != run_manifest:
            raise RuntimeError(
                "Existing stateful-search files use a different configuration. "
                "Choose a new artifact directory rather than mixing results."
            )
    else:
        manifest_path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")

    screening_training = StatefulTrainingConfig(
        maximum_epochs=20,
        early_stopping_patience=5,
    )
    screening_path = artifact_directory / "screening_partial.csv"
    screening_rows: list[dict[str, object]] = (
        pd.read_csv(screening_path).to_dict("records")
        if screening_path.exists()
        else []
    )
    screened_ids = {int(row["candidate_id"]) for row in screening_rows}
    screening_train, screening_validation = folds[0]

    for candidate_id, parameters in enumerate(candidates, start=1):
        if candidate_id in screened_ids:
            print(f"screen candidate {candidate_id}/{len(candidates)}: resumed", flush=True)
            continue
        result = train_stateful_fold(
            sequences,
            train_indices=screening_train,
            validation_indices=screening_validation,
            parameters=parameters,
            experiment_config=experiment_config,
            training_config=screening_training,
            device=device,
            seed=experiment_config.seed + candidate_id * 100 + 1,
            checkpoint_path=(
                artifact_directory / f"screen_candidate_{candidate_id}_best.pt"
            ),
            log_prefix=f"screen candidate {candidate_id}/{len(candidates)}",
        )
        screening_rows.append(
            {
                "candidate_id": candidate_id,
                "parameters": json.dumps(parameters, sort_keys=True),
                "screen_macro_mae_mps": result.macro_journey_mae_mps,
                "screen_macro_mae_kmh": result.macro_journey_mae_mps * 3.6,
                "best_epoch": result.best_epoch,
                "elapsed_seconds": result.elapsed_seconds,
            }
        )
        pd.DataFrame(screening_rows).to_csv(
            screening_path, index=False
        )
        del result
        if device.type == "cuda":
            torch.cuda.empty_cache()

    screening = pd.DataFrame(screening_rows).sort_values(
        "screen_macro_mae_mps"
    ).reset_index(drop=True)
    finalist_ids = set(screening.head(finalists).candidate_id.astype(int))
    confirmation_training = StatefulTrainingConfig()
    confirmation_folds_path = artifact_directory / "confirmation_folds_partial.csv"
    confirmation_folds: list[dict[str, object]] = (
        pd.read_csv(confirmation_folds_path).to_dict("records")
        if confirmation_folds_path.exists()
        else []
    )
    completed_confirmation = {
        (int(row["candidate_id"]), int(row["fold_id"]))
        for row in confirmation_folds
    }
    final_rows_by_candidate: dict[int, dict[str, object]] = {}

    for candidate_id, parameters in enumerate(candidates, start=1):
        if candidate_id not in finalist_ids:
            continue
        scores: list[float] = []
        epochs: list[int] = []
        durations: list[float] = []
        for fold_id, (train, validation) in enumerate(folds, start=1):
            key = (candidate_id, fold_id)
            if key in completed_confirmation:
                record = next(
                    row
                    for row in confirmation_folds
                    if (
                        int(row["candidate_id"]), int(row["fold_id"])
                    ) == key
                )
                print(
                    f"finalist {candidate_id}, fold {fold_id}/{len(folds)}: resumed",
                    flush=True,
                )
            else:
                result = train_stateful_fold(
                    sequences,
                    train_indices=train,
                    validation_indices=validation,
                    parameters=parameters,
                    experiment_config=experiment_config,
                    training_config=confirmation_training,
                    device=device,
                    seed=experiment_config.seed + candidate_id * 100 + fold_id,
                    checkpoint_path=(
                        artifact_directory
                        / f"candidate_{candidate_id}_fold_{fold_id}_best.pt"
                    ),
                    log_prefix=(
                        f"finalist {candidate_id}, fold {fold_id}/{len(folds)}"
                    ),
                )
                record = {
                    "candidate_id": candidate_id,
                    "fold_id": fold_id,
                    "parameters": json.dumps(parameters, sort_keys=True),
                    "macro_journey_mae_mps": result.macro_journey_mae_mps,
                    "best_epoch": result.best_epoch,
                    "elapsed_seconds": result.elapsed_seconds,
                }
                confirmation_folds.append(record)
                completed_confirmation.add(key)
                pd.DataFrame(confirmation_folds).to_csv(
                    confirmation_folds_path,
                    index=False,
                )
                del result
                if device.type == "cuda":
                    torch.cuda.empty_cache()
            scores.append(float(record["macro_journey_mae_mps"]))
            epochs.append(int(record["best_epoch"]))
            durations.append(float(record["elapsed_seconds"]))

        final_rows_by_candidate[candidate_id] = {
            "model": "stateful_anchor_delta_gru",
            "candidate_id": candidate_id,
            "parameters": json.dumps(parameters, sort_keys=True),
            "cv_macro_mae_mps": float(np.mean(scores)),
            "cv_macro_mae_kmh": float(np.mean(scores) * 3.6),
            "cv_macro_mae_std_mps": float(np.std(scores)),
            "fold_best_epochs": json.dumps(epochs),
            "mean_fold_seconds": float(np.mean(durations)),
        }
        pd.DataFrame(final_rows_by_candidate.values()).to_csv(
            artifact_directory / "confirmation_selection_partial.csv",
            index=False,
        )

    confirmation = pd.DataFrame(final_rows_by_candidate.values()).sort_values(
        "cv_macro_mae_mps"
    ).reset_index(drop=True)
    screening.to_csv(artifact_directory / "screening_results.csv", index=False)
    confirmation.to_csv(
        artifact_directory / "stateful_cv_selection.csv", index=False
    )
    return screening, confirmation


def _load_trusted_checkpoint(path: Path, *, device: torch.device) -> dict[str, object]:
    """Load a locally produced PyTorch checkpoint, including its metadata.

    ``weights_only=False`` is intentional here: confirmation checkpoints are
    produced by this repository and final-refit checkpoints include the fitted
    sklearn scaler.  This helper must never be pointed at an untrusted file.
    """

    checkpoint = torch.load(path, map_location=device, weights_only=False)
    if not isinstance(checkpoint, dict):
        raise RuntimeError(f"Checkpoint {path} is not a metadata dictionary.")
    return checkpoint


def collect_stateful_oof_predictions(
    sequences: Sequence[StatefulBlackoutSequence],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    candidate_id: int,
    parameters: dict[str, object],
    experiment_config: ExperimentConfig,
    device: torch.device,
    artifact_directory: Path,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Reconstruct OOF predictions from the selected CV checkpoints.

    The expensive grouped-CV confirmation has already trained and saved one
    best model per fold.  Rebuilding each fold's training-only scaler and
    running its saved checkpoint on that fold's validation journeys gives the
    required OOF residuals without performing the five trainings a second
    time.  These OOF residuals are later the valid input for uncertainty-model
    training; they are not predictions from a model that saw its own target.
    """

    if not folds:
        raise ValueError("At least one grouped fold is required for OOF output.")
    artifact_directory.mkdir(parents=True, exist_ok=True)
    normalized_parameters = json.dumps(parameters, sort_keys=True)
    manifest_path = artifact_directory / "stateful_oof_manifest.json"
    manifest = {
        "schema_version": 1,
        "candidate_id": candidate_id,
        "parameters": parameters,
        "fold_count": len(folds),
        "feature_names": list(STATEFUL_FEATURE_NAMES),
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise RuntimeError(
                "Existing OOF files belong to a different stateful candidate. "
                "Use a separate artifact directory rather than mixing runs."
            )
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    fold_frames: list[pd.DataFrame] = []
    for fold_id, (train_indices, validation_indices) in enumerate(folds, start=1):
        output_path = artifact_directory / f"stateful_oof_fold_{fold_id}.csv"
        if output_path.exists():
            frame = pd.read_csv(output_path)
            required_columns = {
                "sequence_index",
                "journey_id",
                "anchor_timestamp_ns",
                "horizon_s",
                "actual_speed_mps",
                "prediction_speed_mps",
                "fold",
                "model",
            }
            if not required_columns.issubset(frame.columns):
                raise RuntimeError(f"OOF file {output_path} has an incompatible schema.")
            print(f"OOF fold {fold_id}/{len(folds)}: resumed", flush=True)
        else:
            checkpoint_path = (
                artifact_directory
                / f"candidate_{candidate_id}_fold_{fold_id}_best.pt"
            )
            if not checkpoint_path.exists():
                raise FileNotFoundError(
                    "The selected confirmation checkpoint is missing: "
                    f"{checkpoint_path}. Re-run the resumable selection cell first."
                )
            checkpoint = _load_trusted_checkpoint(checkpoint_path, device=device)
            checkpoint_parameters = json.dumps(
                checkpoint.get("parameters"), sort_keys=True
            )
            if checkpoint_parameters != normalized_parameters:
                raise RuntimeError(
                    f"Checkpoint {checkpoint_path.name} does not match the selected "
                    "hyperparameters."
                )
            state_dict = checkpoint.get("state_dict")
            if not isinstance(state_dict, dict):
                raise RuntimeError(f"Checkpoint {checkpoint_path} has no state_dict.")

            # Refit scaler only on this fold's training journeys.  It is
            # deterministic and prevents a validation distribution leak.
            scaler = _fit_scaler(sequences, train_indices)
            validation_items = _prepare_scaled_items(
                sequences, validation_indices, scaler
            )
            validation_loader = _loader(
                validation_items,
                batch_size=StatefulTrainingConfig().batch_size,
                seed=experiment_config.seed + candidate_id * 100 + fold_id,
                shuffle_buckets=False,
            )
            model = StatefulAnchorDeltaGru(
                hidden_size=int(parameters["hidden_size"]),
                num_layers=int(parameters["num_layers"]),
                dropout=float(parameters["dropout"]),
            ).to(device)
            model.load_state_dict(state_dict)
            frame = _predict(
                model,
                validation_loader,
                device=device,
                chunk_steps=StatefulTrainingConfig().chunk_steps,
                sample_period_s=experiment_config.sample_period_s,
            ).assign(fold=fold_id, model="stateful_anchor_delta_gru")
            saved_score = float(checkpoint.get("validation_macro_mae_mps", np.nan))
            reconstructed_score = _macro_journey_mae(frame)
            if np.isfinite(saved_score) and not np.isclose(
                reconstructed_score, saved_score, rtol=1e-5, atol=1e-5
            ):
                raise RuntimeError(
                    f"OOF reconstruction for fold {fold_id} disagrees with its "
                    "saved validation score."
                )
            frame.to_csv(output_path, index=False)
            print(
                f"OOF fold {fold_id}/{len(folds)}: reconstructed "
                f"({reconstructed_score * 3.6:.2f} km/h)",
                flush=True,
            )
            del model
            if device.type == "cuda":
                torch.cuda.empty_cache()

        if not (frame["fold"] == fold_id).all():
            raise RuntimeError(f"OOF file {output_path} is assigned to the wrong fold.")
        fold_frames.append(frame)

    predictions = pd.concat(fold_frames, ignore_index=True).sort_values(
        ["sequence_index", "horizon_s"]
    ).reset_index(drop=True)
    if predictions.duplicated(["sequence_index", "horizon_s"]).any():
        raise AssertionError("OOF output contains duplicate sequence/horizon rows.")
    metrics = regression_metrics(
        predictions.actual_speed_mps.to_numpy(),
        predictions.prediction_speed_mps.to_numpy(),
        predictions.journey_id.to_numpy(),
    )
    predictions.to_csv(artifact_directory / "stateful_oof_predictions.csv", index=False)
    (artifact_directory / "stateful_oof_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    return predictions, metrics


def fit_stateful_final_model(
    sequences: Sequence[StatefulBlackoutSequence],
    *,
    parameters: dict[str, object],
    experiment_config: ExperimentConfig,
    device: torch.device,
    artifact_directory: Path,
    epochs: int,
) -> tuple[StatefulAnchorDeltaGru, StandardScaler]:
    """Refit one selected architecture on every development sequence.

    This is the only new training after selection: no candidate search and no
    frozen-test data.  A last-epoch checkpoint is atomically refreshed after
    every epoch, so an interrupted final refit resumes from its completed
    epoch rather than starting again.  As usual for resumed SGD, batch order
    after the interruption can differ, but learned weights and optimizer state
    are retained.
    """

    if epochs <= 0:
        raise ValueError("Final refit epochs must be positive.")
    artifact_directory.mkdir(parents=True, exist_ok=True)
    all_indices = np.arange(len(sequences), dtype=np.int64)
    training = StatefulTrainingConfig(
        maximum_epochs=epochs,
        early_stopping_patience=epochs,
    )
    manifest_path = artifact_directory / "stateful_final_refit_manifest.json"
    checkpoint_path = artifact_directory / "stateful_final_refit_last.pt"
    manifest = {
        "schema_version": 1,
        "parameters": parameters,
        "epochs": epochs,
        "development_sequence_count": int(len(sequences)),
        "training": {
            "chunk_steps": training.chunk_steps,
            "batch_size": training.batch_size,
            "gradient_clip_norm": training.gradient_clip_norm,
        },
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise RuntimeError(
                "Existing final-refit checkpoint uses different settings. Use a "
                "new artifact directory instead of silently mixing runs."
            )
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Set the seed before constructing a fresh model, so an uninterrupted
    # refit is reproducible. A resumed refit replaces these initial weights
    # and optimizer values with its saved state immediately afterwards.
    _seed_everything(experiment_config.seed + 50_000)
    model = StatefulAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        dropout=float(parameters["dropout"]),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(parameters["learning_rate"]),
        weight_decay=float(parameters["weight_decay"]),
    )
    completed_epochs = 0
    if checkpoint_path.exists():
        checkpoint = _load_trusted_checkpoint(checkpoint_path, device=device)
        if checkpoint.get("parameters") != parameters:
            raise RuntimeError("Final-refit checkpoint parameters do not match.")
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scaler = checkpoint["feature_scaler"]
        if not isinstance(scaler, StandardScaler):
            raise RuntimeError("Final-refit checkpoint has an invalid feature scaler.")
        completed_epochs = int(checkpoint["completed_epochs"])
        print(f"Final refit: resumed after epoch {completed_epochs}", flush=True)
    else:
        scaler = _fit_scaler(sequences, all_indices)

    train_items = _prepare_scaled_items(sequences, all_indices, scaler)
    train_loader = _loader(
        train_items,
        batch_size=training.batch_size,
        seed=experiment_config.seed + 50_000,
        shuffle_buckets=True,
    )
    for epoch in range(completed_epochs + 1, epochs + 1):
        model.train()
        total_loss = 0.0
        batch_count = 0
        for batch in train_loader:
            features = batch["features"].to(device)
            targets = batch["targets"].to(device)
            full_mask = batch["training_mask"].to(device).float()
            weights = batch["weights"].to(device)
            denominator = (full_mask * weights[:, None]).sum().clamp_min(1.0)
            hidden: torch.Tensor | None = None
            optimizer.zero_grad(set_to_none=True)
            batch_loss = 0.0
            for start in range(0, features.shape[1], training.chunk_steps):
                stop = start + training.chunk_steps
                encoded, hidden = model.gru(features[:, start:stop], hidden)
                predicted = model.head(encoded).squeeze(-1)
                chunk_mask = full_mask[:, start:stop]
                if bool(chunk_mask.any()):
                    pointwise = F.smooth_l1_loss(
                        predicted,
                        targets[:, start:stop],
                        beta=experiment_config.huber_beta_mps,
                        reduction="none",
                    )
                    chunk_loss = (
                        pointwise * chunk_mask * weights[:, None]
                    ).sum() / denominator
                    chunk_loss.backward()
                    batch_loss += float(chunk_loss.detach().cpu())
                hidden = hidden.detach()
            nn.utils.clip_grad_norm_(model.parameters(), training.gradient_clip_norm)
            optimizer.step()
            total_loss += batch_loss
            batch_count += 1

        torch.save(
            {
                "state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "feature_scaler": scaler,
                "parameters": parameters,
                "completed_epochs": epoch,
            },
            checkpoint_path,
        )
        print(
            f"Final refit epoch {epoch:03d}/{epochs} | "
            f"train loss {total_loss / max(batch_count, 1):.4f}",
            flush=True,
        )
    return model, scaler


def finalize_stateful_winner(
    sequences: Sequence[StatefulBlackoutSequence],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    *,
    candidate_id: int,
    parameters: dict[str, object],
    fold_best_epochs: Sequence[int],
    experiment_config: ExperimentConfig,
    device: torch.device,
    artifact_directory: Path,
) -> StatefulFinalizationResult:
    """Create valid OOF residuals and a resumable development-only refit."""

    if not fold_best_epochs:
        raise ValueError("Selected candidate has no grouped-fold epoch history.")
    oof_predictions, oof_metrics = collect_stateful_oof_predictions(
        sequences,
        folds,
        candidate_id=candidate_id,
        parameters=parameters,
        experiment_config=experiment_config,
        device=device,
        artifact_directory=artifact_directory,
    )
    final_epochs = max(1, int(round(float(np.median(fold_best_epochs)))))
    model, scaler = fit_stateful_final_model(
        sequences,
        parameters=parameters,
        experiment_config=experiment_config,
        device=device,
        artifact_directory=artifact_directory,
        epochs=final_epochs,
    )
    torch.save(
        {
            "schema_version": 1,
            "model_name": "stateful_anchor_delta_gru_candidate",
            "state_dict": model.cpu().state_dict(),
            "feature_scaler": scaler,
            "feature_names": STATEFUL_FEATURE_NAMES,
            "parameters": parameters,
            "final_refit_epochs": final_epochs,
            "selection_metric": "grouped-CV macro journey MAE in m/s",
            "training_scope": "development journeys only",
            "deployment_status": "experimental; stateful runtime adapter pending",
        },
        artifact_directory / "stateful_anchor_delta_gru_candidate.pt",
    )
    return StatefulFinalizationResult(
        oof_predictions=oof_predictions,
        oof_metrics=oof_metrics,
        final_model=model,
        final_scaler=scaler,
        final_epochs=final_epochs,
    )


def predict_stateful_sequences(
    sequences: Sequence[StatefulBlackoutSequence],
    *,
    model: StatefulAnchorDeltaGru,
    scaler: StandardScaler,
    experiment_config: ExperimentConfig,
    device: torch.device,
) -> pd.DataFrame:
    """Predict complete sequences using a frozen stateful model and scaler."""

    indices = np.arange(len(sequences), dtype=np.int64)
    items = _prepare_scaled_items(sequences, indices, scaler)
    loader = _loader(
        items,
        batch_size=StatefulTrainingConfig().batch_size,
        seed=experiment_config.seed,
        shuffle_buckets=False,
    )
    return _predict(
        model.to(device),
        loader,
        device=device,
        chunk_steps=StatefulTrainingConfig().chunk_steps,
        sample_period_s=experiment_config.sample_period_s,
    )


def plot_stateful_vs_windowed_trace(
    sequences: Sequence[StatefulBlackoutSequence],
    oof_predictions: pd.DataFrame,
    *,
    stateful_model: StatefulAnchorDeltaGru,
    stateful_scaler: StandardScaler,
    experiment_config: ExperimentConfig,
    device: torch.device,
    prior_windowed_artifact_directory: Path,
    output_path: Path,
) -> object:
    """Plot one median-error development trace against the earlier 5 s GRU.

    The picture is deliberately qualitative: both selected final models were
    refit on development journeys.  The OOF table remains the leakage-safe
    comparison for model selection.  Choosing the sequence with median OOF
    stateful error avoids cherry-picking an unusually good or bad trace.
    """

    import matplotlib.pyplot as plt

    from idr_backend.adapters.anchor_delta_gru import AnchorDeltaGruPredictor
    from idr_backend.adapters.velocity_predictor import VelocityInferenceContext

    required = {
        "sequence_index",
        "actual_speed_mps",
        "prediction_speed_mps",
    }
    if not required.issubset(oof_predictions.columns):
        raise ValueError("OOF frame cannot select a stateful comparison trace.")
    per_sequence_error = (
        oof_predictions.assign(
            absolute_error=lambda rows: np.abs(
                rows.actual_speed_mps - rows.prediction_speed_mps
            )
        )
        .groupby("sequence_index")["absolute_error"]
        .mean()
        .sort_values()
    )
    sequence_index = int(per_sequence_error.index[len(per_sequence_error) // 2])
    sequence = sequences[sequence_index]
    elapsed_s = np.arange(len(sequence.features)) * experiment_config.sample_period_s
    actual_speed_mps = np.maximum(
        0.0, sequence.anchor_speed_mps + sequence.target_delta_mps
    )
    integrated_speed_mps = sequence.features[:, 7]

    scaled = stateful_scaler.transform(sequence.features).astype(np.float32)
    stateful_model = stateful_model.to(device).eval()
    with torch.inference_mode():
        encoded, _ = stateful_model.gru(torch.from_numpy(scaled)[None].to(device))
        delta_mps = stateful_model.head(encoded).squeeze().cpu().numpy()
    stateful_speed_mps = np.maximum(0.0, sequence.anchor_speed_mps + delta_mps)

    previous = AnchorDeltaGruPredictor.from_artifact_directory(
        prior_windowed_artifact_directory
    )
    windowed_speed_mps = np.full(len(sequence.features), np.nan)
    for step in range(previous.window_size - 1, len(sequence.features)):
        values = sequence.features[step]
        windowed_speed_mps[step] = previous.predict_speed_mps(
            tuple(
                tuple(row)
                for row in sequence.features[
                    step - previous.window_size + 1 : step + 1, :6
                ]
            ),
            VelocityInferenceContext(
                source_id="development-trace",
                anchor_timestamp_ns=sequence.anchor_timestamp_ns,
                anchor_speed_mps=float(values[6]),
                integrated_speed_mps=float(values[7]),
                seconds_since_anchor=float(values[8]),
                mean_calibration_confidence=float(values[9]),
                minimum_calibration_confidence=float(values[10]),
            ),
        )

    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(
        elapsed_s,
        actual_speed_mps * 3.6,
        color="black",
        lw=2,
        label="GNSS-derived target",
    )
    axis.plot(
        elapsed_s,
        integrated_speed_mps * 3.6,
        color="#9ca3af",
        ls=":",
        label="pure IMU integration",
    )
    axis.plot(
        elapsed_s,
        windowed_speed_mps * 3.6,
        color="#2563eb",
        alpha=0.85,
        label="previous 5 s GRU",
    )
    axis.plot(
        elapsed_s,
        stateful_speed_mps * 3.6,
        color="#dc2626",
        lw=1.8,
        label="selected stateful GRU",
    )
    axis.set(
        xlabel="seconds since GNSS anchor",
        ylabel="speed (km/h)",
        title=(
            "Development trace: stateful vs five-second GRU "
            f"(sequence {sequence_index})"
        ),
    )
    axis.grid(alpha=0.25)
    axis.legend(ncol=2)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    return figure

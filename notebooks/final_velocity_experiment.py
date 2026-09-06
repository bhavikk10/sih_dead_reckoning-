"""Resumable final velocity-model investigation for the IDR notebook.

This is deliberately notebook support code rather than a runtime module.  It
trains only on development journeys, keeps all whole-journey validation folds
isolated, and writes every checkpoint under the caller-provided artifact
directory.  Nothing in this file selects or replaces a deployed artifact.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pandas as pd
import torch
from sklearn.model_selection import GroupKFold, ParameterSampler
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.nn import functional as functional
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from idr_backend.evaluation.production_velocity import (
    ProductionStatefulSequence,
    ProductionVelocityDataset,
    fold_balanced_sample_weights,
)
from idr_backend.adapters.anchor_delta_gru import ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES
from idr_backend.adapters.stateful_anchor_delta_gru import STATEFUL_FEATURE_NAMES
from idr_backend.sensors.windowing import VELOCITY_MODEL_FEATURE_NAMES


CANONICAL_HORIZONS_S = (5.0, 10.0, 20.0, 30.0, 60.0, 90.0, 120.0)
FINAL_SEARCH_SEED = 20_260_906


@dataclass(frozen=True, slots=True)
class SearchLimits:
    """One bounded training round in the successive-halving schedule."""

    maximum_epochs: int
    patience: int
    batch_size: int


@dataclass(frozen=True, slots=True)
class FoldOutcome:
    """Best held-out result and predictions from one completed grouped fold."""

    macro_journey_mae_mps: float
    best_epoch: int
    elapsed_seconds: float
    # This is a PyTorch CPU proxy used only to break otherwise equivalent CV
    # scores during search.  The promoted candidate must separately meet the
    # stricter ONNX Runtime p95 gate before it can replace the selected model.
    cpu_inference_p95_ms: float
    predictions: pd.DataFrame


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Completed ranking plus honest OOF predictions for the two finalists."""

    screening: pd.DataFrame
    middle_round: pd.DataFrame
    finalists: pd.DataFrame
    finalist_predictions: pd.DataFrame


class WindowedAnchorDeltaGru(nn.Module):
    """Phone-sized five-second GRU predicting speed change from a GNSS anchor."""

    def __init__(
        self,
        *,
        hidden_size: int,
        num_layers: int,
        bidirectional: bool,
        dropout: float,
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=6,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=bidirectional,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        directions = 2 if bidirectional else 1
        self.context = nn.Sequential(nn.Linear(5, 16), nn.ReLU())
        self.head = nn.Sequential(
            nn.Linear(hidden_size * directions + 16, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, sequence: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        """Predict an anchor-relative speed change for one completed window."""

        _, hidden = self.gru(sequence)
        directions = 2 if self.gru.bidirectional else 1
        # GRU returns [layers * directions, batch, hidden].  Its final layer
        # occupies the final ``directions`` rows, which can be transposed and
        # flattened without converting a symbolic batch size to Python during
        # ONNX tracing.
        encoded = hidden[-directions:].transpose(0, 1).flatten(start_dim=1)
        return self.head(torch.cat((encoded, self.context(context)), dim=1)).squeeze(1)


class StreamingAnchorDeltaGru(nn.Module):
    """Unidirectional stateful GRU with explicit reusable hidden state."""

    def __init__(self, *, hidden_size: int, num_layers: int, dropout: float) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=11,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=False,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size, 32), nn.ReLU(), nn.Dropout(dropout), nn.Linear(32, 1)
        )

    def forward(
        self,
        features: torch.Tensor,
        hidden_state: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return one anchor-relative delta per new sample and next hidden state."""

        encoded, next_hidden = self.gru(features, hidden_state)
        return self.head(encoded).squeeze(-1), next_hidden


def seed_everything(seed: int) -> None:
    """Make candidate/fold initialization and sampler order reproducible."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def grouped_folds(journey_ids: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Create and validate the fixed five-fold whole-journey protocol."""

    journey_ids = np.asarray(journey_ids, dtype=str)
    if len(np.unique(journey_ids)) < 5:
        raise ValueError("Five grouped folds require at least five usable journeys.")
    splitter = GroupKFold(n_splits=5)
    folds = list(splitter.split(np.zeros(len(journey_ids)), groups=journey_ids))
    for train, validation in folds:
        if set(journey_ids[train]) & set(journey_ids[validation]):
            raise AssertionError("Grouped velocity folds leak a journey.")
    return folds


def fold_assignment_frame(journey_ids: np.ndarray, folds: Sequence[tuple[np.ndarray, np.ndarray]]) -> pd.DataFrame:
    """Persist the exact fold holding each journey, making later reruns comparable."""

    rows: list[dict[str, object]] = []
    journey_ids = np.asarray(journey_ids, dtype=str)
    for fold_id, (_, validation) in enumerate(folds, start=1):
        for journey_id in np.unique(journey_ids[validation]):
            rows.append({"journey_id": journey_id, "validation_fold": fold_id})
    frame = pd.DataFrame(rows).sort_values("journey_id").reset_index(drop=True)
    if frame.journey_id.duplicated().any():
        raise AssertionError("A journey is assigned to more than one validation fold.")
    return frame


def windowed_candidates(*, seed: int = FINAL_SEARCH_SEED) -> list[dict[str, object]]:
    """Sample the locked 20-candidate deployable windowed-GRU space."""

    space = {
        "hidden_size": [32, 64, 96],
        "num_layers": [1, 2],
        "bidirectional": [False, True],
        "dropout": [0.05, 0.1, 0.2],
        "learning_rate": [1e-3, 5e-4, 3e-4],
        "weight_decay": [0.0, 1e-4, 3e-4],
    }
    return list(ParameterSampler(space, n_iter=20, random_state=seed))


def stateful_candidates(*, seed: int = FINAL_SEARCH_SEED + 1) -> list[dict[str, object]]:
    """Sample the locked 20-candidate streaming-GRU and TBPTT space."""

    space = {
        "hidden_size": [32, 64, 96],
        "num_layers": [1, 2],
        "dropout": [0.05, 0.1, 0.2],
        "learning_rate": [1e-3, 5e-4, 3e-4],
        "weight_decay": [0.0, 1e-4, 3e-4],
        "chunk_steps": [25, 50, 100],
    }
    return list(ParameterSampler(space, n_iter=20, random_state=seed))


def macro_journey_mae(frame: pd.DataFrame) -> float:
    """Score every held-out journey equally, matching selection policy."""

    return float(
        np.mean(
            [
                np.mean(np.abs(rows.actual_speed_mps - rows.prediction_speed_mps))
                for _, rows in frame.groupby("journey_id", sort=False)
            ]
        )
    )


def _atomic_torch_save(value: object, path: Path) -> None:
    """Avoid accepting a partially written checkpoint after an interrupt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(value, temporary)
    os.replace(temporary, path)


def _p95_cpu_latency_ms(
    model: nn.Module,
    *inputs: torch.Tensor,
    repeats: int = 100,
) -> float:
    """Measure a small, repeatable CPU proxy for CV tie-breaking.

    CUDA timing is intentionally not mixed into this value: deployment uses
    ONNX Runtime on CPU.  This does not certify a candidate for deployment;
    final export still has to satisfy the ONNX Runtime p95 requirement.
    """

    if repeats <= 0:
        raise ValueError("repeats must be positive.")
    cpu_model = copy.deepcopy(model).to("cpu").eval()
    cpu_inputs = tuple(value.detach().to("cpu") for value in inputs)
    with torch.inference_mode():
        for _ in range(10):
            cpu_model(*cpu_inputs)
        timings = []
        for _ in range(repeats):
            started = time.perf_counter()
            cpu_model(*cpu_inputs)
            timings.append((time.perf_counter() - started) * 1_000.0)
    return float(np.percentile(timings, 95))


def _windowed_scalers(dataset: ProductionVelocityDataset, train: np.ndarray) -> tuple[StandardScaler, StandardScaler]:
    sequence_scaler = StandardScaler().fit(dataset.sequence_windows[train].reshape(-1, 6))
    context_scaler = StandardScaler().fit(dataset.context_features[train])
    return sequence_scaler, context_scaler


def _windowed_inputs(
    dataset: ProductionVelocityDataset,
    indices: np.ndarray,
    sequence_scaler: StandardScaler,
    context_scaler: StandardScaler,
) -> tuple[np.ndarray, np.ndarray]:
    sequence = dataset.sequence_windows[indices]
    sequence = sequence_scaler.transform(sequence.reshape(-1, 6)).reshape(sequence.shape)
    context = context_scaler.transform(dataset.context_features[indices])
    return sequence.astype(np.float32), context.astype(np.float32)


def _windowed_predictions(
    model: WindowedAnchorDeltaGru,
    dataset: ProductionVelocityDataset,
    indices: np.ndarray,
    sequence_scaler: StandardScaler,
    context_scaler: StandardScaler,
    device: torch.device,
) -> pd.DataFrame:
    """Infer one held-out fold without augmentation or sampler weighting."""

    sequence, context = _windowed_inputs(dataset, indices, sequence_scaler, context_scaler)
    model.eval()
    with torch.inference_mode():
        delta = model(
            torch.from_numpy(sequence).to(device), torch.from_numpy(context).to(device)
        ).cpu().numpy()
    predicted = np.maximum(0.0, dataset.anchor_speed_mps[indices] + delta)
    return pd.DataFrame(
        {
            "journey_id": dataset.journey_ids[indices],
            "anchor_timestamp_ns": dataset.anchor_timestamps_ns[indices],
            "end_timestamp_ns": dataset.end_timestamps_ns[indices],
            "horizon_s": dataset.horizons_s[indices],
            "actual_speed_mps": dataset.target_speed_mps[indices],
            "prediction_speed_mps": predicted,
        }
    )


def fit_windowed_fold(
    dataset: ProductionVelocityDataset,
    *,
    train: np.ndarray,
    validation: np.ndarray,
    parameters: dict[str, object],
    limits: SearchLimits,
    use_balanced_sampler: bool,
    jitter_fraction: float,
    seed: int,
    device: torch.device,
    checkpoint_path: Path,
    log_prefix: str,
) -> FoldOutcome:
    """Train/resume one windowed fold and save its complete state every epoch."""

    if not 0.0 <= jitter_fraction <= 0.05:
        raise ValueError("jitter_fraction must be between zero and 0.05.")
    seed_everything(seed)
    sequence_scaler, context_scaler = _windowed_scalers(dataset, train)
    train_sequence, train_context = _windowed_inputs(dataset, train, sequence_scaler, context_scaler)
    validation_sequence, validation_context = _windowed_inputs(dataset, validation, sequence_scaler, context_scaler)
    targets = dataset.target_delta_mps[train].astype(np.float32)
    generator = torch.Generator().manual_seed(seed)
    sampler = None
    if use_balanced_sampler:
        sampler = WeightedRandomSampler(
            torch.as_tensor(fold_balanced_sample_weights(dataset, train), dtype=torch.double),
            num_samples=len(train),
            replacement=True,
            generator=generator,
        )
    loader = DataLoader(
        TensorDataset(
            torch.from_numpy(train_sequence), torch.from_numpy(train_context), torch.from_numpy(targets)
        ),
        batch_size=limits.batch_size,
        shuffle=sampler is None,
        sampler=sampler,
        generator=generator if sampler is None else None,
    )
    model = WindowedAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]),
        num_layers=int(parameters["num_layers"]),
        bidirectional=bool(parameters["bidirectional"]),
        dropout=float(parameters["dropout"]),
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=float(parameters["weight_decay"])
    )
    best_state: dict[str, torch.Tensor] | None = None
    best_score, best_epoch, stale, start_epoch = float("inf"), 0, 0, 1
    if checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if checkpoint.get("parameters") != parameters or checkpoint.get("limits") != asdict(limits):
            raise RuntimeError(f"Checkpoint {checkpoint_path.name} has a different experiment contract.")
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        best_state = checkpoint["best_state"]
        best_score = float(checkpoint["best_score"])
        best_epoch = int(checkpoint["best_epoch"])
        stale = int(checkpoint["stale"])
        start_epoch = int(checkpoint["completed_epoch"]) + 1

    robust_scale = np.subtract(*np.percentile(dataset.sequence_windows[train], [75, 25], axis=(0, 1))) / 1.349
    normalized_jitter = np.maximum(0.0, jitter_fraction * robust_scale / sequence_scaler.scale_).astype(np.float32)
    started = time.perf_counter()
    for epoch in range(start_epoch, limits.maximum_epochs + 1):
        model.train()
        losses = []
        for sequence, context, target in loader:
            sequence, context, target = sequence.to(device), context.to(device), target.to(device)
            if jitter_fraction:
                scale = torch.from_numpy(normalized_jitter).to(device).view(1, 1, -1)
                sequence = sequence + torch.randn_like(sequence) * scale
            optimizer.zero_grad(set_to_none=True)
            loss = functional.smooth_l1_loss(model(sequence, context), target, beta=2.0)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        validation_frame = _windowed_predictions(
            model, dataset, validation, sequence_scaler, context_scaler, device
        )
        score = macro_journey_mae(validation_frame)
        if score < best_score:
            best_state, best_score, best_epoch, stale = copy.deepcopy(model.state_dict()), score, epoch, 0
        else:
            stale += 1
        _atomic_torch_save(
            {
                "parameters": parameters, "limits": asdict(limits), "state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(), "best_state": best_state,
                "best_score": best_score, "best_epoch": best_epoch, "stale": stale,
                "completed_epoch": epoch, "sequence_scaler": sequence_scaler, "context_scaler": context_scaler,
            }, checkpoint_path,
        )
        print(f"{log_prefix} epoch {epoch:03d} | train loss {np.mean(losses):.4f} | validation macro MAE {score * 3.6:.2f} km/h", flush=True)
        if stale >= limits.patience:
            break
    if best_state is None:
        raise RuntimeError("Windowed fold did not create a valid best state.")
    model.load_state_dict(best_state)
    predictions = _windowed_predictions(model, dataset, validation, sequence_scaler, context_scaler, device)
    latency_ms = _p95_cpu_latency_ms(
        model,
        torch.from_numpy(validation_sequence[:1]),
        torch.from_numpy(validation_context[:1]),
    )
    return FoldOutcome(
        best_score,
        best_epoch,
        time.perf_counter() - started,
        latency_ms,
        predictions,
    )


def sequence_grouped_folds(sequences: Sequence[ProductionStatefulSequence], windowed_folds: Sequence[tuple[np.ndarray, np.ndarray]], dataset: ProductionVelocityDataset) -> list[tuple[np.ndarray, np.ndarray]]:
    """Map persisted windowed journey folds onto the stateful-anchor sequences."""

    sequence_journeys = np.asarray([sequence.journey_id for sequence in sequences], dtype=str)
    folds: list[tuple[np.ndarray, np.ndarray]] = []
    for windowed_train, windowed_validation in windowed_folds:
        train_groups = set(dataset.journey_ids[windowed_train])
        validation_groups = set(dataset.journey_ids[windowed_validation])
        train = np.flatnonzero(np.isin(sequence_journeys, list(train_groups)))
        validation = np.flatnonzero(np.isin(sequence_journeys, list(validation_groups)))
        if not len(train) or not len(validation) or set(sequence_journeys[train]) & set(sequence_journeys[validation]):
            raise AssertionError("Stateful fold cannot be mapped safely from windowed groups.")
        folds.append((train, validation))
    return folds


def _stateful_scaler(sequences: Sequence[ProductionStatefulSequence], train: np.ndarray) -> StandardScaler:
    scaler = StandardScaler()
    for index in train:
        scaler.partial_fit(sequences[int(index)].features)
    return scaler


def _stateful_sequence_weights(
    sequences: Sequence[ProductionStatefulSequence], train: np.ndarray
) -> np.ndarray:
    """Collapse the same journey/tail policy to one sampler weight per anchor.

    A streaming training item is a whole anchor-to-blackout sequence, not an
    independent endpoint.  Its sampler mass is therefore the mean of its
    evaluation-endpoint tail weights, combined with equal journey mass.
    """

    speed_edges = np.asarray((20.0, 40.0, 60.0, 80.0))
    delta_edges = np.asarray((5.0, 10.0, 20.0, 40.0))
    horizon_edges = np.asarray((20.0, 60.0))
    rows: list[tuple[int, str, int, int, int]] = []
    for local_index, sequence_index in enumerate(train):
        sequence = sequences[int(sequence_index)]
        for step in np.flatnonzero(sequence.evaluation_mask):
            target_speed = sequence.anchor_speed_mps + sequence.target_delta_mps[step]
            rows.append((
                local_index,
                sequence.journey_id,
                int(np.digitize(target_speed * 3.6, speed_edges)),
                int(np.digitize(abs(sequence.target_delta_mps[step]) * 3.6, delta_edges)),
                int(np.digitize(sequence.features[step, 8], horizon_edges)),
            ))
    if not rows:
        raise ValueError("Stateful training sequences have no evaluation endpoints.")
    frame = pd.DataFrame(rows, columns=("sequence", "journey", "speed", "delta", "horizon"))
    journey_counts = frame.journey.value_counts()
    stratum_counts = frame.groupby(["speed", "delta", "horizon"], sort=False).size()
    frame["weight"] = (
        len(frame) / (len(journey_counts) * frame.journey.map(journey_counts))
        * np.sqrt(
            len(frame)
            / (
                len(stratum_counts)
                * frame.set_index(["speed", "delta", "horizon"]).index.map(stratum_counts)
            )
        )
    )
    per_sequence = frame.groupby("sequence", sort=False).weight.mean()
    weights = np.asarray([per_sequence.get(index, 1.0) for index in range(len(train))], dtype=np.float64)
    return np.clip(weights / weights.mean(), 0.25, 4.0)


def _stateful_collate(
    sequences: Sequence[ProductionStatefulSequence],
    indices: Sequence[int],
    scaler: StandardScaler,
) -> dict[str, object]:
    selected = [sequences[int(index)] for index in indices]
    maximum = max(len(item.features) for item in selected)
    features = torch.zeros((len(selected), maximum, 11), dtype=torch.float32)
    targets = torch.zeros((len(selected), maximum), dtype=torch.float32)
    training_mask = torch.zeros((len(selected), maximum), dtype=torch.bool)
    evaluation_mask = torch.zeros((len(selected), maximum), dtype=torch.bool)
    for row, item in enumerate(selected):
        length = len(item.features)
        features[row, :length] = torch.from_numpy(scaler.transform(item.features).astype(np.float32))
        targets[row, :length] = torch.from_numpy(item.target_delta_mps)
        training_mask[row, :length] = torch.from_numpy(item.training_mask)
        evaluation_mask[row, :length] = torch.from_numpy(item.evaluation_mask)
    return {"source": selected, "features": features, "targets": targets, "training_mask": training_mask, "evaluation_mask": evaluation_mask}


def _stateful_predict(
    model: StreamingAnchorDeltaGru,
    sequences: Sequence[ProductionStatefulSequence],
    indices: np.ndarray,
    scaler: StandardScaler,
    chunk_steps: int,
    device: torch.device,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    model.eval()
    with torch.inference_mode():
        for index in indices:
            source = sequences[int(index)]
            features = torch.from_numpy(scaler.transform(source.features).astype(np.float32))[None].to(device)
            outputs, hidden = [], None
            for start in range(0, features.shape[1], chunk_steps):
                delta, hidden = model(features[:, start:start + chunk_steps], hidden)
                outputs.append(delta.cpu().numpy()[0])
            prediction_delta = np.concatenate(outputs)
            for step in np.flatnonzero(source.evaluation_mask):
                rows.append({
                    "journey_id": source.journey_id, "anchor_timestamp_ns": source.anchor_timestamp_ns,
                    "end_timestamp_ns": int(source.timestamps_ns[step]),
                    "horizon_s": float(source.features[step, 8]),
                    "actual_speed_mps": max(0.0, source.anchor_speed_mps + float(source.target_delta_mps[step])),
                    "prediction_speed_mps": max(0.0, source.anchor_speed_mps + float(prediction_delta[step])),
                })
    return pd.DataFrame(rows)


def fit_stateful_fold(
    sequences: Sequence[ProductionStatefulSequence],
    *,
    train: np.ndarray,
    validation: np.ndarray,
    parameters: dict[str, object],
    limits: SearchLimits,
    jitter_fraction: float,
    seed: int,
    device: torch.device,
    checkpoint_path: Path,
    log_prefix: str,
) -> FoldOutcome:
    """Train/resume a streaming causal GRU with truncated backpropagation."""

    if not 0.0 <= jitter_fraction <= 0.05:
        raise ValueError("jitter_fraction must be between zero and 0.05.")
    seed_everything(seed)
    scaler = _stateful_scaler(sequences, train)
    weights = _stateful_sequence_weights(sequences, train)
    sampler = WeightedRandomSampler(torch.as_tensor(weights, dtype=torch.double), len(train), replacement=True, generator=torch.Generator().manual_seed(seed))
    loader = DataLoader(train.tolist(), batch_size=limits.batch_size, sampler=sampler, collate_fn=lambda values: _stateful_collate(sequences, values, scaler))
    model = StreamingAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]), num_layers=int(parameters["num_layers"]), dropout=float(parameters["dropout"])
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=float(parameters["weight_decay"]))
    best_state: dict[str, torch.Tensor] | None = None
    best_score, best_epoch, stale, start_epoch = float("inf"), 0, 0, 1
    if checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if checkpoint.get("parameters") != parameters or checkpoint.get("limits") != asdict(limits):
            raise RuntimeError(f"Checkpoint {checkpoint_path.name} has a different experiment contract.")
        model.load_state_dict(checkpoint["state_dict"]); optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        best_state, best_score = checkpoint["best_state"], float(checkpoint["best_score"])
        best_epoch, stale, start_epoch = int(checkpoint["best_epoch"]), int(checkpoint["stale"]), int(checkpoint["completed_epoch"]) + 1
    robust_scale = np.subtract(*np.percentile(np.concatenate([sequences[int(index)].features[:, :6] for index in train]), [75, 25], axis=0)) / 1.349
    normalized_jitter = np.maximum(0.0, jitter_fraction * robust_scale / scaler.scale_[:6]).astype(np.float32)
    started = time.perf_counter()
    chunk_steps = int(parameters["chunk_steps"])
    for epoch in range(start_epoch, limits.maximum_epochs + 1):
        model.train(); losses = []
        for batch in loader:
            features = batch["features"].to(device); targets = batch["targets"].to(device); mask = batch["training_mask"].to(device).float()
            if jitter_fraction:
                scale = torch.from_numpy(normalized_jitter).to(device).view(1, 1, 6)
                features = features.clone(); features[:, :, :6] += torch.randn_like(features[:, :, :6]) * scale
            optimizer.zero_grad(set_to_none=True); hidden = None; loss_total = 0.0
            denominator = mask.sum().clamp_min(1.0)
            for start in range(0, features.shape[1], chunk_steps):
                stop = start + chunk_steps
                delta, hidden = model(features[:, start:stop], hidden)
                chunk_mask = mask[:, start:stop]
                if bool(chunk_mask.any()):
                    loss = (functional.smooth_l1_loss(delta, targets[:, start:stop], beta=2.0, reduction="none") * chunk_mask).sum() / denominator
                    loss.backward(); loss_total += float(loss.detach().cpu())
                hidden = hidden.detach()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step(); losses.append(loss_total)
        validation_frame = _stateful_predict(model, sequences, validation, scaler, chunk_steps, device)
        score = macro_journey_mae(validation_frame)
        if score < best_score:
            best_state, best_score, best_epoch, stale = copy.deepcopy(model.state_dict()), score, epoch, 0
        else:
            stale += 1
        _atomic_torch_save({"parameters": parameters, "limits": asdict(limits), "state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(), "best_state": best_state, "best_score": best_score, "best_epoch": best_epoch, "stale": stale, "completed_epoch": epoch, "scaler": scaler}, checkpoint_path)
        print(f"{log_prefix} epoch {epoch:03d} | train loss {np.mean(losses):.4f} | validation macro MAE {score * 3.6:.2f} km/h", flush=True)
        if stale >= limits.patience:
            break
    if best_state is None:
        raise RuntimeError("Stateful fold did not create a valid best state.")
    model.load_state_dict(best_state)
    predictions = _stateful_predict(model, sequences, validation, scaler, chunk_steps, device)
    latency_ms = _p95_cpu_latency_ms(
        model,
        torch.zeros((1, 1, 11), dtype=torch.float32),
        torch.zeros((model.gru.num_layers, 1, model.gru.hidden_size), dtype=torch.float32),
    )
    return FoldOutcome(
        best_score,
        best_epoch,
        time.perf_counter() - started,
        latency_ms,
        predictions,
    )


FoldTrainer = Callable[[dict[str, object], np.ndarray, np.ndarray, SearchLimits, Path, str], FoldOutcome]


def run_successive_halving(
    *,
    family: str,
    candidates: Sequence[dict[str, object]],
    folds: Sequence[tuple[np.ndarray, np.ndarray]],
    artifact_directory: Path,
    trainer: FoldTrainer,
    batch_size: int,
) -> SearchOutcome:
    """Run the locked 20 → 6 → 2, interruption-safe grouped search schedule."""

    if len(folds) != 5 or len(candidates) != 20:
        raise ValueError("Final search requires exactly five folds and twenty candidates.")
    artifact_directory.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "family": family, "seed": FINAL_SEARCH_SEED, "candidates": list(candidates)}
    manifest_path = artifact_directory / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise RuntimeError("Existing final-search artifact directory has a different manifest.")
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def run_round(name: str, candidate_ids: Sequence[int], fold_ids: Sequence[int], limits: SearchLimits) -> pd.DataFrame:
        path = artifact_directory / f"{name}_folds.csv"
        rows = pd.read_csv(path).to_dict("records") if path.exists() else []
        done = {(int(row["candidate_id"]), int(row["fold_id"])) for row in rows}
        for candidate_id in candidate_ids:
            parameters = candidates[candidate_id - 1]
            for fold_id in fold_ids:
                key = (candidate_id, fold_id)
                if key in done:
                    print(f"{family} {name} candidate {candidate_id}/20, fold {fold_id}/5: resumed", flush=True)
                    continue
                train, validation = folds[fold_id - 1]
                # Candidate and fold identity are part of the stochastic
                # training seed, but are kept out of the public architecture
                # configuration and final metadata.
                training_parameters = {
                    **parameters,
                    "_candidate_id": candidate_id,
                    "_fold_id": fold_id,
                }
                outcome = trainer(
                    training_parameters, train, validation, limits,
                    artifact_directory / "checkpoints" / f"{name}_candidate_{candidate_id}_fold_{fold_id}.pt",
                    f"{family} {name} candidate {candidate_id}/20, fold {fold_id}/5",
                )
                prediction_path = artifact_directory / "predictions" / f"{name}_candidate_{candidate_id}_fold_{fold_id}.csv"
                prediction_path.parent.mkdir(parents=True, exist_ok=True)
                outcome.predictions.assign(candidate_id=candidate_id, fold=fold_id, family=family).to_csv(prediction_path, index=False)
                rows.append({"candidate_id": candidate_id, "fold_id": fold_id, "parameters": json.dumps(parameters, sort_keys=True), "macro_journey_mae_mps": outcome.macro_journey_mae_mps, "best_epoch": outcome.best_epoch, "elapsed_seconds": outcome.elapsed_seconds, "cpu_inference_p95_ms": outcome.cpu_inference_p95_ms})
                pd.DataFrame(rows).to_csv(path, index=False)
                done.add(key)
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        return pd.DataFrame(rows)

    def rank_from_oof(round_rows: pd.DataFrame) -> pd.DataFrame:
        """Rank candidates by concatenated held-out journeys, never fold mean.

        ``GroupKFold`` balances examples, so a validation fold can contain one
        very long journey while another contains several short ones. Averaging
        fold scores would accidentally give those two folds equal influence.
        Reading each saved prediction file and computing macro MAE once across
        its unique held-out journeys implements the declared OOF objective.
        """

        if round_rows.empty:
            raise RuntimeError("Cannot rank an empty search round.")
        ranking_rows: list[dict[str, object]] = []
        for candidate_id, candidate_rows in round_rows.groupby("candidate_id", sort=True):
            prediction_frames = []
            # ``round_rows`` carries the round name, so each selected
            # candidate/fold pair has one unambiguous prediction file.
            for record in candidate_rows.itertuples(index=False):
                prediction_path = (
                    artifact_directory
                    / "predictions"
                    / f"{record.round_name}_candidate_{int(record.candidate_id)}_fold_{int(record.fold_id)}.csv"
                )
                if not prediction_path.is_file():
                    raise FileNotFoundError(
                        f"Completed-fold prediction is missing: {prediction_path}"
                    )
                prediction_frames.append(pd.read_csv(prediction_path))
            predictions = pd.concat(prediction_frames, ignore_index=True)
            fold_scores = candidate_rows["macro_journey_mae_mps"].astype(float).to_numpy()
            latency = candidate_rows["cpu_inference_p95_ms"].astype(float).to_numpy()
            ranking_rows.append(
                {
                    "candidate_id": int(candidate_id),
                    "oof_macro_journey_mae_mps": macro_journey_mae(predictions),
                    "fold_macro_journey_mae_std_mps": float(np.std(fold_scores, ddof=0)),
                    "cpu_inference_p95_ms": float(np.mean(latency)),
                    "validation_fold_count": int(candidate_rows.fold_id.nunique()),
                    "oof_journey_count": int(predictions.journey_id.nunique()),
                }
            )
        return pd.DataFrame(ranking_rows).sort_values(
            [
                "oof_macro_journey_mae_mps",
                "fold_macro_journey_mae_std_mps",
                "cpu_inference_p95_ms",
            ]
        ).reset_index(drop=True)

    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")
    screen = run_round("screen", list(range(1, 21)), (1, 2), SearchLimits(30, 6, batch_size)).assign(round_name="screen")
    screen_ranked = rank_from_oof(screen)
    middle_ids = screen_ranked.head(6).candidate_id.astype(int).tolist()
    middle = run_round("middle", middle_ids, (3, 4), SearchLimits(75, 12, batch_size)).assign(round_name="middle")
    combined = rank_from_oof(pd.concat((screen, middle), ignore_index=True))
    final_ids = combined.head(2).candidate_id.astype(int).tolist()
    final_folds = run_round("final", final_ids, (1, 2, 3, 4, 5), SearchLimits(150, 20, batch_size)).assign(round_name="final")
    finalists = rank_from_oof(final_folds).rename(
        columns={
            "oof_macro_journey_mae_mps": "cv_macro_journey_mae_mps",
            "fold_macro_journey_mae_std_mps": "cv_macro_journey_mae_std_mps",
        }
    )
    final_summary = final_folds.groupby("candidate_id", as_index=False).agg(
        fold_best_epochs=("best_epoch", list),
        mean_fold_seconds=("elapsed_seconds", "mean"),
    )
    finalists = finalists.merge(final_summary, on="candidate_id", validate="one_to_one")
    finalists = finalists.sort_values(
        [
            "cv_macro_journey_mae_mps",
            "cv_macro_journey_mae_std_mps",
            "cpu_inference_p95_ms",
        ]
    ).reset_index(drop=True)
    finalists["family"] = family
    finalists["parameters"] = finalists.candidate_id.map(
        lambda candidate_id: json.dumps(candidates[int(candidate_id) - 1], sort_keys=True)
    )
    finalists["cv_macro_journey_mae_kmh"] = finalists.cv_macro_journey_mae_mps * 3.6
    predictions = pd.concat([pd.read_csv(artifact_directory / "predictions" / f"final_candidate_{candidate_id}_fold_{fold_id}.csv") for candidate_id in final_ids for fold_id in range(1, 6)], ignore_index=True)
    screen_ranked.to_csv(artifact_directory / "screening_ranked.csv", index=False)
    combined.to_csv(artifact_directory / "middle_round_ranked.csv", index=False)
    finalists.to_csv(artifact_directory / "finalists.csv", index=False)
    predictions.to_csv(artifact_directory / "finalist_oof_predictions.csv", index=False)
    return SearchOutcome(screen_ranked, combined, finalists, predictions)


def refit_windowed_winner(
    dataset: ProductionVelocityDataset,
    *,
    parameters: dict[str, object],
    epochs: int,
    use_balanced_sampler: bool,
    jitter_fraction: float,
    seed: int,
    device: torch.device,
    checkpoint_path: Path,
) -> tuple[WindowedAnchorDeltaGru, StandardScaler, StandardScaler]:
    """Refit exactly one selected windowed candidate on all development data."""

    if epochs <= 0:
        raise ValueError("Final refit epochs must be positive.")
    indices = np.arange(len(dataset.target_delta_mps), dtype=np.int64)
    seed_everything(seed)
    sequence_scaler, context_scaler = _windowed_scalers(dataset, indices)
    sequence, context = _windowed_inputs(dataset, indices, sequence_scaler, context_scaler)
    generator = torch.Generator().manual_seed(seed)
    sampler = None
    if use_balanced_sampler:
        sampler = WeightedRandomSampler(
            torch.as_tensor(fold_balanced_sample_weights(dataset, indices), dtype=torch.double),
            len(indices), replacement=True, generator=generator,
        )
    loader = DataLoader(
        TensorDataset(torch.from_numpy(sequence), torch.from_numpy(context), torch.from_numpy(dataset.target_delta_mps.astype(np.float32))),
        batch_size=128, shuffle=sampler is None, sampler=sampler,
        generator=generator if sampler is None else None,
    )
    model = WindowedAnchorDeltaGru(
        hidden_size=int(parameters["hidden_size"]), num_layers=int(parameters["num_layers"]),
        bidirectional=bool(parameters["bidirectional"]), dropout=float(parameters["dropout"]),
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=float(parameters["weight_decay"]))
    completed = 0
    if checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if checkpoint.get("parameters") != parameters or int(checkpoint.get("epochs", -1)) != epochs:
            raise RuntimeError("Final windowed refit checkpoint uses a different contract.")
        model.load_state_dict(checkpoint["state_dict"]); optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        completed = int(checkpoint["completed_epochs"])
    robust_scale = np.subtract(*np.percentile(dataset.sequence_windows, [75, 25], axis=(0, 1))) / 1.349
    normalized_jitter = np.maximum(0.0, jitter_fraction * robust_scale / sequence_scaler.scale_).astype(np.float32)
    for epoch in range(completed + 1, epochs + 1):
        model.train(); losses = []
        for batch_sequence, batch_context, target in loader:
            batch_sequence, batch_context, target = batch_sequence.to(device), batch_context.to(device), target.to(device)
            if jitter_fraction:
                batch_sequence = batch_sequence + torch.randn_like(batch_sequence) * torch.from_numpy(normalized_jitter).to(device).view(1, 1, 6)
            optimizer.zero_grad(set_to_none=True)
            loss = functional.smooth_l1_loss(model(batch_sequence, batch_context), target, beta=2.0)
            loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step(); losses.append(float(loss.detach().cpu()))
        _atomic_torch_save({"parameters": parameters, "epochs": epochs, "state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(), "completed_epochs": epoch, "sequence_scaler": sequence_scaler, "context_scaler": context_scaler}, checkpoint_path)
        print(f"windowed final refit {epoch:03d}/{epochs} | train loss {np.mean(losses):.4f}", flush=True)
    return model.eval().to("cpu"), sequence_scaler, context_scaler


def refit_stateful_winner(
    sequences: Sequence[ProductionStatefulSequence],
    *,
    parameters: dict[str, object],
    epochs: int,
    jitter_fraction: float,
    seed: int,
    device: torch.device,
    checkpoint_path: Path,
) -> tuple[StreamingAnchorDeltaGru, StandardScaler]:
    """Refit one selected streaming candidate, retaining resumable TBPTT state."""

    if epochs <= 0:
        raise ValueError("Final refit epochs must be positive.")
    indices = np.arange(len(sequences), dtype=np.int64)
    seed_everything(seed)
    scaler = _stateful_scaler(sequences, indices)
    sampler = WeightedRandomSampler(torch.as_tensor(_stateful_sequence_weights(sequences, indices), dtype=torch.double), len(indices), replacement=True, generator=torch.Generator().manual_seed(seed))
    loader = DataLoader(indices.tolist(), batch_size=8, sampler=sampler, collate_fn=lambda values: _stateful_collate(sequences, values, scaler))
    model = StreamingAnchorDeltaGru(hidden_size=int(parameters["hidden_size"]), num_layers=int(parameters["num_layers"]), dropout=float(parameters["dropout"])).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(parameters["learning_rate"]), weight_decay=float(parameters["weight_decay"]))
    completed = 0
    if checkpoint_path.exists():
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if checkpoint.get("parameters") != parameters or int(checkpoint.get("epochs", -1)) != epochs:
            raise RuntimeError("Final stateful refit checkpoint uses a different contract.")
        model.load_state_dict(checkpoint["state_dict"]); optimizer.load_state_dict(checkpoint["optimizer_state_dict"]); completed = int(checkpoint["completed_epochs"])
    robust_scale = np.subtract(*np.percentile(np.concatenate([sequence.features[:, :6] for sequence in sequences]), [75, 25], axis=0)) / 1.349
    normalized_jitter = np.maximum(0.0, jitter_fraction * robust_scale / scaler.scale_[:6]).astype(np.float32)
    chunk_steps = int(parameters["chunk_steps"])
    for epoch in range(completed + 1, epochs + 1):
        model.train(); losses = []
        for batch in loader:
            features = batch["features"].to(device); targets = batch["targets"].to(device); mask = batch["training_mask"].to(device).float()
            if jitter_fraction:
                features = features.clone(); features[:, :, :6] += torch.randn_like(features[:, :, :6]) * torch.from_numpy(normalized_jitter).to(device).view(1, 1, 6)
            optimizer.zero_grad(set_to_none=True); hidden = None; denominator = mask.sum().clamp_min(1.0); total = 0.0
            for start in range(0, features.shape[1], chunk_steps):
                stop = start + chunk_steps; delta, hidden = model(features[:, start:stop], hidden); chunk_mask = mask[:, start:stop]
                if bool(chunk_mask.any()):
                    loss = (functional.smooth_l1_loss(delta, targets[:, start:stop], beta=2.0, reduction="none") * chunk_mask).sum() / denominator
                    loss.backward(); total += float(loss.detach().cpu())
                hidden = hidden.detach()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0); optimizer.step(); losses.append(total)
        _atomic_torch_save({"parameters": parameters, "epochs": epochs, "state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(), "completed_epochs": epoch, "scaler": scaler}, checkpoint_path)
        print(f"stateful final refit {epoch:03d}/{epochs} | train loss {np.mean(losses):.4f}", flush=True)
    return model.eval().to("cpu"), scaler


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_onnx_parity(
    *,
    onnx_path: Path,
    input_values: dict[str, np.ndarray],
    expected: Sequence[np.ndarray],
    output_names: Sequence[str],
) -> dict[str, float]:
    """Fail export rather than accept a graph whose runtime values drift."""

    try:
        import onnxruntime as ort
    except (ImportError, OSError) as error:
        raise RuntimeError("A working CPU ONNX Runtime is required for export parity.") from error
    received = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"]).run(list(output_names), input_values)
    errors = {name: float(np.max(np.abs(np.asarray(left) - np.asarray(right)))) for name, left, right in zip(output_names, expected, received, strict=True)}
    if any(error > 1e-5 for error in errors.values()):
        raise RuntimeError(f"ONNX parity failed: {errors!r}")
    return errors


def _onnx_cpu_p95_ms(
    *,
    onnx_path: Path,
    input_values: dict[str, np.ndarray],
    repeats: int = 200,
) -> float:
    """Measure exported-model CPU latency under the exact ONNX input contract."""

    try:
        import onnxruntime as ort
    except (ImportError, OSError) as error:
        raise RuntimeError("A working CPU ONNX Runtime is required for latency checks.") from error
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    for _ in range(20):
        session.run(None, input_values)
    timings = []
    for _ in range(repeats):
        started = time.perf_counter()
        session.run(None, input_values)
        timings.append((time.perf_counter() - started) * 1_000.0)
    return float(np.percentile(timings, 95))


def export_windowed_onnx(
    *,
    model: WindowedAnchorDeltaGru,
    sequence_scaler: StandardScaler,
    context_scaler: StandardScaler,
    parameters: dict[str, object],
    artifact_directory: Path,
    final_refit_epochs: int,
) -> tuple[Path, Path]:
    """Export the selected windowed model in the existing runtime contract."""

    artifact_directory.mkdir(parents=True, exist_ok=True)
    onnx_path = artifact_directory / "anchor_delta_gru.onnx"
    metadata_path = artifact_directory / "anchor_delta_gru.metadata.json"
    model.eval()
    example_sequence = torch.zeros((1, 50, 6), dtype=torch.float32)
    example_context = torch.zeros((1, 5), dtype=torch.float32)
    torch.onnx.export(model, (example_sequence, example_context), str(onnx_path), input_names=["imu_window", "context"], output_names=["speed_delta_mps"], opset_version=17)
    generator = np.random.default_rng(FINAL_SEARCH_SEED)
    sequence = generator.normal(size=(1, 50, 6)).astype(np.float32)
    context = generator.normal(size=(1, 5)).astype(np.float32)
    with torch.inference_mode():
        expected = [model(torch.from_numpy(sequence), torch.from_numpy(context)).numpy()]
    errors = _verify_onnx_parity(onnx_path=onnx_path, input_values={"imu_window": sequence, "context": context}, expected=expected, output_names=("speed_delta_mps",))
    onnx_cpu_p95_ms = _onnx_cpu_p95_ms(
        onnx_path=onnx_path,
        input_values={"imu_window": sequence, "context": context},
    )
    metadata_path.write_text(json.dumps({
        "schema_version": 1, "model_family": "anchor_delta_gru", "model_id": "anchor_delta_gru_final_search_v2",
        "input": {"sequence_feature_names": list(VELOCITY_MODEL_FEATURE_NAMES), "context_feature_names": list(ANCHOR_DELTA_GRU_CONTEXT_FEATURE_NAMES), "window_size": 50, "sample_period_ns": 100_000_000},
        "target": {"kind": "speed_delta_from_anchor", "unit": "m/s", "postprocess": "max(0, anchor_speed_mps + model_output)"},
        "normalization": {"sequence": {"mean": sequence_scaler.mean_.tolist(), "scale": sequence_scaler.scale_.tolist()}, "context": {"mean": context_scaler.mean_.tolist(), "scale": context_scaler.scale_.tolist()}},
        "training": {"parameters": parameters, "final_refit_epochs": final_refit_epochs, "selection": "five-fold grouped CV; development data only"},
        "onnx_parity": errors, "onnx_cpu_p95_ms": onnx_cpu_p95_ms,
    }, indent=2), encoding="utf-8")
    return onnx_path, metadata_path


def export_stateful_onnx(
    *,
    model: StreamingAnchorDeltaGru,
    scaler: StandardScaler,
    parameters: dict[str, object],
    artifact_directory: Path,
    final_refit_epochs: int,
) -> tuple[Path, Path]:
    """Export a streaming model compatible with the existing stateful adapter."""

    artifact_directory.mkdir(parents=True, exist_ok=True)
    onnx_path = artifact_directory / "stateful_anchor_delta_gru.onnx"
    metadata_path = artifact_directory / "stateful_anchor_delta_gru.metadata.json"
    hidden_shape = [int(parameters["num_layers"]), 1, int(parameters["hidden_size"])]
    model.eval(); features = torch.zeros((1, 7, 11), dtype=torch.float32); hidden = torch.zeros(hidden_shape, dtype=torch.float32)
    torch.onnx.export(model, (features, hidden), str(onnx_path), input_names=["features", "hidden_state"], output_names=["speed_delta_mps", "next_hidden_state"], dynamic_axes={"features": {1: "sequence_steps"}, "speed_delta_mps": {1: "sequence_steps"}}, opset_version=17)
    generator = np.random.default_rng(FINAL_SEARCH_SEED); feature_array = generator.normal(size=(1, 7, 11)).astype(np.float32); hidden_array = generator.normal(size=hidden_shape).astype(np.float32)
    with torch.inference_mode():
        expected = [value.numpy() for value in model(torch.from_numpy(feature_array), torch.from_numpy(hidden_array))]
    errors = _verify_onnx_parity(onnx_path=onnx_path, input_values={"features": feature_array, "hidden_state": hidden_array}, expected=expected, output_names=("speed_delta_mps", "next_hidden_state"))
    # After warm-up the streaming adapter normally supplies only new samples,
    # so measure the one-sample recurrent call that determines live p95.
    onnx_cpu_p95_ms = _onnx_cpu_p95_ms(
        onnx_path=onnx_path,
        input_values={
            "features": feature_array[:, :1, :],
            "hidden_state": hidden_array,
        },
    )
    metadata_path.write_text(json.dumps({
        "schema_version": 1, "model_id": "stateful_anchor_delta_gru_final_search_v2", "model_family": "stateful_anchor_delta_gru",
        "architecture": {"hidden_size": hidden_shape[2], "num_layers": hidden_shape[0], "dropout": float(parameters["dropout"]), "parameters": parameters, "final_refit_epochs": final_refit_epochs},
        "input": {"warmup_window_size": 50, "sample_period_ns": 100_000_000, "feature_names": list(STATEFUL_FEATURE_NAMES)},
        "recurrent_state": {"input_name": "hidden_state", "output_name": "next_hidden_state", "shape": hidden_shape, "reset_events": ["trusted_gnss_anchor_change", "imu_stream_or_device_change", "fixed_rate_continuity_break", "calibration_loss"]},
        "normalization": {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()},
        "target": {"kind": "speed_delta_from_anchor", "unit": "m/s", "postprocess": "max(0, anchor_speed_mps + model_output)"},
        "training": {"selection": "five-fold grouped CV; development data only"}, "onnx_parity": errors, "onnx_cpu_p95_ms": onnx_cpu_p95_ms,
    }, indent=2), encoding="utf-8")
    return onnx_path, metadata_path


def write_deterministic_uncertainty_profile(
    *,
    predictions: pd.DataFrame,
    dataset: ProductionVelocityDataset,
    model_id: str,
    onnx_path: Path,
    metadata_path: Path,
    output_path: Path,
) -> None:
    """Calibrate a monotone deterministic covariance schedule from OOF residuals."""

    required = {"journey_id", "anchor_timestamp_ns", "end_timestamp_ns", "horizon_s", "actual_speed_mps", "prediction_speed_mps"}
    if not required.issubset(predictions.columns):
        raise ValueError("OOF prediction frame lacks the required windowed columns.")
    facts = pd.DataFrame({
        "journey_id": dataset.journey_ids, "anchor_timestamp_ns": dataset.anchor_timestamps_ns,
        "end_timestamp_ns": dataset.end_timestamps_ns, "horizon_s": dataset.horizons_s,
        "linear_acceleration_std_mps2": dataset.uncertainty_base_features[:, 1],
        "angular_velocity_rms_radps": dataset.uncertainty_base_features[:, 2],
        "minimum_calibration_confidence": dataset.uncertainty_base_features[:, 3],
        "final_quality_score": dataset.uncertainty_base_features[:, 4],
    })
    merged = predictions.merge(facts, on=["journey_id", "anchor_timestamp_ns", "end_timestamp_ns", "horizon_s"], how="inner", validate="one_to_one")
    if len(merged) != len(predictions):
        raise ValueError("OOF predictions could not be aligned to uncertainty facts.")
    horizons = np.sort(merged.horizon_s.unique())
    standard_deviation = np.asarray([np.quantile(np.abs(rows.actual_speed_mps - rows.prediction_speed_mps), 0.6827) for _, rows in merged.groupby("horizon_s", sort=True)])
    standard_deviation = np.maximum.accumulate(np.maximum(standard_deviation, 0.25))
    document = {
        "schema_version": 1, "profile_kind": "deterministic_velocity_uncertainty", "velocity_model_id": model_id,
        "velocity_onnx_sha256": _sha256(onnx_path), "velocity_metadata_sha256": _sha256(metadata_path),
        "horizon_seconds": [float(value) for value in horizons], "base_standard_deviation_mps": standard_deviation.tolist(),
        "variance_ceiling_m2ps2": float(max(25.0, (3.0 * standard_deviation[-1]) ** 2)),
        "risk_inflation": {"reference_acceleration_std_mps2": float(max(0.1, merged.linear_acceleration_std_mps2.quantile(0.75))), "reference_angular_velocity_rms_radps": float(max(0.1, merged.angular_velocity_rms_radps.quantile(0.75))), "reference_minimum_calibration_confidence": float(max(0.01, merged.minimum_calibration_confidence.median())), "reference_final_quality_score": float(max(0.01, merged.final_quality_score.median())), "roughness_std_multiplier": 0.25, "turn_std_multiplier": 0.25, "calibration_std_multiplier": 0.50, "quality_std_multiplier": 0.25},
        "calibration_data": "grouped out-of-fold residuals from final production-preprocessor search only",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def write_stateful_deterministic_uncertainty_profile(
    *,
    predictions: pd.DataFrame,
    sequences: Sequence[ProductionStatefulSequence],
    model_id: str,
    onnx_path: Path,
    metadata_path: Path,
    output_path: Path,
) -> None:
    """Fit the same deterministic profile from streaming model OOF residuals."""

    facts: list[dict[str, object]] = []
    for sequence in sequences:
        for step in np.flatnonzero(sequence.evaluation_mask):
            window_start = max(0, step - 49)
            facts.append({
                "journey_id": sequence.journey_id,
                "anchor_timestamp_ns": sequence.anchor_timestamp_ns,
                "end_timestamp_ns": int(sequence.timestamps_ns[step]),
                "horizon_s": float(sequence.features[step, 8]),
                "linear_acceleration_std_mps2": float(np.std(sequence.features[window_start:step + 1, 0])),
                "angular_velocity_rms_radps": float(np.sqrt(np.mean(np.square(sequence.features[window_start:step + 1, 5])))),
                "minimum_calibration_confidence": float(sequence.features[step, 10]),
                "final_quality_score": float(sequence.final_quality_score[step]),
            })
    frame = pd.DataFrame(facts)
    required = {"journey_id", "anchor_timestamp_ns", "end_timestamp_ns", "horizon_s", "actual_speed_mps", "prediction_speed_mps"}
    if not required.issubset(predictions.columns):
        raise ValueError("Stateful OOF predictions lack the required columns.")

    # A persisted OOF frame crosses a CSV round trip in the resumable search.
    # Its floating horizon can therefore differ from the replay feature by a
    # few ulps even when it represents the identical endpoint.  The journey,
    # anchor and endpoint timestamp are the actual unique replay identity;
    # use them for the join and retain an explicit horizon consistency check.
    key_columns = ["journey_id", "anchor_timestamp_ns", "end_timestamp_ns"]
    predictions = predictions.copy()
    for table, label in ((predictions, "predictions"), (frame, "facts")):
        for column in key_columns[1:]:
            table[column] = pd.to_numeric(table[column], errors="raise").astype(
                np.int64
            )
        table["horizon_s"] = pd.to_numeric(table["horizon_s"], errors="raise")
        if not np.isfinite(table["horizon_s"]).all():
            raise ValueError(f"Stateful uncertainty {label} contain non-finite horizons.")
        if table.duplicated(key_columns).any():
            raise ValueError(
                f"Stateful uncertainty {label} contain duplicate replay endpoints."
            )

    merged = predictions.merge(
        frame,
        on=key_columns,
        how="inner",
        suffixes=("_prediction", "_fact"),
        validate="one_to_one",
    )
    if len(merged) != len(predictions):
        raise ValueError(
            "Stateful OOF predictions could not be aligned to uncertainty facts: "
            f"matched {len(merged):,} of {len(predictions):,} replay endpoints."
        )

    predicted_horizons = merged["horizon_s_prediction"].to_numpy(dtype=float)
    factual_horizons = merged["horizon_s_fact"].to_numpy(dtype=float)
    if not np.allclose(predicted_horizons, factual_horizons, rtol=1e-6, atol=1e-6):
        maximum_difference = float(np.max(np.abs(predicted_horizons - factual_horizons)))
        raise ValueError(
            "Stateful OOF horizon values do not match their replay endpoints; "
            f"maximum difference is {maximum_difference:.6f} seconds."
        )

    # Evaluation points are retained around each requested five-second horizon
    # to absorb real replay-timing jitter.  Calibrating each raw float
    # independently would yield many one-sample buckets and an unusable live
    # schedule. Collapse each point to its intended five-second horizon before
    # estimating the monotone residual quantiles used by the runtime.
    horizon_step_s = 5.0
    final_horizon_step = int(round(float(factual_horizons.max()) / horizon_step_s))
    canonical_horizons = horizon_step_s * np.arange(
        1, final_horizon_step + 1, dtype=float
    )
    nearest_indices = np.abs(
        factual_horizons[:, None] - canonical_horizons[None, :]
    ).argmin(axis=1)
    nearest_horizons = canonical_horizons[nearest_indices]
    maximum_offset = float(np.max(np.abs(factual_horizons - nearest_horizons)))
    if maximum_offset > 0.25:
        raise ValueError(
            "Stateful OOF includes an endpoint outside the canonical-horizon "
            f"tolerance; maximum offset is {maximum_offset:.6f} seconds."
        )
    merged["horizon_s"] = nearest_horizons
    horizons = np.sort(merged.horizon_s.unique())
    standard_deviation = np.asarray([np.quantile(np.abs(rows.actual_speed_mps - rows.prediction_speed_mps), 0.6827) for _, rows in merged.groupby("horizon_s", sort=True)])
    standard_deviation = np.maximum.accumulate(np.maximum(standard_deviation, 0.25))
    document = {
        "schema_version": 1, "profile_kind": "deterministic_velocity_uncertainty", "velocity_model_id": model_id,
        "velocity_onnx_sha256": _sha256(onnx_path), "velocity_metadata_sha256": _sha256(metadata_path),
        "horizon_seconds": [float(value) for value in horizons], "base_standard_deviation_mps": standard_deviation.tolist(),
        "variance_ceiling_m2ps2": float(max(25.0, (3.0 * standard_deviation[-1]) ** 2)),
        "risk_inflation": {"reference_acceleration_std_mps2": float(max(0.1, merged.linear_acceleration_std_mps2.quantile(0.75))), "reference_angular_velocity_rms_radps": float(max(0.1, merged.angular_velocity_rms_radps.quantile(0.75))), "reference_minimum_calibration_confidence": float(max(0.01, merged.minimum_calibration_confidence.median())), "reference_final_quality_score": float(max(0.01, merged.final_quality_score.median())), "roughness_std_multiplier": 0.25, "turn_std_multiplier": 0.25, "calibration_std_multiplier": 0.50, "quality_std_multiplier": 0.25},
        "calibration_data": "grouped out-of-fold residuals from final production-preprocessor streaming search only",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")

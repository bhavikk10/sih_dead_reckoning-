# hey

Model changed

gpt-5.6-sol -> gpt-5.6-terra

> understand the codebase and [IDR_Architecture_Brief.docx](IDR_Architecture_Brief.docx) and the current progress, dont alter anhy file or ongoing proecess

<details><summary>12 previous messages</summary>

> I’ll review the architecture brief, repository structure, and current Git/runtime state without modifying files or interrupting anything. I’m using the document-review workflow because the brief is a `.docx`.
>
> <details><summary>Explored a file, ran 9 commands</summary>
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/bhavi/.codex/plugins/cache/openai-primary-runtime/documents/26.903.11726/skills/documents/SKILL.md`
>
> </details>
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -First 180`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 360`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 180 -First 180`
>
> <details><summary>Explored a file</summary>
>
> - Read `C:/Users/bhavi/.codex/plugins/cache/openai-primary-runtime/documents/26.903.11726/skills/documents/tasks/read_review.md`
>
> </details>
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 120 -First 80`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 280 -First 80`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 200 -First 80`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 360 -First 80`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 440 -First 80`
>
> - Ran `Get-Content 'C:\Users\bhavi\.codex\plugins\cache\openai-primary-runtime\documents\26.903.11726\skills\documents\SKILL.md' | Select-Object -Skip 520`
>
> </details>
>
> I’ve confirmed the document review path and am now mapping the repo, change history, and running processes in parallel. All checks are read-only.
>
> <details><summary>Ran 7 commands</summary>
>
> - Ran `Get-ChildItem -Force | Select-Object Mode,Length,LastWriteTime,Name | Format-Table -AutoSize`
> - Ran `git status --short --branch`
> - Ran `rg --files -g '!node_modules/**' -g '!dist/**' -g '!build/**' -g '!*.lock'`
> - Ran `git diff --stat`
> - Ran `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'dead reckoning|vite|next|react-scripts|uvicorn|fastapi|flask|node' } | Select-Object ProcessId,Name,CommandLine | Format-List`
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from docx import Document; d=Document(r'E:\dead reckoning\IDR_Architecture_Brief.docx'); print('paragraphs',len(d.paragraphs),'tables',len(d.tables),'sections',len(d.sections)); [print(('H' if p.style.name.lower().startswith('heading') else 'P')+' | '+p.style.name+' | '+p.text.strip()) for p in d.paragraphs if p.text.strip()]"`
> - Ran `git log --oneline --decorate -12`
>
> </details>
>
> The repository is a Python inertial dead-reckoning backend with one initial commit and active, uncommitted work around GNSS/preprocessing/calibration evidence and a velocity experiment. I found no running application server or training process—only editor/Codex services—so nothing needs protecting or stopping.
>
> <details><summary>Explored 10 files, ran 8 commands</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from docx import Document; d=Document(r'E:\dead reckoning\IDR_Architecture_Brief.docx'); print('paragraphs',len(d.paragraphs),'tables',len(d.tables),'sections',len(d.sections)); [print(('H' if (p.style and p.style.name.lower().startswith('heading')) else 'P')+' | '+(p.style.name if p.style else '<none>')+' | '+p.text.strip()) for p in d.paragraphs if p.text.strip()]; [print('TABLE '+str(i+1)+' | '+' || '.join(' | '.join(c.text.replace(chr(10),' / ').strip() for c in row.cells) for row in t.rows)) for i,t in enumerate(d.tables)]"`
>
> <details><summary>Explored 5 files</summary>
>
> - Read `./docs/architecture.md`
> - Read `./README.md`
> - Read `./docs/decisions.md`
> - Read `./docs/validation_plan.md`
> - Read `./pyproject.toml`
>
> </details>
>
> - Ran `git diff --cached --stat`
>
> - Ran `Get-ChildItem artifacts -Recurse -File | Select-Object Length,LastWriteTime,FullName | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); from docx import Document; d=Document(r'E:\dead reckoning\IDR_Architecture_Brief.docx'); [print('TABLE '+str(i+1)+'\n'+'\n'.join(' || '.join(c.text.replace(chr(10),' / ').strip() for c in row.cells) for row in t.rows)) for i,t in enumerate(d.tables)]"`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); from docx import Document; d=Document(r'E:\dead reckoning\IDR_Architecture_Brief.docx'); [print(str(i+1)+' | '+('H' if (p.style and p.style.name.lower().startswith('heading')) else 'P')+' | '+(p.style.name if p.style else '<none>')+' | '+p.text.strip()) for i,p in enumerate(d.paragraphs[55:],start=55) if p.text.strip()]"`
>
> - Ran `Get-ChildItem src -Recurse -File -Filter *.py | Select-Object FullName,@{Name='Lines';Expression={(Get-Content $_.FullName).Count}},Length,LastWriteTime | Format-Table -AutoSize`
>
> - Ran `rg -n "^(class |def |async def |@dataclass|from |import )" src tests scripts notebooks\velocity_experiment.py -g '*.py'`
>
> - Ran `git diff -- .gitignore src/idr_backend/sensors/types.py`
>
> <details><summary>Explored 5 files</summary>
>
> - Read `./artifacts/anchored_velocity_comparison/manifest.json`
> - Read `./artifacts/anchored_velocity_comparison/frozen_test_comparison.csv`
> - Read `./artifacts/anchored_velocity_comparison/cv_selection.csv`
> - Read `./artifacts/anchored_velocity_comparison/acceptance_targets.csv`
> - Read `./configs/README.md`
>
> </details>
>
> </details>
>
> The implementation has moved beyond the committed “scaffold” documentation: the sensors package now contains concrete deterministic preprocessing pieces, while fusion, map matching, uncertainty, and road-context remain largely boundary/placeholder territory. I’m reviewing the active files and experiment evidence to distinguish demonstrated work from planned architecture.
>
> <details><summary>Explored 9 files, ran 8 commands</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import ast,pathlib; root=pathlib.Path('src'); [print(f'{p.as_posix()}:{getattr(n,chr(39)linenochr(39),0)} {type(n).__name__} {n.name}'+((' — '+ast.get_docstring(n).splitlines()[0]) if ast.get_docstring(n) else '')) for p in root.rglob('*.py') for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]"`
>
> <details><summary>Explored 4 files</summary>
>
> - Read `./src/idr_backend/sensors/calibration_evidence.py`
> - Read `./src/idr_backend/sensors/preprocessing.py`
> - Read `./src/idr_backend/sensors/gnss.py`
> - Read `./tests/unit/test_velocity_experiment.py`
>
> </details>
>
> - Ran `Get-Item notebooks\velocity_experiment.py | Select-Object Length,LastWriteTime,@{Name='Lines';Expression={(Get-Content $_.FullName).Count}} | Format-List`
>
> - Ran `Get-Item notebooks\retrain_clean_velocity_models.ipynb | Select-Object Length,LastWriteTime | Format-List`
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./scripts/README.md`
> - Read `./tests/unit/README.md`
>
> </details>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import ast,pathlib; p=pathlib.Path('notebooks/velocity_experiment.py'); t=ast.parse(p.read_text(encoding='utf-8')); [print(str(getattr(n,'lineno',0))+' | '+type(n).__name__+' | '+n.name+(' | '+ast.get_docstring(n).splitlines()[0] if ast.get_docstring(n) else '')) for n in ast.walk(t) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]"`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import ast,pathlib; [print(p.as_posix()+' | '+str(getattr(n,'lineno',0))+' | '+type(n).__name__+' | '+n.name+(' | '+ast.get_docstring(n).splitlines()[0] if ast.get_docstring(n) else '')) for p in pathlib.Path('src/idr_backend/sensors').glob('*.py') for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef))]"`
>
> - Ran `Get-Content notebooks\velocity_experiment.py | Select-Object -First 360`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); import nbformat; n=nbformat.read(r'E:\dead reckoning\notebooks\retrain_clean_velocity_models.ipynb',as_version=4); print('cells',len(n.cells)); [print('CELL '+str(i+1)+' '+c.cell_type+'\n'+c.source) for i,c in enumerate(n.cells)]"`
>
> <details><summary>Explored 3 files</summary>
>
> - Read `./artifacts/anchored_velocity_comparison/latency.csv`
> - Read `./artifacts/anchored_velocity_comparison/error_by_horizon_and_speed.csv`
> - Read `./artifacts/anchored_velocity_comparison/preprocessing_audit.csv`
>
> </details>
>
> - Ran `Get-Content chat.md -Tail 160`
>
> </details>
>
> The experiment is genuinely running as a documented offline evaluation, not yet a deployable velocity component. Its strongest current candidate is an anchored residual GRU; it improves substantially over raw integration and the prior absolute-speed models, but it misses every stated 30/60/120-second drift target. The saved run used the `smoke` search profile, so it is an informative baseline rather than the promised full search.
>
> <details><summary>Explored 2 files, ran 6 commands</summary>
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys; sys.stdout.reconfigure(encoding='utf-8'); import nbformat; n=nbformat.read(r'E:\dead reckoning\notebooks\retrain_clean_velocity_models.ipynb',as_version=4); [print('MARKDOWN '+str(i+1)+'\n'+c.source) for i,c in enumerate(n.cells) if c.cell_type=='markdown']"`
>
> - Ran `Get-Content notebooks\velocity_experiment.py | Select-Object -Skip 300 -First 590`
>
> - Ran `Get-Content notebooks\velocity_experiment.py | Select-Object -Skip 950 -First 360`
>
> - Ran `& 'C:\Users\bhavi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import ast,pathlib; [print(p.name+' | classes='+','.join(n.name for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef))+' | functions='+','.join(n.name for n in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)))) for p in sorted(pathlib.Path('src/idr_backend/sensors').glob('*.py'))]"`
>
> - Ran `Get-Content chat.md -Tail 80`
>
> <details><summary>Explored 2 files</summary>
>
> - Read `./artifacts/anchored_velocity_comparison/fold_audit.csv`
> - Read `./artifacts/anchored_velocity_comparison/skipped_journeys.csv`
>
> </details>
>
> - Ran `Get-Content artifacts\anchored_velocity_comparison\frozen_test_predictions.csv | Measure-Object -Line | Select-Object -ExpandProperty Lines`
>
> </details>
>
> I’ve completed the read-only review. I’m doing one final Git-state check only, to verify my inspection did not change the workspace; I will not run tests because they may update cache files.
>
> <details><summary>Ran 3 commands</summary>
>
> - Ran `git status --short --branch`
> - Ran `git diff --numstat`
> - Ran `git diff --cached --numstat`
>
> </details>
</details>

I’ve mapped the codebase and brief, and made no changes or process interruptions. :codex-file-citation{path="E:/dead reckoning/IDR_Architecture_Brief.docx" purpose="source" artifact_kind="document"}

The intended system is phone/external-IMU preprocessing → 15-state error-state EKF → GNSS/NHC/velocity/road-context updates → incremental HMM map matching, with offline OSM and a Flutter-based mobile app. The brief’s three learned components are velocity, uncertainty, and road context.

Current implementation is narrower:

- Sensor utilities are concrete: synchronization, normalization, orientation, dynamic mounting calibration, gravity removal, quality checks, resampling, and causal windows.
- New uncommitted work adds GNSS contracts/quality evaluation and a deterministic preprocessor, but EKF fusion, map matching, uncertainty, road context, adapters, and frontend remain mostly planned interfaces/placeholders.
- The active research focus is the local velocity experiment in [velocity_experiment.py](<./notebooks/velocity_experiment.py>): anchored residual prediction using last trusted GNSS speed + integrated clean forward acceleration + learned correction. It uses journey-isolated CV and simulated GNSS blackouts.
- Latest saved experiment results favor the residual GRU (macro test MAE 15.13 km/h), much better than pure integration (43.17 km/h), but it misses all stated targets: 30/60/120-second MAE is 15.25/16.81/18.33 km/h versus 5/8/12. The saved run is only a `smoke` search, and artifacts predate the latest notebook/module edits.
- No project server or training job is running. I did not run tests because that could update cache files.

One important static observation: the new GNSS-backed calibration/preprocessor path appears mid-edit. `calibration_evidence.py` contains class-body references to undefined names, and its current accuracy-score arithmetic would collapse evidence confidence to zero; the velocity experiment does not use this new path. I left it untouched.

The workspace remains exactly dirty as it was: the notebook, sensor types, new GNSS/preprocessing files, experiment module, and focused experiment test are uncommitted; nothing is staged.

> okay so work till velocity estimation is pretty much doen right

Not quite: the velocity-estimation experiment is substantially built, but the deployable velocity engine is not done.

Done: deterministic replay, blackout dataset, grouped CV, baselines, GRU/CNN/RF comparisons, saved weights/artifacts, and leakage-focused tests.

Still needed: repair and integrate the GNSS/preprocessing path, run the full model search, meet the 30/60/120-second accuracy targets (the current GRU misses all three), define runtime inference/adapter behavior, and connect its output to uncertainty and EKF fusion.

> so ekf fusion and uncertainity model can be parallely built right

Yes. They can proceed in parallel.

- EKF fusion can be built against the existing `VelocityObservation` and `UncertaintyEstimate` contracts, using replayed/placeholder speed observations initially.
- The uncertainty model can train from the same velocity experiment data: prediction residuals, blackout age, IMU/calibration quality, and model metadata.

They only need to agree early on the measurement interface: timestamp, speed in m/s, variance in `(m/s)²`, quality flags, and fallback behavior. The final velocity model can then be swapped in without redesigning either system.

> right so start with the first file of ekf fusion, give fn snippets for each file one by one, with detailed expln of each, fn then expln then next fn and so on, llets start with the first file right of ekf, try to minimise the token usage by not reading the whole folder every pass

<details><summary>2 previous messages</summary>

> I’ll start with `fusion/state.py`: it should define the 15-state nominal/error-state container before propagation, covariance, or measurement updates depend on it. I’ll inspect only that file and the already-known shared sensor types, then give the functions in implementation order without editing anything.
>
> <details><summary>Explored 2 files, ran a command</summary>
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/state.py`
>
> </details>
>
> - Ran `Get-Content src\idr_backend\sensors\types.py | Select-Object -First 220`
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/README.md`
>
> </details>
>
> </details>
</details>

Start with [`state.py`](<./src/idr_backend/fusion/state.py>). It is currently only a TODO, and I would build it before propagation/covariance/measurements.

Use this fixed error order everywhere:

```python
# δx = [δp_ENU, δv_ENU, δθ_vehicle, δb_acc_vehicle, δb_gyro_vehicle]
ERROR_STATE_DIM = 15

POSITION = slice(0, 3)
VELOCITY = slice(3, 6)
ATTITUDE = slice(6, 9)
ACCEL_BIAS = slice(9, 12)
GYRO_BIAS = slice(12, 15)
```

`δp` and `δv` are ENU; orientation and biases are vehicle-FLU. The attitude correction is right-multiplied, so `δθ` is a small rotation expressed in the vehicle frame.

```python
@dataclass(frozen=True, slots=True)
class NominalNavigationState:
    timestamp_ns: int
    position_enu_m: np.ndarray
    velocity_enu_mps: np.ndarray
    vehicle_to_navigation_wxyz: QuaternionWxyz
    accelerometer_bias_vehicle_mps2: np.ndarray
    gyroscope_bias_vehicle_radps: np.ndarray

@dataclass(frozen=True, slots=True)
class ErrorStateEkfState:
    nominal: NominalNavigationState
    covariance: np.ndarray  # shape: (15, 15)
```

The nominal state is the usable answer: position, velocity, attitude, and estimated IMU biases. The 15-vector is never published; it represents uncertainty around that nominal state.

```python
def initialise_filter_state(
    *,
    timestamp_ns: int,
    position_enu_m: Vector3,
    velocity_enu_mps: Vector3,
    vehicle_to_navigation_wxyz: QuaternionWxyz,
    initial_error_std: np.ndarray,
) -> ErrorStateEkfState:
    """Create a fully initialized filter with zero IMU-bias estimates."""

    std = np.asarray(initial_error_std, dtype=float)
    if std.shape != (ERROR_STATE_DIM,) or not np.all(np.isfinite(std)):
        raise ValueError("initial_error_std must be a finite 15-vector.")
    if np.any(std <= 0.0):
        raise ValueError("All initial error standard deviations must be positive.")

    nominal = NominalNavigationState(
        timestamp_ns=timestamp_ns,
        position_enu_m=np.asarray(position_enu_m, dtype=float),
        velocity_enu_mps=np.asarray(velocity_enu_mps, dtype=float),
        vehicle_to_navigation_wxyz=normalize_quaternion(
            vehicle_to_navigation_wxyz
        ),
        accelerometer_bias_vehicle_mps2=np.zeros(3),
        gyroscope_bias_vehicle_radps=np.zeros(3),
    )
    return ErrorStateEkfState(nominal=nominal, covariance=np.diag(std**2))
```

Call this only after a trustworthy initial GNSS fix and vehicle orientation/calibration are available. The passed standard deviations establish how much the filter initially trusts GNSS position, GNSS velocity, attitude, and the assumption that IMU biases begin near zero.

```python
def small_angle_quaternion(
    rotation_vector_vehicle_rad: np.ndarray,
) -> QuaternionWxyz:
    """Convert a vehicle-frame rotation vector into a correction quaternion."""

    angle = float(np.linalg.norm(rotation_vector_vehicle_rad))
    if angle < 1e-12:
        return (1.0, 0.0, 0.0, 0.0)

    axis = rotation_vector_vehicle_rad / angle
    half_angle = 0.5 * angle
    return (
        float(np.cos(half_angle)),
        float(axis[0] * np.sin(half_angle)),
        float(axis[1] * np.sin(half_angle)),
        float(axis[2] * np.sin(half_angle)),
    )
```

An EKF stores a tiny three-axis attitude error, not a second full quaternion. This converts that correction into a valid quaternion just before it is injected into the nominal attitude.

```python
def inject_nominal_error(
    nominal: NominalNavigationState,
    delta_x: np.ndarray,
) -> NominalNavigationState:
    """Apply one estimated 15-state correction to the nominal navigation state."""

    correction = np.asarray(delta_x, dtype=float)
    if correction.shape != (ERROR_STATE_DIM,) or not np.all(np.isfinite(correction)):
        raise ValueError("delta_x must be a finite 15-vector.")

    corrected_attitude = normalize_quaternion(
        quaternion_multiply(
            nominal.vehicle_to_navigation_wxyz,
            small_angle_quaternion(correction[ATTITUDE]),
        )
    )

    return NominalNavigationState(
        timestamp_ns=nominal.timestamp_ns,
        position_enu_m=nominal.position_enu_m + correction[POSITION],
        velocity_enu_mps=nominal.velocity_enu_mps + correction[VELOCITY],
        vehicle_to_navigation_wxyz=corrected_attitude,
        accelerometer_bias_vehicle_mps2=(
            nominal.accelerometer_bias_vehicle_mps2 + correction[ACCEL_BIAS]
        ),
        gyroscope_bias_vehicle_radps=(
            nominal.gyroscope_bias_vehicle_radps + correction[GYRO_BIAS]
        ),
    )
```

Every accepted GNSS, velocity, NHC, or road-context measurement will eventually produce `delta_x`. This function applies it consistently. It deliberately does not reset/update the covariance; that belongs in the next file, `covariance.py`, because the reset Jacobian must be applied there.

> next, and make the xplns and comments more detailed

<details><summary>2 previous messages</summary>

> Next is `fusion/covariance.py`. It owns the uncertainty mathematics shared by propagation and measurement updates: symmetry/PSD checks, process-noise construction, innovation covariance, and the mandatory covariance reset after injecting an error-state correction. I’ll inspect only that placeholder.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/covariance.py`
>
> </details>
</details>

Next: [`covariance.py`](<./src/idr_backend/fusion/covariance.py>). This file should be the numerical-safety layer for the EKF. It should not know what GNSS, NHC, or velocity measurements mean; it only keeps their covariance math valid.

I am showing proposed snippets only; I have not written them into the file.

```python
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

from .state import ATTITUDE, ERROR_STATE_DIM

Matrix = NDArray[np.float64]

class CovarianceHealthError(ValueError):
    """Raised when covariance is non-finite, asymmetric, or meaningfully non-PSD."""

@dataclass(frozen=True, slots=True)
class ImuNoiseDensity:
    """Continuous-time white-noise and bias-random-walk densities.

    These values are sensor-characterization inputs, not parameters learned
    during a drive. Phone and external-IMU profiles will provide different
    instances later through configuration.
    """

    accelerometer_mps2_per_sqrt_hz: float
    gyroscope_radps_per_sqrt_hz: float
    accelerometer_bias_rw_mps2_per_sqrt_s: float
    gyroscope_bias_rw_radps_per_sqrt_s: float
```

This defines the noise units before doing any covariance work. The EKF must distinguish:

- instant IMU measurement noise, which affects velocity/attitude propagation;
- slowly wandering IMU bias, which affects the bias states over time.

Do not use one generic “EKF noise” number: it prevents tuning a phone and a high-grade external IMU independently.

```python
def symmetrise_covariance(covariance: Matrix) -> Matrix:
    """Remove floating-point asymmetry without hiding invalid uncertainty."""

    matrix = np.asarray(covariance, dtype=float)
    if matrix.shape != (ERROR_STATE_DIM, ERROR_STATE_DIM):
        raise CovarianceHealthError("Covariance must have shape (15, 15).")
    if not np.all(np.isfinite(matrix)):
        raise CovarianceHealthError("Covariance contains NaN or infinity.")

    return 0.5 * (matrix + matrix.T)
```

In exact mathematics, covariance is always symmetric. Matrix multiplication and inversion introduce tiny asymmetries, such as `P[2, 7] != P[7, 2]` by `1e-15`. Averaging the two halves fixes that harmless numerical noise. It must not be used to conceal a bad covariance shape or non-finite values.

```python
def require_positive_semidefinite(
    covariance: Matrix,
    *,
    negative_eigenvalue_tolerance: float = 1e-10,
) -> Matrix:
    """Return a symmetric PSD covariance or raise a visible health failure."""

    symmetric = symmetrise_covariance(covariance)
    eigenvalues = np.linalg.eigvalsh(symmetric)

    if eigenvalues[0] < -negative_eigenvalue_tolerance:
        raise CovarianceHealthError(
            "Covariance is not positive semidefinite; "
            f"minimum eigenvalue is {eigenvalues[0]:.3e}."
        )

    # A tiny negative eigenvalue can arise purely from rounding. Clip only that
    # near-zero numerical residue; a materially invalid matrix already raised.
    eigenvalues = np.maximum(eigenvalues, 0.0)
    vectors = np.linalg.eigh(symmetric)[1]
    repaired = (vectors * eigenvalues) @ vectors.T
    return symmetrise_covariance(repaired)
```

Positive semidefinite means the filter never claims a negative variance in any direction. A substantial negative eigenvalue is a real algorithm/configuration failure and must stop or trigger explicit recovery. Only microscopic negative values caused by floating-point rounding may be clipped.

```python
def continuous_imu_noise_covariance(noise: ImuNoiseDensity) -> Matrix:
    """Build Qc for [accelerometer noise, gyro noise, accel-bias RW, gyro-bias RW]."""

    densities = np.asarray(
        (
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.accelerometer_mps2_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.gyroscope_radps_per_sqrt_hz,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.accelerometer_bias_rw_mps2_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
            noise.gyroscope_bias_rw_radps_per_sqrt_s,
        ),
        dtype=float,
    )
    if not np.all(np.isfinite(densities)) or np.any(densities <= 0.0):
        raise ValueError("All IMU noise densities must be finite and positive.")

    return np.diag(densities**2)
```

This creates the continuous-time `Qc` matrix, with 12 independent driving-noise terms. The later propagation file builds `G`, which maps these noise sources into the 15 error states. Keeping `Qc` here prevents accidental mixing of sensor noise with the filter’s state covariance `P`.

```python
def discretise_error_dynamics(
    continuous_jacobian: Matrix,
    noise_mapping: Matrix,
    continuous_noise_covariance: Matrix,
    delta_time_s: float,
) -> tuple[Matrix, Matrix]:
    """Return discrete transition Phi and discrete process covariance Qd.

    Uses Van Loan discretisation, avoiding the inaccurate shortcut Qd = Qc * dt
    when attitude, position, and bias errors are coupled.
    """

    if not np.isfinite(delta_time_s) or delta_time_s <= 0.0:
        raise ValueError("delta_time_s must be finite and positive.")

    f = np.asarray(continuous_jacobian, dtype=float)
    g = np.asarray(noise_mapping, dtype=float)
    qc = np.asarray(continuous_noise_covariance, dtype=float)

    if f.shape != (ERROR_STATE_DIM, ERROR_STATE_DIM):
        raise ValueError("continuous_jacobian must have shape (15, 15).")
    if g.shape != (ERROR_STATE_DIM, 12) or qc.shape != (12, 12):
        raise ValueError("Expected G shape (15, 12) and Qc shape (12, 12).")

    driven_noise = g @ qc @ g.T
    van_loan = np.zeros((2 * ERROR_STATE_DIM, 2 * ERROR_STATE_DIM))
    van_loan[:ERROR_STATE_DIM, :ERROR_STATE_DIM] = f
    van_loan[:ERROR_STATE_DIM, ERROR_STATE_DIM:] = driven_noise
    van_loan[ERROR_STATE_DIM:, ERROR_STATE_DIM:] = -f.T

    block_exponential = expm(van_loan * delta_time_s)
    phi = block_exponential[:ERROR_STATE_DIM, :ERROR_STATE_DIM]
    qd = block_exponential[:ERROR_STATE_DIM, ERROR_STATE_DIM:] @ phi.T

    return phi, require_positive_semidefinite(qd)
```

`Phi` tells the filter how a small error evolves during one IMU interval; `Qd` tells it how much new uncertainty the IMU adds during that same interval. Van Loan discretisation matters because an accelerometer error affects velocity first and position later, while gyro error affects attitude and then causes incorrect acceleration rotation.

```python
def joseph_covariance_update(
    prior_covariance: Matrix,
    kalman_gain: Matrix,
    measurement_jacobian: Matrix,
    measurement_covariance: Matrix,
) -> Matrix:
    """Perform a numerically stable EKF measurement covariance update."""

    prior = require_positive_semidefinite(prior_covariance)
    gain = np.asarray(kalman_gain, dtype=float)
    h = np.asarray(measurement_jacobian, dtype=float)
    r = np.asarray(measurement_covariance, dtype=float)

    identity = np.eye(ERROR_STATE_DIM)
    residual_projection = identity - gain @ h

    # Joseph form is safer than P = (I - K H) P. It preserves PSD behavior
    # even when numerical round-off makes the simple form unstable.
    posterior = (
        residual_projection @ prior @ residual_projection.T
        + gain @ r @ gain.T
    )
    return require_positive_semidefinite(posterior)
```

Every measurement type—GNSS position, GNSS speed, velocity model, NHC, or road-context prior—will use this function after calculating its own `H`, `R`, residual, and gain. Joseph form costs little at 15 states and avoids a common EKF failure where uncertainty becomes negative after repeated updates.

```python
def reset_covariance_after_injection(
    covariance: Matrix,
    attitude_correction_vehicle_rad: np.ndarray,
) -> Matrix:
    """Reset covariance after applying the estimated attitude error to nominal state."""

    delta_theta = np.asarray(attitude_correction_vehicle_rad, dtype=float)
    if delta_theta.shape != (3,):
        raise ValueError("attitude_correction_vehicle_rad must have shape (3,).")

    x, y, z = delta_theta
    skew = np.asarray(
        (
            (0.0, -z, y),
            (z, 0.0, -x),
            (-y, x, 0.0),
        )
    )

    reset_jacobian = np.eye(ERROR_STATE_DIM)
    reset_jacobian[ATTITUDE, ATTITUDE] = np.eye(3) - 0.5 * skew

    reset_covariance = (
        reset_jacobian @ covariance @ reset_jacobian.T
    )
    return require_positive_semidefinite(reset_covariance)
```

After a measurement update, `state.py` injects the estimated `δθ` into the nominal quaternion. The error state is then redefined around that newly corrected quaternion, so its covariance must be transformed too. Skipping this step makes position/velocity look correct initially but gradually corrupts attitude uncertainty and eventual heading drift.

Next should be `propagation.py`, which will form `F` and `G`, call `discretise_error_dynamics`, propagate the nominal state from each clean vehicle-frame IMU sample, then calculate `P⁻ = ΦPΦᵀ + Qd`.

> yes

<details><summary>2 previous messages</summary>

> I’ll continue with `fusion/propagation.py` only. This is where each clean vehicle-frame IMU sample advances the nominal position/velocity/attitude and grows the 15-state covariance using the helpers just defined.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/propagation.py`
>
> </details>
</details>

Next: [`propagation.py`](<./src/idr_backend/fusion/propagation.py>).

This file advances the EKF from one accepted `VehicleImuSample` to the next. It must use the EKF’s own nominal attitude; do not overwrite it every sample with `sample.vehicle_to_navigation_wxyz`. The preprocessor attitude is useful for initialization or later attitude aiding, while the EKF remains the source of truth after initialization.

```python
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from ..sensors.orientation import (
    propagate_orientation,
    rotate_vector,
)
from ..sensors.types import VehicleImuSample
from .covariance import (
    ImuNoiseDensity,
    continuous_imu_noise_covariance,
    discretise_error_dynamics,
    require_positive_semidefinite,
)
from .state import (
    ACCEL_BIAS,
    ATTITUDE,
    ERROR_STATE_DIM,
    GYRO_BIAS,
    POSITION,
    VELOCITY,
    ErrorStateEkfState,
    NominalNavigationState,
)

Matrix = NDArray[np.float64]
```

These imports establish a clean boundary:

- sensor preprocessing supplies calibrated, gravity-removed vehicle-FLU IMU data;
- `state.py` owns the nominal state and 15-error-state ordering;
- `covariance.py` owns process-noise discretisation and covariance health checks.

```python
@dataclass(frozen=True, slots=True)
class PropagationConfig:
    """Safety limits and physical IMU-noise settings for one IMU source."""

    noise: ImuNoiseDensity

    # A larger gap means the filter did not observe enough inertial data to
    # honestly integrate through it. Recovery must be explicit.
    maximum_delta_time_s: float = 0.25

class PropagationDisposition(StrEnum):
    """Whether this IMU sample safely advanced the navigation state."""

    PROPAGATED = "propagated"
    TIMING_GAP_REQUIRES_RECOVERY = "timing_gap_requires_recovery"

@dataclass(frozen=True, slots=True)
class PropagationDiagnostics:
    """Audit record for one attempted inertial propagation step."""

    delta_time_s: float
    corrected_acceleration_vehicle_mps2: np.ndarray
    corrected_angular_velocity_vehicle_radps: np.ndarray
    acceleration_navigation_enu_mps2: np.ndarray

@dataclass(frozen=True, slots=True)
class PropagationResult:
    """Result of advancing the prior state with one accepted IMU sample."""

    disposition: PropagationDisposition
    state: ErrorStateEkfState
    diagnostics: PropagationDiagnostics | None
```

A large IMU timing gap must not be silently filled by repeating the last reading or inventing intermediate samples. The caller will receive `TIMING_GAP_REQUIRES_RECOVERY`, retain the last honest state, inflate/reinitialize uncertainty through a later policy, and wait for suitable GNSS or calibration evidence.

```python
def skew_symmetric(vector: np.ndarray) -> Matrix:
    """Return [v]x such that [v]x @ w == v cross w."""

    x, y, z = np.asarray(vector, dtype=float)
    return np.asarray(
        (
            (0.0, -z, y),
            (z, 0.0, -x),
            (-y, x, 0.0),
        ),
        dtype=float,
    )
```

This is used in the linearised error dynamics. For example, an attitude error rotates the measured forward acceleration slightly into a false lateral or vertical acceleration. That relationship is represented by a skew-symmetric matrix rather than by hand-written component formulas.

```python
def vehicle_to_navigation_rotation(
    vehicle_to_navigation_wxyz: tuple[float, float, float, float],
) -> Matrix:
    """Build the 3x3 matrix that maps vehicle-FLU vectors into ENU."""

    return np.column_stack(
        (
            rotate_vector(vehicle_to_navigation_wxyz, (1.0, 0.0, 0.0)),
            rotate_vector(vehicle_to_navigation_wxyz, (0.0, 1.0, 0.0)),
            rotate_vector(vehicle_to_navigation_wxyz, (0.0, 0.0, 1.0)),
        )
    )
```

The EKF stores orientation as a quaternion because it is stable for integration. Position and velocity propagation, however, need a rotation matrix:

`a_ENU = R_vehicle_to_ENU × a_vehicle`

The cleaned accelerometer sample already has gravity removed, so no gravity vector is added here. That decision must remain consistent with the preprocessing contract.

```python
def propagate_nominal_state(
    nominal: NominalNavigationState,
    sample: VehicleImuSample,
    delta_time_s: float,
) -> tuple[NominalNavigationState, np.ndarray, np.ndarray, np.ndarray]:
    """Advance nominal position, velocity, and attitude by one IMU interval."""

    corrected_acceleration_vehicle = (
        np.asarray(sample.linear_acceleration_mps2, dtype=float)
        - nominal.accelerometer_bias_vehicle_mps2
    )
    corrected_angular_velocity_vehicle = (
        np.asarray(sample.angular_velocity_radps, dtype=float)
        - nominal.gyroscope_bias_vehicle_radps
    )

    # Midpoint attitude reduces acceleration-rotation error during turns.
    midpoint_attitude = propagate_orientation(
        nominal.vehicle_to_navigation_wxyz,
        tuple(corrected_angular_velocity_vehicle),
        0.5 * delta_time_s,
    )
    rotation_midpoint = vehicle_to_navigation_rotation(midpoint_attitude)
    acceleration_navigation = (
        rotation_midpoint @ corrected_acceleration_vehicle
    )

    next_position = (
        nominal.position_enu_m
        + nominal.velocity_enu_mps * delta_time_s
        + 0.5 * acceleration_navigation * delta_time_s**2
    )
    next_velocity = (
        nominal.velocity_enu_mps
        + acceleration_navigation * delta_time_s
    )
    next_attitude = propagate_orientation(
        nominal.vehicle_to_navigation_wxyz,
        tuple(corrected_angular_velocity_vehicle),
        delta_time_s,
    )

    return (
        NominalNavigationState(
            timestamp_ns=sample.timestamp_ns,
            position_enu_m=next_position,
            velocity_enu_mps=next_velocity,
            vehicle_to_navigation_wxyz=next_attitude,
            # Bias values evolve in the covariance during propagation. Their
            # nominal estimate changes only after a later measurement update.
            accelerometer_bias_vehicle_mps2=(
                nominal.accelerometer_bias_vehicle_mps2
            ),
            gyroscope_bias_vehicle_radps=(
                nominal.gyroscope_bias_vehicle_radps
            ),
        ),
        corrected_acceleration_vehicle,
        corrected_angular_velocity_vehicle,
        acceleration_navigation,
    )
```

This is the physical strapdown step:

1. Remove the EKF’s current bias estimates from the clean IMU values.
2. Integrate gyro rate into attitude.
3. Rotate the bias-corrected vehicle acceleration into ENU.
4. Integrate acceleration into velocity and position.

The midpoint orientation matters most during turns: using only the old orientation would project part of a forward acceleration onto the wrong ENU direction.

```python
def build_continuous_error_dynamics(
    *,
    vehicle_to_navigation: Matrix,
    corrected_acceleration_vehicle_mps2: np.ndarray,
    corrected_angular_velocity_vehicle_radps: np.ndarray,
) -> tuple[Matrix, Matrix]:
    """Build continuous-time F and G for the 15-state right-error EKF."""

    f = np.zeros((ERROR_STATE_DIM, ERROR_STATE_DIM))
    g = np.zeros((ERROR_STATE_DIM, 12))

    # Position error grows from velocity error.
    f[POSITION, VELOCITY] = np.eye(3)

    # Attitude and accelerometer-bias error create ENU velocity error.
    f[VELOCITY, ATTITUDE] = (
        -vehicle_to_navigation
        @ skew_symmetric(corrected_acceleration_vehicle_mps2)
    )
    f[VELOCITY, ACCEL_BIAS] = -vehicle_to_navigation

    # Right-multiplicative attitude error is expressed in vehicle coordinates.
    f[ATTITUDE, ATTITUDE] = -skew_symmetric(
        corrected_angular_velocity_vehicle_radps
    )
    f[ATTITUDE, GYRO_BIAS] = -np.eye(3)

    # Noise order: accel noise, gyro noise, accel-bias random walk,
    # gyro-bias random walk.
    g[VELOCITY, 0:3] = -vehicle_to_navigation
    g[ATTITUDE, 3:6] = -np.eye(3)
    g[ACCEL_BIAS, 6:9] = np.eye(3)
    g[GYRO_BIAS, 9:12] = np.eye(3)

    return f, g
```

`F` describes how existing uncertainty evolves. For example, a small unknown gyro bias produces growing attitude error; that attitude error rotates acceleration wrongly; the incorrect acceleration then grows velocity and position error.

`G` maps new sensor noise into those states. This is why gyro noise must not be treated as direct position noise—the covariance growth must follow the physical chain.

```python
def propagate_ekf(
    prior: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: PropagationConfig,
) -> PropagationResult:
    """Propagate nominal state and covariance with one accepted IMU sample."""

    delta_time_s = (
        sample.timestamp_ns - prior.nominal.timestamp_ns
    ) * 1e-9

    if (
        not np.isfinite(delta_time_s)
        or delta_time_s <= 0.0
        or delta_time_s > config.maximum_delta_time_s
    ):
        return PropagationResult(
            disposition=PropagationDisposition.TIMING_GAP_REQUIRES_RECOVERY,
            state=prior,
            diagnostics=None,
        )

    propagated_nominal, corrected_accel, corrected_gyro, acceleration_enu = (
        propagate_nominal_state(prior.nominal, sample, delta_time_s)
    )

    rotation = vehicle_to_navigation_rotation(
        prior.nominal.vehicle_to_navigation_wxyz
    )
    continuous_f, noise_mapping = build_continuous_error_dynamics(
        vehicle_to_navigation=rotation,
        corrected_acceleration_vehicle_mps2=corrected_accel,
        corrected_angular_velocity_vehicle_radps=corrected_gyro,
    )
    phi, process_covariance = discretise_error_dynamics(
        continuous_f,
        noise_mapping,
        continuous_imu_noise_covariance(config.noise),
        delta_time_s,
    )

    propagated_covariance = (
        phi @ prior.covariance @ phi.T + process_covariance
    )

    return PropagationResult(
        disposition=PropagationDisposition.PROPAGATED,
        state=ErrorStateEkfState(
            nominal=propagated_nominal,
            covariance=require_positive_semidefinite(
                propagated_covariance
            ),
        ),
        diagnostics=PropagationDiagnostics(
            delta_time_s=delta_time_s,
            corrected_acceleration_vehicle_mps2=corrected_accel,
            corrected_angular_velocity_vehicle_radps=corrected_gyro,
            acceleration_navigation_enu_mps2=acceleration_enu,
        ),
    )
```

This is the single public propagation function used by the orchestrator:

- calculate actual sample period from timestamps, so phone and 200 Hz external IMUs both work;
- reject impossible timing rather than fabricate motion;
- advance nominal navigation state;
- derive `F` and `G`;
- use `covariance.py` to obtain `Φ` and `Qd`;
- calculate `P⁻ = ΦPΦᵀ + Qd`;
- return diagnostics for replay plots and debugging.

Next should be `measurements.py`: a generic measurement contract plus residual, innovation covariance, Kalman-gain, gating, state injection, and Joseph covariance update.

> yes

<details><summary>2 previous messages</summary>

> Next is `fusion/measurements.py`. It should provide one reusable, auditable EKF update path; GNSS, velocity, NHC, and road-context modules will each supply their own residual, Jacobian, covariance, and gate to it.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/measurements.py`
>
> </details>
</details>

Next: [`measurements.py`](<./src/idr_backend/fusion/measurements.py>).

This file should not contain GNSS, velocity, or NHC-specific equations. It defines the common EKF update protocol. Each measurement builder produces:

- residual: `r = z - h(x̂⁻)`
- Jacobian: `H = ∂h/∂δx`
- measurement covariance: `R`
- NIS gate threshold

```python
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from .covariance import (
    joseph_covariance_update,
    reset_covariance_after_injection,
)
from .state import (
    ERROR_STATE_DIM,
    ErrorStateEkfState,
    inject_nominal_error,
)

Matrix = NDArray[np.float64]
Vector = NDArray[np.float64]

class MeasurementKind(StrEnum):
    """Names used for diagnostics and measurement-specific policy."""

    GNSS_POSITION = "gnss_position"
    GNSS_VELOCITY = "gnss_velocity"
    VELOCITY_MODEL = "velocity_model"
    NON_HOLONOMIC_CONSTRAINT = "non_holonomic_constraint"
    ROAD_CONTEXT_SPEED_PRIOR = "road_context_speed_prior"

class MeasurementDisposition(StrEnum):
    """Whether the update changed the filter state."""

    ACCEPTED = "accepted"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
    INNOVATION_REJECTED = "innovation_rejected"
```

The `kind` is not used for math; it is used for auditability. A replay report should be able to answer “how many GNSS updates were rejected?” or “did road context override the speed model?” The answer should never require reconstructing it from raw logs.

```python
@dataclass(frozen=True, slots=True)
class LinearisedMeasurement:
    """One measurement expressed around the current nominal EKF state.

    The residual convention is fixed:
        residual = observed_value - predicted_value

    The Jacobian maps the 15-state error vector into measurement space.
    """

    timestamp_ns: int
    kind: MeasurementKind

    residual: Vector                 # shape (m,)
    jacobian: Matrix                 # shape (m, 15)
    covariance: Matrix               # R, shape (m, m)

    # Normalized Innovation Squared threshold. Builders choose this from the
    # measurement dimension and desired rejection confidence, e.g. chi-square.
    nis_gate: float
```

The residual direction is important. If all builders use `observed - predicted`, then the correction is always:

`δx = K × residual`

Without one shared convention, GNSS may pull the state in the right direction while a velocity measurement pushes it away.

```python
@dataclass(frozen=True, slots=True)
class MeasurementUpdateTrace:
    """Evidence retained whether an update is accepted or rejected."""

    kind: MeasurementKind
    timestamp_ns: int
    disposition: MeasurementDisposition
    nis: float | None
    nis_gate: float | None
    correction: Vector | None

@dataclass(frozen=True, slots=True)
class MeasurementUpdateResult:
    """The unchanged prior or corrected posterior state plus audit trace."""

    state: ErrorStateEkfState
    trace: MeasurementUpdateTrace
```

A rejected measurement is still valuable information. For example, repeated GNSS rejection during a tunnel confirms blackout mode; repeated road-context rejection may reveal a bad road candidate. Therefore the result returns a trace even when the prior state remains unchanged.

```python
def validate_linearised_measurement(
    measurement: LinearisedMeasurement,
) -> tuple[Vector, Matrix, Matrix]:
    """Validate dimensions, finiteness, symmetry, and positive R covariance."""

    residual = np.asarray(measurement.residual, dtype=float)
    jacobian = np.asarray(measurement.jacobian, dtype=float)
    covariance = np.asarray(measurement.covariance, dtype=float)

    if residual.ndim != 1 or len(residual) == 0:
        raise ValueError("Measurement residual must be a non-empty vector.")

    dimension = len(residual)
    if jacobian.shape != (dimension, ERROR_STATE_DIM):
        raise ValueError(
            f"Measurement Jacobian must have shape ({dimension}, 15)."
        )
    if covariance.shape != (dimension, dimension):
        raise ValueError(
            f"Measurement covariance must have shape ({dimension}, {dimension})."
        )

    if not (
        np.all(np.isfinite(residual))
        and np.all(np.isfinite(jacobian))
        and np.all(np.isfinite(covariance))
        and np.isfinite(measurement.nis_gate)
        and measurement.nis_gate > 0.0
    ):
        raise ValueError("Measurement values, covariance, and gate must be finite.")

    symmetric_covariance = 0.5 * (covariance + covariance.T)

    # R must be positive definite, not merely semidefinite: an EKF must never
    # treat any real observation as perfectly certain or invert a singular S.
    if np.linalg.eigvalsh(symmetric_covariance)[0] <= 0.0:
        raise ValueError("Measurement covariance must be positive definite.")

    return residual, jacobian, symmetric_covariance
```

This prevents a dangerous shortcut: encoding a “hard” non-holonomic constraint with zero uncertainty. Every real-world observation, including “the vehicle should not move sideways,” needs finite uncertainty because turns, phone-mount error, skids, and road banking are real.

```python
def innovation_statistics(
    prior: ErrorStateEkfState,
    residual: Vector,
    jacobian: Matrix,
    measurement_covariance: Matrix,
) -> tuple[Matrix, Matrix, float]:
    """Return innovation covariance S, gain K, and normalized innovation squared."""

    innovation_covariance = (
        jacobian @ prior.covariance @ jacobian.T
        + measurement_covariance
    )
    innovation_covariance = 0.5 * (
        innovation_covariance + innovation_covariance.T
    )

    # Solve linear systems instead of calculating inv(S). Explicit inversion is
    # slower and amplifies numerical error when observations are uncertain.
    solved_residual = np.linalg.solve(innovation_covariance, residual)
    kalman_gain = np.linalg.solve(
        innovation_covariance,
        (prior.covariance @ jacobian.T).T,
    ).T

    nis = float(residual.T @ solved_residual)
    return innovation_covariance, kalman_gain, nis
```

`S = HPHᵀ + R` is the predicted uncertainty of the residual. NIS answers whether the actual residual is plausible under that uncertainty:

- low NIS: observation agrees with state and covariance;
- high NIS: likely GNSS multipath, stale model output, wrong road candidate, or poor calibration.

The gain uses `solve`, never `inverse`.

```python
def apply_linearised_measurement(
    prior: ErrorStateEkfState,
    measurement: LinearisedMeasurement,
) -> MeasurementUpdateResult:
    """Gate and, if credible, apply one asynchronous EKF measurement update."""

    if measurement.timestamp_ns != prior.nominal.timestamp_ns:
        return MeasurementUpdateResult(
            state=prior,
            trace=MeasurementUpdateTrace(
                kind=measurement.kind,
                timestamp_ns=measurement.timestamp_ns,
                disposition=MeasurementDisposition.TIMESTAMP_MISMATCH,
                nis=None,
                nis_gate=measurement.nis_gate,
                correction=None,
            ),
        )

    residual, jacobian, covariance = validate_linearised_measurement(measurement)
    _, gain, nis = innovation_statistics(
        prior,
        residual,
        jacobian,
        covariance,
    )

    if nis > measurement.nis_gate:
        return MeasurementUpdateResult(
            state=prior,
            trace=MeasurementUpdateTrace(
                kind=measurement.kind,
                timestamp_ns=measurement.timestamp_ns,
                disposition=MeasurementDisposition.INNOVATION_REJECTED,
                nis=nis,
                nis_gate=measurement.nis_gate,
                correction=None,
            ),
        )

    correction = gain @ residual
    corrected_nominal = inject_nominal_error(prior.nominal, correction)

    # Joseph form preserves PSD behavior. The following reset converts P from
    # the old local attitude-error coordinates to the corrected nominal frame.
    posterior_covariance = joseph_covariance_update(
        prior.covariance,
        gain,
        jacobian,
        covariance,
    )
    posterior_covariance = reset_covariance_after_injection(
        posterior_covariance,
        correction[6:9],
    )

    posterior = ErrorStateEkfState(
        nominal=corrected_nominal,
        covariance=posterior_covariance,
    )
    return MeasurementUpdateResult(
        state=posterior,
        trace=MeasurementUpdateTrace(
            kind=measurement.kind,
            timestamp_ns=measurement.timestamp_ns,
            disposition=MeasurementDisposition.ACCEPTED,
            nis=nis,
            nis_gate=measurement.nis_gate,
            correction=correction,
        ),
    )
```

The timestamp check is deliberately strict. The orchestrator must first propagate to the observation timestamp; it must not apply a delayed GNSS fix as if it describes the current state. Proper out-of-sequence measurement replay can be added later with a state-history buffer, rather than being silently faked here.

For an accepted measurement, the sequence is always:

1. calculate residual and NIS;
2. reject if the observation is implausible;
3. calculate `δx = Kr`;
4. inject `δx` into nominal state;
5. use Joseph covariance update;
6. reset covariance after attitude injection;
7. record an audit trace.

Next: `constraints.py`, which will build the NHC measurement—lateral and vertical vehicle velocity should be near zero—using this generic update path.

> yes

<details><summary>2 previous messages</summary>

> Next is `fusion/constraints.py`. It will construct the non-holonomic constraint measurement, then call the generic update function rather than implementing EKF algebra again.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/constraints.py`
>
> </details>
</details>

Next: [`constraints.py`](<./src/idr_backend/fusion/constraints.py>).

This file builds the non-holonomic constraint (NHC): a normal wheeled vehicle should have approximately zero lateral and vertical velocity in its own FLU frame. It must never constrain forward velocity; that is the job of IMU propagation, GNSS, and the velocity model.

```python
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from ..sensors.types import VehicleImuSample
from .measurements import (
    LinearisedMeasurement,
    MeasurementKind,
)
from .propagation import (
    skew_symmetric,
    vehicle_to_navigation_rotation,
)
from .state import ATTITUDE, VELOCITY, ErrorStateEkfState

@dataclass(frozen=True, slots=True)
class NonHolonomicConstraintConfig:
    """Policy for using lateral/vertical near-zero velocity constraints."""

    # A weak phone-to-vehicle rotation makes vehicle-left/up meaningless.
    minimum_calibration_confidence: float

    # Moderate turns retain NHC but receive less trust. Beyond this bound, an
    # unmodelled phone offset or aggressive manoeuvre makes NHC unsafe.
    soft_yaw_rate_radps: float
    maximum_yaw_rate_radps: float

    # These are standard deviations, not variances.
    lateral_velocity_std_mps: float
    vertical_velocity_std_mps: float

    # 2D chi-square gate; normally selected outside this module, e.g. 9.21 for
    # a 99% gate. It remains explicit and auditable.
    nis_gate: float

class NonHolonomicDisposition(StrEnum):
    """Why an NHC measurement was or was not constructed."""

    ELIGIBLE = "eligible"
    CALIBRATION_UNTRUSTED = "calibration_untrusted"
    YAW_RATE_TOO_HIGH = "yaw_rate_too_high"
    TIMESTAMP_MISMATCH = "timestamp_mismatch"
```

NHC is a pseudo-measurement, not a fact. Its uncertainty must remain configurable because a phone can move in its mount, a motorcycle can lean, and a vehicle can skid, bank, or pass over bumps. The constraint becomes less trustworthy during turns and is disabled for aggressive yaw.

```python
@dataclass(frozen=True, slots=True)
class NonHolonomicDecision:
    """Either one valid NHC measurement or a recorded reason to skip it."""

    disposition: NonHolonomicDisposition
    measurement: LinearisedMeasurement | None
```

The caller needs to distinguish “no NHC was available” from “NHC was rejected by the EKF innovation gate.” This decision covers pre-update eligibility; `measurements.py` later records whether an eligible NHC measurement was accepted or rejected.

```python
def nhc_is_eligible(
    state: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: NonHolonomicConstraintConfig,
) -> NonHolonomicDisposition:
    """Reject NHC when its vehicle-frame assumption is not credible."""

    if sample.timestamp_ns != state.nominal.timestamp_ns:
        return NonHolonomicDisposition.TIMESTAMP_MISMATCH

    if (
        sample.calibration_confidence
        < config.minimum_calibration_confidence
    ):
        return NonHolonomicDisposition.CALIBRATION_UNTRUSTED

    corrected_yaw_rate_radps = (
        sample.angular_velocity_radps[2]
        - state.nominal.gyroscope_bias_vehicle_radps[2]
    )
    if abs(corrected_yaw_rate_radps) > config.maximum_yaw_rate_radps:
        return NonHolonomicDisposition.YAW_RATE_TOO_HIGH

    return NonHolonomicDisposition.ELIGIBLE
```

The yaw rate must be bias-corrected before applying the limit. A steady gyro bias should not falsely make the system believe that the car is turning. Note that moderate turns remain eligible; their uncertainty is inflated below instead of being abruptly switched off.

```python
def nhc_measurement_covariance(
    *,
    corrected_yaw_rate_radps: float,
    calibration_confidence: float,
    config: NonHolonomicConstraintConfig,
) -> np.ndarray:
    """Return a conservative 2x2 covariance for [lateral, vertical] velocity."""

    turn_scale = 1.0 + (
        abs(corrected_yaw_rate_radps)
        / max(config.soft_yaw_rate_radps, 1e-6)
    ) ** 2

    # As calibration weakens, an apparent side/up velocity could be a frame
    # error. Inflate R instead of claiming an overly precise constraint.
    calibration_scale = 1.0 / max(calibration_confidence, 1e-3)

    lateral_std = (
        config.lateral_velocity_std_mps
        * turn_scale
        * calibration_scale
    )
    vertical_std = (
        config.vertical_velocity_std_mps
        * turn_scale
        * calibration_scale
    )

    return np.diag((lateral_std**2, vertical_std**2))
```

This produces `R_NHC`, not a fixed zero matrix. A tight covariance makes NHC strongly suppress heading and sideways drift. A larger covariance lets the filter respect turning, rough-road motion, and mounting uncertainty.

```python
def build_non_holonomic_measurement(
    state: ErrorStateEkfState,
    sample: VehicleImuSample,
    config: NonHolonomicConstraintConfig,
) -> NonHolonomicDecision:
    """Create z = [0, 0] for vehicle lateral and vertical velocity."""

    disposition = nhc_is_eligible(state, sample, config)
    if disposition is not NonHolonomicDisposition.ELIGIBLE:
        return NonHolonomicDecision(
            disposition=disposition,
            measurement=None,
        )

    rotation_vehicle_to_enu = vehicle_to_navigation_rotation(
        state.nominal.vehicle_to_navigation_wxyz
    )
    rotation_enu_to_vehicle = rotation_vehicle_to_enu.T

    velocity_vehicle = (
        rotation_enu_to_vehicle @ state.nominal.velocity_enu_mps
    )

    # Observation is always zero. The prediction is the nominal vehicle-frame
    # [left, up] velocity, so residual is z - h(x) = -h(x).
    residual = -velocity_vehicle[[1, 2]]

    select_left_and_up = np.asarray(
        (
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    )

    jacobian = np.zeros((2, 15))

    # h(x) = S R(q)^T v_ENU
    # Velocity error changes vehicle-frame velocity directly.
    jacobian[:, VELOCITY] = (
        select_left_and_up @ rotation_enu_to_vehicle
    )

    # With the right-multiplicative vehicle-frame attitude error selected in
    # state.py, attitude error changes vehicle velocity by [v_vehicle]x δθ.
    jacobian[:, ATTITUDE] = (
        select_left_and_up @ skew_symmetric(velocity_vehicle)
    )

    corrected_yaw_rate_radps = (
        sample.angular_velocity_radps[2]
        - state.nominal.gyroscope_bias_vehicle_radps[2]
    )

    return NonHolonomicDecision(
        disposition=NonHolonomicDisposition.ELIGIBLE,
        measurement=LinearisedMeasurement(
            timestamp_ns=sample.timestamp_ns,
            kind=MeasurementKind.NON_HOLONOMIC_CONSTRAINT,
            residual=residual,
            jacobian=jacobian,
            covariance=nhc_measurement_covariance(
                corrected_yaw_rate_radps=corrected_yaw_rate_radps,
                calibration_confidence=sample.calibration_confidence,
                config=config,
            ),
            nis_gate=config.nis_gate,
        ),
    )
```

The predicted observation is:

`h(x̂) = [v_left, v_up]`

The actual pseudo-observation is:

`z = [0, 0]`

So the residual is the negative of the predicted left/up vehicle velocity. The Jacobian lets NHC correct:

- ENU velocity drift directly;
- attitude drift indirectly, because an incorrect heading can make forward movement appear lateral in the vehicle frame.

It intentionally has no forward-velocity row. Enforcing forward velocity toward zero would stop the car in the filter whenever GNSS is absent.

The orchestrator will use it as:

```python
decision = build_non_holonomic_measurement(state, imu_sample, nhc_config)

if decision.measurement is not None:
    result = apply_linearised_measurement(
        state,
        decision.measurement,
    )
    state = result.state
```

Next should be `modes.py`, which decides GNSS-aided, dead-reckoning, and recovery state from GNSS quality and the accepted/rejected update traces.

> yes

<details><summary>2 previous messages</summary>

> Next is `fusion/modes.py`. It should be a small, explicit state machine: GNSS quality and update outcomes decide the navigation mode, while the EKF itself remains responsible for estimating motion.
>
> <details><summary>Explored a file</summary>
>
> - Read `./src/idr_backend/fusion/modes.py`
>
> </details>
</details>

Next: [`modes.py`](<./src/idr_backend/fusion/modes.py>).

This file is a navigation-mode state machine. It does not change coordinates or manually blend positions; accepted EKF measurements already handle that continuously. Its role is to decide whether the system is GNSS-aided, in blackout dead reckoning, or validating GNSS recovery.

```python
from dataclasses import dataclass
from enum import StrEnum

from ..sensors.gnss import GnssFixQuality
from ..sensors.types import NavigationMode
from .measurements import (
    MeasurementDisposition,
    MeasurementKind,
    MeasurementUpdateTrace,
)

@dataclass(frozen=True, slots=True)
class NavigationModeConfig:
    """Explicit timing policy for GNSS loss and return."""

    # A few missing/rejected fixes should not instantly declare a blackout.
    maximum_accepted_gnss_silence_s: float

    # One plausible GNSS update after a tunnel may still be multipath or stale.
    # Require several consecutive accepted position updates before displaying
    # normal GNSS-aided mode again.
    accepted_gnss_updates_for_recovery: int

class ModeTransitionReason(StrEnum):
    """Why the published navigation mode changed or remained meaningful."""

    GNSS_POSITION_ACCEPTED = "gnss_position_accepted"
    GNSS_ACCEPTED_SILENCE_EXCEEDED = "gnss_accepted_silence_exceeded"
    GNSS_QUALITY_UNACCEPTABLE = "gnss_quality_unacceptable"
    GNSS_INNOVATION_REJECTED = "gnss_innovation_rejected"
    GNSS_UNAVAILABLE = "gnss_unavailable"
```

The important threshold is not “time since any GNSS packet.” It is time since an accepted GNSS-position EKF update. A packet can arrive while being unusable because its reported accuracy is poor or because its innovation gate rejects it.

```python
@dataclass(frozen=True, slots=True)
class NavigationModeState:
    """Persistent state of GNSS handoff across fusion cycles."""

    mode: NavigationMode

    # Most recent GNSS position update that passed both receiver-quality checks
    # and the EKF innovation gate.
    last_accepted_gnss_position_timestamp_ns: int | None

    # Set when accepted GNSS support has been absent long enough to declare
    # dead reckoning. It is useful for uncertainty growth and UI messaging.
    blackout_started_timestamp_ns: int | None

    # Counts only consecutive accepted GNSS-position updates during RECOVERY.
    recovery_accepted_position_updates: int = 0

@dataclass(frozen=True, slots=True)
class ModeTransition:
    """One mode decision retained for replay, diagnostics, and UI state."""

    previous_mode: NavigationMode
    current_mode: NavigationMode
    reason: ModeTransitionReason
    blackout_elapsed_s: float | None

@dataclass(frozen=True, slots=True)
class ModeUpdateResult:
    """Updated persistent mode state plus an explainable transition record."""

    state: NavigationModeState
    transition: ModeTransition
```

`NavigationModeState` is not part of the 15-state EKF. It is operational state: the app needs it for status/UI, and the uncertainty engine can use blackout duration as an input, but it must never modify position directly.

```python
def gnss_position_was_accepted(
    trace: MeasurementUpdateTrace | None,
) -> bool:
    """Return true only for a GNSS-position EKF update accepted this cycle."""

    return (
        trace is not None
        and trace.kind is MeasurementKind.GNSS_POSITION
        and trace.disposition is MeasurementDisposition.ACCEPTED
    )
```

This deliberately ignores a merely “good-looking” GNSS fix. GNSS must first pass:

1. receiver-quality validation in `sensors/gnss.py`;
2. construction of a GNSS position measurement;
3. innovation/NIS gating in `measurements.py`.

Only then may it reset the blackout timer.

```python
def current_gnss_reason(
    quality: GnssFixQuality | None,
    trace: MeasurementUpdateTrace | None,
) -> ModeTransitionReason:
    """Describe the best available explanation for missing GNSS assistance."""

    if (
        trace is not None
        and trace.kind is MeasurementKind.GNSS_POSITION
        and trace.disposition is MeasurementDisposition.INNOVATION_REJECTED
    ):
        return ModeTransitionReason.GNSS_INNOVATION_REJECTED

    if quality is None:
        return ModeTransitionReason.GNSS_UNAVAILABLE

    if not quality.position_is_acceptable:
        return ModeTransitionReason.GNSS_QUALITY_UNACCEPTABLE

    # A usable receiver fix may simply not have reached the update boundary yet.
    return ModeTransitionReason.GNSS_UNAVAILABLE
```

This reason is diagnostic only. It should not overwrite the EKF state. A GNSS fix rejected by NIS could mean genuine vehicle motion, multipath, a bad local ENU origin, or an already-underestimated covariance—so replay diagnostics need to preserve that distinction.

```python
def blackout_elapsed_seconds(
    mode_state: NavigationModeState,
    timestamp_ns: int,
) -> float | None:
    """Return dead-reckoning duration when a declared blackout is active."""

    if mode_state.blackout_started_timestamp_ns is None:
        return None

    return max(
        0.0,
        (timestamp_ns - mode_state.blackout_started_timestamp_ns) * 1e-9,
    )
```

The uncertainty model will eventually use this value. Longer GNSS outages should normally widen velocity and position uncertainty even if the velocity estimate remains numerically plausible.

```python
def advance_navigation_mode(
    *,
    prior: NavigationModeState,
    timestamp_ns: int,
    gnss_quality: GnssFixQuality | None,
    gnss_position_trace: MeasurementUpdateTrace | None,
    config: NavigationModeConfig,
) -> ModeUpdateResult:
    """Advance GNSS-aided, dead-reckoning, and recovery mode safely."""

    if timestamp_ns < 0:
        raise ValueError("timestamp_ns must be non-negative.")
    if config.maximum_accepted_gnss_silence_s <= 0.0:
        raise ValueError("maximum_accepted_gnss_silence_s must be positive.")
    if config.accepted_gnss_updates_for_recovery < 1:
        raise ValueError("accepted_gnss_updates_for_recovery must be at least one.")

    if gnss_position_was_accepted(gnss_position_trace):
        if prior.mode is NavigationMode.DEAD_RECKONING:
            next_mode = NavigationMode.RECOVERY
            recovery_count = 1
            blackout_started = prior.blackout_started_timestamp_ns

        elif prior.mode is NavigationMode.RECOVERY:
            recovery_count = prior.recovery_accepted_position_updates + 1
            next_mode = (
                NavigationMode.GNSS_AIDED
                if recovery_count >= config.accepted_gnss_updates_for_recovery
                else NavigationMode.RECOVERY
            )
            blackout_started = (
                None
                if next_mode is NavigationMode.GNSS_AIDED
                else prior.blackout_started_timestamp_ns
            )

        else:
            next_mode = NavigationMode.GNSS_AIDED
            recovery_count = 0
            blackout_started = None

        next_state = NavigationModeState(
            mode=next_mode,
            last_accepted_gnss_position_timestamp_ns=timestamp_ns,
            blackout_started_timestamp_ns=blackout_started,
            recovery_accepted_position_updates=recovery_count,
        )
        return ModeUpdateResult(
            state=next_state,
            transition=ModeTransition(
                previous_mode=prior.mode,
                current_mode=next_mode,
                reason=ModeTransitionReason.GNSS_POSITION_ACCEPTED,
                blackout_elapsed_s=blackout_elapsed_seconds(
                    next_state,
                    timestamp_ns,
                ),
            ),
        )

    last_accepted = prior.last_accepted_gnss_position_timestamp_ns
    silence_s = (
        None
        if last_accepted is None
        else (timestamp_ns - last_accepted) * 1e-9
    )

    if (
        silence_s is not None
        and silence_s > config.maximum_accepted_gnss_silence_s
    ):
        blackout_started = (
            prior.blackout_started_timestamp_ns
            if prior.blackout_started_timestamp_ns is not None
            else timestamp_ns
        )
        next_state = NavigationModeState(
            mode=NavigationMode.DEAD_RECKONING,
            last_accepted_gnss_position_timestamp_ns=last_accepted,
            blackout_started_timestamp_ns=blackout_started,
            recovery_accepted_position_updates=0,
        )
        return ModeUpdateResult(
            state=next_state,
            transition=ModeTransition(
                previous_mode=prior.mode,
                current_mode=NavigationMode.DEAD_RECKONING,
                reason=ModeTransitionReason.GNSS_ACCEPTED_SILENCE_EXCEEDED,
                blackout_elapsed_s=blackout_elapsed_seconds(
                    next_state,
                    timestamp_ns,
                ),
            ),
        )

    return ModeUpdateResult(
        state=prior,
        transition=ModeTransition(
            previous_mode=prior.mode,
            current_mode=prior.mode,
            reason=current_gnss_reason(
                gnss_quality,
                gnss_position_trace,
            ),
            blackout_elapsed_s=blackout_elapsed_seconds(
                prior,
                timestamp_ns,
            ),
        ),
    )
```

The key transitions are:

- `GNSS_AIDED → DEAD_RECKONING`: accepted GNSS silence exceeds the configured tolerance.
- `DEAD_RECKONING → RECOVERY`: one GNSS position measurement passes all checks.
- `RECOVERY → GNSS_AIDED`: several consecutive accepted GNSS updates establish that reacquisition is genuine.
- `RECOVERY → DEAD_RECKONING`: GNSS assistance disappears long enough again.

A GNSS return does not create a coordinate jump. The accepted GNSS measurement changes the EKF through its covariance-weighted update; mode only describes confidence and handoff status.

Next should be `state` initialization wiring or, if staying in the fusion folder order, `orchestrator.py` to define the per-sample execution sequence.

> what about ipynb cells for making the uncertainity engine model, check the docs how it is to be made, and do we hve ot wait for the velocity predictor to be completed for it or can some code be resued but independent model or diff from scratch anyway?

<details><summary>2 previous messages</summary>

> I’ll check the uncertainty-specific architecture notes and only the uncertainty package/script/config files—not the rest of the repository. The key question is whether it should be a joint heteroscedastic head on the velocity model or an independently trained post-hoc calibrator.
>
> <details><summary>Explored 7 files, ran 2 commands</summary>
>
> - Ran `Get-ChildItem src\idr_backend\uncertainty -File | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize`
>
> - Ran `rg -n -i "uncertainty|heteroscedastic|gaussian nll|differentiable ekf|covariance|velocity" docs configs scripts src\idr_backend\uncertainty`
>
> <details><summary>Explored 7 files</summary>
>
> - Read `./src/idr_backend/uncertainty/model.py`
> - Read `./src/idr_backend/uncertainty/training.py`
> - Read `./src/idr_backend/uncertainty/features.py`
> - Read `./src/idr_backend/uncertainty/calibration.py`
> - Read `./src/idr_backend/uncertainty/heuristics.py`
> - Read `./scripts/train_uncertainty.py`
> - Read `./configs/training.toml`
>
> </details>
>
> </details>
</details>

You can build the uncertainty engine in parallel, but its learned model is not truly independent of velocity prediction.

The docs specify:

- Tier 1: deterministic heuristic variance fallback.
- Tier 2: heteroscedastic uncertainty—predict speed variance with Gaussian NLL.
- Tier 3: differentiable EKF tuning, explicitly a stretch goal.

The repository architecture also treats uncertainty as a separate engine: it receives a `VelocityObservation` and returns an `UncertaintyEstimate` (bounded speed variance), rather than owning velocity prediction. All uncertainty files are currently placeholders.

Recommended path: build it as a separate post-hoc uncertainty model first. Reuse the velocity experiment’s replay, blackout examples, journey-grouped folds, calibration confidence, IMU windows, and model outputs—but train a new small model to predict variance, not speed.

Notebook cell sequence:

1. Define uncertainty config: variance floor/ceiling, split policy, Gaussian-NLL objective.
2. Reuse `replay_clean_journey()` and `build_blackout_dataset()`.
3. Generate out-of-fold velocity predictions on development journeys.
4. Build blackout-safe features: predicted speed, elapsed blackout time, integrated-vs-predicted disagreement, IMU variance/jerk/yaw, calibration confidence, quality flags, device/model ID.
5. Train a variance model with
   `0.5 × (log(σ²) + residual² / σ²)`.
6. Calibrate predicted variance on a separate held-out development split.
7. Evaluate reliability: NLL, 68/95% coverage, standardized-residual distribution, sharpness, and per-horizon coverage.
8. Run the frozen test set once, after model choice is fixed.

Do not train it on the existing `frozen_test_predictions.csv`; that would contaminate the final test. The current artifacts contain test predictions and CV summaries, but not saved out-of-fold development predictions—creating those is the first required notebook output.

So: start Tier 1, the data/features, OOF prediction generation, calibration, and evaluation now. For the final learned model, wait until the velocity model architecture/checkpoint is stable enough to produce representative predictions. The current residual GRU’s mean error still misses the blackout targets; uncertainty can correctly downweight it, but it cannot repair that mean-error problem.

The later Tier-2 alternative is to modify the GRU/CNN to output both `mean_speed` and `log_variance` jointly. That is more aligned with the architecture brief, but it couples uncertainty training to every velocity-model retrain.

> or lets first just fill the [pipeline](src/idr_backend/pipeline/) folder now that youve given all files of [fusion](src/idr_backend/fusion/) , if we know that major changes wont be have to made later on in them

<details><summary>2 previous messages</summary>

> Yes—with one boundary: the pipeline can be implemented now as orchestration and lifecycle code, but it should depend only on stable contracts, not on unfinished GNSS/velocity/road-context internals. I’ll inspect the three existing pipeline placeholders to choose the implementation order; I won’t change them yet.
>
> <details><summary>Explored 4 files</summary>
>
> - Read `./src/idr_backend/pipeline/orchestrator.py`
> - Read `./src/idr_backend/pipeline/runtime.py`
> - Read `./src/idr_backend/pipeline/feedback.py`
> - Read `./src/idr_backend/pipeline/__init__.py`
>
> </details>
</details>

Yes—start the pipeline folder now, but make it contract-driven so only adapters change later.

The low-change order is:

1. [`runtime.py`](<./src/idr_backend/pipeline/runtime.py>) — lifecycle states, diagnostics, latency/backpressure policy, and one owner for live navigation state.
2. [`feedback.py`](<./src/idr_backend/pipeline/feedback.py>) — persist only prior-cycle map-match belief/candidate provenance, preventing the road-context/HMM circular dependency.
3. [`orchestrator.py`](<./src/idr_backend/pipeline/orchestrator.py>) — event order: preprocess → propagate → optional updates → NHC → map feedback → publish.

These contracts are already stable: `GnssFix`, `VelocityObservation`, `UncertaintyEstimate`, `RoadContextPrior`, `NavigationEstimate`, preprocessing output, and the EKF state/update API.

The parts likely to evolve are only providers/adapters: the final velocity checkpoint, learned uncertainty model, GNSS measurement builder, and exact HMM-belief representation. The orchestrator should receive their observations through optional interfaces, never call a GRU/CNN directly.

So yes: build the pipeline now. Start with `runtime.py`; it will not need major redesign later if we keep model-specific logic outside it.

> yes give it, same drill which we were following

Start [`runtime.py`](<./src/idr_backend/pipeline/runtime.py>). This file owns lifecycle, atomic cycle commits, bounded diagnostics, and backpressure policy. It does not decide fusion equations or run models.

```python
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter_ns

from ..fusion.measurements import MeasurementUpdateTrace
from ..fusion.modes import NavigationModeState
from ..fusion.propagation import PropagationDisposition
from ..fusion.state import ErrorStateEkfState
from ..sensors.types import NavigationEstimate
```

The runtime may depend on completed fusion contracts, but fusion must never depend on pipeline code. That keeps the EKF reusable for offline replay and avoids circular imports.

```python
class RuntimePhase(StrEnum):
    """Backend execution lifecycle, separate from GNSS navigation mode."""

    COLD = "cold"
    WARMING_UP = "warming_up"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class NavigationRuntimeConfig:
    """Operational limits, not sensor-fusion tuning parameters."""

    maximum_pending_events: int
    cycle_latency_budget_ms: float
    late_cycles_before_degraded: int
    trace_history_capacity: int
```

`RuntimePhase` is distinct from `NavigationMode`:

- `NavigationMode.DEAD_RECKONING` means GNSS is unavailable but fusion still runs normally.
- `RuntimePhase.DEGRADED` means an operational problem exists: timing gaps, repeated late cycles, queue overload, or a recoverable component failure.

That separation prevents a normal tunnel blackout from being reported as a runtime failure.

```python
@dataclass(frozen=True, slots=True)
class CycleToken:
    """Uniquely identifies one serial fusion cycle being processed."""

    sequence_number: int
    timestamp_ns: int
    started_performance_ns: int

@dataclass(frozen=True, slots=True)
class CycleOutcome:
    """Everything produced by one successfully processed cycle."""

    filter_state: ErrorStateEkfState
    mode_state: NavigationModeState
    navigation_estimate: NavigationEstimate

    propagation_disposition: PropagationDisposition
    measurement_traces: tuple[MeasurementUpdateTrace, ...]

@dataclass(frozen=True, slots=True)
class RuntimeTrace:
    """Privacy-safe, bounded diagnostic record without raw sensor values."""

    sequence_number: int
    timestamp_ns: int
    processing_latency_ms: float
    runtime_phase: RuntimePhase
    propagation_disposition: PropagationDisposition
    accepted_measurements: int
    rejected_measurements: int
```

`CycleToken` prevents accidental concurrent or double commits. `CycleOutcome` groups every component result before publishing; either a complete cycle becomes visible or the previous complete state remains visible.

`RuntimeTrace` must avoid raw latitude, longitude, IMU values, and model-window data. It records enough operational evidence for replay and performance debugging without becoming a location-history store.

```python
@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Last atomically committed runtime state."""

    phase: RuntimePhase
    last_cycle_timestamp_ns: int | None
    cycle_count: int
    late_cycle_streak: int

    filter_state: ErrorStateEkfState | None
    mode_state: NavigationModeState | None
    navigation_estimate: NavigationEstimate | None
```

The rest of the system reads this snapshot only after `commit_cycle()`. It must never see a state where propagation has happened but GNSS/NHC updates or map matching have not yet completed.

```python
def has_queue_capacity(
    pending_event_count: int,
    config: NavigationRuntimeConfig,
) -> bool:
    """Return whether the orchestrator may accept one more source event."""

    if pending_event_count < 0:
        raise ValueError("pending_event_count must not be negative.")
    if config.maximum_pending_events < 1:
        raise ValueError("maximum_pending_events must be at least one.")

    return pending_event_count < config.maximum_pending_events
```

The runtime does not silently discard IMU samples. The later orchestrator checks this before accepting a callback/event. If capacity is exhausted, it records backpressure and enters a controlled recovery path rather than inventing missing motion.

```python
class NavigationRuntime:
    """Single-owner lifecycle and atomic publication boundary."""

    def __init__(self, config: NavigationRuntimeConfig) -> None:
        if config.cycle_latency_budget_ms <= 0.0:
            raise ValueError("cycle_latency_budget_ms must be positive.")
        if config.late_cycles_before_degraded < 1:
            raise ValueError("late_cycles_before_degraded must be at least one.")
        if config.trace_history_capacity < 1:
            raise ValueError("trace_history_capacity must be at least one.")

        self._config = config
        self._phase = RuntimePhase.COLD
        self._snapshot = RuntimeSnapshot(
            phase=RuntimePhase.COLD,
            last_cycle_timestamp_ns=None,
            cycle_count=0,
            late_cycle_streak=0,
            filter_state=None,
            mode_state=None,
            navigation_estimate=None,
        )
        self._active_cycle: CycleToken | None = None
        self._traces: deque[RuntimeTrace] = deque(
            maxlen=config.trace_history_capacity
        )
```

One runtime instance owns one chronological navigation session: one phone or external IMU stream, its corresponding EKF, mode state, and map-match feedback. Do not share one instance across vehicles or parallel sensor sessions.

```python
    def start(self) -> RuntimeSnapshot:
        """Enter warm-up while preprocessing gathers calibration/GNSS evidence."""

        if self._phase is not RuntimePhase.COLD:
            raise RuntimeError("Runtime can only start from COLD.")

        self._phase = RuntimePhase.WARMING_UP
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=None,
            cycle_count=0,
            late_cycle_streak=0,
            filter_state=None,
            mode_state=None,
            navigation_estimate=None,
        )
        return self._snapshot
```

Warm-up exists because the system must not publish fabricated navigation before it has enough calibration and GNSS evidence to initialize an honest EKF covariance. Preprocessing may run during warm-up, but there is no `NavigationEstimate` yet.

```python
    def begin_cycle(self, timestamp_ns: int) -> CycleToken:
        """Reserve exactly one monotonic IMU-driven fusion cycle."""

        if self._phase in {
            RuntimePhase.COLD,
            RuntimePhase.STOPPED,
            RuntimePhase.FAILED,
        }:
            raise RuntimeError(f"Cannot process events while {self._phase}.")
        if self._active_cycle is not None:
            raise RuntimeError("Previous cycle has not been committed or aborted.")

        previous_timestamp = self._snapshot.last_cycle_timestamp_ns
        if (
            previous_timestamp is not None
            and timestamp_ns <= previous_timestamp
        ):
            raise ValueError("Pipeline cycle timestamps must be strictly increasing.")

        token = CycleToken(
            sequence_number=self._snapshot.cycle_count + 1,
            timestamp_ns=timestamp_ns,
            started_performance_ns=perf_counter_ns(),
        )
        self._active_cycle = token
        return token
```

The pipeline is serial by timestamp, even if phone callbacks arrive on different threads. GNSS, velocity, NHC, and road-context observations with the same timestamp are consumed inside this one IMU-driven cycle; they do not open independent cycles.

```python
    def commit_cycle(
        self,
        token: CycleToken,
        outcome: CycleOutcome,
    ) -> RuntimeSnapshot:
        """Atomically publish a complete fusion result and bounded diagnostics."""

        if token != self._active_cycle:
            raise RuntimeError("Only the active cycle token may be committed.")
        if outcome.filter_state.nominal.timestamp_ns != token.timestamp_ns:
            raise ValueError("Filter state timestamp does not match cycle token.")
        if outcome.navigation_estimate.timestamp_ns != token.timestamp_ns:
            raise ValueError("Published estimate timestamp does not match cycle token.")
        if outcome.navigation_estimate.mode != outcome.mode_state.mode:
            raise ValueError("Published estimate and mode state disagree.")

        latency_ms = (
            perf_counter_ns() - token.started_performance_ns
        ) / 1_000_000.0

        late_streak = (
            self._snapshot.late_cycle_streak + 1
            if latency_ms > self._config.cycle_latency_budget_ms
            else 0
        )
        next_phase = (
            RuntimePhase.DEGRADED
            if late_streak >= self._config.late_cycles_before_degraded
            else RuntimePhase.RUNNING
        )

        accepted = sum(
            trace.disposition.value == "accepted"
            for trace in outcome.measurement_traces
        )
        rejected = sum(
            trace.disposition.value != "accepted"
            for trace in outcome.measurement_traces
        )

        self._snapshot = RuntimeSnapshot(
            phase=next_phase,
            last_cycle_timestamp_ns=token.timestamp_ns,
            cycle_count=token.sequence_number,
            late_cycle_streak=late_streak,
            filter_state=outcome.filter_state,
            mode_state=outcome.mode_state,
            navigation_estimate=outcome.navigation_estimate,
        )
        self._phase = next_phase
        self._traces.append(
            RuntimeTrace(
                sequence_number=token.sequence_number,
                timestamp_ns=token.timestamp_ns,
                processing_latency_ms=latency_ms,
                runtime_phase=next_phase,
                propagation_disposition=outcome.propagation_disposition,
                accepted_measurements=accepted,
                rejected_measurements=rejected,
            )
        )
        self._active_cycle = None
        return self._snapshot
```

This is the only method allowed to publish a new state. It validates cross-component consistency first, then records latency and measurement outcomes, then commits all state together.

A late cycle does not discard valid navigation. Repeated lateness moves the runtime to `DEGRADED`, allowing the UI and later resource policy to react without corrupting the EKF.

```python
    def abort_cycle(self, token: CycleToken, reason: str) -> RuntimeSnapshot:
        """Discard incomplete work while preserving the last complete estimate."""

        if token != self._active_cycle:
            raise RuntimeError("Only the active cycle token may be aborted.")
        if not reason.strip():
            raise ValueError("A non-empty abort reason is required.")

        self._active_cycle = None
        self._phase = RuntimePhase.DEGRADED
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=self._snapshot.last_cycle_timestamp_ns,
            cycle_count=self._snapshot.cycle_count,
            late_cycle_streak=self._snapshot.late_cycle_streak,
            filter_state=self._snapshot.filter_state,
            mode_state=self._snapshot.mode_state,
            navigation_estimate=self._snapshot.navigation_estimate,
        )
        return self._snapshot
```

If propagation encounters a timing gap or an optional component throws a recoverable error, abort the incomplete cycle. The last committed navigation estimate remains available; partial state never leaks out.

```python
    def stop(self) -> RuntimeSnapshot:
        """End the session after all active work has completed or been aborted."""

        if self._active_cycle is not None:
            raise RuntimeError("Abort or commit the active cycle before stopping.")

        self._phase = RuntimePhase.STOPPED
        self._snapshot = RuntimeSnapshot(
            phase=self._phase,
            last_cycle_timestamp_ns=self._snapshot.last_cycle_timestamp_ns,
            cycle_count=self._snapshot.cycle_count,
            late_cycle_streak=self._snapshot.late_cycle_streak,
            filter_state=self._snapshot.filter_state,
            mode_state=self._snapshot.mode_state,
            navigation_estimate=self._snapshot.navigation_estimate,
        )
        return self._snapshot
```

Stopping does not erase the final snapshot. That supports clean shutdown diagnostics and replay comparison, while a new physical navigation session must create a new runtime instance.

Next: `feedback.py`, which will keep only the previous completed map-match belief and candidate provenance for the following cycle’s road-context engine.

> yes

Next: [`feedback.py`](<./src/idr_backend/pipeline/feedback.py>).

This file stores the completed HMM road belief from cycle `t` and makes it available only to cycle `t+1`. It does not run Viterbi, generate road candidates, or calculate road-context speed; that keeps the feedback loop explicit and prevents same-cycle circular logic.

```python
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from ..sensors.types import RoadCandidate

@dataclass(frozen=True, slots=True)
class FeedbackConfig:
    """Safety policy for reusing a prior map-match belief."""

    # A belief that has not been refreshed is unsafe after this age.
    maximum_feedback_age_s: float

    # Low-confidence HMM output must not steer road-context priors.
    minimum_map_match_confidence: float
```

The feedback age matters when map matching stalls, graph coverage disappears, or the pipeline is overloaded. Road context may use the last good belief briefly, but it must not continue treating an old road as current indefinitely.

```python
@dataclass(frozen=True, slots=True)
class CandidateBelief:
    """One road candidate and its normalized probability after HMM scoring."""

    candidate: RoadCandidate
    probability: float

@dataclass(frozen=True, slots=True)
class MapMatchFeedback:
    """Completed, prior-cycle HMM result safe to expose to road context."""

    timestamp_ns: int
    graph_id: str

    # Keep only a compact posterior, not the full Viterbi trellis/history.
    candidate_beliefs: tuple[CandidateBelief, ...]

    selected_candidate_id: str | None
    map_match_confidence: float
```

This is deliberately smaller than the map matcher’s internal state. The feedback layer needs only enough information for the next cycle to:

- generate plausible next road candidates;
- construct road-context features for those roads;
- explain which prior road hypothesis was used.

The full HMM trellis remains private to `map_matching/`.

```python
class FeedbackDisposition(StrEnum):
    """Whether a prior belief may be used for the current cycle."""

    AVAILABLE = "available"
    ABSENT = "absent"
    STALE = "stale"
    LOW_CONFIDENCE = "low_confidence"
    GRAPH_MISMATCH = "graph_mismatch"
    SAME_CYCLE_OR_FUTURE = "same_cycle_or_future"

@dataclass(frozen=True, slots=True)
class FeedbackLookup:
    """Result of requesting a prior belief for one new fusion cycle."""

    disposition: FeedbackDisposition
    feedback: MapMatchFeedback | None
    age_s: float | None
```

A caller must receive a reason when road feedback is absent. `ABSENT` is normal at startup; `STALE`, `LOW_CONFIDENCE`, and `GRAPH_MISMATCH` are diagnostic evidence that should appear in replay logs and should stop road context from pretending it knows the vehicle’s road.

```python
def validate_map_match_feedback(
    feedback: MapMatchFeedback,
) -> None:
    """Reject malformed or internally inconsistent HMM output."""

    if feedback.timestamp_ns < 0:
        raise ValueError("Feedback timestamp must be non-negative.")
    if not feedback.graph_id.strip():
        raise ValueError("Feedback graph_id must not be blank.")
    if not (
        isfinite(feedback.map_match_confidence)
        and 0.0 <= feedback.map_match_confidence <= 1.0
    ):
        raise ValueError("Map-match confidence must lie between zero and one.")
    if not feedback.candidate_beliefs:
        raise ValueError("Feedback must contain at least one candidate belief.")

    candidate_ids: set[str] = set()
    probability_sum = 0.0

    for belief in feedback.candidate_beliefs:
        candidate = belief.candidate

        if candidate.timestamp_ns != feedback.timestamp_ns:
            raise ValueError("Candidate timestamp must match feedback timestamp.")
        if candidate.graph_id != feedback.graph_id:
            raise ValueError("All candidates must belong to feedback graph_id.")
        if candidate.candidate_id in candidate_ids:
            raise ValueError("Candidate identifiers must be unique.")
        if not isfinite(belief.probability) or belief.probability < 0.0:
            raise ValueError("Candidate probabilities must be finite and non-negative.")

        candidate_ids.add(candidate.candidate_id)
        probability_sum += belief.probability

    if not abs(probability_sum - 1.0) <= 1e-6:
        raise ValueError("Candidate probabilities must sum to one.")

    if (
        feedback.selected_candidate_id is not None
        and feedback.selected_candidate_id not in candidate_ids
    ):
        raise ValueError("Selected candidate must appear in candidate beliefs.")
```

The map matcher must normalize its posterior before publishing feedback. Road context should not infer confidence from raw Viterbi scores because their scale changes with window length and graph topology.

The timestamp equality requirement is especially important: candidates and probabilities must describe the same map-match cycle.

```python
class MapMatchFeedbackStore:
    """One-session store for the latest completed and usable HMM belief."""

    def __init__(self, config: FeedbackConfig) -> None:
        if config.maximum_feedback_age_s <= 0.0:
            raise ValueError("maximum_feedback_age_s must be positive.")
        if not (
            0.0
            <= config.minimum_map_match_confidence
            <= 1.0
        ):
            raise ValueError(
                "minimum_map_match_confidence must be between zero and one."
            )

        self._config = config
        self._latest: MapMatchFeedback | None = None
```

One store belongs to one `NavigationRuntime` session. It must be cleared between drives, when switching offline map extracts, or when map matching loses graph coverage.

```python
    def publish_completed_match(
        self,
        feedback: MapMatchFeedback,
    ) -> None:
        """Commit HMM output after its entire fusion/map-match cycle completes."""

        validate_map_match_feedback(feedback)

        if (
            self._latest is not None
            and feedback.timestamp_ns <= self._latest.timestamp_ns
        ):
            raise ValueError(
                "Map-match feedback must be committed in strictly increasing time."
            )

        # A weak match is retained nowhere. The next cycle should work without
        # road-context assistance rather than inherit a likely wrong road.
        if (
            feedback.map_match_confidence
            < self._config.minimum_map_match_confidence
        ):
            self._latest = None
            return

        self._latest = feedback
```

This method is called only at the end of an accepted cycle, after HMM scoring is complete. It must never be called before road-context construction in that same cycle.

A low-confidence match clears feedback rather than publishing a questionable selected road. The deterministic EKF remains operational without road context.

```python
    def prior_for_cycle(
        self,
        *,
        cycle_timestamp_ns: int,
        graph_id: str,
    ) -> FeedbackLookup:
        """Return only belief created before the current cycle."""

        if self._latest is None:
            return FeedbackLookup(
                disposition=FeedbackDisposition.ABSENT,
                feedback=None,
                age_s=None,
            )

        if self._latest.graph_id != graph_id:
            return FeedbackLookup(
                disposition=FeedbackDisposition.GRAPH_MISMATCH,
                feedback=None,
                age_s=None,
            )

        if self._latest.timestamp_ns >= cycle_timestamp_ns:
            return FeedbackLookup(
                disposition=FeedbackDisposition.SAME_CYCLE_OR_FUTURE,
                feedback=None,
                age_s=None,
            )

        age_s = (
            cycle_timestamp_ns - self._latest.timestamp_ns
        ) * 1e-9

        if age_s > self._config.maximum_feedback_age_s:
            return FeedbackLookup(
                disposition=FeedbackDisposition.STALE,
                feedback=None,
                age_s=age_s,
            )

        return FeedbackLookup(
            disposition=FeedbackDisposition.AVAILABLE,
            feedback=self._latest,
            age_s=age_s,
        )
```

This is the anti-circular-dependency guard.

At cycle `t`, the orchestrator performs:

```python
prior_feedback = feedback_store.prior_for_cycle(
    cycle_timestamp_ns=imu_sample.timestamp_ns,
    graph_id=active_graph_id,
)

# Use prior_feedback.feedback only for candidates and road context.
# Run fusion and current HMM afterward.
# Then publish the current HMM result for cycle t + 1.
```

So road context can influence the EKF at cycle `t`, but it is based only on map-match evidence from an earlier cycle—not on a road match that was itself affected by that same road-context update.

```python
    def reset(self) -> None:
        """Forget map feedback after graph loss, remount/session reset, or reset."""

        self._latest = None
```

Call `reset()` when:

- the active offline map graph changes;
- no road candidates are reachable;
- the map matcher resets its HMM history;
- runtime starts a new driving session;
- a confirmed state reset invalidates road continuity.

Next is `orchestrator.py`, which will use `NavigationRuntime`, `MapMatchFeedbackStore`, preprocessing, propagation, optional measurement updates, and final map-match publication in one strict timestamp order.

> yes

Next: [`orchestrator.py`](<./src/idr_backend/pipeline/orchestrator.py>).

This is the only file that knows full cycle order. It must orchestrate components, never duplicate fusion equations or call a GRU/CNN implementation directly.

```python
from dataclasses import dataclass
from typing import Protocol

from ..fusion.constraints import build_non_holonomic_measurement
from ..fusion.measurements import (
    LinearisedMeasurement,
    MeasurementUpdateTrace,
    apply_linearised_measurement,
)
from ..fusion.modes import advance_navigation_mode
from ..fusion.propagation import propagate_ekf
from ..fusion.state import ErrorStateEkfState
from ..sensors.preprocessing import (
    DeterministicImuPreprocessor,
    PreprocessedImuResult,
    PreprocessingDisposition,
)
from ..sensors.types import (
    GnssFix,
    NavigationEstimate,
    VehicleImuSample,
)
from .feedback import (
    MapMatchFeedback,
    MapMatchFeedbackStore,
)
from .runtime import (
    CycleOutcome,
    NavigationRuntime,
    RuntimeSnapshot,
)
```

The orchestrator imports public component functions only. It never reaches into a model’s internal tensors, map matcher trellis, preprocessor buffers, or EKF covariance internals.

```python
class MeasurementProvider(Protocol):
    """Optional source that creates EKF measurements but never mutates EKF state."""

    def measurements_for_cycle(
        self,
        *,
        timestamp_ns: int,
        state: ErrorStateEkfState,
        prior_map_feedback: MapMatchFeedback | None,
    ) -> tuple[LinearisedMeasurement, ...]:
        """Return zero or more timestamp-matched measurement updates."""

class MapMatcher(Protocol):
    """Incremental map matcher invoked only after current-cycle fusion."""

    def update_after_fusion(
        self,
        *,
        timestamp_ns: int,
        state: ErrorStateEkfState,
    ) -> MapMatchFeedback | None:
        """Return completed HMM feedback for the next pipeline cycle."""
```

A velocity provider, uncertainty provider, GNSS provider, and road-context provider should all implement the same `MeasurementProvider` boundary.

That means:

- a missing velocity model returns no measurement;
- an unavailable road-context model returns no measurement;
- an uncertainty model affects the velocity measurement’s `R`, not the EKF directly;
- the EKF remains deterministic and operational if every optional provider is absent.

```python
@dataclass(frozen=True, slots=True)
class PipelineDependencies:
    """Injected components; model implementations remain outside orchestration."""

    preprocessor: DeterministicImuPreprocessor
    runtime: NavigationRuntime
    feedback_store: MapMatchFeedbackStore

    gnss_measurements: MeasurementProvider
    velocity_measurements: MeasurementProvider
    road_context_measurements: MeasurementProvider
    map_matcher: MapMatcher
```

Dependency injection is what prevents major rewrites later. The final GRU, uncertainty model, ONNX runtime, road-context model, and HMM implementation can all change behind these interfaces. The orchestrator’s timestamp order remains stable.

```python
def apply_measurements_in_order(
    state: ErrorStateEkfState,
    measurements: tuple[LinearisedMeasurement, ...],
) -> tuple[ErrorStateEkfState, tuple[MeasurementUpdateTrace, ...]]:
    """Apply one deterministic sequence of optional EKF measurements."""

    current_state = state
    traces: list[MeasurementUpdateTrace] = []

    for measurement in measurements:
        update = apply_linearised_measurement(
            current_state,
            measurement,
        )
        current_state = update.state
        traces.append(update.trace)

    return current_state, tuple(traces)
```

Measurement order is a design decision and must be visible in one place. The recommended cycle order is:

1. GNSS position/velocity;
2. external velocity observation with learned or heuristic covariance;
3. NHC;
4. road-context speed prior.

Each accepted update changes the nominal state and covariance before the next update. A rejected observation records a trace but does not block later observations.

```python
def build_navigation_estimate(
    *,
    state: ErrorStateEkfState,
    mode_state,
    map_feedback: MapMatchFeedback | None,
) -> NavigationEstimate:
    """Convert internal EKF state plus optional road match into public output."""

    covariance = state.covariance

    matched_edge_id: str | None = None
    map_match_confidence: float | None = None

    if (
        map_feedback is not None
        and map_feedback.selected_candidate_id is not None
    ):
        selected = next(
            belief.candidate
            for belief in map_feedback.candidate_beliefs
            if belief.candidate.candidate_id
            == map_feedback.selected_candidate_id
        )
        matched_edge_id = selected.edge_id
        map_match_confidence = map_feedback.map_match_confidence

    return NavigationEstimate(
        timestamp_ns=state.nominal.timestamp_ns,
        mode=mode_state.mode,
        position_enu_m=tuple(state.nominal.position_enu_m),
        velocity_enu_mps=tuple(state.nominal.velocity_enu_mps),
        vehicle_to_navigation_wxyz=(
            state.nominal.vehicle_to_navigation_wxyz
        ),
        position_covariance_enu_m2=tuple(
            tuple(float(value) for value in row)
            for row in covariance[0:3, 0:3]
        ),
        velocity_covariance_enu_m2ps2=tuple(
            tuple(float(value) for value in row)
            for row in covariance[3:6, 3:6]
        ),
        # Vehicle-FLU z-axis rotation is yaw/heading under the selected error
        # convention from state.py.
        heading_variance_rad2=float(covariance[8, 8]),
        matched_road_edge_id=matched_edge_id,
        map_match_confidence=map_match_confidence,
    )
```

This is the only conversion from internal EKF state to public output. It exposes covariance summaries, not the complete 15×15 matrix. The HMM road match remains optional: no map feedback means `None`, not a fabricated road identifier.

```python
class NavigationPipeline:
    """Serial causal pipeline for one physical driving session."""

    def __init__(self, dependencies: PipelineDependencies) -> None:
        self._deps = dependencies

    def push_gnss_fix(self, fix: GnssFix) -> None:
        """Give GNSS to preprocessing and the GNSS measurement provider."""

        quality = self._deps.preprocessor.push_gnss_fix(fix)

        # The concrete GNSS provider will own its timestamp-ordered buffer and
        # later construct an ENU EKF measurement at the matching IMU cycle.
        ingest = getattr(self._deps.gnss_measurements, "push_gnss_fix", None)
        if ingest is not None:
            ingest(fix, quality)
```

GNSS serves two independent roles:

- preprocessing uses it for calibration evidence;
- fusion uses it later as a position/velocity observation.

Both receive the same original fix and quality decision. The pipeline never invents GNSS during a blackout.

```python
    def push_raw_imu_sample(
        self,
        raw_sample,
    ) -> tuple[RuntimeSnapshot, ...]:
        """Process one accelerometer or gyroscope callback causally."""

        preprocessing_results = self._deps.preprocessor.push_raw_sample(
            raw_sample
        )
        snapshots: list[RuntimeSnapshot] = []

        for result in preprocessing_results:
            if (
                result.disposition
                is not PreprocessingDisposition.ACCEPTED
            ):
                continue

            if result.vehicle_imu_sample is None:
                raise RuntimeError(
                    "Accepted preprocessing result must contain vehicle IMU."
                )

            snapshots.append(
                self._run_accepted_vehicle_imu_cycle(
                    result,
                    result.vehicle_imu_sample,
                )
            )

        return tuple(snapshots)
```

Phone accelerometer and gyro callbacks arrive independently. The preprocessor may emit zero or more synchronized samples for each callback; only accepted, calibrated, quality-approved vehicle IMU samples create an EKF cycle.

Warm-up samples are not failures. They simply cannot yet produce reliable navigation.

```python
    def _run_accepted_vehicle_imu_cycle(
        self,
        preprocessing: PreprocessedImuResult,
        vehicle_imu: VehicleImuSample,
    ) -> RuntimeSnapshot:
        """Run one complete propagate-update-match-publish cycle."""

        runtime = self._deps.runtime
        previous = runtime.snapshot

        if previous.filter_state is None:
            # Initialisation must use trustworthy GNSS plus calibrated vehicle
            # orientation. Do not fabricate origin, velocity, or covariance.
            return previous

        token = runtime.begin_cycle(vehicle_imu.timestamp_ns)

        propagation = propagate_ekf(
            previous.filter_state,
            vehicle_imu,
            config=self._propagation_config,
        )
        if propagation.disposition.value != "propagated":
            return runtime.abort_cycle(
                token,
                reason=propagation.disposition.value,
            )

        prior_feedback = self._deps.feedback_store.prior_for_cycle(
            cycle_timestamp_ns=vehicle_imu.timestamp_ns,
            graph_id=self._active_graph_id,
        )

        # GNSS first, then velocity, then physical NHC, then weak road context.
        gnss = self._deps.gnss_measurements.measurements_for_cycle(
            timestamp_ns=vehicle_imu.timestamp_ns,
            state=propagation.state,
            prior_map_feedback=None,
        )
        velocity = self._deps.velocity_measurements.measurements_for_cycle(
            timestamp_ns=vehicle_imu.timestamp_ns,
            state=propagation.state,
            prior_map_feedback=None,
        )

        nhc_decision = build_non_holonomic_measurement(
            propagation.state,
            vehicle_imu,
            self._nhc_config,
        )
        nhc = (
            ()
            if nhc_decision.measurement is None
            else (nhc_decision.measurement,)
        )

        road_context = self._deps.road_context_measurements.measurements_for_cycle(
            timestamp_ns=vehicle_imu.timestamp_ns,
            state=propagation.state,
            prior_map_feedback=prior_feedback.feedback,
        )

        updated_state, traces = apply_measurements_in_order(
            propagation.state,
            gnss + velocity + nhc + road_context,
        )
```

This is the central ordering rule:

`preprocess → propagate → GNSS → velocity → NHC → prior-cycle road context → HMM`

Road context receives only `prior_feedback.feedback`; it cannot depend on the HMM result produced later in this same function.

The constructor would receive `_propagation_config`, `_nhc_config`, and `_active_graph_id` explicitly through a small pipeline configuration object. They are shown as fields here only to keep the cycle readable.

```python
        gnss_trace = next(
            (
                trace
                for trace in traces
                if trace.kind.value == "gnss_position"
            ),
            None,
        )
        mode_update = advance_navigation_mode(
            prior=previous.mode_state,
            timestamp_ns=vehicle_imu.timestamp_ns,
            gnss_quality=self._latest_gnss_quality,
            gnss_position_trace=gnss_trace,
            config=self._mode_config,
        )

        current_map_feedback = (
            self._deps.map_matcher.update_after_fusion(
                timestamp_ns=vehicle_imu.timestamp_ns,
                state=updated_state,
            )
        )
        if current_map_feedback is not None:
            self._deps.feedback_store.publish_completed_match(
                current_map_feedback
            )

        estimate = build_navigation_estimate(
            state=updated_state,
            mode_state=mode_update.state,
            map_feedback=current_map_feedback,
        )

        return runtime.commit_cycle(
            token,
            CycleOutcome(
                filter_state=updated_state,
                mode_state=mode_update.state,
                navigation_estimate=estimate,
                propagation_disposition=propagation.disposition,
                measurement_traces=traces,
            ),
        )
```

Only after all fusion updates does the current HMM update run. Its result becomes feedback for the next cycle, is converted into the public navigation estimate, and is atomically committed by `runtime.py`.

One correction before implementation: `NavigationRuntime` needs a read-only `snapshot` property, while this orchestrator needs explicit configuration and initialization dependencies. Those should be added before this code is connected, rather than hidden as private fields.

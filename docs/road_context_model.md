# Road-Context Speed-Prior Model: Design and Methodology

**Status:** Proposed design, not yet implemented  
**Date:** 2026-09-06  
**Scope:** Offline data preparation, candidate-level speed-quantile modelling,
deterministic safety rules, runtime aggregation, EKF integration, validation,
and deployment gates.

## 1. Executive summary

The road-context engine is a sensor-independent supporting engine for the
navigation pipeline. It does not consume accelerometer, gyroscope, velocity-GRU,
or CAN data at runtime. Instead, it uses:

- the previous completed HMM map-matching belief;
- versioned OpenStreetMap-derived road attributes;
- derived road geometry and topology;
- trustworthy time-of-day information, when available.

For every plausible candidate road, a tabular quantile model predicts a low,
median, and high plausible speed. Candidate distributions are combined using
the previous HMM probabilities. Disagreement between candidates automatically
increases uncertainty. Deterministic rules then widen, suppress, or reject the
result when the map, candidate belief, time context, or model output is unsafe.

An accepted result becomes a weak, low-rate scalar speed prior for the EKF. It
never becomes a position observation, never replaces the velocity model, and
never uses same-cycle HMM output. When the engine is uncertain, its correct
output is an explicit omission rather than a guessed speed.

The expected benefit is not superior instantaneous speed prediction in every
condition. The expected benefit is a complementary, map-informed constraint
that reduces implausible speed drift during GNSS blackouts, especially when one
road hypothesis is clearly more plausible than its alternatives. Deployment is
conditional on calibrated held-out quantiles and measurable downstream replay
improvement.

## 2. What the current dataset actually contains

### 2.1 Verified raw-data inventory

The paired raw dataset contains GNSS data in addition to IMU and CAN data. A
read-only profile using `load_raw_replay_journey` found:

| Inventory | Verified value |
|---|---:|
| Paired smartphone/vehicle journeys | 40 |
| Journeys successfully loaded | 40 |
| Aligned complete rows | 685,940 |
| Combined aligned duration | 16.73 hours |
| Rows with phone horizontal accuracy at or below 20 m | 99.84% |
| Final-v2 development journeys | 35 |
| Final-v2 development aligned rows | 594,138 |
| Final-v2 development aligned duration | 14.18 hours |

The final velocity-v2 experiment excluded five previously exposed journeys and
used 35 development journeys. Only 21 of those journeys produced usable
production-compatible velocity examples because velocity training additionally
requires synchronized IMU, calibration, fixed-rate continuity, and accepted
preprocessing. Road-context preparation does not require those IMU conditions,
so it can potentially use substantially more of the 35-journey development
partition.

These counts describe rows surviving the current raw/CAN alignment loader. They
are not a claim that every coordinate is map-matchable or that every row should
become a statistically independent training example.

### 2.2 Available fields

The smartphone recording supplies:

- timestamp and elapsed time;
- GPS latitude and longitude;
- GPS altitude;
- GPS speed;
- GPS horizontal accuracy;
- GPS orientation/course;
- accelerometer and gyroscope channels.

The paired vehicle/reference recording supplies:

- indicated CAN/ECU vehicle speed;
- reference latitude and longitude;
- vehicle elapsed time.

The current loader aligns vehicle rows to phone rows by relative elapsed time
with a 75 ms nearest-neighbour tolerance and drops rows missing required values.
The road-context dataset builder should reuse the established clock alignment,
but it needs its own quality and map-matching audit rather than inheriting the
velocity dataset's IMU-specific acceptance decision.

### 2.3 Runtime versus offline use

The existence of GNSS in the recorded dataset does not mean GNSS becomes a
runtime road-context feature during a blackout.

| Signal | Offline dataset construction | Runtime road-context model |
|---|---|---|
| Phone/reference position | Map matching and quality checks | No direct use during blackout |
| CAN speed | Preferred target label | Never available |
| GNSS speed | Secondary/filtering label | Never available during blackout |
| IMU channels | Not needed | Not used |
| Velocity-GRU output | Not used | Not used |
| OSM road attributes | Model features | Model features |
| Prior HMM candidate belief | Replay/audit | Candidate weighting and gating |
| Wall-clock time | Optional model feature | Optional model feature |

The dense velocity cache does not retain the full coordinate sequence needed
for road-feature joining. A new versioned road-context dataset must therefore be
built from the paired raw files, not reconstructed from velocity windows.

## 3. Problem definition

During GNSS loss, inertial propagation and a learned velocity observation can
still drift. A road map contains weak but useful information about plausible
speed: a motorway, a residential street, a short service link, and a roundabout
do not generally have identical speed distributions.

The map matcher already maintains multiple candidate roads. Selecting one road
before creating the speed prior would discard uncertainty and could force a
wrong road into the EKF. The road-context engine must instead preserve all
credible candidates and represent both:

1. uncertainty within each candidate road's predicted speed distribution; and
2. disagreement between candidate roads.

### 3.1 Goals

- Produce calibrated candidate-specific speed distributions.
- Preserve HMM ambiguity instead of prematurely choosing one road.
- Convert an accepted candidate mixture into a conservative EKF covariance.
- Remain causal by using only a prior completed HMM belief.
- Avoid double-counting IMU/GRU evidence.
- Fail safely by omitting an unsafe or uninformative prior.
- Improve downstream blackout navigation on grouped held-out replay.

### 3.2 Non-goals

- Road context is not a position estimator.
- It is not a route planner or turn-intent predictor.
- It does not replace IMU propagation, GNSS, the velocity model, or the HMM.
- It does not infer the state of a traffic signal without a live signal feed.
- It does not treat OSM tags as guaranteed legal or current truth.
- It does not provide reliable navigation when both IMU and GNSS are absent for
  an extended period.

## 4. Causal system architecture

At cycle `t`, road context consumes the HMM posterior completed at cycle `t-1`:

```text
Completed HMM belief at t-1
        |
        v
Candidate roads + OSM + time
        |
        v
Candidate quantile predictions
        |
        v
Rules, calibration, mixture and gating
        |
        +---- unsafe/uninformative ----> explicit omission
        |
        v
Weak scalar road-speed prior
        |
        v
EKF cycle t: propagation -> GNSS -> velocity -> road context -> NHC
        |
        v
Current navigation estimate -> HMM cycle t -> stored for t+1
```

This one-cycle delay avoids a circular same-cycle dependency. The current HMM
cannot use a road-influenced EKF state and simultaneously provide the belief
that created that same road update.

### 4.1 Meaning of "parallel" and "no IMU"

The road-context model is parallel in feature ownership: it reads no IMU or GRU
feature. It is not a standalone parallel navigation solution because it depends
on a previously initialized map belief and only outputs speed plausibility.

The current runtime is driven by raw IMU callbacks. If IMU messages literally
stop, no EKF fusion cycle is currently scheduled. Supporting road-context
inference during such a gap would require an independent low-rate timer or a
GNSS-driven tick. Even then, the prior can only remain usable briefly while its
source HMM belief is fresh. It cannot determine how far the vehicle travelled
or which branch it selected without new motion/position evidence.

## 5. Runtime contracts

### 5.1 Candidate-level prediction

The existing `RoadContextPrior` contract already represents candidate-level:

- source belief timestamp;
- candidate and edge identity;
- speed p10, p50, and p90;
- optional rule speed limit;
- confidence.

The implementation should retain this candidate-level object but add an
aggregate decision object with auditable dispositions.

Proposed aggregate fields:

- current timestamp;
- source HMM belief timestamp and graph ID;
- candidate priors and normalized mixture weights;
- aggregate speed estimate and variance;
- model/calibration artifact IDs;
- applied variance-inflation factors;
- final disposition;
- machine-readable reasons;
- whether the decision was shadow-only or eligible for fusion.

Suggested dispositions include:

- `available`;
- `absent_feedback`;
- `stale_feedback`;
- `low_map_confidence`;
- `high_candidate_entropy`;
- `candidate_heading_conflict`;
- `missing_road_features`;
- `out_of_distribution`;
- `invalid_quantiles`;
- `uninformative_interval`;
- `fresh_gnss_preferred`;
- `rate_limited`.

### 5.2 Feature separation

The learned quantile model should receive only context that describes the road
and external environment:

- OSM road class;
- speed-limit value and availability flag;
- lane count and availability flag;
- one-way/directionality information;
- link, tunnel, bridge, and roundabout flags;
- segment length;
- curvature summaries;
- distance to the next intersection;
- distance to the next mapped traffic signal;
- local connectivity/node-degree summaries;
- wall-clock hour encoded cyclically;
- weekday/weekend or day-of-week, if trustworthy.

The following belong outside the learned model and are used only for weighting,
gating, or covariance inflation:

- HMM candidate probability;
- posterior entropy;
- top-one versus top-two probability margin;
- feedback age;
- lateral distance;
- heading disagreement;
- graph-feature completeness;
- artifact/version compatibility.

Keeping HMM confidence out of the quantile learner lets the model learn the
speed distribution of a road rather than the confidence behaviour of one
particular map matcher.

### 5.3 Explicitly excluded features

- current or recent velocity-GRU predictions;
- accelerometer or gyroscope features;
- current EKF speed;
- runtime CAN speed;
- same-cycle HMM output;
- future coordinates, speed, route, or traffic observations.

These exclusions prevent target leakage and reduce cross-source evidence
correlation. A later history-aware model would need an explicit correlated-
measurement treatment rather than being fused as an independent EKF update.

## 6. Dataset-construction methodology

### 6.1 Source priority

1. **First-party GPS/CAN journeys.** These match the phone, vehicle population,
   geography, map conventions, and intended runtime.
2. **New targeted GPS/OBD collection.** Road context needs position, time, and
   speed labels, so additional collection is cheaper than IMU-model collection.
3. **Approved Indian trajectory datasets.** Use for mixed-traffic and geographic
   diversity after schema and licence review.
4. **International trajectory datasets.** Use for feature robustness and
   stress tests, not direct Indian calibration.
5. **SUMO scenarios.** Use for controlled tests and optional pretraining, never
   as the sole calibration source.

### 6.2 Building one first-party training row

For every selected timestamp:

1. Load aligned phone and vehicle data using the established relative clocks.
2. Validate position, speed, course, accuracy, timestamp ordering, and jump
   plausibility.
3. Prefer the higher-quality reference coordinate for offline matching when its
   provenance and clock alignment are valid; otherwise use quality-gated phone
   GNSS.
4. Match the offline coordinate sequence to a versioned OSM graph using a
   trajectory-level matcher, not independent nearest-edge snapping.
5. Reject or mark ambiguous points where the offline road identity is not
   sufficiently trustworthy.
6. Look up static road attributes and derive geometry/topology features.
7. Use indicated CAN speed as the primary target.
8. Retain phone GNSS speed only for cross-checks or as a lower-quality fallback.
9. Store data-source provenance, raw journey ID, graph ID/hash, source way ID,
   directed edge, map-match confidence, and all quality dispositions.

### 6.3 Sampling cadence and statistical independence

The raw aligned dataset has hundreds of thousands of rows, but adjacent 10 Hz
rows are nearly duplicates. Treating them as independent would make long roads
and long journeys dominate training and would produce overconfident validation.

The initial road-context dataset should sample at the intended runtime cadence,
starting with one row every 2 seconds. A 5-second variant should be included in
an ablation. Event rows around road-class changes, junctions, roundabouts, and
candidate transitions may be retained at a denser cadence, but their weighting
must remain bounded.

### 6.4 Training weights

Weights must be computed inside each training fold only.

Recommended procedure:

1. Equalize total contribution by journey.
2. Within a journey, reduce repeated exposure to the same directed edge using
   inverse-square-root edge frequency.
3. Renormalize so each journey retains equal total mass.
4. Optionally upweight genuinely sparse road-class/context combinations.
5. Normalize the final mean weight to one and clip to `0.25-4.0`.

Full inverse-frequency edge weighting is not recommended because a five-second
service-road fragment should not receive the same total importance as a long,
well-observed road.

### 6.5 Leakage-safe splitting

At least two evaluations are required:

1. **Journey-held-out evaluation:** whole journeys stay in one fold.
2. **Spatial generalization evaluation:** road edges or geographic tiles stay
   entirely in one fold.

Repeated traversals of the same road must not appear on both sides of a spatial
holdout. Calibration must be fit only on training/calibration groups and then
evaluated on untouched groups.

The five journeys excluded from final velocity-v2 training have already been
examined in earlier work and are not a pristine road-context test set. A new
road-context evaluation partition should be fixed and exported before model
comparison.

### 6.6 External data

- The Chennai mixed-traffic trajectory data provides real Indian urban vehicle
  trajectories and derivable speed but represents a narrow location.
- IIT Roorkee's ITD covers varied Indian road environments, but its primary
  artifact is annotated imagery/video; metric speeds require tracking,
  homography/camera calibration, and separate quality review.
- FHWA NGSIM provides freely available US highway and arterial trajectories.
- INTERACTION provides vehicle tracks and semantic maps across varied driving
  scenarios; dataset-access terms must be reviewed separately from its scripts.
- SUMO can produce vehicle position, speed, acceleration, route, and traffic
  outputs on controlled networks.

Every source must retain provenance and source-specific weight. External and
synthetic rows must never silently dominate first-party calibration.

## 7. Modelling methodology

### 7.1 Baselines

Before learned models, implement:

- global empirical speed quantiles;
- road-class empirical quantiles;
- road-class plus time-bucket quantiles;
- OSM speed-limit-only soft bounds;
- deterministic rules without learned quantiles.

The learned model must improve on these baselines under the same grouped splits.

### 7.2 Candidate models

Use a common interface to compare LightGBM and XGBoost gradient-boosted trees.
This is tabular, heterogeneous, missing-value-heavy data; a deep recurrent or
graph neural network is not justified for the first production attempt.

Train independent or jointly wrapped quantile objectives for:

- q10 (`alpha=0.10`);
- q50 (`alpha=0.50`);
- q90 (`alpha=0.90`).

The primary training score is grouped out-of-fold pinball loss, with median MAE,
interval coverage, interval width, subgroup stability, and runtime latency as
secondary criteria.

Use a small, reproducible hyperparameter search over:

- tree depth/leaves;
- learning rate;
- number of estimators with early stopping;
- minimum child observations;
- row and feature subsampling;
- L1/L2 regularization.

Do not conduct a large search until the spatial split, map joins, and baselines
are verified.

### 7.3 Quantile ordering

Published outputs must satisfy:

```text
0 <= q10 <= q50 <= q90
```

Crossing quantiles should be measured before correction. A deterministic sort
can guarantee runtime ordering, but frequent crossings indicate a model-quality
failure and must not be hidden by post-processing.

### 7.4 From quantiles to candidate moments

For candidate `i`, use the initial approximation:

```text
mu_i approximately equals q50_i
sigma_i approximately equals (q90_i - q10_i) / (2 * 1.2816)
```

The scale `1.2816` is the normal-distribution z-score for the 10th/90th
quantiles. This is a moment approximation, not an assertion that stop/go speed
is Gaussian. Median is not always equal to mean, particularly around junctions
and congestion. Grouped residual calibration must therefore correct the final
variance conservatively.

A later improvement may estimate moments from a denser quantile grid or a
piecewise quantile distribution if the three-quantile approximation is
materially biased.

### 7.5 Candidate-mixture aggregation

Let `w_i` be normalized probabilities from the previous completed HMM belief.
Given candidate moments `(mu_i, sigma_i^2)`, compute:

```text
mu_mix = sum_i w_i * mu_i

var_mix = sum_i w_i * (sigma_i^2 + (mu_i - mu_mix)^2)
```

The variance contains:

- within-candidate uncertainty `sigma_i^2`; and
- between-candidate disagreement `(mu_i - mu_mix)^2`.

Therefore a high-speed main road competing with a low-speed service road
automatically produces a wider prior. The mixture calculation is the law of
total variance once candidate means and variances are supplied; the preceding
conversion from three quantiles remains approximate.

### 7.6 Calibration

For each grouped fold:

1. Train the quantile models on training journeys/areas only.
2. Estimate any calibration factor on a separate training-side calibration
   subset.
3. Build candidate mixtures on the held-out fold.
4. Measure q10-q90 coverage and standardized residuals.
5. Fit only conservative variance expansion; never shrink below the raw model
   estimate during initial deployment.

The final EKF covariance is:

```text
R = max(variance_floor, k * var_mix) * reliability_inflation
```

where `k >= 1` is estimated from grouped out-of-fold residuals and
`reliability_inflation >= 1` accounts for feedback age, feature missingness,
map ambiguity, out-of-distribution conditions, and other runtime risks.

If useful calibration requires an extremely large `k`, the model is not
informative enough for fusion and should remain shadow-only.

## 8. Deterministic rules and gates

Rules may widen or omit a prior. They should not create falsely precise speeds.

### 8.1 Map and belief gates

- Reject absent, stale, future, same-cycle, or graph-mismatched feedback.
- Require a configured minimum map-match confidence.
- Measure posterior entropy and top-two margin.
- Omit when candidate headings are mutually incompatible.
- Increase variance when plausible candidates disagree.
- Reset on graph/session changes.

### 8.2 OSM-quality rules

- Preserve missing speed limits and lane counts as missing.
- Treat OSM speed limits as weak evidence rather than guaranteed truth.
- Retain graph/source version and feature provenance.
- Increase uncertainty for unknown road classes or feature ranges not observed
  during training.
- Do not infer live congestion from static OSM.

OpenStreetMap data is available under the ODbL and requires attribution and
applicable share-alike handling for adapted databases.

### 8.3 Physical and topology rules

- Ensure finite, non-negative, ordered quantiles.
- Use a generous curvature-based upper plausibility bound when road geometry is
  reliable.
- Do not assume a mapped traffic signal is red.
- Do not force a stop at an intersection or roundabout.
- Widen uncertainty near junctions and short connectors.
- Reject intervals that are narrower than a configured physical/calibration
  floor.

### 8.4 Fresh-GNSS policy

While fresh GNSS velocity is accepted, road context should run in shadow mode
but should not be fused. This provides continuous calibration evidence while
allowing the stronger direct observation to dominate. Road-context fusion is
primarily for dead-reckoning mode.

## 9. EKF integration

### 9.1 Measurement form

An accepted road-context result becomes a scalar forward-speed observation,
using the same frame-aware velocity/attitude Jacobian pattern as the existing
learned-speed measurement. It has its own measurement kind, covariance floor,
association-age rule, and NIS gate.

Recommended measurement order:

1. propagate IMU state;
2. apply fresh qualified GNSS position/velocity;
3. apply selected velocity-model observation;
4. apply eligible road-context prior;
5. apply non-holonomic constraint;
6. commit the EKF state;
7. update the current HMM and publish feedback for the next cycle.

Road context should be skipped when fresh GNSS velocity has already been
accepted in the cycle.

### 9.2 Rate limiting and correlation control

Static road information does not become independent evidence merely because
the IMU callback repeats. Applying the same prior at 10 Hz would incorrectly
collapse EKF covariance.

Initial policy:

- ordinary road-context fusion no more often than every 2-5 seconds;
- never reuse the same accepted source decision without explicit correlation
  inflation;
- record the last source belief, edge signature, and injection timestamp;
- permit an event-triggered recomputation when the top candidate changes,
  posterior entropy changes sharply, or the prior edge disappears;
- omit during unresolved post-fork ambiguity;
- allow one refreshed decision when the fork becomes confidently resolved.

### 9.3 Required pipeline refactor

The current map-matching composition completes fusion before running the HMM and
explicitly prevents map matching from changing the current EKF state. Road
context needs a controlled pre-commit extension point while preserving the
one-cycle delay.

Recommended integration:

- add a narrow optional `RoadContextPriorSource` protocol to the fusion layer;
- bind it to the graph and existing `MapMatchFeedbackStore` in the outer
  navigation composition;
- request a prior after direct speed observations and before NHC/commit;
- allow the source to read only feedback older than the active cycle;
- keep the current HMM downstream of the committed EKF state;
- make absence of a road-context source reproduce current behaviour exactly.

If literal IMU outages must trigger road-context evaluation, add a separate
low-rate scheduler. That scheduler must not pretend that a speed prior is a
propagated position estimate.

## 10. Validation methodology

### 10.1 Dataset and feature tests

- paired-file discovery and clock-alignment audit;
- coordinate, speed, accuracy, and course validity;
- impossible-jump and timestamp-gap rejection;
- deterministic graph joins and graph-version binding;
- no journey/edge/tile leakage across folds;
- feature missingness and category coverage;
- target/runtime feature separation;
- source and licence provenance.

### 10.2 Model tests

- finite non-negative predictions;
- quantile ordering and crossing rate;
- grouped pinball loss;
- q50 MAE and bias;
- q10-q90 empirical coverage;
- interval width and sharpness;
- calibration by road class, speed, junction proximity, missing tags, time,
  journey, seen road, and unseen road;
- deterministic inference and artifact-schema validation;
- CPU latency and memory use.

### 10.3 Mixture and rule tests

- one-candidate identity case;
- identical candidate distributions;
- high-speed versus service-road disagreement;
- opposing-heading candidates;
- missing probabilities and non-normalized probabilities;
- stale, low-confidence, graph-mismatched, and same-cycle feedback;
- quantile crossing and non-finite outputs;
- missing OSM tags and unseen road class;
- rate limiting and event-trigger refresh;
- explicit omission without modifying EKF state.

### 10.4 Shadow-mode evaluation

Run the complete road-context engine during GNSS-aided replay without applying
its measurement. Compare every decision with CAN/reference speed and record:

- availability/omission rate and reasons;
- absolute residual and bias;
- interval coverage;
- standardized residual and proposed NIS;
- covariance-floor activation;
- calibration by context and feedback age;
- inference latency.

### 10.5 End-to-end blackout evaluation

Use controlled 30, 60, 90, and 120-second GNSS blackouts. Compare:

- current pipeline without road context;
- deterministic road rules only;
- learned candidate quantiles without EKF fusion, for diagnosis;
- full calibrated road-context fusion.

Report:

- overall and macro-journey velocity MAE/RMSE;
- horizontal position error and endpoint drift;
- median and p95 drift;
- errors by blackout horizon;
- per-journey changes;
- map-match correctness/confidence;
- road-context acceptance/rejection rate;
- NIS distribution and EKF covariance consistency;
- GNSS reacquisition time and rejection behaviour;
- CPU p50/p95 latency.

## 11. Proposed deployment gates

Thresholds are initial engineering targets and should be frozen before reading
the final road-context evaluation.

| Gate | Initial requirement |
|---|---|
| Data leakage | Zero shared journeys in journey folds; zero shared held-out edges/tiles in spatial folds |
| Quantile validity | 100% finite, non-negative, ordered published outputs |
| Raw crossing rate | Reported and low enough that sorting is exceptional, not routine |
| q10-q90 coverage | Approximately 75-85% overall for a nominal 80% interval |
| Major subgroup coverage | No sufficiently supported major subgroup below 70% |
| Learned value | Better grouped pinball loss than road-class/time empirical baseline |
| Variance calibration | Conservative grouped holdout residual calibration with `k >= 1` |
| Unsafe contexts | Explicitly omitted; never converted to zero speed |
| CPU latency | Road-context inference and aggregation p95 below 5 ms on target CPU |
| Blackout benefit | At least 5% improvement in macro-journey endpoint drift or another predeclared primary trajectory metric |
| Tail safety | No material p95 drift degradation and no unacceptable canonical-horizon regression |
| Recovery safety | No material degradation in GNSS acceptance/recovery behaviour |

If the learned model fails, deterministic rules may still be retained for
shadow diagnostics, but the current navigation pipeline remains unchanged.

## 12. Expected outcomes

### 12.1 Expected positive behaviour

- A confident motorway candidate produces a higher but still uncertain speed
  prior than a residential or service-road candidate.
- Competing road types widen the covariance automatically instead of forcing a
  single-road decision.
- Missing tags, stale feedback, junctions, and unfamiliar contexts reduce
  authority or suppress the prior.
- The road prior can limit implausible velocity drift during a GNSS blackout.
- Improved speed plausibility can indirectly reduce along-road position drift
  because the EKF integrates velocity over time.
- Shadow mode supplies continuous real-world calibration evidence without
  altering navigation.
- Failure or missing artifacts degrade cleanly to the existing pipeline.

### 12.2 Outcomes that should not be promised before evaluation

- Road context is not expected to beat the velocity GRU on every instantaneous
  speed sample; it has less direct motion information.
- It cannot determine turn intent at an unresolved fork.
- It cannot correct cross-road position by itself.
- It cannot guarantee useful output on unmapped, poorly tagged, or rapidly
  changing roads.
- It cannot recover navigation during a prolonged total IMU-and-GNSS outage.
- Exact trajectory improvement cannot be estimated from the current velocity
  training logs; it must be measured in composed replay.

The realistic success condition is modest but reliable downstream improvement,
not a dramatic standalone speed-model score.

## 13. Principal risks and mitigations

| Risk | Mitigation |
|---|---|
| Geographic memorization | Spatial edge/tile holdouts and first-party/external provenance reporting |
| False sample size from 10 Hz rows | 2-5 second sampling, grouped folds, journey weighting |
| OSM missing/outdated tags | Missingness flags, weak rules, variance inflation, omission |
| Wrong road candidate | Candidate mixture, entropy/heading gates, between-candidate variance |
| Same-cycle feedback loop | Strict source timestamp `<` current cycle timestamp |
| Repeated correlated updates | Low-rate injection, decision identity, covariance floor |
| Double-counted motion evidence | Exclude IMU, GRU, and current EKF speed from learned features |
| Simulator domain gap | Synthetic data limited to tests/pretraining; real grouped calibration required |
| Quantile-to-Gaussian mismatch | Conservative grouped residual scaling and shadow NIS analysis |
| Time feature unavailable | Explicit wall-clock contract or static-only model; never derive time-of-day from monotonic elapsed time |
| Public-data licence incompatibility | Source-specific review and isolated provenance before inclusion |

## 14. Implementation phases

### Phase A: Data audit and deterministic baseline

- Build a coordinate/speed/accuracy audit for all 40 paired journeys.
- Freeze development, calibration, spatial, and final evaluation partitions.
- Import/version the relevant OSM extract.
- Build offline trajectory-level road matches.
- Export a versioned road-context table and audit report.
- Implement global, road-class, time-bucket, and rule-only baselines.

### Phase B: Contracts, features, and rules

- Complete road-context dataclasses and dispositions.
- Implement deterministic feature extraction from `RoadGraph`.
- Add curvature, distance-to-junction, and topology features.
- Implement map/belief/OSM/physical gates.
- Add unit tests for all omission and mixture cases.

### Phase C: Quantile-model experiment

- Compare LightGBM and XGBoost under identical grouped folds.
- Evaluate 2-second versus 5-second cadence.
- Evaluate journey-only versus journey-plus-edge weighting.
- Calibrate quantiles and aggregate variance using training-side grouped data.
- Export the model, feature schema, calibration metadata, and graph compatibility.

### Phase D: Shadow runtime

- Add the one-cycle `RoadContextPriorSource` integration point.
- Run inference while GNSS is available but do not modify the EKF.
- Collect coverage, NIS, omission, subgroup, and latency reports.
- Adjust only predeclared calibration/rule parameters on development data.

### Phase E: Controlled fusion and selection

- Enable low-rate fusion in replay only.
- Compare no-road, rules-only, and learned-road variants.
- Evaluate all canonical blackout horizons and GNSS recovery.
- Export the final artifacts only if every deployment gate passes.
- Keep road context disabled by default unless every deployment gate passes.

## 15. Current repository integration points

The design is intended to extend the existing backend rather than create a
second navigation stack. The main code anchors are:

- [`feedback.py`](../src/idr_backend/pipeline/feedback.py) for the completed
  map-match feedback store;
- [`types.py`](../src/idr_backend/sensors/types.py) for shared timestamped sensor
  contracts;
- [`graph.py`](../src/idr_backend/map_matching/graph.py) for the road graph and
  OSM-derived edge data;
- [`observations.py`](../src/idr_backend/fusion/observations.py) for EKF
  observation construction;
- [`fusion.py`](../src/idr_backend/pipeline/fusion.py) for the narrow optional
  road-prior injection point;
- [`map_matching.py`](../src/idr_backend/pipeline/map_matching.py) for preserving
  the causal order between committed EKF state and the next HMM belief;
- [`replay.py`](../src/idr_backend/evaluation/replay.py) for the established raw
  phone/vehicle discovery and clock alignment used by offline preparation.

Exact module boundaries may change during implementation, but the causality,
feature-separation, and omission contracts in this document should not.

## 16. External data and methodology references

- [OpenStreetMap copyright and licence](https://www.openstreetmap.org/copyright)
  describes ODbL attribution and share-alike requirements.
- [SUMO simulation outputs](https://sumo.dlr.de/docs/Simulation/Output/index.html)
  documents controlled position, speed, acceleration, route, and traffic
  outputs suitable for tests and optional pretraining.
- [FHWA NGSIM](https://ops.fhwa.dot.gov/trafficanalysistools/ngsim.htm)
  provides public US vehicle-trajectory datasets for robustness experiments.
- [INTERACTION dataset tools](https://github.com/interaction-dataset/interaction-dataset)
  provide tracks and semantic maps; dataset access terms must be checked
  independently of the repository's script licence.
- [IIT Roorkee ITD](https://github.com/teg-iitr/ITD-Indian-traffic-dataset)
  provides Indian traffic imagery/video and annotations, but metric velocity
  extraction would require a separate computer-vision and calibration stage.
- [Chennai mixed-traffic trajectories](https://toledo.net.technion.ac.il/mixed-traffic-trajectory-data/)
  provide a geographically relevant real-traffic source with narrower spatial
  coverage than the intended deployment domain.

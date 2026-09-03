# Planned architecture

## Ownership boundary

The backend owns deterministic navigation, uncertainty estimation, road-context
estimation, and their integration. The velocity predictor is an external source
of a speed observation; it is not implemented in this repository.

## Intended cycle order

1. Collect and validate phone or external-IMU samples and GNSS observations.
2. Synchronize timestamps, normalize units, estimate attitude, calibrate the
   phone-to-vehicle transform, and remove gravity.
3. Propagate a 15-state error-state EKF using the validated inertial data.
4. Receive a velocity observation through the external adapter and have the
   uncertainty engine produce a safe covariance/reliability estimate.
5. Generate road candidates from the previous incremental HMM belief and the
   EKF prediction.
6. Produce a road-context speed prior from candidate segments, OSM features,
   time features, and recent kinematic history.
7. Apply eligible GNSS, NHC, velocity, and road-context measurement updates.
8. Update the incremental or sliding-window HMM map matcher and publish the
   navigation estimate.

## Future state and contracts

Future implementation will define, but must not yet expose as stable APIs:
`ImuSample`, `GnssFix`, `VelocityObservation`, `UncertaintyEstimate`,
`RoadContextPrior`, `RoadCandidate`, and `NavigationEstimate`.

The 15-state filter is expected to use a nominal inertial state and an error
state spanning position, velocity, attitude error, accelerometer bias, and gyro
bias. The exact coordinate-frame convention and measurement equations remain
implementation decisions to document before code is added.

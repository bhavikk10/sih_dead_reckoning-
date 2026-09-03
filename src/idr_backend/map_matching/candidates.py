"""Future road-candidate generation.

TODO:
- propose nearby and reachable road segments from the EKF prediction and prior HMM belief;
- bound spatial search, candidate count, and behavior at junctions or parallel roads;
- retain candidate provenance for road-context priors and HMM scoring;
- reject unsupported coordinate frames or missing graph coverage transparently.
"""

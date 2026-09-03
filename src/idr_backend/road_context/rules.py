"""Future deterministic road-context bounds and gates.

TODO:
- define conservative lower/upper plausibility limits from road type and traffic controls;
- treat OSM speed limits as weak evidence, not unqualified truth;
- gate priors near junctions, route ambiguity, missing tags, and poor map confidence;
- prevent rules from overriding strong inertial or GNSS evidence.
"""

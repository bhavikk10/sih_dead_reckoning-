"""Future HMM emission and transition scoring.

TODO:
- score spatial agreement, heading, uncertainty, road reachability, and speed plausibility;
- avoid double-counting the same road-context evidence in both fusion and map matching;
- document log-probability normalization and impossible-transition handling;
- preserve diagnostics explaining candidate rejection and route changes.
"""

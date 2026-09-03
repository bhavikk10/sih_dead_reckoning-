"""Future incremental or sliding-window HMM/Viterbi implementation.

TODO:
- choose a bounded latency window suitable for real-time navigation;
- retain enough history to avoid rapid flips between parallel or service roads;
- define state pruning, backtracking, reset, and GNSS-reacquisition behavior;
- emit a belief suitable for next-cycle road-context candidate generation.
"""

"""Future candidate-road prior construction.

TODO:
- combine candidate-specific quantiles, deterministic rules, and confidence metadata;
- consume the previous HMM belief plus current EKF prediction, not a same-cycle map match;
- represent ambiguity across candidates without forcing a single road prematurely;
- map the result to a weak, bounded fusion measurement or covariance modifier.
"""

"""Small statistics helpers: Wilson intervals (weighted via effective sample size), rates, Kendall tau."""

import math

Z = 1.96


def wilson_p(p, n, z=Z):
    """Wilson score interval for proportion p over n (n may be an effective, non-integer size). (None, None) when n is 0."""
    if not n:
        return None, None
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson(k, n, z=Z):
    return wilson_p(k / n, n, z) if n else (None, None)


def weighted_rate(pairs):
    """pairs: (hit, weight). Returns (rate, effective_n, lower, upper); rate is None with no weight."""
    pairs = list(pairs)
    total = sum(w for _, w in pairs)
    if not total:
        return None, 0.0, None, None
    rate = sum(w for h, w in pairs if h) / total
    n_eff = total * total / sum(w * w for _, w in pairs)
    lo, hi = wilson_p(rate, n_eff)
    return rate, n_eff, lo, hi


def kendall_tau(order_a, order_b):
    """Kendall tau-a between two rankings (lists of ids best first) over the ids they share; None under two shared ids."""
    shared = [x for x in order_a if x in set(order_b)]
    if len(shared) < 2:
        return None
    pos = {x: i for i, x in enumerate(order_b)}
    conc = disc = 0
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            conc, disc = (conc + 1, disc) if pos[shared[i]] < pos[shared[j]] else (conc, disc + 1)
    return (conc - disc) / (conc + disc)

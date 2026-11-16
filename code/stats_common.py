"""Statistical functions shared by scoring checks and analysis (paper sections 3.5–3.6).

Usage: imported by analysis.py, adjudicate.py and human_check.py; no network or file writes.
Newcombe method 10 uses ordinary Wilson margins and continuity correction only in
positive phi (Newcombe 1998, Statistics in Medicine 17:2635–2650, p.2639).
Bootstrap percentiles use linear interpolation at (B-1)*q. Monte Carlo sign-flip
p-values include ties and the observed arrangement by the plus-one convention.
"""
from collections import Counter
import json
import math
import random
import statistics


def wilson(successes, n, z=1.959963984540054):
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("invalid binomial counts")
    if not n:
        return None, None
    p = successes / n
    den = 1 + z*z/n
    center = (p + z*z/(2*n)) / den
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / den
    return max(0.0, center-radius), min(1.0, center+radius)


def newcombe(both, second_only, first_only, neither):
    e, f, g, h = both, second_only, first_only, neither
    if min(e, f, g, h) < 0:
        raise ValueError("negative paired count")
    n = e+f+g+h
    if not n:
        return None, None
    p2, p1 = (e+f)/n, (e+g)/n
    l2, u2 = wilson(e+f, n)
    l1, u1 = wilson(e+g, n)
    den = math.sqrt((e+f)*(g+h)*(e+g)*(f+h))
    numerator = e*h-f*g
    if numerator > 0:
        numerator = max(numerator-n/2, 0)
    phi = numerator/den if den else 0.0
    low = math.sqrt(max(0, (p2-l2)**2+(u1-p1)**2-2*phi*(p2-l2)*(u1-p1)))
    high = math.sqrt(max(0, (u2-p2)**2+(p1-l1)**2-2*phi*(u2-p2)*(p1-l1)))
    return max(-1.0, p2-p1-low), min(1.0, p2-p1+high)


def mcnemar_midp(second_only, first_only):
    b, c = second_only, first_only
    if min(b, c) < 0:
        raise ValueError("negative discordant count")
    n = b+c
    if not n:
        return 1.0
    k = min(b, c)
    if b == c:  # Fagerland et al. (2013): the two tails overlap at the centre, so mid-p = 1 - P(X = k)/2
        return 1 - math.comb(n, k)/2**(n+1)
    return min(1.0, (2*sum(math.comb(n, i) for i in range(k+1))-math.comb(n, k))/2**n)


def holm(pvalues):
    """Keep the planned family size, including unavailable tests represented by None."""
    result = [None]*len(pvalues)
    largest = 0.0
    for rank, (p, index) in enumerate(sorted((p, i) for i, p in enumerate(pvalues) if p is not None)):
        if not 0 <= p <= 1:
            raise ValueError("p-value outside [0,1]")
        largest = max(largest, (len(pvalues)-rank)*p)
        result[index] = min(1.0, largest)
    return result


def agreement(left, right):
    """Exact nominal agreement; structured values are canonical JSON, not semantic labels."""
    if len(left) != len(right):
        raise ValueError("agreement vectors differ in length")
    encode = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    a, b = [encode(x) for x in left], [encode(x) for x in right]
    n = len(a)
    counts = Counter(zip(a, b))
    contingency = [{"left": json.loads(x), "right": json.loads(y), "n": v}
                   for (x, y), v in sorted(counts.items())]
    if not n:
        return {"n": 0, "agreement": None, "kappa": None, "contingency": contingency}
    pa, pb = Counter(a), Counter(b)
    observed = sum(x == y for x, y in zip(a, b))/n
    expected = sum(pa[x]*pb[x] for x in set(a+b))/(n*n)
    kappa = (observed-expected)/(1-expected) if expected < 1 else None
    return {"n": n, "agreement": observed, "kappa": kappa, "contingency": contingency}


def quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered)-1)*q
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo] + (ordered[hi]-ordered[lo])*(index-lo)


def pooled(deltas, seed=20261115, resamples=10000, sign_test=True):
    """Topic-level bootstrap and sign flips; each delta is already a model mean."""
    if not deltas:
        return {"n": 0, "nonzero": 0, "mean": None, "ci_low": None, "ci_high": None, "p_value": None}
    if resamples < 1:
        raise ValueError("resamples must be positive")
    n = len(deltas)
    observed = statistics.mean(deltas)
    bootstrap_rng, sign_rng = random.Random(seed), random.Random(seed+1)
    bootstrap = [sum(deltas[bootstrap_rng.randrange(n)] for _ in range(n))/n for _ in range(resamples)]
    exceed = sum(abs(sum(x if sign_rng.getrandbits(1) else -x for x in deltas)/n) >= abs(observed)-1e-12
                 for _ in range(resamples)) if sign_test else None
    return {"n": n, "nonzero": sum(1 for x in deltas if x != 0), "mean": observed, "ci_low": quantile(bootstrap, .025),
            "ci_high": quantile(bootstrap, .975), "p_value": (exceed+1)/(resamples+1) if sign_test else None}

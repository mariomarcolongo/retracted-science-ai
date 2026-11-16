"""Power check for the paired comparisons (Methods, section 3.6).

Usage: python3 -I code/power.py

Standard library only; fixed seeds, so the output is the same on every run (about two minutes).

Per model: n topics, each answered in two tests (e.g. R3 and R4). A pair is discordant when only one
test fails. d1 = share of topics failing only in the second test, d2 = only in the first. The true
difference is d1 - d2. Tests: McNemar exact conditional and mid-p (Fagerland et al. 2013), two-sided,
at alpha 0.05 and at 0.05/9 (the strictest Holm step across nine models).

Across models: nine models answer the same topics. Each topic has its own baseline failure rate
(Beta(2, 8), mean 0.2); four models are unaffected and five carry the effect, so the average change
across models equals the stated value. For each topic the change (+1 / 0 / -1 per model) is averaged
over the nine models; the test is a two-sided sign-flip permutation test on the topic averages, at
alpha 0.05 and at 0.025 (the stricter Holm step across the two primary comparisons, R3-R4 and K3-K4).
These are assumptions for planning, not estimates from data.

Baseline sensitivity (D68): the same across-model simulation with other baseline failure rates. A change can only
be as large as the room the baseline leaves: when nearly every answer already fails in the first test, a forged
note cannot raise the failure rate, whatever its true effect. The last table prints, for each baseline, the change
that is actually realised and the power at 0.025. Baselines: Beta(0.3, 9.7), mean 0.03 (a test in which failure is
rare, as expected for K3 and for a labelled copy, R5); Beta(8, 2), mean 0.8, and Beta(19, 1), mean 0.95 (a test in
which most answers already fail, as R3 would be if models rarely look up an unlabelled paper).
"""
import math, random, statistics


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def mcnemar_midp(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    cdf = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * cdf - math.comb(n, k) / 2 ** n)


def per_model_power(n, diff, reverse, alpha, test, sims=4000, seed=1):
    rng = random.Random(seed)
    d1, d2 = diff + reverse, reverse
    hits = 0
    for _ in range(sims):
        b = c = 0
        for _ in range(n):
            u = rng.random()
            if u < d1:
                b += 1
            elif u < d1 + d2:
                c += 1
        hits += test(b, c) < alpha
    return hits / sims


def sign_flip_p(values, flips, rng):
    obs = abs(statistics.mean(values))
    count = 0
    for _ in range(flips):
        m = abs(statistics.mean(v if rng.random() < 0.5 else -v for v in values))
        count += m >= obs - 1e-12
    return (count + 1) / (flips + 1)


def pooled_power(n, avg, alpha=0.05, sims=400, flips=999, seed=2, baseline=(2, 8), realised=False):
    rng = random.Random(seed)
    effects = [0.0] * 4 + [avg * 9 / 5] * 5
    hits, means = 0, []
    for _ in range(sims):
        topic_changes = []
        for _ in range(n):
            base = rng.betavariate(*baseline)
            change = 0
            for e in effects:
                change += (rng.random() < min(1.0, base + e)) - (rng.random() < base)
            topic_changes.append(change / 9)
        means.append(statistics.mean(topic_changes))
        hits += sign_flip_p(topic_changes, flips, rng) < alpha
    return (hits / sims, statistics.mean(means)) if realised else hits / sims


if __name__ == "__main__":
    print("Per model (reverse discordance 5%): n, true difference, power")
    print("n   diff  exact@.05  mid-p@.05  mid-p@.05/9")
    for n in (25,):  # the study size: 25 pairs (D64)
        for diff in (0.2, 0.3, 0.4):
            print(f"{n}  {diff:.2f}  {per_model_power(n, diff, .05, .05, mcnemar_exact):9.2f}"
                  f"  {per_model_power(n, diff, .05, .05, mcnemar_midp):9.2f}"
                  f"  {per_model_power(n, diff, .05, .05 / 9, mcnemar_midp):11.2f}")
    print("\nAcross nine models (4 unaffected, 5 affected): n topics, average change, power (sign-flip)")
    print("n   change  @.05  @.025")
    for n in (25,):  # the study size: 25 pairs (D64)
        for avg in (0.05, 0.10, 0.15):
            print(f"{n}  {avg:.2f}   {pooled_power(n, avg):.2f}  {pooled_power(n, avg, alpha=0.025):.2f}")
    print("\nBaseline sensitivity, across nine models, 25 topics, @.025: baseline failure rate, intended change,"
          " realised change, power")
    for label, baseline in (("0.03", (0.3, 9.7)), ("0.20", (2, 8)), ("0.80", (8, 2)), ("0.95", (19, 1))):
        for avg in (0.10, 0.15):
            power, change = pooled_power(25, avg, alpha=0.025, baseline=baseline, realised=True)
            print(f"{label}  {avg:.2f}  {change:+.3f}  {power:.2f}")

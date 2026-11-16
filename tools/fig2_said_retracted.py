"""Figure 2: share of papers each model called "retracted", retracted papers vs valid controls (main sample).
Reads results/status-question/status-only/outcomes.jsonl; writes paper/figures/fig2-said-retracted.svg."""
import json, math
ORDER = ["Claude Sonnet 5.5", "Gemini 4 Hydrogen", "Gemini 3.5 Flash-Lite", "Seed 2.0 Lite", "ERNIE 5.5 Flash Preview",
         "GPT-6.1 Sol", "GPT-6 Luna", "DeepSeek V4.1 Flash 1017", "Qwen3.8 Flash"]
rows = [json.loads(l) for l in open("results/status-question/status-only/outcomes.jsonl")]
def wilson(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)
data = {}
for m in ORDER:
    for side in "RK":
        a = [r for r in rows if r["sample"] == "main" and r["model_name"] == m and r["side"] == side and r["usable"]]
        k = sum(r["asserted_status"] == "retracted" for r in a)
        data[m, side] = (k, len(a), *wilson(k, len(a)))
W, L, R, T, RH = 680, 190, 30, 44, 30
H = T + RH * len(ORDER) + 46
x = lambda v: L + v * (W - L - R)
s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif" font-size="12">',
     f'<rect width="{W}" height="{H}" fill="#fff"/>']
for v in (0, .25, .5, .75, 1):
    s.append(f'<line x1="{x(v):.1f}" y1="{T-8}" x2="{x(v):.1f}" y2="{T+RH*len(ORDER)}" stroke="#ddd"/>')
    s.append(f'<text x="{x(v):.1f}" y="{T+RH*len(ORDER)+16}" text-anchor="middle" fill="#444">{int(v*100)}%</text>')
s.append(f'<text x="{(L+W-R)/2:.0f}" y="{H-8}" text-anchor="middle" fill="#222">Share of papers the model called "retracted"</text>')
s.append(f'<circle cx="{L}" cy="18" r="5" fill="#b42318"/><text x="{L+10}" y="22" fill="#222">retracted papers</text>')
s.append(f'<circle cx="{L+140}" cy="18" r="5" fill="#fff" stroke="#1f4e9c" stroke-width="2"/><text x="{L+150}" y="22" fill="#222">valid controls</text>')
for i, m in enumerate(ORDER):
    y = T + RH * i + RH / 2
    s.append(f'<text x="{L-10}" y="{y+4:.1f}" text-anchor="end" fill="#222">{m}</text>')
    for side, dy, col, fill in (("R", -5, "#b42318", "#b42318"), ("K", 5, "#1f4e9c", "#fff")):
        k, n, lo, hi = data[m, side]
        s.append(f'<line x1="{x(lo):.1f}" y1="{y+dy:.1f}" x2="{x(hi):.1f}" y2="{y+dy:.1f}" stroke="{col}" stroke-width="1.5"/>')
        s.append(f'<circle cx="{x(k/n):.1f}" cy="{y+dy:.1f}" r="4.5" fill="{fill}" stroke="{col}" stroke-width="2"><title>{m}, {"retracted papers" if side=="R" else "controls"}: {k}/{n}</title></circle>')
s.append("</svg>")
open("paper/figures/fig2-said-retracted.svg", "w").write("\n".join(s))
for m in ORDER: print(m, data[m, "R"][:2], data[m, "K"][:2])

# Status-question results

Offline analysis of the nine tested API configurations. Main sample: 25 pairs; pilot: 3 separate pairs. 504 terminal runs, 503 usable answers. One Qwen control answer in the main sample was cut off without usable text.

Counts below are correct / incorrect / uncertain. Operational missing answers are excluded from these denominators and reported separately in rates.csv. “Correct” is relative to the sampled status classification; control status is bounded by the screening and registry snapshot.

## Main sample

| Model | Retracted papers: C / I / U | Control papers: C / I / U |
|---|---:|---:|
| Claude Sonnet 5.5 | 0 / 0 / 25 (n=25) | 0 / 0 / 25 (n=25) |
| DeepSeek V4.1 Flash 1017 | 24 / 1 / 0 (n=25) | 0 / 25 / 0 (n=25) |
| ERNIE 5.5 Flash Preview | 8 / 0 / 17 (n=25) | 2 / 6 / 17 (n=25) |
| GPT-6 Luna | 21 / 4 / 0 (n=25) | 12 / 13 / 0 (n=25) |
| GPT-6.1 Sol | 15 / 0 / 10 (n=25) | 0 / 13 / 12 (n=25) |
| Gemini 3.5 Flash-Lite | 0 / 13 / 12 (n=25) | 14 / 0 / 11 (n=25) |
| Gemini 4 Hydrogen | 0 / 1 / 24 (n=25) | 0 / 0 / 25 (n=25) |
| Qwen3.8 Flash | 25 / 0 / 0 (n=25) | 1 / 23 / 0 (n=24) |
| Seed 2.0 Lite | 4 / 21 / 0 (n=25) | 23 / 2 / 0 (n=25) |

## Pilot sample

| Model | Retracted papers: C / I / U | Control papers: C / I / U |
|---|---:|---:|
| Claude Sonnet 5.5 | 0 / 0 / 3 (n=3) | 0 / 0 / 3 (n=3) |
| DeepSeek V4.1 Flash 1017 | 3 / 0 / 0 (n=3) | 0 / 3 / 0 (n=3) |
| ERNIE 5.5 Flash Preview | 1 / 0 / 2 (n=3) | 0 / 1 / 2 (n=3) |
| GPT-6 Luna | 2 / 0 / 1 (n=3) | 2 / 1 / 0 (n=3) |
| GPT-6.1 Sol | 3 / 0 / 0 (n=3) | 0 / 1 / 2 (n=3) |
| Gemini 3.5 Flash-Lite | 0 / 0 / 3 (n=3) | 3 / 0 / 0 (n=3) |
| Gemini 4 Hydrogen | 0 / 0 / 3 (n=3) | 0 / 0 / 3 (n=3) |
| Qwen3.8 Flash | 3 / 0 / 0 (n=3) | 0 / 3 / 0 (n=3) |
| Seed 2.0 Lite | 0 / 3 / 0 (n=3) | 3 / 0 / 0 (n=3) |

## Reading the retracted-paper column

Every retracted paper in both samples was retracted between 2026-07-02 and 2026-11-07, after every published training cutoff (the latest is June 2026). Four models publish no cutoff: Seed 2.0 Lite (released 10 Mar 2026), Qwen3.8 Flash (26 Aug 2026), DeepSeek V4.1 Flash (10 Sep 2026, updated 17 Oct) and ERNIE 5.5 Flash (11 Nov 2026); for the last three, exposure to some of these retractions cannot be ruled out. For models with a published cutoff, a “correct” answer on a retracted paper cannot reflect knowledge of the notice; for the others it is unlikely to, and a retraction year before 2026 is wrong in every case. For papers retracted after the cutoff, “uncertain” is the expected well-calibrated answer on both sides. The same holds in the other direction: a definite “not retracted” cannot reflect knowledge of the current record either, so a model that says “not retracted” to everything scores well on controls and fails every retracted paper (false reassurance). The informative comparison is how often a model calls a paper retracted when it is retracted versus when it is a control: similar rates mean no discrimination.

| Model | Called retracted: retracted papers | Called retracted: control papers | Both correct (pairs) |
|---|---:|---:|---:|
| Claude Sonnet 5.5 | 0/25 | 0/25 | 0/25 |
| DeepSeek V4.1 Flash 1017 | 24/25 | 25/25 | 0/25 |
| ERNIE 5.5 Flash Preview | 8/25 | 6/25 | 1/25 |
| GPT-6 Luna | 21/25 | 13/25 | 9/25 |
| GPT-6.1 Sol | 15/25 | 13/25 | 0/25 |
| Gemini 3.5 Flash-Lite | 0/25 | 0/25 | 0/25 |
| Gemini 4 Hydrogen | 0/25 | 0/25 | 0/25 |
| Qwen3.8 Flash | 25/25 | 23/24 | 1/24 |
| Seed 2.0 Lite | 4/25 | 1/25 | 4/25 |

Main sample only; denominators are non-refusal usable answers. “Both correct” counts pairs where the retracted paper is called retracted and its control not retracted (both_correct.csv, with Wilson intervals).

## Scoring and limitations

The author resolved 21 asserted-status disagreements categorically; no written rationales were collected. No disagreements on refusal or conflicting assertions required adjudication. The original independent 36-answer human check is preserved separately from adjudication.

Human agreement on asserted status against the final label, which the frozen D66 gate uses: 36/36 (kappa 1.00); against each raw judge: judge 1 36/36 (kappa 1.00), judge 2 35/36 (kappa 0.96). Refusal: judge 1 36/36 (kappa undefined), judge 2 36/36 (kappa undefined); conflicting assertions: judge 1 36/36 (kappa undefined), judge 2 36/36 (kappa undefined) (kappa is undefined where labels are constant). This meets the pre-existing pooled human-check rule, but does not independently verify every answer or factual claim.

Raw judge agreement on asserted status is 482/503 (kappa 0.94). Uncertainty and no stated status map to the uncertain outcome under the existing scoring rule. Refusals and unusable answers are operational missing, not uncertain.

The dedicated status-only workflow leaves 429 ancillary disagreements unresolved: source 204, claimed checks 159, notice details 66. No ancillary outcomes are reported or implicitly settled. Omission of written rationales and separation from the original full-form pipeline are disclosed workflow changes.

Per-model, per-side Wilson 95% intervals are in rates.csv. Main and pilot are not pooled. High accuracy on retracted papers alone does not establish discrimination: a model can call controls retracted too. These results do not establish absence of training knowledge and do not evaluate simulated retrieval, tools or forged notices.

Reproduce: `python3 -I code/status_only.py`. Input hashes are recorded in manifest.json. No paid calls or external retrieval are needed.

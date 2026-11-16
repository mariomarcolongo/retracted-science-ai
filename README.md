# Do AI assistants notice retracted science?

A controlled study of how nine AI model configurations use scientific papers when search results contain retraction labels or forged publication-status claims. The core tests ask whether assistants check an available registry and whether their answers follow its evidence.

**Status: work in progress (AI x Epistemics Research Sprint, 13–15 November 2026).** The method is still being finalised; every design decision and correction is logged with its date and source in [`DECISIONS.md`](DECISIONS.md) and [`CHANGELOG.md`](CHANGELOG.md). Counts in this repository are provisional until screening is complete.

## What is tested

| Test | What the model sees |
|---|---|
| R1–R4 | A retracted paper: unlabelled, labelled, with a registry lookup tool, or with a forged "reinstated" note |
| R5–R6 | A retracted paper with its true retraction label and the tool: alone, or followed by a forged "reinstated" note |
| K3–K4 | A paper not retracted (as of the snapshot date): with the tool, or with a forged "retracted" note |
| R4-I, K4-I | R4 and K4 again, with one instruction in the system prompt to check status with the tool |

Everyday questions, consumer-app checks, reasoning-effort comparisons and other languages are reserved for future work. The two main comparisons each add one forged status line to a result whose status information is true: R5 against R6 (fake reinstatement on a labelled retracted paper) and K3 against K4 (fake retraction on a paper with no notice). The design to be frozen before the main run is in [`FROZEN_DESIGN.md`](FROZEN_DESIGN.md).

## Repository layout

| Path | Contents |
|---|---|
| `paper/` | Paper draft (Markdown source) |
| `code/` | Study code, Python standard library only: candidate pool, draw and controls, knowledge check, topic drafting, items, test runner, judges, scoring, costs and analysis; full run order in `code/RUN_ORDER.txt` |
| `tools/` | Paper tooling, not needed to reproduce the study: HTML view of the draft, reference checks |
| `data/work/` | Candidate pool with OpenAlex and PubMed metadata; `candidates.csv`; the main draw (`draw/`) and the pilot draw (`pilot/`) with screening sheets, controls and API caches |
| `data/snapshots/` | OpenRouter model catalogue snapshot, 13 Nov 2026, and endpoint snapshots (`endpoints/`) |
| `tests/` | Offline tests of the pipeline (no network, no API key): `python3 -I tests/run_all.py` |
| `data/costs/` | Cost and time of the study: per-request costs, totals, estimate vs actual, credits, author hours, software environment (filled during and after the runs; field guide in its README) |
| `data/raw/` | Not committed: Retraction Watch data (pinned download URL and SHA-256 in `code/RUN_ORDER.txt`) |

## Reproduce

Python 3, standard library only; no API keys are needed for the pool steps. Run from the project folder.

1. Download the Retraction Watch data from the pinned URL in `code/RUN_ORDER.txt` to `data/raw/retraction_watch.csv` and check its SHA-256.
2. Run steps 2–5 of `code/RUN_ORDER.txt`. They rebuild the candidate pool and print each filtering step.
3. Power check for the analysis plan (Methods §3.6): `python3 -I code/power.py` (about a minute; fixed seeds, same output every run).
4. Draw, screening and controls, knowledge check, topic drafting, items, pilot, main and stability runs, scoring, costs and analysis: sections B–H of `code/RUN_ORDER.txt`, one command per step. Steps that call models need an OpenRouter API key in `OPENROUTER_API_KEY`; scoring and analysis outputs go to `results/`.

OpenAlex citation counts change over time, so step 3 of the run order can give slightly different counts than ours (queried 14 Nov 2026). Our outputs are kept in `data/work/`.

## Data sources

Retraction Watch data via Crossref; OpenAlex; PubMed (NCBI E-utilities); OpenRouter model catalogue.

## Responsible release

Every log is released in full, including the forged status notes exactly as the models saw them. Each record that contains a forged note says so and gives the paper's true status, and every data file carries a canary string asking that it not be used to train models. Abstracts are included as text where the article's licence allows; for the others, the source, ID and hash are released with a script that restores the exact text.

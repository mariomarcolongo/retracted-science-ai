# Continuation checkpoint — 16 November 2026

## User objective and constraints

Produce scientifically defensible, reproducible and auditable research. User is a
solo author, cannot independently audit the code, and prioritizes validity over
rushing a large run. They explicitly prefer resetting the assistant's usage limit
over losing quality. Current thinking setting was reported by the user as High.
Do not mistake AI review or synthetic tests for independent human validation.

Competition deadline confirmed by the user and the official page: **16 November
2026, 12:59 Europe/Rome (11:59 UTC)**. Unfinished work is allowed; report only work
actually completed. Keep time for an accurate PDF and submission.
Source: https://apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15

The prior Fable/Claude session was scheduled to resume at 06:51 local. User accepted
Codex taking over, but did not separately confirm disabling that session. Avoid
simultaneous writers; recheck file state if it resumes. No external messages or
submissions have been sent by this Codex chat. No paid calls have been authorized
as a specific budget in this chat or executed by this continuation.

## Completed in this continuation (D69)

- Fixed the failing check-run fixture: two distinct model IDs shared one name,
  mixing their logs. Fixture names are now distinct; duplicate manifest names fail.
- Run-check output no longer claims missing service-tier information is verified.
  Partial pricing and invalid-only lookups stay NOTE. Price anomalies require
  investigation without diagnosing a service tier. Incomplete/duplicate terminal
  counts fail. Exit 0 explicitly means no failed checks, not full readiness.
- Added `tests/test_d68.py`: R5/R6 differ only by the forged update, at every target
  position; missing/duplicated notices fail prechecks; registry truth is unchanged.
  Existing `test_planted.py` already checks R5/R6 scoring and statistical effects.
- Added `FROZEN_DESIGN.md`, explicitly DRAFT with pending pilot/item/freeze fields.
- Moved stability selection before main runs in RUN_ORDER, matching the protocol.
- Corrected Appendix C: November 16 local is not automatically after the deadline.
  Model-run dates remain pending; do not invent completed work.
- Corrected D68's premature completion claims; recorded D69 and changelog updates.
- Created `data/work/check_items.json`: 28 pairs / 56 papers for auxiliary SQ checks.
- Created `results/estimate.csv` using pinned snapshots. Whole-study estimates:
  low $60.44 / middle $157.69 / high $363.40. Knowledge check + its judging + all
  topic drafting alone: middle $7.40 / high $16.50. Assumptions, not a live quote.
- Automated text/type scan of 56 selected papers found no missing abstracts,
  retraction/reinstatement words, or control PubMed retraction-type flags. This is
  not verification of every article's full provenance or scientific suitability.
- Verified registry SHA-256 matches RUN_ORDER. Config hash is in FROZEN_DESIGN.

Validation: `python3 -I tests/run_all.py` => **118 tests, OK**, 40.169 s.
Local log: `/tmp/retracted-science-repair-tests.log`.
Only synthetic offline calls; all test inputs are temporary. No real API run.

## Current readiness

Selected main and pilot targets/controls exist. No topics, alternative-result
packets, final items, auxiliary live check, live pilot, scored empirical results,
public freeze, or main run have been completed in this continuation. The paper is
a working protocol with placeholders, not a completed empirical paper.

`OPENROUTER_API_KEY` is absent in the execution shell. Do not print or request the
key in chat or logs. Arrange secure local configuration before any paid command.
No credential values were read in this continuation.

Scientific cautions to retain:
- These are fixed API configurations and supplied evidence, not consumer apps.
- Absence of a registry notice is not universal proof of non-retraction; controls
  are defined against the stated snapshot and screening sources.
- The primary contrast changed before model results. Retain the documented reason;
  do not change outcomes or model selection to obtain significance.
- 25 topics give limited per-model precision. Power simulations are assumption-
  dependent; they are not an assurance of a significant result.
- The human check is 180 experimental + 36 status answers, plus adjudication.
  Timing is unmeasured. Do not silently replace author checks with AI approvals.
- A model that never calls the tool leaves its tool path untested; a separate
  plumbing check must stay outside experimental results.
- The live-run checker is a diagnostic, not proof of exact endpoint identity,
  provider billing behavior, or complete scientific validity.
- Five stability pairs remain the protocol; no extra conditions were added here.

## Next actions, in order

1. Confirm one active writer and secure API configuration; agree a bounded paid
   preparation budget. Do not launch the main run on the basis of offline tests.
2. Follow RUN_ORDER C: auxiliary status check on 56 papers (five auxiliary models,
   280 planned answers), judging, author resolution of disagreements/replacements.
   Existing commands use $5 and $10 scheduling guards. These are not hard billing
   caps; inspect cost logs before restarting or raising them.
3. Draft the six pilot topics first; author checks topic wording and fit of the
   four alternative results for each. Main topic drafting can follow once the
   drafter knowledge check is resolved. Never fill author checkboxes on their behalf
   merely to unblock the runner.
4. Build pilot items, exercise live paths, score and manually inspect a matched
   pair end-to-end. Measure latency, actual cost, missing replies, target use and
   annotation burden. Resolve genuine failures before scaling.
5. Decide submission scope from observed feasibility. Full main run alone is
   2,700 answers (including status questions), before pilot/stability and judging.
   Preserve report/submission time. A pilot-only report must remain pilot-only;
   a three-pair pilot cannot support the main-study power claims.
6. Finalize and publicly timestamp the freeze before any main run. Review the
   license-aware release process before publishing data/ or logs. No remote is
   currently configured. Local checkpoint should exclude data/, results/, private/
   and credentials; preserve these local files rather than deleting anything.

## Checkpoint

Initial local code/document/test commit: pending at the time this file was written;
check `git log -1` for the completed checkpoint. No push or public release authorized
or performed by this continuation. Data and estimates remain local and untracked.

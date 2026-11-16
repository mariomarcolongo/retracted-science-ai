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
submissions have been sent by this Codex chat. User expressed willingness to spend if the trade-off is positive after the $20
preparation proposal. Codex explained the expected benefit and proceeded with the
first $5-guard auxiliary stage. The provider rejected it before any answers
completed; see the current execution status at the end of this file.

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

`OPENROUTER_API_KEY` is absent in the execution shell, but the runner's fallback
file `~/.config/retracted-science-ai/openrouter.key` exists and is nonempty. Only
existence/size were checked; no credential values were printed or read. The runner
can load this file. Do not ask the user to paste a key. The preparation-stage target is $20 (knowledge check, judging, drafting only).
No pilot or main run has been authorized by this continuation.

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

Initial local code/document/test checkpoint: `e7bcba3` (118 offline tests passed).
No push or public release authorized or performed by this continuation. Data and
estimates remain local and untracked. A public metadata-only endpoint check also
found all 14 pinned endpoints (nine tested plus drafter, judges and backups).
Record: `results/live_endpoint_preflight.json`. This is availability metadata, not
a successful inference/tool roundtrip. No authenticated or paid call was made.

## Live price discrepancy found before any spending

Public endpoint metadata lists DeepSeek V4.1 Flash 1017 at $0.30 input / $1.20
output per million tokens, versus $0.15 / $0.60 in the saved endpoint snapshot.
Other selected endpoint prompt/completion prices matched their snapshots. Preserve
the old snapshot; resolve/update the pricing basis before the main run and before
using check_run price comparisons for DeepSeek. Do not diagnose this as a tier
change solely from the price difference.

Current endpoint metadata is saved separately in `results/endpoints-current/`.
`results/estimate-current.csv` gives low $61.08 / middle $159.69 / high $368.71,
with the same token assumptions. Auxiliary preparation remains $7.40 / $16.50.
These are expected costs, not caps. No live inference calls have been made.

## Current execution status: auxiliary check stopped by provider (HTTP 402)

The first live attempt used:

```sh
python3 -I code/run_tests.py data/work/check_items.json data/logs/knowledge_check --phase knowledge_check --roles aux --tests SQ --budget 5
```

Run ended at approximately 02:38 UTC (03:38 Rome), 16 Nov. Ten already-in-flight
requests received HTTP 402; the account-stop safeguard stopped further work.
**0/280 terminal model answers. No recorded charge in returned usage.** Provider
error classification mentions needing more credits / max_tokens. The key file
exists; do not expose its contents or the full account error in chat.

The console's `$2.50 spent` is ten $0.25 conservative reservations for requests
whose cost is unknown, NOT confirmed billing. Do not report it as actual spend or
claim definitively that billing was zero. Logs must be preserved. On resume the
budget reconstructs these reservations; do not delete logs to reset the guard.
Review scheduling allowance if it pauses because of those retained reservations,
while keeping total preparation within the agreed $20 target.

User was asked through the async question tool to resolve the OpenRouter funding
or key-credit limit and report readiness, without sharing credentials/account
information. **This is the current dependency. Do not keep retrying 402.** Do not
lower MAX_TOKENS merely to bypass it: that changes the configured experiment.

After the user resolves it, resume the SAME command and log directory. Inspect
completion and actual costs before launching `judge.py --budget 10`; then apply
`knowledge_check.py`, resolve author decisions, and prepare pilot topics first.
No judge calls, topic drafting, live pilot or main run have started.

Console: `/tmp/retracted-knowledge-run-console.log`.
Persistent audit records: `data/logs/knowledge_check/` (local, untracked).

## Funding resolved; auxiliary run resumed

User reported purchasing the credits. Resumed the same auxiliary command with
`--budget 5`; session 83943 in this chat. Live HTTP 200 responses and usable
answers are now arriving. Earlier 402 logs and conservative reservations remain
intact. Judge/drafting still pending. Check running processes and logs before
resuming again. No pilot or main-run authorization.

### Resume allowance adjustment
First funded attempt stopped at 10/280 because retained $2.50 reservations plus
concurrent request reserves triggered the $5 guard. Recorded real usage was
$0.0415; no logs removed. Resumed with --budget 8, session 17040. Overall
preparation target stays $20, including later judging/drafting. Pilot target
drafting also started (configured MiMo, --budget 0.5); provisional until drafter
eligibility is resolved, as permitted by D61. Never run target/control drafting
concurrently in the same draw directory.

## Current continuation after user said “bought” and “continue”

- User wants to WAIT for the knowledge-check result before reviewing pilot topics.
- All 56 topics have been drafted by configured MiMo (50 main + 6 pilot). No author
  checkboxes filled. CSVs: data/work/{draw,pilot}/topic_check.csv.
- Pilot review UI: results/pilot-topic-review.html. Export was smoke-tested using
  synthetic values (six rows, CSV quoting/newlines, incomplete-review refusal);
  actual author CSV unchanged. Do not import /tmp synthetic export as human review.
- Auxiliary runner session 17040 uses --budget 8 (includes prior $2.50 conservative
  reservations, not confirmed charges); nearly finished at 03:07 UTC.
- First judging session 6994 uses --budget 10. It captured 246 answers at startup;
  it must be resumed to judge the remaining answers. GLM finished that batch; Grok
  is slower. Do not interrupt in-flight paid calls merely to speed it up.
- **Coordinator session 9671 is already running**. It waits for BOTH runner and
  first judging locks to release, verifies all 280 terminal answers, resumes the
  SAME judge directory at --budget 10, then runs knowledge_check.py. It stops
  there; it does not approve author decisions, run a pilot or launch the main run.
  Script: /tmp/retracted-finish-preparation.py (copy in results/).
  Logs: /tmp/retracted-preparation-coordinator.log,
  /tmp/retracted-knowledge-judge-final.log, /tmp/retracted-knowledge-result.log.
  Do not start duplicate judges/coordinators. Read existing state first.
- All four drafting commands finished (each --budget 0.5, logdirs under
  data/logs/drafting/). Latest saved cost snapshot: results/preparation-progress.json
  at 03:03:57 UTC showed $2.3501 known costs total, not including unknown reserves.
  Recompute before reporting final cost.
- Next required author action may be knowledge_decisions.csv if judges disagree.
  Then pilot topic review, alternative-result fit review, pilot build/live validation.
  Do not silently perform author labels or checks in the user's name.

## FINAL PREPARATION CHECKPOINT — author decisions required

All running preparation processes finished (runner 17040, judge 6994, coordinator
9671). No automatic pilot/main continuation exists. Auxiliary check has 280/280
usable terminal answers; both judges returned valid forms for all answers (560).
The knowledge-check script stopped as designed at **28 author disagreements**:
27 refusal versus not-called-retracted, one called-retracted versus not-called.
**No model keep/replace decision is final yet.** Do not call this a passed check.

Author CSV: data/logs/knowledge_check/knowledge_decisions.csv (all decisions blank).
Readable author UI: results/knowledge-decisions-review.html. It exports
knowledge-decisions-reviewed.csv; source CSV is unchanged. Model names and true
paper statuses hidden. No decisions prefilled. UI script syntax checked; previous
pilot UI export was tested with synthetic values only.

User explicitly chose to wait for knowledge-check result before reviewing pilot
topics. Next: ask them to review these 28 answers, export the CSV and report its
path. Validate that codes/questions/answers match, only valid decisions are filled,
and archive the original before importing. Then rerun code/knowledge_check.py.
If a drafter/judge is replaced, follow the actual rule and preserve old outputs;
do not quietly approve current drafts or labels. If kept, pilot topic review can
proceed using results/pilot-topic-review.html (six rows). Main review still has
50 drafts. No author checks completed, no final evidence packets built.

Final known inference charges across the auxiliary check, both judges and all
56 topic drafts: **$4.1764** (see results/preparation-progress.json for exact sum).
Separate old unknown-cost reservations from ten HTTP 402 responses: $2.50; not
confirmed charges. Do not include purchase fees/VAT in inference usage totals.
Auxiliary run diagnostic: results/knowledge-run-check.txt (no FAIL; NOTE metadata
checks remain unverified). No tested-model pilot or main run, no public freeze,
no submission, no publication. The funded preparation target remains $20.

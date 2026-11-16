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

## Author adjudication update

User agreed to not-called-retracted for the original 28 under a definition that
separates declining the task from uncertainty. User explicitly discussed #12
(promise to check, no follow-up: status not stated) and corrected #28 (explicit
not retracted). Entered all 28 with provenance and per-case reasons; preserved
original CSV. Running knowledge_check.py gives provisional KEEP for all five.
An audit also found SIX answers where BOTH judges marked refusal AND uncertain;
these contain the same cannot-verify language. Raw judgments unchanged. Review:
results/knowledge-consensus-review.md. Author decisions for these six are pending;
do not label this a fully resolved classification check. Current parser only
adjudicates disagreements; any consensus correction needs a transparent override
mechanism or documented recalibration, not silent raw-judge editing. No further
paid calls since the $4.1764 preparation total.

## D70 resolved and remaining work

User approved the six consensus cases as the same uncertainty-plus-verification
pattern. All 34 decisions are saved in knowledge_decisions.csv; originals and
author provenance preserved. knowledge_check.py now supports content-bound
consensus corrections and rejects stale codes; regression coverage added.
Knowledge check now has zero unanswered papers for each auxiliary model and KEEP
for all five. This means eligibility under the threshold, not demonstrated lack
of knowledge or general status accuracy. The author suggested uncertainty as a
behavioral outcome; retained separately in raw descriptive export
results/knowledge-raw-judge-statuses.csv (explicitly ORIGINAL judge assessments,
not corrected final labels). Author-reviewed subset: 32 uncertain, 1 not stated,
1 explicitly not retracted. No quantitative verification-advice coding added.
Future judge refusal instructions clarified in both forms; old auxiliary judgments
remain under their original saved form version. Do not resume judge.py into that
old directory using the new guide; no rejudging is needed for these adjudications.
D70 documented in paper/decisions/changelog. Next user action: six pilot topics
can now be reviewed in results/pilot-topic-review.html. Do not fill author checks
for them. No new paid calls; recorded total still $4.1764.

## Pilot topic review assistance

User said the six topics are too specialized for them to edit. Reviewed all six
against source abstracts and wrote results/pilot-topic-editorial-review.md plus
pilot-topic-revision-proposals.json. The HTML review page now shows plain-language
fields, specific source-matching concerns and proposed revisions in its editable
final-topic boxes. Original drafts retained; topic_check.csv unchanged; no boxes
checked. Proposals are AI-assisted editorial checks, not expert biomedical
validation. Four alternative papers have NOT been verified for any proposal.
Do not silently treat the new HTML values as approved or the prior original
drafts as all leading: microsurgery device and nanoparticles drafts were already
direction-neutral. User workload/domain-expertise limits need honest handling.

## Author objection: AI topic rewriting NOT adopted

User explicitly objected that Codex proposing/broadening all six topics changes
the methodology and may add bias. Acknowledge this, do not treat author-edit
permission as automatic authorization for a second AI drafter. Restored original
MiMo drafts in results/pilot-topic-review.html; source topic_check.csv unchanged
(zero final edits, zero criteria checked). Preserved proposals with NOT ADOPTED
labels. No proposals used in evidence packets or tested-model calls. The original
review workload/expertise problem remains unresolved: do not quietly rewrite
topics, certify specialist fit, or start a pilot with unreviewed materials. Any
change to topic-review roles/rules needs explicit prospective documentation and
a consistent rule across papers, not an ad hoc rescue of individual topics.

## Candidate standardized topic method v2 (not activated)

The author prioritized methodological strength, reproducibility and auditability,
and objected to conversation-context-dependent GPT rewrites. Prepared an exact
candidate prompt and procedure in protocol/topic-drafting-v2/: PROMPT.txt,
PROTOCOL.md, original-v1-template.txt and manifest.json. The method distinguishes
source fidelity, neutral premises, biological setting, incidental identifiers,
scope and format, then separately verifies alternative-paper relevance and the
four-paper packet's contribution without the target. Its literature mapping cites
Hoang Ha et al. Appendix C, Taslimi et al. Appendices F-G and WildBench, distinguishing
precedents from unvalidated additions. Does not claim expert or independent review.

Offline preparation only: results/topic-drafting-v2-candidate contains six exact
PREPARED_NOT_SENT request bodies (title/abstract only, neutral code outside body,
common system prompt, existing MiMo/provider, proposed temperature 0, top_p 1,
max_tokens 4000) and 36 blank Stage A criterion rows. A saved endpoint snapshot lists
these settings as supported; no new request acceptance has been tested. The prompt,
protocol, inputs and artifacts have hashes. Original pilot/main drafts, checks and
runner files were verified unchanged. No paid calls or new reviewer approvals.

Integration requirements are listed explicitly, including a newly confirmed gap:
other_results.py/build_items.py currently treat blank alternative-fit decisions as
acceptance. The candidate requires explicit approval and content-bound reviews.
Also separate provisional scope judgment before search from demonstrated alternative
availability after search. Do not run the existing scripts as if these changes are
implemented. Do not count development results as held-out validation: six pilot
drafts informed this prompt, and main v1 drafts plus auxiliary SQ answers exist.
No per-item conversational rescue, semantic rerolls, outcome-guided topic editing,
or automatic exclusions/replacements are authorized by this candidate package.

## Candidate v2.1: target must remain substantively usable

Author clarified that broadening must retain a genuine opportunity for the target
to be cited and used, consistent with the study's status-handling question.
Prepared protocol/topic-drafting-v2.1 and results/topic-drafting-v2.1-candidate;
v2 remains intact. Rule 5 and Stage A1 now require a principal reported target
analysis/finding to contribute directly to answering the question, not only share
background keywords. Added explicit prohibition on selecting or redrafting topics
using observed experimental citation/reliance rates. Same criterion for targets
and matched controls. Relevant articles may legitimately be rejected or omitted;
noncitation alone is not status recognition or proof of internal consideration.
Both version manifests verified; six updated requests unsent, 36 review decisions
blank. Active runner, original topics, and paper unchanged. No paid calls.

## D71 adopted and six v2.1 drafts completed

User approved using v2.1 and requested disclosure. Added isolated runner
code/draft_topics_v2.py, explicit optional sampling parameters in openrouter.chat
(other phases retain omitted defaults), and offline regressions for frozen input,
no semantic rerolls, resume recovery after an HTTP completion, and review preservation.
Full suite: 122 passed. Drafting tests use synthetic fixtures, not private local data.
Paper section 3.4, Appendix B (exact prompt), AI contribution disclosure, D71, run
order and freeze record updated; HTML regenerated with Python 3.13 (the renderer
uses syntax unsupported by the system Python 3.9). ADOPTION.md explains conversational
Codex involvement, author-reported GPT-6 Astra/High setting with unverified backend
revision, chronology and limits. Original prompts and all original drafts retained.

Six paid MiMo calls completed in data/logs/drafting-v2.1/pilot, costing $0.0061206816;
no unknown costs. Approximate cumulative preparation cost $4.182521. All six are
pending_scientific_review; 36 review decisions blank. All raw requests/responses and
source-bound review identities preserved. Read-only comparison:
results/pilot-topic-v21-comparison.html. Report: results/topic-development-v21-report.json.
The prevention premise is removed, but several topics remain narrow/multi-component;
no claim of scientific validation. No semantic rerolls, no main redrafting, no
verified alternatives or tested-model pilot/main execution. Next: assess draft
fidelity/scope and establish the scientific review role without misrepresenting
non-specialist or AI checks. New drafts MUST NOT enter the legacy five-checkbox
pipeline. Its blank-means-accepted alternative-fit behavior and missing Stage B
packet gate still need integration before final experimental materials.

## Author preference: concise disclosure, retained version history

Shortened the main-paper AI disclosure to GPT-6 Astra/High/Codex role, isolated
MiMo drafting, and availability of original/revised pilot outputs. Full provenance
(including interface-reported identity and context) remains in ADOPTION.md. The two
executed pilot draft sets are v1 and v2.1; intermediate v2 was never sent. Describe
comparisons as development evidence, not independent validation. No new calls.

## v2.1 documentary source screen completed

After author agreement to check both sides, read all six v2.1 titles, abstracts and
questions under the same criteria. Saved results/topic-v21-source-screen.md and
.json with exact source excerpts verified as substrings and source-bound question
hashes. All six focal papers (3 R, 3 K) directly contribute evidence to their own
question. Main concerns: narrow/multi-component scopes; possible P53-presupposition
in 10D131; possible cell-free vs cellular endpoint conflation in 3E1E72. F471E5's
human alveolar epithelial-cell description IS supported by its TITLE, even though
the abstract says A549. Do not flag that phrase as invented. Scope concerns do not
prove alternatives absent. This is contextual AI assistance, NOT formal pass/fail
or independent specialist review. No edits to drafts or the 36 blank decisions;
no calls, searches for alternatives, sampling exclusions or experimental runs.

## Retrieval bottleneck established; no alternative packets approved

User asked what to do. Added an explicit development-only retrieval mode to
other_results.py: input source/text hashes checked, separate DEVELOPMENT outputs,
blank is unreviewed, no fabricated author approval. Added a regression within
test_materials.py; 7 material and 22 D66 tests passed. Documented review-order
amendment BEFORE queries in protocol/topic-drafting-v2.1/FEASIBILITY-AMENDMENT.md.
Copied pilot metadata into data/work/pilot-v21-retrieval-feasibility. All six exact
v2.1 question searches returned ZERO OpenAlex records, before exclusions.

Official OpenAlex docs (https://help.openalex.org/api/searching/, checked today)
say unconnected words are ANDed. Fixed 12 diagnostic shorter queries before
execution, saved results/topic-retrieval-diagnostic-plan.json. Counts central/broad:
1160E2 22/37630; 3E1E72 1306/9275; F471E5 113/4384; 10D131 22/841; DDC269 70/574;
C643C6 4/16. These are RAW matches, not eligible/relevant alternatives; examples
include focal papers, retracted papers and tangential works. Context-informed
manual probes are NOT a final selection procedure. Raw responses and exact URLs
are saved, with summary in results/topic-retrieval-feasibility.md. No paid model
calls, topic edits, formal review approvals, pair exclusions or experiments.

Recommended next action: keep MiMo and current questions provisionally; define a
standardized, logged question-to-keyword/Boolean-query procedure before a new
retrieval pass. Do not blindly use full sentences as OpenAlex AND queries or
claim that zero results mean no alternatives exist. This is a real protocol
amendment, with original search failure preserved; no silent post hoc query rescue.

## D72 implemented and six standardized OpenAlex searches completed

User clarified the intended design: simulate prior search returning the focal
retracted/control paper alongside other evidence; evaluate subsequent behavior,
not autonomous search by tested models. Then authorized creating OpenAlex searches.
Added protocol/search-query-v1/PROMPT.txt and PROTOCOL.md, frozen before calls;
code/generate_search_queries.py makes isolated MiMo calls with QUESTION ONLY,
temp0/top_p1/max4000, same provider. Two context/focus concept groups must contain
verbatim question spans; deterministic compiler ANDs groups, ORs alternatives,
ANDs tokens within spans. No outside synonyms or per-item adaptive widening.
All six first outputs compiled. Costs $0.0050614566; cumulative preparation approx
$4.18758214. Logs and frozen plans: data/logs/search-query-v1/pilot/.

other_results.py gained --query-plan bound to source question hashes, and retains
development-only output names/blank unreviewed decisions. Isolated metadata and
raw search/PubMed cache: data/work/pilot-search-query-v1/. Full pools retained,
up to first200 by OpenAlex relevance, eligibility then citation ranking as before.
Counts raw/initial candidates: 1160E2 892/8; DDC269 9/8; F471E5 110/8; C643C6 1/0;
10D131 22/8; 3E1E72 1512/8. C643C6 sole match is its focal control itself.
Many of the 40 initial candidate titles are tangential; metadata eligibility and
citation rank are NOT relevance. None of the 40 candidates approved, no packets
built or tested-model experiments run. Formal question review still unresolved.

Read-only viewer: results/pilot-openalex-search-review.html. Report .md/.json at
results/pilot-openalex-search-report.*. Actual completion note in
protocol/search-query-v1/RESULTS.md (does not modify frozen protocol). All six
query-generation completion timestamps precede first retrieval timestamp.
125 offline tests passed (38.606sec). Paper methods/exact query prompt, D72,
changelog, run order, and freeze record updated; keep main AI disclosure concise.
Next: screen retained candidate pools for direct relevance and decide transparently
how to handle the failed chicken-embryo packet. Do not claim all five other topics
have four verified alternatives, silently reroll queries, or auto-drop/replace
the control. Original v1/v2.1 questions and both prior retrieval stages preserved.

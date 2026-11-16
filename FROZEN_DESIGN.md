# Design record — DRAFT, NOT FROZEN

Prepared 16 November 2026. This document is a checklist and summary of the current
protocol, not evidence of preregistration, a completed pilot, or permission to start
the main experiment. Complete the pending fields after the pilot, then timestamp
the final version publicly before any main-model outputs are examined. Record any
later deviations with dates and reasons; do not silently replace this version.

## Question and scope

How do nine fixed API configurations respond to true and forged publication-status
signals in supplied scientific search results, with a frozen registry available?
The study measures this controlled setup, not the retrieval behavior of consumer
apps or the prevalence of retracted papers in real-world answers.

## Planned sample and conditions

- Main: 25 retracted health papers, each with a matched control; pilot: three separate
  pairs. Each paper has its own checked topic and four checked alternative results.
- Conditions: R1, R2, R3, R4, R5, R6, K3, K4, R4-I, K4-I, as defined in paper Table 2
  and `code/materials.py`. Each condition starts a fresh conversation. The target's
  position is seeded and fixed across conditions.
- Primary R contrast: R5 versus R6. Both show the true retraction label and offer the
  lookup tool; R6 alone adds a forged reinstatement. Outcome: unwarned reliance.
- Primary K contrast: K3 versus K4. Both offer the tool; K4 alone adds a forged
  retraction. Outcome: false retraction, as defined in paper Table 3.
- R3 versus R4 and the two instruction comparisons are secondary. Remaining
  comparisons, including R2 versus R5, are exploratory (paper Table 4).
- Separate status question on each paper. Stability: five seeded pairs, six
  conditions (R3, R4, R5, R6, K3, K4), twice more; select and record these pairs
  before examining main outputs. Only the first run enters primary comparisons.

## Analysis and scoring

Use the exact definitions in paper sections 3.5–3.6 and their implementation in
`code/outcomes.py`, `code/analysis.py` and `code/stats_common.py`.

- Primary estimates average paired changes over the fixed model configurations
  within each topic, then over topics. Resample whole topics for intervals and
  sign-flip topic differences for p-values; Holm-adjust the two primary p-values.
  The sign-flip procedure assumes null symmetry of topic differences. It is not
  justified merely by the number of model answers.
- Per-model comparisons are exploratory, with paired intervals and mid-p McNemar
  tests, Holm-adjusted within each planned nine-model family.
- Operationally missing paired answers are omitted under the stated protocol;
  report omissions and available model counts per topic. This may change the
  composition of the across-model estimate when failures differ by model.
- Two model judges produce meaning fields. The author settles disagreements.
  Human checks cover 180 experimental answers plus 36 status answers, before the
  author sees judge labels for those answers. Report agreement with each judge
  separately and disclose that the author also adjudicates the final labels.
  These checks are not independent human replication.
- Report all prespecified sensitivity analyses (each judge alone, both answers
  citing the target, any retraction mention counted as warning, and a repeated
  forged retraction counted as false retraction). Do not select the reported
  comparison or outcome according to the most favorable observed result.

## Materials and configuration identifiers

These are the locally verified identifiers when this draft was created. Recheck
them at freeze; any change must be recorded before the main run.

| Artifact | Identifier |
|---|---|
| Retraction Watch snapshot date | 13 November 2026 |
| `data/raw/retraction_watch.csv` SHA-256 | `4d0509f648ec6dc7f7de43a2260943ed15c56b239d882d73f468f4f40ef917dd` |
| `code/models.json` SHA-256 | `dd240bdb1c4a3b4d9a23048f8bee7a8e2a295e2509bfb1e177dd2ce1e958cb69` |
| Main `items.json` SHA-256 | PENDING: not built |
| Pilot `items.json` SHA-256 | PENDING: not built |
| Stability selection file and SHA-256 | PENDING |
| Tested code commit | PENDING |
| Final public freeze URL and UTC timestamp | PENDING |

## Evidence required before the main run

- [ ] All topics and alternative-result fit checks completed by the author and logged.
- [ ] Auxiliary model knowledge check completed and replacements resolved.
- [ ] Offline regression suite passes on the code commit being used.
- [ ] Pilot uses separate items, and its request/response logs are preserved.
- [ ] Each API path has a demonstrated valid tool call followed by a usable answer.
      If the pilot model never calls the tool, document a separate plumbing check;
      do not count that check as an experimental response.
- [ ] Pilot scored through the complete pipeline; one complete matched pair checked
      manually. Label/forgery visibility, citation rates, missing responses, actual
      annotation time and cost reported. Any template changes documented.
- [ ] `check_run.py` failures resolved. NOTE entries explicitly reviewed: a zero exit
      code alone does not establish routing, pricing, or tool-path readiness.
- [ ] Updated estimate and phase budgets recorded. The runner's budget is a
      scheduling reserve, not a guaranteed provider billing cap.
- [ ] Main items, model settings, analysis and scoring rules frozen and published.

Topic-method update D71: prompt v2.1 adopted for six pilot development drafts only;
see protocol/topic-drafting-v2.1/ADOPTION.md. Scientific review and the new explicit
alternative/packet approval gates remain pending. The old five-checkbox pipeline
cannot establish v2.1 approval.

Search update D72: standardized question-to-concept extraction and deterministic
Boolean compilation adopted for development; complete query plans are frozen
before OpenAlex retrieval. These candidates still require explicit scientific
relevance and packet review. See protocol/search-query-v1/PROTOCOL.md.

Pilot report / decisions: PENDING. Main run authorization and start time: PENDING.
If only a pilot is completed for the competition, label it as pilot evidence and
leave these main-study fields pending. No power or population claim follows from
three pilot pairs.

D73 development update: materials-development-v3 revises question scope and query coverage uniformly for the six pilot items. Two isolated AI question assessments are development evidence only. First 24 eligible candidates per item are prepared in the existing rank order for feasibility; any additional screening must use the retained pool and documented rule. Scientific suitability and four-alternative packets remain unresolved. Original versions and failures are preserved. No main-material freeze or experiment is authorized by these calls.

D74 update: v4 and a uniform auxiliary-drafter comparison are development work, not a final model selection. Kimi16k retrieval produced 24/8/9/0/0/15 prepared candidates (1160E2/3E1E72/F471E5/10D131/DDC269/C643C6). Counts are not relevance approvals. Candidate AI screening is separate; no six-item packet set is established. See versioned v4 protocols and retained failure logs.

# Development retrieval before final question approval

16 November 2026, before the retrieval calls described here.

The author asked how to proceed after the six-item source screen. The next action is to test whether the frozen v2.1 questions yield plausible alternative papers under the existing retrieval rule, rather than infer literature availability from the specificity of their wording.

This changes the order proposed in PROTOCOL.md: Stage A flags remain unresolved while a development-only retrieval check is performed. It is explicitly not final Stage B approval, an expert review, or permission to run the experiment. No topic wording, focal-paper selection or search rule changes in this check. Its purpose is to identify whether the bottleneck is retrieval or question scope before any further prompt revision. Later revisions informed by these results must be disclosed as additional development.

Use all six first v2.1 drafts, preserving their exact text. Apply the same existing query, date/type/abstract filters, exclusions and ranking rule to both sides. Initially inspect the first eight eligible candidates from the fixed pool (four candidates plus four reserves); no result is approved by default. A shortfall under this rule does not establish that the literature contains no suitable studies.

Implementation: `code/other_results.py --development-drafts data/logs/drafting-v2.1/pilot/drafts.jsonl` in an isolated copy of the pilot metadata. It verifies source/text identities and produces files explicitly named DEVELOPMENT, with no official `other_candidates.json` or approved topic sheet. The legacy experimental builder therefore cannot consume this output accidentally. Exact queries, responses, counts and source hashes are retained. No paid LLM calls are involved; the public literature APIs are queried.

Do not select only supportive papers, redefine the question after seeing retrieved evidence without a new version, or fill the author's scientific-review fields. Findings from this step are contextual AI-assisted screening, with unresolved cases left unresolved.

## Observed result

All six literal full-question searches returned zero records. Twelve diagnostic shorter searches, fixed in results/topic-retrieval-diagnostic-plan.json before their execution, returned nonzero counts for all six topics with the same metadata filters. These context-informed probes are not adopted as the final selection rule. See results/topic-retrieval-feasibility.md. A standardized question-to-query procedure is now required before alternative selection; no question, pair or candidate was approved or dropped.

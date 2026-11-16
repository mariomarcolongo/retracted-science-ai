# Search-query construction v1

Adopted for the six pilot development items on 16 November 2026 following the author's instruction to create the OpenAlex searches. Frozen before generating this batch of search terms. This amends the failed full-sentence retrieval rule; it does not change the scientific questions or the experimental status manipulations.

## Fixed procedure

1. Use each first v2.1 question unchanged. A fresh MiMo-V2.5-Pro call receives the system text in PROMPT.txt and only `{"question": "..."}`. No title, abstract, status, hypothesis, previous query, search yield, citation outcome or conversation is provided. Same pinned provider and temperature 0/top_p 1 for all items; max_tokens 4000. Other provider settings remain omitted. One completion per item; no semantic rerolls. This preparation batch uses a $1 scheduling guard within the existing $20 preparation target.
2. Extract two concept groups, context and focus. Each has 1–3 short spans found verbatim in the question, at most five words each. Alternative terms within a group are ORed; the two groups are ANDed. This is a deliberately limited recall-oriented search representation, not a rewrite of the scientific scope.
3. Compile mechanically. Within a span, alphanumeric tokens are ANDed after removing a fixed list of grammatical words. Do not require an exact phrase. Escape by construction: accept only letters, digits, spaces and hyphens in spans; never execute model-generated search syntax. Missing groups, unsupported spans, a needs_review output, truncated output or invalid JSON leave the item unresolved. Every raw response is retained.
4. Freeze all six compiled queries before retrieval. No item-specific query widening, selective reroll, additional synonyms, or choice among queries according to yield is part of v1. Any later change needs a new version and disclosure of prior retrieval exposure.
5. Search OpenAlex once per question (up to 200 records in its relevance order), retaining the existing article/type, abstract/language, publication-year, registry, target/control and shared-author exclusions. Rank eligible papers by citation count with DOI tie-break. Initially prepare eight candidates per question (four plus four reserves), using PubMed abstracts where available under the existing rule. Retain the full returned pool so later candidates from that pool can be reviewed in the fixed order without new queries.
6. All candidates remain unapproved. Concept matching, search rank or citation count is not a relevance judgment. Review against the complete unchanged question, including scope and study setting. The final four-paper packet must contribute to the central question without the focal paper. No selection based on agreement with the focal result or tested-model behavior.

## Rationale and limits

The original six full-sentence searches returned zero records. OpenAlex documents that ordinary search terms are ANDed, with stemming and stop-word removal. Separating a natural-language information need from its database query addresses that interface problem. Documentation: https://help.openalex.org/api/searching/ (checked 16 November 2026).

Context and focus can omit details needed for relevance, intentionally increasing the candidate pool. Those details are not waived at screening. This extraction scheme is a pragmatic study-specific development procedure, not a validated optimal systematic-review search strategy or a claim of exhaustive retrieval. Choosing two groups, limiting spans and excluding outcomes are disclosed methodological choices, not requirements established by OpenAlex.

Codex assisted in designing this procedure after seeing the failed searches and twelve diagnostic probes; that history is retained. The new per-item calls do not see those probes. Extracted spans may still reflect model-dependent choices. This is AI-assisted material preparation; the tested models do not perform these searches. The controlled experiment concerns responses after a focal paper has been supplied with alternative evidence.

Record prompt/source/configuration/code hashes, exact messages, model/provider returned, raw outputs, compilation, UTC timing, usage and failed attempts. Preserve all prior full-sentence and diagnostic searches. No final Stage A or Stage B approval is implied by successful query generation.

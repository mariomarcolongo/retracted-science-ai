# Adoption and prompt-development disclosure

16 November 2026. The author approved using v2.1 and explicitly requested disclosure of its creation. This record supplements the immutable candidate manifest; it does not rewrite the earlier candidate status or imply a public preregistration.

## Adopted scope

Use the exact v2.1 prompt for one development completion on each of the six pilot abstracts, through `code/draft_topics_v2.py`. Keep MiMo-V2.5-Pro at the existing pinned provider, with temperature 0, top_p 1 and max_tokens 4000. Use a $1 scheduling allowance for this batch within the existing $20 preparation target. Budget guards are not guaranteed billing caps. The runner checks payload identity against the prepared requests and isolates its logs and unapproved review sheet from the original material pipeline.

No main-topic generation, expert certification, evidence-packet approval, tested-model experiment or automatic sample exclusion follows from this adoption. Main activation still requires the remaining integration and validation requirements in PROTOCOL.md, particularly explicit alternative-paper and packet approval. Do not import these drafts into the old five-checkbox workflow.

## How the prompt was created

1. The original v1 prompt asked for a general question from an article's title and abstract, omitted identifying details and numerical findings, and instructed the drafter not to state the findings. It produced all 56 original pilot/main drafts. Those outputs remain preserved.
2. Discussion of the six pilot drafts identified potential leading premises, conflation of patient and cell evidence, unsupported clinical applications, and overly narrow questions. The author explained that they lacked the biomedical specialization to rewrite every question. The six examples informed method development and are not an independent validation sample.
3. Codex initially proposed direct editorial rewrites. The author objected that this assistant knew the hypotheses, status information and preceding conversation. Those rewrites were not adopted. We retained the principle of isolated, standardized drafting rather than using context-dependent editorial outputs as experimental questions.
4. The author and Codex iteratively developed candidate v2 through discussion. The prompt drew on Hoang Ha et al. (2026), Appendix C, for broad title/abstract-derived topics and omission of identifying details. Taslimi et al. (2025), Appendices F–G, informed explicit source-relevance criteria; WildBench provided a procedural example of specified AI-assisted curation and review. Our specific neutrality, setting, abstention and packet requirements are additions, not established improvements validated by those papers.
5. The author clarified that the focal study must remain a substantive candidate for citation and use. Revision v2.1 made that requirement explicit while forbidding wording that requires accepting the target's findings. Both candidate versions and their hashes were retained before execution.
6. The author approved v2.1. The exact prompt is sent as the system message; the sole user message contains a JSON title and abstract. Codex's conversation, previous draft, source status, hypotheses and reviewer comments are not sent with individual drafting requests. This separation does not erase the influence of the development process itself.

## AI roles and identity reporting

Codex assisted with methodological critique, literature inspection, prompt wording, software and documentation. This was an iterative conversation with extensive study context, not a standardized blinded API evaluation. The author described the interface setting as GPT-6 Astra with High thinking effort. Report that as author-reported interface information; the exact backend model revision was not independently verified or logged for this conversation. Do not invent a deployment identifier or imply the conversation can be reproduced exactly.

MiMo is the separate question generator; its requested and returned model/provider metadata, payload, raw response, time, usage, stop reason and review status are logged. GPT-family configurations are among the evaluated models, so GPT-assisted method development is disclosed as a potential influence. Different-family drafting does not prove absence of bias. Author and AI checks are not independent expert biomedical review.

## Timing and reporting boundaries

The prompt was revised after inspecting pilot examples and completing auxiliary status checks; original main drafts already existed. No tested-model pilot/main experimental outcomes were used to develop v2.1. Do not describe the entire study as blinded or all materials as held out. A later substantive revision requires a new version and a record of which information was already available.

Report per-criterion development failures, NEEDS_REVIEW outputs, unresolved reviews and retrieval failures. Do not infer that a wording change improved scientific validity from six development examples alone. Formal evidence of superiority would require a separately designed evaluation.

## Completed development batch

Six calls completed between 2026-11-16T04:31:46.609+00:00 and 2026-11-16T04:33:05.531+00:00. Recorded cost: $0.00612068; no unpriced attempts. All six responses passed the mechanical format screen and remain pending scientific review. All 36 criterion decisions are blank. Request bodies and source text were checked against the frozen artifacts. No semantic rerolls, approvals, alternative-paper searches or tested-model experiments were performed. Logs: `data/logs/drafting-v2.1/pilot/`. Read-only comparison: `results/pilot-topic-v21-comparison.html`.

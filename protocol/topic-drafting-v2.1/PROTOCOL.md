# Topic drafting v2.1: candidate method and validation plan

Status: CANDIDATE, NOT ACTIVE OR VALIDATED. Prepared 16 November 2026 following author discussion. No model calls, source-topic edits, reviewer approvals, or evidence-packet construction are authorized by the existence of these files. The current runner still uses its original prompt. Adoption requires synchronizing the code, review interface, methods, and decision record; the concrete changes are listed below.

## Objective and limits

Construct neutral, source-grounded questions for a controlled evidence-synthesis experiment. Each question must keep its focal article directly relevant without making it the only plausible source of evidence. Question quality and alternative-paper relevance are separate requirements. A good prompt cannot establish that suitable alternatives exist, that an abstract is correct, or that reviewers have domain expertise.

The experimental contribution concerns responses to publication-status signals. Prompt development supports the validity of those measurements; it is not itself evidence of a new superior question-generation method. Describe additions as safeguards intended to reduce identifiable errors until results support a stronger claim.

## Revision 2.1: preserve a genuine opportunity to use the target

The author clarified that the focal article must remain a substantive candidate for citation and use, not merely belong to the same broad topic. This study tests responses to true and forged publication-status signals when evidence is supplied. If the question makes the target peripheral, non-use is less informative about status handling. Conversely, making the target indispensable removes a meaningful opportunity to use alternative evidence.

Therefore require both (a) a source passage identifying a principal target analysis or finding that directly helps answer the question, and (b) independently relevant alternative evidence addressing that same central question. Do not require that every alternative has identical methods or equal evidential quality. Do not strengthen the target's claims or optimize wording to increase target citation or unwarned reliance. Apply the target-relevance criterion to both retracted and matched-control articles using the same wording and without explicit status labels.

Target relevance is an eligibility judgment about the materials, not an inclusion rule based on observed model behavior. Never discard a topic because tested models do not cite or use the target. Retain and report such responses under the planned outcomes. A relevant target may legitimately be rejected or omitted; noncitation alone is not proof that the model recognized its status. Actual attention or internal consideration is not established by supplying a relevant article.

This revision was prompted by author feedback before any v2 candidate requests were sent. The v2 package remains intact. Revision 2.1 has not generated new questions or run any model experiments.

## Literature and our departures

| Source | Supported design choice | Boundary / proposed addition |
|---|---|---|
| Hoang Ha et al. (2026), Appendix C | Generates a broad literature-review topic from title and abstract; removes identifying names, specific quantities, and proprietary compound names; prepares search queries before model runs. | Our explicit rules against presupposed results, population/system conflation, and unsupported applications are additions. We clarify that numeric characters inside scientific names are not numerical findings. We do not claim to copy their exact extraction prompt or their retrieval procedure. |
| Taslimi et al. (2025), sections 3.1 and Appendices F–G | Defines the generation task and assesses question relevance to its source with an explicit rubric. | Their goal is understanding an individual article, not verifying that multiple papers answer a synthesis question. We do not adopt their interestingness/novelty score: optimizing for surprising findings would be inappropriate here. |
| WildBench (2024), sections 2.1 and 3.1 | Uses specified AI-assisted curation, manual checks, and task-specific evaluation criteria. | This is a procedural precedent, not validation of biomedical topic accuracy or proof that model-family overlap is harmless. |

Sources, accessed 16 November 2026:

- https://aclanthology.org/2026.findings-emnlp.2070.pdf
- https://aclanthology.org/2025.coling-main.573.pdf
- https://arxiv.org/html/2406.04770v2

## Exact input, output, and configuration

The full system message is the UTF-8 contents of `PROMPT.txt`. The user message is a JSON object with exactly `title` and `abstract`, serialized with `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`. No prior messages, tools, target/control label, DOI metadata, study hypothesis, judge output, alternative papers, author corrections, or this chat enter the model request. The title and abstract use the existing logged status-marker and publisher-boilerplate cleaning; do not introduce content-changing cleaning under this amendment.

Proposed development configuration: the existing MiMo drafter and pinned provider, explicit temperature 0 and top_p 1, max_tokens 4000. No seed is assumed supported. The saved endpoint snapshot lists these sampling parameters as supported, but availability and actual request acceptance must be checked before execution. Other parameters, including reasoning settings, are omitted and logged as omitted/provider default, not described as fixed internal behavior. Do not silently change settings to overcome a rejection.

The output is one question or `NEEDS_REVIEW`. The sentinel is a material-development failure requiring review; it is not an experimental response or a reason to drop a paper automatically. Empty, truncated, or malformed responses are also failures. Preserve exact raw text before any explicitly logged whitespace normalization. Do not silently parse a question out of an explanation.

Temperature 0 does not guarantee identical regeneration. Exact released question bytes are the reproducible experimental materials; model re-execution is a separate reproducibility question. Archive model/provider requested and returned, UTC times, complete requests and responses without credentials, usage, stop reasons, prompt and input hashes, configuration, code version, and all attempts. A named API model is not a verified immutable weight snapshot.

## Development and stopping rules

1. Use the existing six pilot abstracts for development only. Generate one completion per item with the identical configuration and prompt. Do not choose the best of several completions or mix models item by item. Preserve original v1 outputs alongside the v2.1 outputs.
2. Score every draft using the rubric below before looking for alternatives. The six pilot items have already informed prompt development; they cannot provide an unbiased validation estimate. Original main-sample drafts also already exist, and auxiliary status answers have been seen. Disclose this history; do not claim untouched holdout materials or full researcher blinding.
3. A blank, fail, or uncertain rating prevents approval. One failed critical criterion cannot be offset by good scores on other criteria. If any pilot item is unresolved, do not extend the candidate procedure to main materials as though it passed. Review the common failure pattern and record a new version before any further development batch. No per-item conversational rescue or selective semantic reroll is part of v2.1.
4. Retain the current transport retry policy and log every attempt, distinguishing operational failure from a valid but inadequate question. Never retry a successful answer merely because its content is inconvenient.
5. Freeze the selected prompt, model, review roles, and retrieval rules before generating final main questions. Switching models requires a separately dated selection rationale, the applicable auxiliary eligibility check, and regeneration under one common method. Model switching is not preauthorized by v2 and is not evidence of better quality by itself.
6. A later change after inspecting main materials must be recorded as further development, not hidden as proofreading. Do not tune questions using tested-model experimental responses, citation rates, reliance scores, or the direction of a treatment contrast.

## Stage A: question review

For each item, record a reviewer identifier and role, the exact question and source hashes, date, criterion decision (`pass`, `fail`, or `uncertain`), and a concise reason. For grounding decisions, quote the supporting abstract passage and identify any unsupported phrase in the question. These are checkable evidence notes, not a request for private reasoning traces. No field is pre-approved by the drafting model or by a script.

| Criterion | Pass condition |
|---|---|
| A1: source fidelity and substantive target relevance | Identify the principal reported analysis or finding that contributes to answering the central question, with its abstract passage. Shared background terms are insufficient. The question does not add an outcome, intervention, clinical application, or comparator absent from the described work. Relevance does not certify the finding as reliable or require the model to accept or cite it. |
| A2: neutral premise | The wording does not assume an effect, association, benefit, harm, mechanism, superiority, or result direction; observational findings are not framed as established causal effects. |
| A3: setting and components | Population/system and outcome assignments match the methods; human, animal, cell, and computational components are not conflated. |
| A4: incidental identifiers | The question omits study identifiers, incidental quantities, and numerical findings while retaining scientifically essential distinctions and entity names. |
| A5: appropriate scope | It expresses a coherent research relationship without requiring the target's complete experimental fingerprint or changing to a different broad topic. This is a wording judgment, not proof that alternatives exist. |
| A6: usable format | One standalone English question, with no answer, explanation, status claim, or unresolved sentinel. |

Give reviewers neutral item codes and no explicit target/control labels. The author and this assistant have already seen study details; hiding labels does not make them fully blinded or independent. Record that limitation. A model-assisted evidence map may help locate passages, but it must be identified as AI assistance. Do not require the author to certify specialist content they cannot assess. An uncertain scientific judgment stays unresolved pending suitably qualified review or a separately specified, transparently limited AI-assisted review method. This document does not silently substitute such a method for the author checks in the current paper.

Freeze a question provisionally after Stage A, before searching for alternatives. Stage B can reject a packet; it cannot silently rewrite its question.

## Stage B: alternative-paper and packet review

Retain the current search and ranking rule unless amended explicitly: one exact topic query, first 200 OpenAlex results, current date/type/abstract and exclusion rules, then citation-count ranking with the existing DOI tie-break. Archive query, retrieval date, source responses, and ranked candidates. Screen candidates in that order, including reserves as necessary, up to that fixed candidate pool; record every inspected candidate and exclusion. Do not widen dates, add ad hoc searches, or choose papers according to whether their findings support or contradict the focal article.

For each candidate record an explicit `pass`, `fail`, or `uncertain`, with source passages and a reason:

- Does it directly inform the question's central relationship or a necessary component, rather than merely mention the same disease or molecule in background text?
- Is its population or system within the question's scope? If it informs only one component, record that component; do not treat a cell experiment as patient efficacy evidence.
- Is the exposure/intervention and outcome sufficiently relevant to contribute evidence, without substituting a different relationship through a superficial keyword match?
- Does it meet the protocol's eligibility and status-screening rules? Report the actual registry check; absence from a registry is not proof of non-retraction or overall scientific reliability.

Different designs and null or opposing findings are acceptable. Citation count ranks eligible candidates; it does not validate relevance or reliability. Choose the first four candidates in the frozen order that explicitly pass all requirements. A fifth supporting paper must not displace an earlier eligible contradictory paper.

Then assess the packet as a whole: with the focal article removed, do the four alternatives still provide evidence addressing the central question, rather than only background or secondary components? Record their contributions. This operational check does not require them to settle the question, agree, have equal evidential strength, or validate one another. Do not test it by querying the experimental models and choosing packets from their answers.

If fewer than four pass, or the remaining packet does not address the central question, label it `insufficient_verified_alternatives`. This is failure under this retrieval rule, not proof that the literature contains no alternatives. Leave the item unresolved. No filler papers, question broadening after retrieval, or automatic target replacement is allowed. Any exclusion or replacement would alter the sampled population and requires a documented rule and updated counts/precision claims before main execution. Report attrition and reasons on each side, not just the surviving topics.

## Evidence needed to claim improvement

Report v1 and v2.1 error counts by criterion on all six development items, with reviewer role and assistance disclosed. These are descriptive development results, not proof of superiority, independent validation, or a reliable ranking of models. Report first-pass acceptance, abstentions, revisions, retrieval failures, and reviewer time. For stronger validation, use a predefined additional sample not used for prompt tuning, with appropriately qualified review; define its size and selection before generation. Do not promise that adding a second AI judge supplies that validation.

The defensible contribution is transparent construction with explicit failure handling and inspectable evidence. It is not a claim that a long prompt removes bias.

## Integration requirements before activation

- Load the versioned system prompt and structured source message in `code/draft_topics.py`; include prompt, role structure, sampling settings, normalization, and input in cache identity. Preserve all v1 files in a separate run directory.
- Extend the client to transmit the explicit sampling configuration without changing other phases. Validate actual endpoint support and save the payload.
- Replace the five-field topic interface with Stage A criteria and an unresolved option. Remove any implication that A5 establishes the existence of alternatives.
- Change `code/other_results.py` and `code/build_items.py`: the current fit sheet treats blank as acceptance. Under v2.1, blank or uncertain is unreviewed and cannot enter a frozen packet. Bind decisions to question/candidate content hashes, not only a DOI or topic text, so changed abstracts invalidate prior review.
- Add Stage B packet approval; retain candidate ranking and all rejection reasons. Check both retracted-target and matched-control packets under the same rule.
- Update section 3.4, Appendix B, Table F1, the decision log, run order, and freeze checklist to match actual behavior. Preserve the old method and explain when and why it changed.
- Run targeted offline checks for cache invalidation, unresolved output handling, explicit fit approval, and content-bound reviews. Do not claim these checks validate scientific relevance.
- Freeze actual materials and method before the main experimental runs. This candidate package alone is neither a public preregistration nor a complete implementation.

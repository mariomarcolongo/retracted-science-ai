# AI-assisted candidate relevance feasibility screen

Development procedure, frozen before candidate judging. Existing metadata,
Retraction Watch, author-overlap and notice exclusions are unchanged. Absence
from the registry is not proof of non-retraction. The screening assesses whether
the question can support a relevant packet; it does not confer expert approval.

Input is the already retrieved, immutable DEVELOPMENT candidate file, with up to
24 papers per question in the retained citation-count/DOI order. Grok 4.7 and
GLM-5.2 each assess every prepared candidate, in batches of at most six belonging
to one question. No candidates are skipped because of their findings. Reviewers
see only the question and neutral-ID titles/abstracts, not the focal paper,
author names, citations, publication-status labels, retrieval counts, other
reviews, hypotheses, or conversation. Candidate order within each batch is sorted
by a stable content-derived ID; the request preserves that exact order.

Use pinned endpoints, temperature 0, top_p 1, max_tokens 12000 and a strict JSON
schema. Up to three independent calls concurrently, shared attempt logging and
budget guard. One completion per batch/reviewer; no semantic rerolls. Freeze
requests and schema before calls; retain raw completions and all errors. Require
every candidate ID exactly once and evidence that matches its own title/abstract.
Invalid/missing entries remain unresolved; they do not become passes.

Three criteria assess direct evidence, scope, and the central relationship. Both
reviewers must pass all three for provisional AI agreement on a candidate. Report
every disagreement, fail and uncertainty; do not silently adjudicate them. The
first four jointly passing candidates in the original rank order are proposed,
not finally approved. A packet-level check is still required: removing the focal
paper must leave evidence for the central question, without requiring agreement
or exhaustive coverage. Fewer than four jointly passing candidates leaves the
packet unresolved under this bounded procedure, not proof of absent literature.

The author cannot provide specialist review; this is explicitly AI-assisted
development screening. Do not label it human, blind expert, or independent
verification. Its limitations must remain visible in any adopted main method.
No changes to legacy fit sheets or approval fields, sample membership, final
items or experimental prompts. Use a $4 scheduling guard within the existing
$20 preparation target after reconciling preceding actual costs.

# Materials development v4: problem-level synthesis scope

Development amendment, 16 November 2026. Authorized scope remains the author's
instruction to resolve question breadth and search coverage across all six pilot
items. No sampled article is changed. No experimental responses have been used.

## Trigger and version history

V3 first completions still retained exact candidate molecules and raised a scope concern about
an educational aim not established as measured in the source. Its search yielded only one eligible alternative
for the pediatric microRNA item and three for the cholangiocarcinoma item, before
scientific relevance review. Several generated synonym groups instead combined
different facets of a question with OR. These are documented development failures.
V3's two-model question reviews are preserved, including malformed outputs; they
are not grounds for selecting a favorable question completion. This amendment
was drafted after seeing v3 questions/searches and partial reviews, before v4 calls.

V4 changes the abstraction rule from the particular object/immediate class to the
scientific problem and purpose supported by the principal analyses. A biomarker
can contribute to a question about biomarkers serving the same purpose; a model
can contribute to a question about models serving the same experimental task.
This is an explicit change in question scope. Disease and clinical population
restrictions remain; model implementations may vary without implying equivalence
or patient benefit. A uniform neutral sentence stem and 30-word limit reduce
presupposition and multi-component questions. This rule is our development choice,
not a literature-validated optimal question-generation method.

## Fixed procedure

Apply the new prompt once to ALL six original cleaned title/abstract inputs using
the same MiMo endpoint/settings as v3. Do not feed it v3 drafts, search results,
reviewer comments, status labels or chat. Preserve every output; no selective
rerolls, conversational rewrites or replacement with a preferred earlier version.
Run two isolated question reviewers using the same six scientific criteria, with
JSON-schema response formatting and explicit continuous evidence excerpts. A
quoted passage must be an exact source substring. Retain raw malformed responses;
mechanical format corrections must not be misrepresented as scientific approval.
Questions remain provisional AI assessments, not specialist validation.

Generate all six queries once before retrieval. Search-query-v3 requires a
verbatim question anchor for each group, with at most two alternative wordings of
the same concept. Do not treat parallel components as synonyms. The compiler
validates shapes, anchors and safe syntax; semantic equivalence still requires
review. Use the same title-and-abstract field, first 200 OpenAlex records, metadata
and registry exclusions, citation/DOI order, and PubMed preference as v3. Prepare
up to 24 candidates per item in that order. Keep every earlier query and failure.
Search results are development feasibility evidence; fewer than four suitable
alternatives cannot be repaired by filler papers or silent scope changes.

Use up to three concurrent independent calls per phase, with shared thread-safe
request logging and budget accounting. Stop scheduling on an error; preserve
in-flight completions. Concurrency does not change item inputs or selection.

Use $1 scheduling guards for drafting and query generation, $3 for the twelve
question assessments, within the existing $20 preparation target. Reconcile costs
before candidate screening. No experiment spend or main-sample exclusion follows.
V3's rationale sources remain applicable only within their stated boundaries.
This is a further iteration on known development items, not independent validation
or evidence that v4 is superior. Freeze exact prompts, payloads and implementation
before calls; record model/provider metadata, UTC times, costs and all attempts.

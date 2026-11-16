# Materials development v3: question scope, retrieval and AI-assisted checks

Adopted for development on 16 November 2026 after author authorization to resolve
question breadth and search coverage. All six pilot items receive the same new
procedure. Existing v1/v2.1 drafts and search-query-v1 results remain unchanged.
No tested-model experiments, control replacement or main-sample exclusion follows
automatically from this amendment.

## Why this revision

The six v2.1 questions often retained a study-specific combination of entities,
apparatus and endpoints. C643C6's standardized search found only its focal paper;
other searches retrieved tangential full-text matches. Diagnostic searches and
their inspection informed this revision. These items are development examples,
not held-out validation. Our prompt author has study context; item-level API
calls do not. No question is selected using experimental citation/reliance scores.

The new question instruction permits the immediate scientifically supported
class of a focal biomarker, material, device or model, while retaining the central
problem and direct focal relevance. This is a deliberate change in question
scope, not proofreading. It cannot guarantee literature availability. A 45-word
limit and one or two outcome domains discourage concatenated subquestions.

## Frozen sequence and roles

1. One MiMo-V2.5-Pro completion for each of the same six cleaned title/abstract
inputs, under TOPIC-PROMPT.txt. No prior draft, search results, explicit status,
study hypothesis or chat history. Same pinned provider as previous batches,
temperature 0, top_p 1, max_tokens 4000. Preserve every first completion, including
failure/sentinel. No semantic rerolls or item-specific conversational edits.
2. Two separate fresh question-review calls per item, using the existing eligible
auxiliary judges Grok 4.7 and GLM-5.2 and QUESTION-REVIEW-PROMPT.txt. Inputs contain
only title, abstract and question. Each judge sees neither the other judgment nor
the drafting history. Temperature 0, top_p 1, max_tokens 6000, pinned providers.
These are AI-assisted development assessments, not human specialist review or
independent validation. Check evidence substrings mechanically. Any fail,
uncertain, malformed response, invalid quote, or disagreement remains unresolved.
Do not enter model assessments as author approvals. Passing both is provisional
AI agreement only; limitations remain explicit.
3. Generate one query per question in fresh MiMo calls, question only, under
QUERY-PROMPT.txt, same sampling/provider and max_tokens 4000. Allow conventional
synonyms/abbreviations instead of requiring every term to be verbatim. Compile
safe term tokens with OR within context/focus groups and AND between groups.
No free-form executable search syntax. Freeze all six queries before retrieval;
retrieval may diagnose unresolved questions but never makes them approved.
4. Search OpenAlex title-and-abstract text (`search.title_and_abstract`) rather
than broad full-text/keyword search. Retain first 200 by OpenAlex relevance,
then the existing eligibility filters and citation-count/DOI ordering. Preserve
date window, article/English/abstract rules, exclusions, registry snapshot and
PubMed abstract preference. Review the full question; search synonyms do not
expand eligibility. No adaptive per-item widening or hand-inserted search hits.
5. Candidate relevance screening is a separate stage. Existing fit sheets remain
unapproved. Its exact AI screening rubric and candidate batch must be frozen
before any screening calls; this protocol alone does not approve papers. Require
four relevant alternatives and a packet-level check, with explicit provenance.
If not established, report failure under the procedure, not absence of literature.

Freeze request bodies, prompts, source identities, script/client hashes and UTC
timestamps. Log all HTTP attempts, returned model/provider, usage and stop reason.
Recover saved completions on resume; never repay to reroll inconvenient content.
Use a $1 scheduling guard for each drafting/query batch and $3 for the 12 question
reviews, inside the existing $20 preparation target. Guards are not billing caps;
reconcile actual costs before further work. Author clarified cost of the cheap
drafter is not a reason to sacrifice quality. No new experiment spend authorized.

## Literature-informed rationale and limitations

Cochrane's search guidance supports using few core concepts and OR-combined
synonyms rather than requiring every PICO component. We apply that principle to
candidate retrieval, not a claim of Cochrane-compliant systematic review:
https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04
(accessed 16 November 2026, sections 4.4.2–4.4.4).

OpenAlex documents title-and-abstract search, Boolean operators and broad search
matching full text/keywords: https://help.openalex.org/api/searching/ (same date).
Restricting fields may miss relevant records; the bounded 200-record pool and
citation ranking are pragmatic experimental-material choices, not exhaustive
search. AI-generated synonyms may be imperfect. Model agreement is not proof of
scientific accuracy. A formal main-study adoption still requires material gates,
disclosure and reconciliation of the paper's review description with actual roles.

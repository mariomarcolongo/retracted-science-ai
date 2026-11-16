# Development batch result

All six first completions produced mechanically valid extractive concept groups. All six compiled queries were frozen before the first retrieval call. The question texts were unchanged. Query generation cost $0.0050614566; no unknown-cost attempts.

The six searches yielded 40 initial metadata-eligible candidates across five questions, with zero for C643C6 (chicken-embryo training): its single search match was the focal control itself. Initial inspection also found many tangential titles among the citation-ranked candidates. None is scientifically approved, and no experimental packet is complete.

Exact counts, queries and source records are in results/pilot-openalex-search-report.json and data/work/pilot-search-query-v1/. A read-only view with all candidate abstracts is results/pilot-openalex-search-review.html. The query-generation requests and raw outputs are in data/logs/search-query-v1/pilot/.

125 offline tests passed, including frozen question identity, query compilation, no semantic rerolls, HTTP response recovery, query-plan/subject binding, and unchanged legacy output protection. These are software checks, not scientific validation.

The next task is relevance screening of the retained pools and a documented decision about unresolved packets. Do not silently widen individual queries or replace a control, or present raw candidate counts as proof of adequate alternatives.

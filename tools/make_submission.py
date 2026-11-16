"""Build the sprint submission (paper/submission.md) from paper/paper-draft.md.

Usage: python3 -I tools/make_submission.py [--main-only]
Sprint rule: at most 8 pages, not counting references and appendices; abstract 150-250 words.
The main text keeps the introduction, a short methods summary, the results, discussion and conclusion.
The full related work, the full methods and the limitations table move to appendices, unchanged.
"""
import re, sys
src = open("paper/paper-draft.md", encoding="utf-8").read()
heads = [(m.start(), m.group(1)) for m in re.finditer(r"(?m)^## (.+)$", src)]


def sec(name):
    for k, (pos, title) in enumerate(heads):
        if title.startswith(name):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(src)
            return src[pos:end].rstrip() + "\n"
    raise SystemExit("section not found: " + name)


def body(name):
    return sec(name).split("\n", 1)[1].strip() + "\n"


title = src.split("\n", 1)[0]
author = next(l for l in src.split("\n") if l.startswith("Mario Marcolongo"))
abstract = body("Abstract")
words = len(abstract.split("**Keywords:**")[0].split())
assert 150 <= words <= 250, f"abstract has {words} words"
related = body("2. Related work")
results = sec("4. Results").split("| Item | Content |")[0].rstrip() + "\n"
disc = body("5. Discussion and Limitations")
discussion = disc.split("### Limitations")[0].strip()
limits_table = "### Limitations" + disc.split("### Limitations", 1)[1]

METHODS = """## 3. Methods (summary; full methods in Appendix K)

**Papers.** From the Retraction Watch data (snapshot of 13 Nov 2026) we took full retractions of health research articles, retracted from 1 July 2026 for data-invalidating reasons, published at least a year earlier, with an English abstract and at least 5 citations, at most one per journal and author group: 148 eligible, 33 after the journal and author rule, 25 after hand screening, drawn in a seeded random order. Each is paired with a matched non-retracted article (same journal, year within one, similar citations, no Retraction Watch record). A pilot set of 3 further pairs follows the same rules with 1 to 4 citations.

**Models.** Nine API configurations, each through one pinned provider at its default settings: Gemini 4 Hydrogen, GPT-6 Luna, Gemini 3.5 Flash-Lite, GPT-6.1 Sol, Claude Sonnet 5.5, Seed 2.0 Lite, Qwen3.8 Flash, DeepSeek V4.1 Flash 1017 and ERNIE 5.5 Flash Preview. Product adoption informed the choice; the API does not reproduce the apps (Appendix F, G).

**Status-question test (run).** Each model is asked once per paper, in a fresh conversation with no search results and no tool: "Is '{title}' by {authors} retracted?" (wording of Hoang Ha et al. 2026). An answer is correct if it says retracted for a retracted paper and not retracted for a control; another definite status is incorrect; uncertain answers and answers that state no status are reported as uncertain.

**Forged-status tests (designed, not yet run).** The model receives five search results, one of them the target paper, and a question on the paper's topic. Ten tests change only the target's status line and whether a registry lookup tool is offered (Appendix K, Table 2). The two primary comparisons each add one forged line that the registry contradicts: a fake reinstatement added to a correctly labelled retracted paper (R5 versus R6; outcome: relying on the paper without a status warning), and a fake retraction added to a valid paper (K3 versus K4; outcome: calling the paper retracted or excluding it for that reason). Each is estimated across the nine models with topics resampled, a sign-flip test and Holm adjustment for the two; per-model results are exploratory.

**Scoring.** Code records mechanical fields; two judge models from untested families (Grok 4.7, GLM-5.2) fill a fixed form for every answer without seeing the test, the model or the paper's true status; the author settles their disagreements; code combines the fields into outcomes; a blind human check of a seeded sample measures agreement (target: Cohen's kappa of 0.7 or more).

**Record.** Every design decision, with date and reason, is in DECISIONS.md, including changes made after pre-run reviews and before any tested model was run. All requests, responses, judge forms and labels are logged.
"""

main = [title, "", author, "", "## Abstract", "", abstract, "---", "", sec("1. Introduction"),
        "## 2. Related work\n\nSix studies tested language models on retracted papers; Appendix J lists what each found and what it "
        "could not show. None gave models a registry to check or showed them a forged status claim, and none tested models "
        "from the developers of Doubao, Baidu Search or the Qwen app.\n\n" + related.split("Models tested in each study: Table G1.")[1].strip() + "\n",
        METHODS, results, "## 5. Discussion and Limitations\n\n" + discussion +
        "\n\n**Limitations.** The main ones for this result are listed with it in §4.1: one question wording asked once, 25 papers "
        "per group, one human annotator who also settled the judges' disagreements, training exposure not established, and three "
        "model-to-product links not established. The forged-status tests have not been run, so nothing here shows how models "
        "handle search results, labels, forged notes or a registry. The full list is in Appendix A.\n",
        sec("6. Conclusion"), "## Code and data\n\nThe code, prompts, decision log and the logs of this run (every request, response, judge form and label) "
        "are kept in a versioned repository, not yet public; they will be released with the completed study.\n", sec("Author contributions").split("**AI assistance.**")[0].rstrip() + "\n", sec("LLM usage statement")]
back = [sec("References"), sec("Appendix A").rstrip() + "\n\n" + limits_table.replace("### Limitations", "**Full list of limitations**", 1),
        sec("Appendix B"), sec("Appendix C"), sec("Appendix D"), sec("Appendix E"), sec("Appendix F"), sec("Appendix G"),
        "## Appendix J. Related work in detail\n\n" + related,
        "## Appendix K. Full methods\n\n" + body("3. Methods")]
back = [b.replace("| [check] |", "| not yet checked |").replace(" [check: model used in app]", " (model used in the app not established)")
        .replace(" [check: model used in search]", " (model used in search not established)").replace("| [N] health papers", "| 25 health papers")
        for b in back]
# Submission-specific wording: cross-references to parts that moved, and contributions stated as what exists today.
FIX = [("(Table 1). We chose", "(Appendix J, Table 1). We chose"), ("figures in Table 1)", "figures in Appendix J, Table 1)"),
       ("1. The first test we found of **forged publication status in both directions**",
        "1. A design, not yet run, for the first test we found of **forged publication status in both directions**"),
       ("2. A controlled test of recent retractions, with a separate status-question test to measure recognition without retrieved evidence.",
        "2. A completed status-question test on recent retractions, measuring recognition without retrieved evidence, on nine models."),
       ("3. A comparison of nine API configurations", "3. A panel of nine API configurations"),
       ("Only the status-question test (§3.1) has been run. The forged-status tests (Table 2)",
        "Only the status-question test (§3) has been run. The forged-status tests (Appendix K, Table 2)"),
       ("the outcome rule of §3.5", "the outcome rule of Appendix K, §3.5"), ("\n---\n\n---\n", "\n---\n")]
main = "\n".join(main)
for a, b in FIX:
    assert main.count(a) == 1, a
    main = main.replace(a, b)
main = [main]
out = "\n".join(main if "--main-only" in sys.argv else main + back)
open("paper/submission-main.md" if "--main-only" in sys.argv else "paper/submission.md", "w", encoding="utf-8").write(out)
print("abstract words:", words, "| written", "main only" if "--main-only" in sys.argv else "full")
